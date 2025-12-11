import json
import re
from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Q
from django.forms import model_to_dict
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.timezone import now

from bet.models import PossibleBet
from bet.utils import MatchAnalyzer
from get_events import SofaScore
from jogos.models import League, LiveSnapshot, Match, MatchStats
from jogos.utils import analyze_match


@dataclass
class MatchStatFilters:
    """Encapsula filtros numéricos aplicados a estatísticas de partidas."""

    xg_min: float | None = None
    xg_max: float | None = None
    possession_min: float | None = None
    possession_max: float | None = None
    shots_min: int | None = None
    shots_max: int | None = None

    @classmethod
    def from_request(cls, request):
        def parse_float(value):
            try:
                return float(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        def parse_int(value):
            try:
                return int(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return cls(
            xg_min=parse_float(request.GET.get("xg_min")),
            xg_max=parse_float(request.GET.get("xg_max")),
            possession_min=parse_float(request.GET.get("possession_min")),
            possession_max=parse_float(request.GET.get("possession_max")),
            shots_min=parse_int(request.GET.get("shots_min")),
            shots_max=parse_int(request.GET.get("shots_max")),
        )

    def is_empty(self):
        return not any(
            [
                self.xg_min,
                self.xg_max,
                self.possession_min,
                self.possession_max,
                self.shots_min,
                self.shots_max,
            ]
        )

    def match_stats(self, stats):
        """Retorna True se o objeto de estatísticas cumpre os filtros definidos."""

        def total(field_home, field_away):
            return (getattr(stats, field_home, 0) or 0) + (
                getattr(stats, field_away, 0) or 0
            )

        def average(field_home, field_away):
            return (
                (getattr(stats, field_home, 0) or 0)
                + (getattr(stats, field_away, 0) or 0)
            ) / 2

        total_xg = total("xg_home", "xg_away")
        if self.xg_min is not None and total_xg < self.xg_min:
            return False
        if self.xg_max is not None and total_xg > self.xg_max:
            return False

        avg_possession = average("possession_home", "possession_away")
        if self.possession_min is not None and avg_possession < self.possession_min:
            return False
        if self.possession_max is not None and avg_possession > self.possession_max:
            return False

        total_shots = total("shots_home", "shots_away")
        if self.shots_min is not None and total_shots < self.shots_min:
            return False
        if self.shots_max is not None and total_shots > self.shots_max:
            return False

        return True


def filter_matches_by_stats(matches, stat_filters):
    """Aplica filtros numéricos de forma segura retornando apenas partidas válidas."""

    if stat_filters.is_empty():
        return list(matches)

    filtered = []
    for match in matches:
        stats = getattr(match, "stats", None)
        if not stats:
            continue

        if stat_filters.match_stats(stats):
            filtered.append(match)

    return filtered


def match_analysis(request):
    matches = Match.objects.filter(finalizado=False)
    insights_list = []

    for match in matches:
        try:
            event_json = (
                json.loads(match.raw_event_json) if match.raw_event_json else {}
            )
            stats_json = (
                json.loads(match.raw_statistics_json)
                if match.raw_statistics_json
                else {}
            )

            analysis = analyze_match(event_json, stats_json)
            insights_list.append({"match": match, "analysis": analysis})
        except Exception as exc:
            print(f"Erro analisando match {match.id}: {exc}")

    return render(request, "betting/analysis.html", {"insights": insights_list})


def matches_list(request):
    query = request.GET.get("q", "").strip()
    season_id = request.GET.get("season")
    is_live = request.GET.get("live")
    page_number = request.GET.get("page", 1)

    stat_filters = MatchStatFilters.from_request(request)

    today = timezone.localdate()

    matches = (
        Match.objects.select_related(
            "home_team", "away_team", "season", "season__league"
        )
        .prefetch_related("stats")
        .filter(date__date=today, finalizado=False)
        .order_by("-date")
    )

    if query:
        matches = matches.filter(
            Q(home_team__name__icontains=query)
            | Q(away_team__name__icontains=query)
            | Q(season__league__name__icontains=query)
        )

    if season_id:
        matches = matches.filter(season_id=season_id)

    if is_live == "1":
        matches = matches.filter(finalizado=False)

    final_matches = filter_matches_by_stats(matches, stat_filters)

    paginator = Paginator(final_matches, 12)
    page_obj = paginator.get_page(page_number)

    seasons = (
        Match.objects.filter(season__isnull=False)
        .values_list("season__id", "season__name", "season__league__name")
        .distinct()
        .order_by("season__league__name")
    )

    params = request.GET.copy()
    if "page" in params:
        params.pop("page")

    context = {
        "matches": page_obj.object_list,
        "page_obj": page_obj,
        "seasons": seasons,
        "params": params,
        "query": query,
        "season_id": season_id,
        "live": is_live,
        "xg_min": stat_filters.xg_min,
        "xg_max": stat_filters.xg_max,
        "possession_min": stat_filters.possession_min,
        "possession_max": stat_filters.possession_max,
        "shots_min": stat_filters.shots_min,
        "shots_max": stat_filters.shots_max,
    }

    return render(request, "betting/matches.html", context)


def extract_balanced_json(text, title):
    """
    Encontra o bloco JSON após um título e retorna o JSON completo,
    usando contador de chaves para evitar truncamento.
    """

    match = re.search(re.escape(title), text)
    if not match:
        return None

    start_idx = match.end()

    brace_start = text.find("{", start_idx)
    if brace_start == -1:
        return None

    depth = 0
    i = brace_start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                block = text[brace_start : i + 1]
                try:
                    return json.loads(block)
                except Exception as exc:
                    print(f"ERRO PARSING JSON ({title}):", exc)
                    print("JSON CAPTURADO:\n", block)
                    return None
        i += 1

    return None


def parse_summary(raw):
    if not raw:
        return {}

    insights = []
    ins = re.search(r"?? INSIGHTS(.*?)(??|$)", raw, flags=re.S)
    if ins:
        for line in ins.group(1).splitlines():
            line = line.strip()
            if line.startswith("-"):
                insights.append(line.lstrip("- ").strip())

    forecast = extract_balanced_json(raw, "?? PREVISÇO AUTOMµTICA") or {}
    streaks = extract_balanced_json(raw, "?? STREAKS") or {}
    standings = extract_balanced_json(raw, "?? STANDINGS") or {}

    return {
        "insights": insights,
        "forecast": forecast,
        "streaks": streaks,
        "standings": standings,
    }


STAT_LABELS = [
    ("possession", "Posse de Bola (%)"),
    ("expectedGoals", "xG (Gols Esperados)"),
    ("totalShotsOnGoal", "Finalizações"),
    ("cornerKicks", "Escanteios"),
    ("bigChanceCreated", "Grandes Chances"),
    ("finalThirdEntries", "Entradas no Terço Final"),
    ("touchesInOppBox", "Toques na Área Rival"),
    ("fouls", "Faltas"),
    ("yellowCards", "Cartões Amarelos"),
    ("xg", "Expected Goals"),
    ("shots_on", "Chutes no Gol"),
    ("shots_total", "Finalizações"),
    ("corners", "Escanteios"),
    ("touches_box", "Toques na Área"),
    ("final_third_entries", "Entradas no Terço Final"),
    ("big_chances", "Grandes Chances"),
    ("shots_inside_box", "Chutes na Área"),
    ("recoveries", "Recuperações"),
]


def _compute_live_analysis(match, analyzer):
    if match.stats_json and match.event_json:
        return analyzer.analyze_json_data(match.stats_json, match.event_json)
    return {"insights": [], "pressure_index": {"home": 50, "away": 50}}


def _parse_match_summary(match):
    stats = MatchStats.objects.filter(match=match).first()
    return stats, parse_summary(stats.summary) if stats and stats.summary else {}


def _apply_streak_impact(base_analysis, streak_analysis):
    if not (base_analysis and "probabilities" in base_analysis):
        return base_analysis

    probs = base_analysis["probabilities"]
    impact = streak_analysis.get("impact", {})

    def to_odd(pct):
        return round(100 / pct, 2) if pct > 1 else 1.01

    probs["over_2_5"] = min(
        95, probs.get("over_2_5", 50) + impact.get("over_goals", 0) * 5
    )
    probs["btts"] = min(95, probs.get("btts", 50) + impact.get("btts", 0) * 5)

    momentum_factor = impact.get("momentum", 0) * 3
    probs["home"] = min(90, max(10, probs.get("home", 33) + momentum_factor))

    base_analysis["odds"] = {key: to_odd(val) for key, val in probs.items()}
    return base_analysis


def match_detail(request, pk):
    match = get_object_or_404(
        Match.objects.select_related("home_team", "away_team", "season"), pk=pk
    )

    analyzer = MatchAnalyzer(match)
    live_analysis = _compute_live_analysis(match, analyzer)

    stats, summary = _parse_match_summary(match)
    streak_analysis = analyzer.analyze_streaks(summary.get("streaks", {}))

    base_analysis = _apply_streak_impact(
        SofaScore().get_analise_event(match), streak_analysis
    )

    context = {
        "match": match,
        "stats": stats,
        "summary": summary,
        "analysis": base_analysis,
        "streak_analysis": streak_analysis,
        "live_analysis": live_analysis,
        "possible_bets": PossibleBet.objects.filter(event_id=match.external_id),
        "stat_labels": STAT_LABELS,
        "current_home": match.home_team_score or 0,
        "current_away": match.away_team_score or 0,
    }

    return render(request, "betting/match_detail.html", context)


def post_status(request):
    try:
        if request.method == "POST":
            event_id = request.POST.get("event_id")
            match = Match.objects.get(id=event_id)
            snapshot = SofaScore().get_stats(event_id)

            if snapshot is None:
                return JsonResponse({"error": "No snapshot created"}, status=400)

            analysis_live = SofaScore().analyze_last_snapshots(match, window=10)

            data = model_to_dict(snapshot)
            data["analysis_live"] = analysis_live

            return JsonResponse(data)
    except Exception as exc:
        print(exc.__traceback__.tb_lineno)


def match_snapshots(request, match_id):
    snaps = LiveSnapshot.objects.filter(match_id=match_id).order_by("minute")

    data = []
    for snapshot in snaps:
        data.append(
            {
                "minute": snapshot.minute,
                "xg_home": snapshot.xg_home,
                "xg_away": snapshot.xg_away,
                "shots_total_home": snapshot.shots_total_home,
                "shots_total_away": snapshot.shots_total_away,
                "shots_on_home": snapshot.shots_on_home,
                "shots_on_away": snapshot.shots_on_away,
                "possession_home": snapshot.possession_home,
                "possession_away": snapshot.possession_away,
                "corners_home": snapshot.corners_home,
                "corners_away": snapshot.corners_away,
                "touches_box_home": snapshot.touches_box_home,
                "touches_box_away": snapshot.touches_box_away,
                "final_third_entries_home": snapshot.final_third_entries_home,
                "final_third_entries_away": snapshot.final_third_entries_away,
                "momentum_score": snapshot.momentum_score,
            }
        )

    return JsonResponse({"snapshots": data})


def result(request):
    stake = float(request.GET.get("stake", 100))
    odd_media = float(request.GET.get("odd", 1.45))
    liga_id = request.GET.get("liga")

    matches = Match.objects.select_related(
        "home_team", "away_team", "season", "season__league"
    ).all()

    if liga_id:
        matches = matches.filter(season__league_id=liga_id)

    ligas_disponiveis = League.objects.order_by("name").all()

    resultados = []
    greens = reds = pushes = 0
    hoje = now()
    for match in matches:
        if not match.finalizado:
            continue
        stats = MatchStats.objects.filter(match=match).first()
        summary = parse_summary(stats.summary) if stats and stats.summary else {}

        principal = (
            summary.get("forecast", {})
            .get("mercados_sugeridos_modelo", {})
            .get("principal", "")
        )

        if principal == "Nenhum mercado seguro" or not principal:
            continue

        if principal.startswith("Over "):
            tipo = "Maior"
        elif principal.startswith("Under "):
            tipo = "Menor"
        else:
            tipo = "Desconhecido"

        linha_str = principal.replace("Over ", "").replace("Under ", "")

        try:
            linha = float(linha_str)
        except ValueError:
            continue

        placar = (match.home_team_score or 0) + (match.away_team_score or 0)

        if tipo == "Maior":
            if placar > linha:
                status = "GREEN"
                greens += 1
            elif placar < linha:
                status = "RED"
                reds += 1
            else:
                status = "PUSH"
                pushes += 1

        elif tipo == "Menor":
            if placar < linha:
                status = "GREEN"
                greens += 1
            elif placar > linha:
                status = "RED"
                reds += 1
            else:
                status = "PUSH"
                pushes += 1
        else:
            status = "N/A"

        resultados.append(
            {
                "match": match,
                "stats": stats,
                "principal": linha,
                "tipo": tipo,
                "status": status,
                "placar": placar,
                "liga": match.season,
            }
        )

    total_bets = len(resultados)
    winrate = (greens / total_bets * 100) if total_bets > 0 else 0
    lucro = (greens * (stake * (odd_media - 1))) - (reds * stake)

    insights = {
        "total_bets": total_bets,
        "greens": greens,
        "reds": reds,
        "pushes": pushes,
        "winrate": winrate,
        "stake": stake,
        "odd_media": odd_media,
        "lucro": lucro,
        "liga_selecionada": liga_id or "",
    }

    return render(
        request,
        "betting/resultados.html",
        {
            "resultados": resultados,
            "insights": insights,
            "ligas": ligas_disponiveis,
        },
    )
