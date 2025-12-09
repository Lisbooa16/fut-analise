import calendar
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from curl_cffi import requests as cureq
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.forms import model_to_dict
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import now

from bet.models import Bankroll, Bet, PossibleBet, Status
from bet.utils import MatchAnalyzer, generate_bankroll_alerts
from get_events import SofaScore
from jogos.models import League, LiveSnapshot, Match, MatchStats, RunningToday, Season
from jogos.utils import analyze_match, save_sofascore_data


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


def create_bet_from_model(request, pb_id):
    pb = get_object_or_404(PossibleBet, id=pb_id)
    bankroll = Bankroll.objects.first()

    try:
        match = Match.objects.get(external_id=pb.event_id)
    except Match.DoesNotExist:
        messages.error(request, "Não foi possível encontrar o jogo desta aposta.")
        return redirect("dashboard")

    stake = Decimal("10.00")
    odd = Decimal("1.50")

    bet = Bet.objects.create(
        bankroll=bankroll,
        match=match,
        market=pb.market,
        odd=odd,
        stake=stake,
        potential_profit=stake * odd,
    )

    bankroll.withdraw(stake, note=f"Aposta gerada a partir do modelo: {pb.market}")
    bankroll.save(update_fields=["balance"])

    messages.success(request, f"Aposta criada: {pb.market}")
    return redirect("match_detail", pk=match.id)


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
            insights_list.append(
                {
                    "match": match,
                    "analysis": analysis,
                }
            )
        except Exception as e:
            print(f"Erro analisando match {match.id}: {e}")

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

    m = re.search(re.escape(title), text)
    if not m:
        return None

    start_idx = m.end()

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
                except Exception as e:
                    print(f"ERRO PARSING JSON ({title}):", e)
                    print("JSON CAPTURADO:\n", block)
                    return None
        i += 1

    return None


def parse_summary(raw):
    if not raw:
        return {}

    insights = []
    ins = re.search(r"📌 INSIGHTS(.*?)(📌|$)", raw, flags=re.S)
    if ins:
        for line in ins.group(1).splitlines():
            line = line.strip()
            if line.startswith("-"):
                insights.append(line.lstrip("- ").strip())

    forecast = extract_balanced_json(raw, "📌 PREVISÃO AUTOMÁTICA") or {}

    streaks = extract_balanced_json(raw, "📌 STREAKS") or {}

    standings = extract_balanced_json(raw, "📌 STANDINGS") or {}

    return {
        "insights": insights,
        "forecast": forecast,
        "streaks": streaks,
        "standings": standings,
    }


