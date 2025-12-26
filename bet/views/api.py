import calendar
import random
import time
from decimal import Decimal

import requests
from curl_cffi import requests as cureq
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from bet.models import MatchModelEvaluation
from jogos.models import Match

BASE = "https://www.sofascore.com/api/v1"
headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def get_json(url):
    try:
        resp = cureq.get(url, impersonate="chrome", timeout=15, verify=False)
        if resp.status_code != 200:
            print(f"HTTP {resp.status_code} em {url}")
            return None
        return resp.json()
    except Exception as exc:
        print(f"Erro em {url}: {exc}")
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
        leitura_fav = "Partida equilibrada - sem favorito claro."

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
        "leitura_geral": {"gols": mercado_gols, "favorito": leitura_fav},
        "mercados_sugeridos_modelo": {
            "principal": mercado_seguro,
            "gols": mercado_gols,
        },
    }


class MatchOddsFeaturedView(APIView):
    """
    Retorna odds convertidas e probabilidades implícitas (já normalizadas).
    """

    @staticmethod
    def fractional_to_decimal(frac: str) -> float:
        """Converte fração '27/20' em decimal 2.35."""
        num, den = frac.split("/")
        return 1 + (float(num) / float(den))

    @staticmethod
    def implied_probability(decimal_odd: float) -> float:
        """Converte odd decimal para probabilidade implícita da casa: 1 / odd."""
        return 1 / decimal_odd

    @staticmethod
    def normalize_probabilities(prob_dict):
        """Remove o overround dividindo pelo total."""
        total = sum(prob_dict.values())
        return {key: value / total for key, value in prob_dict.items()}

    def get(self, request, pk):
        from jogos.models import Match

        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return Response(
                {"error": "Match not found"}, status=status.HTTP_404_NOT_FOUND
            )

        external_id = match.external_id
        if not external_id:
            return Response({"error": "Match does not have external_id"}, status=400)

        url = f"https://www.sofascore.com/api/v1/event/{external_id}/odds/100/featured"
        local_headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

        try:
            resp = requests.get(url, headers=local_headers, timeout=6)
            resp.raise_for_status()
        except requests.RequestException as exc:
            return Response(
                {"error": "Failed to fetch odds", "details": str(exc)}, status=500
            )

        data = resp.json()
        fulltime = data["featured"].get("fullTime") or data["featured"].get("default")
        choices = fulltime["choices"]

        odd_home = self.fractional_to_decimal(choices[0]["fractionalValue"])
        odd_draw = self.fractional_to_decimal(choices[1]["fractionalValue"])
        odd_away = self.fractional_to_decimal(choices[2]["fractionalValue"])

        probs_raw = {
            "home": self.implied_probability(odd_home),
            "draw": self.implied_probability(odd_draw),
            "away": self.implied_probability(odd_away),
        }

        probs_norm = self.normalize_probabilities(probs_raw)

        ah = data["featured"].get("asian")
        asian_choices = ah["choices"]
        asian_label = ah.get("choiceGroup") or "+0.25"

        ah_home = self.fractional_to_decimal(asian_choices[0]["fractionalValue"])
        ah_away = self.fractional_to_decimal(asian_choices[1]["fractionalValue"])

        probs_ah_raw = {
            "home": self.implied_probability(ah_home),
            "away": self.implied_probability(ah_away),
        }
        probs_ah = self.normalize_probabilities(probs_ah_raw)

        result = {
            "match_id": pk,
            "external_id": external_id,
            "markets": {
                "1x2": {
                    "home": {"odd": odd_home, "prob": round(probs_norm["home"], 4)},
                    "draw": {"odd": odd_draw, "prob": round(probs_norm["draw"], 4)},
                    "away": {"odd": odd_away, "prob": round(probs_norm["away"], 4)},
                },
                "asian": {
                    "label": asian_label,
                    "home": {"odd": ah_home, "prob": round(probs_ah["home"], 4)},
                    "away": {"odd": ah_away, "prob": round(probs_ah["away"], 4)},
                },
            },
        }

        return Response(result, status=200)


