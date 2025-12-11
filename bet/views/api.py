import calendar
import random
import time

import requests
from curl_cffi import requests as cureq
from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

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
                "asian_0_25": {
                    "home": {"odd": ah_home, "prob": round(probs_ah["home"], 4)},
                    "away": {"odd": ah_away, "prob": round(probs_ah["away"], 4)},
                },
            },
        }

        return Response(result, status=200)


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