def match_detail(request, pk):

    match = get_object_or_404(
        Match.objects.select_related("home_team", "away_team", "season"), pk=pk
    )

    analyzer = MatchAnalyzer(match)

    if match.stats_json and match.event_json:
        live_analysis = analyzer.analyze_json_data(match.stats_json, match.event_json)
    else:

        live_analysis = {"insights": [], "pressure_index": {"home": 50, "away": 50}}

    stats = MatchStats.objects.filter(match=match).first()
    summary = parse_summary(stats.summary) if stats and stats.summary else {}

    streak_data = summary.get("streaks", {})
    streak_analysis = analyzer.analyze_streaks(streak_data)

    base_analysis = SofaScore().get_analise_event(match)

    impact = streak_analysis.get("impact", {})

    if base_analysis and "probabilities" in base_analysis:
        probs = base_analysis["probabilities"]

        probs["over_2_5"] = min(
            95, probs.get("over_2_5", 50) + impact.get("over_goals", 0) * 5
        )
        probs["btts"] = min(95, probs.get("btts", 50) + impact.get("btts", 0) * 5)

        momentum_factor = impact.get("momentum", 0) * 3
        probs["home"] = min(90, max(10, probs.get("home", 33) + momentum_factor))

        def to_odd(p):
            return round(100 / p, 2) if p > 1 else 1.01

        base_analysis["odds"] = {k: to_odd(v) for k, v in probs.items()}

    current_home = match.home_team_score if match.home_team_score is not None else 0
    current_away = match.away_team_score if match.away_team_score is not None else 0

    possible_bets = PossibleBet.objects.filter(event_id=match.external_id)

    stat_labels = [
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

    return render(
        request,
        "betting/match_detail.html",
        {
            "match": match,
            "stats": stats,
            "summary": summary,
            "analysis": base_analysis,
            "streak_analysis": streak_analysis,
            "live_analysis": live_analysis,
            "possible_bets": possible_bets,
            "stat_labels": stat_labels,
        },
    )


def get_recommended_stake_and_odd(bankroll, probability=None):
    """
    Retorna (stake_recomendada, odd_recomendada)
    probability = probabilidade em % (ex: 67.7)
    """

    if probability is None:
        percent = Decimal("0.01")
    elif probability >= 70:
        percent = Decimal("0.02")
    elif probability >= 55:
        percent = Decimal("0.015")
    else:
        percent = Decimal("0.01")

    stake = bankroll.balance * percent

    if probability:
        prob_decimal = Decimal(probability) / Decimal("100")
        odd_fair = Decimal("1") / prob_decimal
        odd_recommended = odd_fair.quantize(Decimal("0.01"))
    else:
        odd_recommended = Decimal("1.50")

    return (stake.quantize(Decimal("0.01")), odd_recommended)


def place_bet(request, match_id):
    match = get_object_or_404(Match, id=match_id)
    bankroll, _ = Bankroll.objects.get_or_create(name="Banca Principal")
    alerts = generate_bankroll_alerts(bankroll)

    probability = None

    if hasattr(match, "analysis"):

        try:

            probs = getattr(match.analysis, "probabilities", {})
            probability = probs.get("over_2_5")
        except:
            pass

    recommended_stake, recommended_odd = get_recommended_stake_and_odd(
        bankroll, probability
    )

    if request.method == "POST":
        market = request.POST.get("market")
        raw_odd = request.POST.get("odd")
        raw_stake = request.POST.get("stake")

        try:

            odd = Decimal(raw_odd.replace(",", "."))
            stake = Decimal(raw_stake.replace(",", "."))

            if stake <= 0 or odd <= 1:
                messages.error(request, "Stake deve ser positiva e Odd maior que 1.")
            elif bankroll.balance < stake:
                messages.error(
                    request, f"Saldo insuficiente. Você tem R$ {bankroll.balance}."
                )
            else:
                bet = Bet.objects.create(
                    bankroll=bankroll,
                    match=match,
                    market=market,
                    odd=odd,
                    stake=stake,
                )

                bet.register_bet()

                messages.success(
                    request,
                    f"✅ Aposta confirmada em {match.home_team} vs {match.away_team}!",
                )
                return redirect("dashboard")

        except (InvalidOperation, ValueError):
            messages.error(request, "Valores inválidos. Verifique os campos numéricos.")
        except Exception as e:
            messages.error(request, f"Erro ao registrar aposta: {e}")

    return render(
        request,
        "betting/place_bet.html",
        {
            "match": match,
            "bankroll": bankroll,
            "recommended_stake": recommended_stake,
            "recommended_odd": recommended_odd,
            "probability": probability,
            "alerts": alerts,
        },
    )


def _parse_decimal(value: str | None) -> Decimal:
    if value is None:
        raise ValueError("Nenhum valor informado.")
    return Decimal(value.replace(",", "."))


def _bankroll_totals(bets):
    return (
        bets.filter(result="GREEN").aggregate(Sum("potential_profit"))[
            "potential_profit__sum"
        ]
        or Decimal("0")
    ), (bets.filter(result="RED").aggregate(Sum("stake"))["stake__sum"] or Decimal("0"))


def bankroll_view(request):
    """Exibe a banca e permite adicionar saldo."""

    bankroll, _ = Bankroll.objects.get_or_create(
        name="Banca Principal", defaults={"balance": 0}
    )

    if request.method == "POST":
        action = request.POST.get("action")
        amount = request.POST.get("amount")

        try:
            value = _parse_decimal(amount)

            if value <= 0:
                messages.error(request, "O valor deve ser maior que zero.")
            elif action in {"increase", "increese"}:
                bankroll.deposit(value, note="Depósito manual")
                messages.success(request, f"💰 Adicionado R$ {value} à banca!")
                return redirect("bankroll_view")
            elif action == "remove":
                bankroll.withdraw(value, note="Saque manual")
                messages.success(request, f"💸 Removido R$ {value} da banca!")
                return redirect("bankroll_view")
            else:
                messages.error(request, "Ação inválida.")

        except (InvalidOperation, ValueError) as exc:
            messages.error(request, f"Valor inválido. {exc}")
        except Exception as exc:
            messages.error(request, f"Erro ao processar: {exc}")

    bets = bankroll.bets.all().order_by("-created_at")
    total_green, total_red = _bankroll_totals(bets)

    return render(
        request,
        "betting/bankroll.html",
        {
            "bankroll": bankroll,
            "bets": bets,
            "total_green": total_green,
            "total_red": total_red,
        },
    )


def dashboard(request):
    """Visão geral: banca + métricas reais."""

    today = date.today().isoformat()
    if not RunningToday.objects.filter(data=today, rodou=True).exists():

        try:
            SofaScore([today]).get_events()
            RunningToday.objects.update_or_create(data=today, defaults={"rodou": True})
        except Exception as e:
            print(f"Erro ao rodar scraper: {e}")

    bankroll, _ = Bankroll.objects.get_or_create(name="Banca Principal")

    all_bets = Bet.objects.all()

    metrics = all_bets.aggregate(
        total_stake_green=Sum("stake", filter=Q(result="GREEN")),
        total_return_green=Sum("potential_profit", filter=Q(result="GREEN")),
        total_loss=Sum("stake", filter=Q(result="RED")),
        greens_30d=Count(
            "id",
            filter=Q(
                result="GREEN", created_at__gte=timezone.now() - timedelta(days=30)
            ),
        ),
    )

    stake_green = metrics["total_stake_green"] or 0
    return_green = metrics["total_return_green"] or 0
    total_loss = metrics["total_loss"] or 0

    profit_net = return_green - stake_green

    overall_performance = profit_net - total_loss

    recent_bets = all_bets.order_by("-created_at")[:8]

    return render(
        request,
        "betting/dashboard.html",
        {
            "user_name": request.user.first_name or request.user.username,
            "bankroll": bankroll,
            "bets": recent_bets,
            "chart_profit": profit_net,
            "chart_loss": total_loss,
            "chart_balance": bankroll.balance,
            "greens_last_30": metrics["greens_30d"],
            "users_online": 1,
        },
    )


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
    except Exception as e:
        print(e.__traceback__.tb_lineno)


def match_snapshots(request, match_id):
    snaps = LiveSnapshot.objects.filter(match_id=match_id).order_by("minute")

    data = []
    for s in snaps:
        data.append(
            {
                "minute": s.minute,
                "xg_home": s.xg_home,
                "xg_away": s.xg_away,
                "shots_total_home": s.shots_total_home,
                "shots_total_away": s.shots_total_away,
                "shots_on_home": s.shots_on_home,
                "shots_on_away": s.shots_on_away,
                "possession_home": s.possession_home,
                "possession_away": s.possession_away,
                "corners_home": s.corners_home,
                "corners_away": s.corners_away,
                "touches_box_home": s.touches_box_home,
                "touches_box_away": s.touches_box_away,
                "final_third_entries_home": s.final_third_entries_home,
                "final_third_entries_away": s.final_third_entries_away,
                "momentum_score": s.momentum_score,
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


def update_bet_result(request, bet_id):
    """Atualiza o resultado da aposta (Green ou Red)."""
    bet = get_object_or_404(Bet, id=bet_id)

    result = request.GET.get("result")
    if result == "green":
        bet.settle_bet(is_green=True)
        messages.success(
            request, f"Aposta marcada como GREEN! Lucro adicionado à banca."
        )
    elif result == "red":
        bet.settle_bet(is_green=False)
        messages.warning(request, f"Aposta marcada como RED. Nenhum valor retornado.")
    else:
        messages.error(request, "Resultado inválido.")

    return redirect("bankroll_view")


BASE = "https://www.sofascore.com/api/v1"
headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get_json(url):
    try:
        resp = cureq.get(url, impersonate="chrome", timeout=15, verify=False)
        if resp.status_code != 200:
            print(f"❌ HTTP {resp.status_code} em {url}")
            return None
        return resp.json()
    except Exception as e:
        print(f"❌ Erro em {url}: {e}")
        return None


def prob_from_ratio(ratio):
    if ratio is None:
        return 50
    return min(int(ratio * 100), 100)


def generate_auto_prediction(event, stats, streaks, standings):
    home = event["homeTeam"]["name"]
    away = event["awayTeam"]["name"]

    home_st = standings.get("home") or {}
    away_st = standings.get("away") or {}

    streaks_gen = streaks.get("general", []) or []
    streaks_h2h = streaks.get("head2head", []) or []

    stats_block = stats or {}
    xg_h = float(stats_block.get("xg", {}).get("home", 0.0))
    xg_a = float(stats_block.get("xg", {}).get("away", 0.0))

    shots_h = float(stats_block.get("shots", {}).get("home", 0.0))
    shots_a = float(stats_block.get("shots", {}).get("away", 0.0))

    sot_h = float(stats_block.get("shots_on", {}).get("home", 0.0))
    sot_a = float(stats_block.get("shots_on", {}).get("away", 0.0))

    poss_h = float(stats_block.get("posse", {}).get("home", 0.0))
    poss_a = float(stats_block.get("posse", {}).get("away", 0.0))

    total_xg = xg_h + xg_a
    total_shots = shots_h + shots_a
    total_sot = sot_h + sot_a

    start_ts = event.get("startTimestamp")
    current_ts = event.get("time", {}).get("timestamp")

    minute = None
    if start_ts and current_ts:
        elapsed = max(0, current_ts - start_ts)
        minute = int(elapsed // 60)

    if minute is None:
        phase = "pre"
    elif minute <= 30:
        phase = "early"
    elif minute <= 70:
        phase = "mid"
    else:
        phase = "late"

    under_signals, over_signals = [], []
    home_signals, away_signals = [], []

    def is_goal_streak(name):
        name = name.lower()
        return ("goal" in name) or ("gols" in name) or ("goals" in name)

    for item in streaks_gen + streaks_h2h:
        ratio = item.get("ratio")
        if ratio is None:
            continue

        name = (item.get("name") or "").lower()
        team = item.get("team")

        if is_goal_streak(name):
            if "more than" in name or "mais de" in name:
                over_signals.append(prob_from_ratio(ratio))
            if "less than" in name or "menos de" in name:
                under_signals.append(prob_from_ratio(ratio))

        if team == "home" and ratio >= 0.60:
            home_signals.append(prob_from_ratio(ratio))
        if team == "away" and ratio >= 0.60:
            away_signals.append(prob_from_ratio(ratio))

    pts_home = home_st.get("points", 0)
    pts_away = away_st.get("points", 0)
    diff_pts = pts_home - pts_away

    if diff_pts > 2:
        home_signals.append(65)
    elif diff_pts < -2:
        away_signals.append(65)

    if total_xg >= 2.0:
        over_signals.append(80)
    elif total_xg >= 1.2:
        over_signals.append(70)
    elif total_xg >= 0.8:
        over_signals.append(60)
    elif total_xg <= 0.4 and phase in ("mid", "late"):
        under_signals.append(70)

    if total_shots >= 18:
        over_signals.append(70)
    elif total_shots >= 10:
        over_signals.append(60)
    elif total_shots <= 4 and phase in ("mid", "late"):
        under_signals.append(65)

    if total_sot >= 7:
        over_signals.append(75)
    elif total_sot >= 4:
        over_signals.append(65)
    elif total_sot <= 1 and phase in ("mid", "late"):
        under_signals.append(65)

    hs = event.get("homeScore", {}) or {}
    as_ = event.get("awayScore", {}) or {}
    score_h = hs.get("current", 0)
    score_a = as_.get("current", 0)
    total_goals = score_h + score_a

    if phase == "late" and total_goals == 0 and total_xg < 1.0:
        under_signals.append(80)

    if xg_h > xg_a * 1.5 and xg_h > 0.4:
        home_signals.append(70)
    elif xg_a > xg_h * 1.5 and xg_a > 0.4:
        away_signals.append(70)

    if sot_h >= 3 and sot_h >= sot_a + 2:
        home_signals.append(60)
    if sot_a >= 3 and sot_a >= sot_h + 2:
        away_signals.append(60)

    if poss_h >= 60:
        home_signals.append(55)
    elif poss_a >= 60:
        away_signals.append(55)

    def avg_or_50(values):
        return int(sum(values) / len(values)) if values else 50

    prob_over = avg_or_50(over_signals)
    prob_under = avg_or_50(under_signals)
    prob_home = avg_or_50(home_signals)
    prob_away = avg_or_50(away_signals)

    prob_over = max(5, min(95, prob_over))
    prob_under = max(5, min(95, prob_under))
    prob_home = max(5, min(95, prob_home))
    prob_away = max(5, min(95, prob_away))

    diff_gols = prob_over - prob_under

    if diff_gols >= 15:
        mercado_gols = "Over 2.5"
    elif diff_gols >= 8:
        mercado_gols = "Over 1.5"
    elif diff_gols <= -15:
        mercado_gols = "Under 2.5"
    elif diff_gols <= -8:
        mercado_gols = "Under 3.5"
    else:
        mercado_gols = "Nenhum mercado claro"

    diff_prob = prob_home - prob_away
    score_home = diff_prob * 0.7 + diff_pts * 0.3

    if score_home >= 12:
        leitura_fav = f"{home} aparece como favorito pelo momento."
    elif score_home <= -12:
        leitura_fav = f"{away} aparece como favorito pelo momento."
    else:
        leitura_fav = "Partida equilibrada — sem favorito claro."

    if mercado_gols.startswith("Under"):
        mercado_seguro = "Under 3.5" if "2.5" in mercado_gols else mercado_gols
    elif mercado_gols.startswith("Over"):
        mercado_seguro = "Over 1.5" if "2.5" in mercado_gols else mercado_gols
    else:
        if abs(score_home) < 10:
            mercado_seguro = "Nenhum mercado seguro"
        else:
            mercado_seguro = (
                "Dupla chance mandante" if score_home > 0 else "Dupla chance visitante"
            )

    return {
        "probabilidades": {
            "under": prob_under,
            "over": prob_over,
            "home": prob_home,
            "away": prob_away,
        },
        "leitura_geral": {
            "gols": mercado_gols,
            "favorito": leitura_fav,
        },
        "mercados_sugeridos_modelo": {
            "principal": mercado_seguro,
            "gols": mercado_gols,
        },
    }


def sofascore_scrape_view(request):

    year, month = 2025, 10
    num_days = calendar.monthrange(year, month)[1]

    date_list = [f"{year}-{month:02d}-{d:02d}" for d in range(1, num_days + 1)]

    allowed_leagues = {
        "premier-league",
        "laliga",
        "serie-a",
        "conmebol-libertadores",
        "brasileirao-serie-a",
        "ligue-1",
        "bundesliga",
        "trendyol-super-lig",
    }

    allowed_countries = {
        "england",
        "spain",
        "italy",
        "south-america",
        "brazil",
        "france",
        "germany",
        "turkey",
    }

    log = []

    for date_str in date_list:
        url = f"{BASE}/sport/football/scheduled-events/{date_str}"
        data = get_json(url)

        if not data or "events" not in data:
            continue

        events = [
            e
            for e in data["events"]
            if e["tournament"]["slug"] in allowed_leagues
            and e["tournament"]["category"]["slug"] in allowed_countries
        ]

        for event in events:
            event_id = event["id"]

            stats = get_json(f"{BASE}/event/{event_id}/statistics")
            streaks = get_json(f"{BASE}/event/{event_id}/team-streaks")

            tournament_id = event["tournament"]["id"]
            season_id = event["season"]["id"]
            standings = get_json(
                f"{BASE}/tournament/{tournament_id}/season/{season_id}/standings/total"
            )

            time.sleep(random.uniform(1.0, 2.5))

            log.append(f"Processado evento {event_id}")

    return JsonResponse({"status": "ok", "log": log})