class MatchOddsAllView(APIView):
    """
    Retorna mercados principais de /odds/1/all com odds decimais e probs normalizadas por mercado.
    """

    @staticmethod
    def fractional_to_decimal(frac: str) -> float:
        num, den = frac.split("/")
        return 1 + (float(num) / float(den))

    @staticmethod
    def implied_probability(decimal_odd: float) -> float:
        return 1 / decimal_odd

    @staticmethod
    def normalize_probabilities(prob_dict):
        total = sum(prob_dict.values())
        return (
            {key: value / total for key, value in prob_dict.items()}
            if total
            else prob_dict
        )

    def _convert_market(self, market):
        choices = market.get("choices") or []
        if not choices:
            return None

        odds = {}
        prob_raw = {}
        for choice in choices:
            name = choice.get("name")
            frac = choice.get("fractionalValue")
            if not name or not frac:
                continue
            dec = self.fractional_to_decimal(frac)
            odds[name] = dec
            prob_raw[name] = self.implied_probability(dec)

        if not odds:
            return None

        probs = self.normalize_probabilities(prob_raw)
        converted_choices = [
            {"name": k, "odd": round(odds[k], 2), "prob": round(probs.get(k, 0), 4)}
            for k in odds
        ]

        return {
            "market_id": market.get("marketId"),
            "market": market.get("marketName"),
            "group": market.get("marketGroup"),
            "period": market.get("marketPeriod"),
            "label": market.get("choiceGroup"),
            "choices": converted_choices,
        }

    def get(self, request, pk):
        from jogos.models import Match

        try:
            match = Match.objects.get(pk=pk)
        except Match.DoesNotExist:
            return Response(
                {"error": "Match not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if not match.external_id:
            return Response({"error": "Match does not have external_id"}, status=400)

        url = f"https://www.sofascore.com/api/v1/event/{match.external_id}/odds/1/all"
        local_headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

        try:
            resp = requests.get(url, headers=local_headers, timeout=8)
            resp.raise_for_status()
        except requests.RequestException as exc:
            return Response(
                {"error": "Failed to fetch odds", "details": str(exc)}, status=500
            )

        data = resp.json()
        print(data)
        markets_raw = data.get("markets") or []

        converted = []
        for market in markets_raw:
            conv = self._convert_market(market)
            if conv:
                converted.append(conv)

        return Response(
            {"match_id": pk, "external_id": match.external_id, "markets": converted},
            status=200,
        )


def sofascore_scrape_view(request):
    year, month = 2025, 10
    num_days = calendar.monthrange(year, month)[1]

    date_list = [f"{year}-{month:02d}-{day:02d}" for day in range(1, num_days + 1)]

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
            event
            for event in data["events"]
            if event["tournament"]["slug"] in allowed_leagues
            and event["tournament"]["category"]["slug"] in allowed_countries
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


def model_comparison_view(request, match_id=None):
    context = {}

    # ---------------------------
    # Visão por jogo (se existir)
    # ---------------------------
    if match_id:
        match = get_object_or_404(Match, pk=match_id)

        evaluations = MatchModelEvaluation.objects.filter(match=match)

        markets = {}
        for e in evaluations:
            markets.setdefault(e.market, {})
            key = e.model_version.replace(".", "_")  # v3.1 -> v3_1
            markets[e.market][key] = e.result
            markets[e.market]["real"] = e.real_value

        # Decide vencedor do jogo
        score = {"v3_1": 0, "v3_2": 0}
        for m in markets.values():
            for model in ["v3_1", "v3_2"]:
                if m.get(model) == "hit":
                    score[model] += 1

        winner = (
            "v3.1"
            if score["v3_1"] > score["v3_2"]
            else "v3.2" if score["v3_2"] > score["v3_1"] else "Empate"
        )

        context.update(
            {
                "match": match,
                "markets": markets,
                "winner_model": winner,
            }
        )

    # ---------------------------
    # Visão agregada (performance geral)
    # ---------------------------
    summary_qs = MatchModelEvaluation.objects.values(
        "model_version", "market"
    ).annotate(
        total=Count("id"),
        hits=Count("id", filter=Q(result="hit")),
    )

    summary = {}
    for row in summary_qs:
        market = row["market"]
        model_key = row["model_version"].replace(".", "_")  # v3.1 -> v3_1

        summary.setdefault(market, {})
        summary[market][model_key] = (
            round(100 * row["hits"] / row["total"], 1) if row["total"] else 0
        )

    # garante que ambos existam (evita None no template)
    for market in summary.values():
        market.setdefault("v3_1", 0)
        market.setdefault("v3_2", 0)

    context["summary"] = summary

    return render(request, "betting/model_comparison.html", context)


class PreBetAnalysisView(View):
    template_name = "betting/pre_bet_analysis.html"

    def parse_ratio(self, value):
        if "/" not in value:
            return None
        try:
            x, y = value.split("/")
            return int(x) / int(y)
        except Exception:
            return None

    def calculate_market_prob(self, match_data, market_name):
        general_probs = []
        h2h_probs = []

        for item in match_data.get("general", []):
            if item["name"].lower() == market_name.lower():
                p = self.parse_ratio(item["value"])
                if p:
                    general_probs.append(p)

        for item in match_data.get("head2head", []):
            if item["name"].lower() == market_name.lower():
                p = self.parse_ratio(item["value"])
                if p:
                    h2h_probs.append(p)

        # pesos: 70% general / 30% h2h
        if general_probs and h2h_probs:
            return (sum(general_probs) / len(general_probs)) * 0.7 + (
                sum(h2h_probs) / len(h2h_probs)
            ) * 0.3

        if general_probs:
            return sum(general_probs) / len(general_probs)

        if h2h_probs:
            return sum(h2h_probs) / len(h2h_probs)

        return None

    MARKETS = [
        "More than 2.5 goals",
        "Both teams scoring",
        "Less than 10.5 corners",
        "More than 10.5 corners",
        "Less than 4.5 cards",
        "First to score",
    ]

    def get(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)

        return render(
            request,
            self.template_name,
            {
                "match": match,
                "markets": self.MARKETS,
            },
        )

    def post(self, request, match_id):
        match = get_object_or_404(Match, pk=match_id)

        market = request.POST.get("market")
        odd = Decimal(request.POST.get("odd"))

        # aqui você já tem o JSON da partida
        match_data = match.streaks_json or {}

        prob = self.calculate_market_prob(match_data, market)

        book_prob = Decimal(1) / odd if odd else None

        should_bet = prob and book_prob and prob > float(book_prob)

        context = {
            "match": match,
            "markets": self.MARKETS,
            "selected_market": market,
            "odd": float(odd),
            "analysis": (
                {
                    "model_prob_pct": round(prob * 100, 1) if prob else None,
                    "book_prob_pct": (
                        round(float(book_prob) * 100, 1) if book_prob else None
                    ),
                    "difference_pct": (
                        round((prob - float(book_prob)) * 100, 1) if prob else None
                    ),
                    "decision": "APOSTAR" if should_bet else "NÃO APOSTAR",
                    "is_good": should_bet,
                }
                if prob
                else None
            ),
            "error": None if prob else "Não há dados suficientes para esse mercado.",
        }

        return render(request, self.template_name, context)
