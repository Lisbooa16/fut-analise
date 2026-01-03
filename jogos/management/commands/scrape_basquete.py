import calendar
import json
import random
import time

import requests
from django.core.management.base import BaseCommand

from bet.models import PossibleBet
from jogos.utils import save_sofascore_data, save_sofascore_data_nba

BASE = "https://www.sofascore.com/api/v1"
headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


class Command(BaseCommand):
    help = "Busca dados do Sofascore e salva no banco"

    def handle(self, *args, **options):
        self.stdout.write("🚀 Rodando Sofascore...")

        BASE = "https://www.sofascore.com/api/v1"
        cookies = {
            "_gcl_au": "1.1.1410777148.1764702710",
            "_ga": "GA1.1.838785703.1764702710",
            "g_state": '{"i_l":0,"i_ll":1764703841911,"i_b":"kzI411mdJm/trbDD2qLywikojotJdzMe/hB+FJfeR3g"}',
            "_fbp": "fb.1.1764703877532.613688672911968169",
            "_ga_47RNFYWRSH": "GS2.1.s1764703877$o1$g1$t1764705250$j60$l0$h0",
            "_ga_L47NC0LK6B": "GS2.1.s1764703877$o1$g1$t1764705250$j60$l0$h0",
            "_cc_id": "75f94bbc4fb7420f2cf0732add121ee8",
            "panoramaId_expiry": "1765227822427",
            "panoramaId": "f24d1c8d12a2bd311529d14ad201a9fb927a8664dc2840c748397f30ee346a7d",
            "_li_dcdm_c": ".sofascore.com",
            "__gads": "ID=3f9ce32c3b9d171f:T=1764754455:RT=1765191429:S=ALNI_MYr2Vv6qo93NrYYfMx5dQya31ik5A",
            "__gpi": "UID=000013174b6ee948:T=1764754455:RT=1765191429:S=ALNI_MYXhI_jzeqSzp7nYT5SEb5uRsUqNg",
            "__eoi": "ID=ffb5200279ec53dd:T=1764754455:RT=1765191429:S=AA-Afja_UFR3d-IDkbT7lQk2PjiU",
            "cto_bundle": "8ERIz19UVnZOd01BR2xTODglMkZJJTJCY1dCNDBsUXR3ak4wTjVKTER1WnFuYmg2WSUyRlVScXZvQ2VOc3d5Ym42Uzk5c1VMcVZGRERONCUyQjJySFRVVzJLckc4TyUyQnVRTGdhVEdiempxWXQwJTJGaERuZjkxMSUyQkVDWkdEM1JOT1hyZWFmbHlGN3dSU1hrRkZBYW5zMThXaVZIVWElMkJCWm1xYSUyQnclM0QlM0Q",
            "cto_bidid": "y9lkfF9SbHdYb3R5Tk1HS2tRR1VlRU53Y2xJTXZWZFliMXVBSmNEMzlTREQyJTJGdFdSJTJGeGFmSDdzWlpqYXpNRENVcDl6Y3REelBoQjJkZzhMNmV6dFA5bndDTTlMQzFZeCUyRjR3TEhzYzNQJTJCNk5IbjRVJTNE",
            "FCCDCF": "%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22b315cfb6-6a31-49d0-adc0-37ac33640eb4%5C%22%2C%5B1764702709%2C46000000%5D%5D%22%5D%5D%5D",
            "FCNEC": "%5B%5B%22AKsRol8MsFQcadw0VDOr3KtAkXnyahayOlyhq3J1D3P82XYz0GSuUIEQqcQEE1ja_xb11dIIcwsEeuZUewUywz5h3dJ9TrVhRoYoXVkK8GYxpNr_ZmAgB46lnoBg7I43rY9BRE9YlaJNhiwoQW2Tzu44HNAJwD_YNA%3D%3D%22%5D%5D",
            "_ga_HNQ9P9MGZR": "GS2.1.s1765191430$o21$g1$t1765193157$j50$l0$h0",
        }

        headers = {
            "accept": "*/*",
            "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "baggage": "sentry-environment=production,sentry-release=0nhNlgUdv5nxc_UsEpdfD,sentry-public_key=d693747a6bb242d9bb9cf7069fb57988,sentry-trace_id=dbc7b2174ca14e084df635b543355a84",
            "cache-control": "max-age=0",
            "priority": "u=1, i",
            "referer": "https://www.sofascore.com/pt/",
            "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sentry-trace": "dbc7b2174ca14e084df635b543355a84-870d2e1df1444643",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
            "x-captcha": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3NjUyNzc4MzJ9.kgrvz9xvs1l4rc1FRjbYP65BzCvMh_dea-Yi51yKdOg",
            "x-requested-with": "f690cc",
            # 'cookie': '_gcl_au=1.1.1410777148.1764702710; _ga=GA1.1.838785703.1764702710; g_state={"i_l":0,"i_ll":1764703841911,"i_b":"kzI411mdJm/trbDD2qLywikojotJdzMe/hB+FJfeR3g"}; _fbp=fb.1.1764703877532.613688672911968169; _ga_47RNFYWRSH=GS2.1.s1764703877$o1$g1$t1764705250$j60$l0$h0; _ga_L47NC0LK6B=GS2.1.s1764703877$o1$g1$t1764705250$j60$l0$h0; _cc_id=75f94bbc4fb7420f2cf0732add121ee8; panoramaId_expiry=1765227822427; panoramaId=f24d1c8d12a2bd311529d14ad201a9fb927a8664dc2840c748397f30ee346a7d; _li_dcdm_c=.sofascore.com; __gads=ID=3f9ce32c3b9d171f:T=1764754455:RT=1765191429:S=ALNI_MYr2Vv6qo93NrYYfMx5dQya31ik5A; __gpi=UID=000013174b6ee948:T=1764754455:RT=1765191429:S=ALNI_MYXhI_jzeqSzp7nYT5SEb5uRsUqNg; __eoi=ID=ffb5200279ec53dd:T=1764754455:RT=1765191429:S=AA-Afja_UFR3d-IDkbT7lQk2PjiU; cto_bundle=8ERIz19UVnZOd01BR2xTODglMkZJJTJCY1dCNDBsUXR3ak4wTjVKTER1WnFuYmg2WSUyRlVScXZvQ2VOc3d5Ym42Uzk5c1VMcVZGRERONCUyQjJySFRVVzJLckc4TyUyQnVRTGdhVEdiempxWXQwJTJGaERuZjkxMSUyQkVDWkdEM1JOT1hyZWFmbHlGN3dSU1hrRkZBYW5zMThXaVZIVWElMkJCWm1xYSUyQnclM0QlM0Q; cto_bidid=y9lkfF9SbHdYb3R5Tk1HS2tRR1VlRU53Y2xJTXZWZFliMXVBSmNEMzlTREQyJTJGdFdSJTJGeGFmSDdzWlpqYXpNRENVcDl6Y3REelBoQjJkZzhMNmV6dFA5bndDTTlMQzFZeCUyRjR3TEhzYzNQJTJCNk5IbjRVJTNE; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22b315cfb6-6a31-49d0-adc0-37ac33640eb4%5C%22%2C%5B1764702709%2C46000000%5D%5D%22%5D%5D%5D; FCNEC=%5B%5B%22AKsRol8MsFQcadw0VDOr3KtAkXnyahayOlyhq3J1D3P82XYz0GSuUIEQqcQEE1ja_xb11dIIcwsEeuZUewUywz5h3dJ9TrVhRoYoXVkK8GYxpNr_ZmAgB46lnoBg7I43rY9BRE9YlaJNhiwoQW2Tzu44HNAJwD_YNA%3D%3D%22%5D%5D; _ga_HNQ9P9MGZR=GS2.1.s1765191430$o21$g1$t1765193157$j50$l0$h0',
        }

        def get_json(url):
            try:
                r = requests.get(url, headers=headers, cookies=cookies, timeout=10)
                r.raise_for_status()
                return r.json()
            except:
                return {}

        def prob_from_ratio(ratio):
            """
            Converte 0.8 → 80%
            Converte 3.0 → 300% (mas limitada a 100%)
            """
            if ratio is None:
                return 50
            return min(int(ratio * 100), 100)

        def generate_auto_prediction_nba(event, stats, streaks):
            home = event["homeTeam"]["name"]
            away = event["awayTeam"]["name"]

            # -----------------------------
            # MÉTRICAS BÁSICAS
            # -----------------------------
            def get_stat(key):
                for g in stats.get("groups", []):
                    for it in g.get("statisticsItems", []):
                        if it.get("key") == key:
                            return float(it.get("homeValue", 0)), float(
                                it.get("awayValue", 0)
                            )
                return 0.0, 0.0

            pts_h, pts_a = get_stat("points")
            pace_h, pace_a = get_stat("pace")
            off_h, off_a = get_stat("offensiveRating")
            def_h, def_a = get_stat("defensiveRating")

            avg_points = pts_h + pts_a
            avg_pace = (pace_h + pace_a) / 2

            # -----------------------------
            # TENDÊNCIAS (streaks)
            # -----------------------------
            home_hot = any(
                s["team"] == "home" and s["hot"] for s in streaks.get("general", [])
            )
            away_hot = any(
                s["team"] == "away" and s["hot"] for s in streaks.get("general", [])
            )

            # -----------------------------
            # OVER / UNDER
            # -----------------------------
            over_score = 50
            if avg_points >= 220:
                over_score = 80
            elif avg_points >= 214:
                over_score = 70
            elif avg_points <= 205:
                over_score = 35

            # pace influencia muito
            if avg_pace >= 102:
                over_score += 10
            elif avg_pace <= 96:
                over_score -= 10

            over_score = max(5, min(95, over_score))
            under_score = 100 - over_score

            # -----------------------------
            # FAVORITO / SPREAD
            # -----------------------------
            home_power = off_h - def_h + (3 if home_hot else 0)
            away_power = off_a - def_a + (3 if away_hot else 0)

            diff = home_power - away_power

            if diff >= 6:
                favorito = home
                spread = -5.5
                prob_home = 75
            elif diff >= 3:
                favorito = home
                spread = -3.5
                prob_home = 65
            elif diff <= -6:
                favorito = away
                spread = +5.5
                prob_home = 25
            else:
                favorito = "Equilibrado"
                spread = 0
                prob_home = 50

            prob_away = 100 - prob_home

            # -----------------------------
            # MERCADOS SUGERIDOS
            # -----------------------------
            mercados = []

            if over_score >= 65:
                mercados.append("Over 214.5")
            elif under_score >= 65:
                mercados.append("Under 214.5")

            if favorito == home:
                mercados.append("Vitória mandante")
                mercados.append("Spread -5.5")
            elif favorito == away:
                mercados.append("Vitória visitante")
                mercados.append("Spread +5.5")

            return {
                "probabilidades": {
                    "over": over_score,
                    "under": under_score,
                    "home": prob_home,
                    "away": prob_away,
                },
                "leitura_geral": {
                    "total_pontos": (
                        "Tendência de jogo rápido e pontuado"
                        if over_score > under_score
                        else "Jogo mais cadenciado"
                    ),
                    "favorito": favorito,
                },
                "mercados_sugeridos_modelo": mercados,
                "extra_contexto": {
                    "avg_points": avg_points,
                    "pace": avg_pace,
                    "spread_estimado": spread,
                },
            }

        # =====================================================
        #  EXTRAI ESTATÍSTICA DA ROTA /statistics
        # =====================================================
        def extract_stat(stats, key):
            for period in stats.get("statistics", []):
                if period.get("period") != "ALL":
                    continue
                for group in period.get("groups", []):
                    for item in group.get("statisticsItems", []):
                        if item.get("key") == key:
                            return float(item.get("homeValue", 0)), float(
                                item.get("awayValue", 0)
                            )
            return 0.0, 0.0

        # =====================================================
        #  INSIGHTS BÁSICOS DO JOGO
        # =====================================================
        def generate_insights_basketball(event, stats):
            home = event["homeTeam"]["name"]
            away = event["awayTeam"]["name"]

            hs = event.get("homeScore", {}) or {}
            as_ = event.get("awayScore", {}) or {}

            # placar atual
            score_home = hs.get("current", 0) or 0
            score_away = as_.get("current", 0) or 0
            total_points = score_home + score_away

            # pontuação por períodos (quarters)
            q1_home = hs.get("period1", 0) or 0
            q1_away = as_.get("period1", 0) or 0
            q2_home = hs.get("period2", 0) or 0
            q2_away = as_.get("period2", 0) or 0

            insights = []

            # -----------------------------
            # DOMÍNIO
            # -----------------------------
            if score_home > score_away + 10:
                insights.append(f"{home} domina a partida com boa vantagem.")
            elif score_away > score_home + 10:
                insights.append(f"{away} domina a partida com boa vantagem.")
            else:
                insights.append("Partida equilibrada até o momento.")

            # -----------------------------
            # RITMO
            # -----------------------------
            first_half = q1_home + q1_away + q2_home + q2_away

            if first_half >= 110:
                insights.append("Jogo muito rápido e ofensivo.")
            elif first_half <= 90:
                insights.append("Jogo mais truncado e cadenciado.")
            else:
                insights.append("Ritmo moderado de jogo.")

            # -----------------------------
            # LEITURA DE PONTOS
            # -----------------------------
            if total_points >= 220:
                insights.append("Partida com tendência forte de Over em pontos.")
            elif total_points <= 205:
                insights.append("Partida com tendência de Under em pontos.")

            return {
                "eventId": event["id"],
                "slug": event.get("slug"),
                "tournament": event.get("tournament", {}).get("name"),
                "homeTeam": home,
                "awayTeam": away,
                "placar": f"{score_home}-{score_away}",
                "stats": {
                    "points": {"home": score_home, "away": score_away},
                    "first_half": first_half,
                    "total": total_points,
                },
                "insights": insights,
            }

        # =====================================================
        #  INSIGHTS PROFISSIONAIS
        # =====================================================
        def generate_deep_insights(stats):
            if not stats or "statistics" not in stats or not stats["statistics"]:
                return []

            ALL = next(
                (p for p in stats["statistics"] if p.get("period") == "ALL"), None
            )
            if not ALL:
                return []

            def get(key, default=(0, 0)):
                for g in ALL.get("groups", []):
                    for it in g.get("statisticsItems", []):
                        if it.get("key") == key:
                            return float(it.get("homeValue", 0)), float(
                                it.get("awayValue", 0)
                            )
                return default

            insights = []

            # dados
            xg_h, xg_a = get("expectedGoals")
            shots_h, shots_a = get("totalShotsOnGoal")
            sot_h, sot_a = get("shotsOnGoal")
            poss_h, poss_a = get("ballPossession")
            bc_h, bc_a = get("bigChanceCreated")
            bcm_h, bcm_a = get("bigChanceMissed")
            box_h, box_a = get("touchesInOppBox")
            third_h, third_a = get("finalThirdEntries")
            duel_h, duel_a = get("duelWonPercent")
            drib_h, drib_a = get("dribblesPercentage")
            prevent_h, prevent_a = get("goalsPrevented")

            # domínio xG
            if xg_h > xg_a * 1.6:
                insights.append("O mandante dominou amplamente pelo xG.")
            elif xg_a > xg_h * 1.6:
                insights.append("O visitante criou muito mais perigo real (xG).")

            # precisão
            if sot_h < shots_h * 0.25:
                insights.append("Mandante finalizou muito mal (baixa precisão).")
            if sot_a < shots_a * 0.25:
                insights.append("Visitante finalizou mal (baixa precisão).")

            # big chances
            if (bc_h + bc_a) >= 5:
                insights.append("Partida aberta — muitas chances claras.")

            if bcm_h > 0:
                insights.append("Mandante desperdiçou big chances.")
            if bcm_a > 0:
                insights.append("Visitante desperdiçou big chances.")

            # terço final
            if third_h > third_a * 1.5:
                insights.append("Mandante dominou o terço final.")
            elif third_a > third_h * 1.5:
                insights.append("Visitante dominou o terço final.")

            # duelos
            if duel_h > 58:
                insights.append("Mandante venceu a maioria dos duelos.")
            if duel_a > 58:
                insights.append("Visitante venceu mais duelos.")

            return insights

        # =====================================================
        #  TEAM STREAKS / HOT
        # =====================================================
        def analyze_streaks(streaks):

            def parse_value(v):
                if isinstance(v, (int, float)):
                    return float(v)
                if "/" in v:
                    a, b = v.split("/")
                    try:
                        return float(a) / float(b)
                    except:
                        return None
                try:
                    return float(v)
                except:
                    return None

            analyzed = {"general": [], "head2head": []}

            def classify(ratio):
                if ratio is None:
                    return "unknown"
                if ratio >= 0.75:
                    return "strong"
                if ratio >= 0.60:
                    return "medium"
                return "weak"

            def insight_text(name, ratio, team):
                pct = int(ratio * 100)
                if ratio >= 0.75:
                    return f"{team.capitalize()} tem forte tendência: {name} ({pct}%)."
                elif ratio >= 0.60:
                    return (
                        f"{team.capitalize()} tem tendência moderada: {name} ({pct}%)."
                    )
                return f"Tendência fraca para {name} ({pct}%)."

            for group in ["general", "head2head"]:
                for item in streaks.get(group, []):
                    r = parse_value(item.get("value", "0"))

                    analyzed[group].append(
                        {
                            "name": item.get("name"),
                            "team": item.get("team"),
                            "value": item.get("value"),
                            "ratio": r,
                            "hot": r is not None and r >= 0.60,
                            "intensity": classify(r),
                            "insight": (
                                insight_text(item.get("name"), r, item.get("team"))
                                if r
                                else None
                            ),
                        }
                    )

            return analyzed

        # =====================================================
        #  STANDINGS + FAVORITO
        # =====================================================
        def get_standings(event):
            """Pega standings da temporada e descobre quem é o favorito."""

            tournament_id = (
                event.get("tournament", {}).get("uniqueTournament", {}).get("id")
            )
            season_id = event.get("season", {}).get("id")

            if not tournament_id or not season_id:
                return None, None, None

            url = (
                f"{BASE}/tournament/{tournament_id}/season/{season_id}/standings/total"
            )
            standings_json = get_json(url)

            rows = standings_json.get("standings", [{}])[0].get("rows", [])

            # montar dict { team_id: posição }
            table = {row["team"]["id"]: row["position"] for row in rows}

            home_id = event["homeTeam"]["id"]
            away_id = event["awayTeam"]["id"]

            pos_home = table.get(home_id)
            pos_away = table.get(away_id)

            favorito = None
            if pos_home and pos_away:
                favorito = (
                    event["homeTeam"]["name"]
                    if pos_home < pos_away
                    else event["awayTeam"]["name"]
                )

            return pos_home, pos_away, favorito

        def get_team_standing(standings, team_id):
            try:
                rows = standings["standings"][0]["rows"]
                for row in rows:
                    if row["team"]["id"] == team_id:
                        return {
                            "position": row["position"],
                            "points": row["points"],
                            "wins": row["wins"],
                            "draws": row["draws"],
                            "losses": row["losses"],
                            "goals_for": row["scoresFor"],
                            "goals_against": row["scoresAgainst"],
                            "goal_diff": row["scoreDiffFormatted"],
                            "is_top": row["position"] <= 4,
                            "is_relegation": row.get("promotion", {}).get("text")
                            == "Relegation",
                        }

                return None
            except:
                return None

        def table_favorite(home_stand, away_stand):
            if not home_stand or not away_stand:
                return None

            # diferença de pontos
            diff = home_stand["points"] - away_stand["points"]

            if abs(diff) <= 2:
                return "Equilibrado"

            if diff > 2:
                return f"Favorito: Mandante (+{diff} pts)"
            else:
                return f"Favorito: Visitante (+{-diff} pts)"

        def rank_best_games(results):
            """
            Recebe o JSON final (lista de jogos)
            e retorna os 3 melhores jogos para análise.
            """

            ranked = []

            for r in results:
                prev = r.get("previsao_automatica", {})
                probs = prev.get("probabilidades", {})

                streaks = r.get("streaks", {})
                general = streaks.get("general", [])
                h2h = streaks.get("head2head", [])

                # Conta HOT STRONG (tendências muito fortes)
                strong_count = sum(
                    1 for it in general + h2h if it["intensity"] == "strong"
                )

                # Define "clareza" da leitura
                prob_home = probs.get("home", 50)
                prob_away = probs.get("away", 50)
                prob_over = probs.get("over", 50)
                prob_under = probs.get("under", 50)

                # quanto mais extremo, maior o score
                extremidade = max(prob_home, prob_away, prob_over, prob_under) - 50

                # equilíbrio técnico também é informativo
                standings = r.get("standings", {})
                home_st = standings.get("home", {})
                away_st = standings.get("away", {})

                diff_pts = abs(home_st.get("points", 0) - away_st.get("points", 0))

                if diff_pts <= 2:
                    equilibrio_bonus = 20  # jogos equilibrados são bons
                else:
                    equilibrio_bonus = 0

                # score final
                score = strong_count * 12 + extremidade * 2 + equilibrio_bonus

                ranked.append(
                    {
                        "score": score,
                        "eventId": r["eventId"],
                        "slug": r["slug"],
                        "home": r["homeTeam"],
                        "away": r["awayTeam"],
                        "tournament": r["tournament"],
                        "insights": r["insights"],
                        "previsao": r["previsao_automatica"],
                        "streaks": r["streaks"],
                    }
                )

            # ordena
            ranked = sorted(ranked, key=lambda x: x["score"], reverse=True)

            # pega top 3
            return ranked[:3]

        # =====================================================
        #  FLUXO PRINCIPAL
        # =====================================================
        year, month = 2025, 10
        num_days = calendar.monthrange(year, month)[1]
        # date = [
        #     f"{year}-{month:02d}-{day:02d}"
        #     for day in range(1, num_days + 1)
        # ]

        import time
        from datetime import date, timedelta

        def get_month_dates(year, month, start_day=1):
            start = date(year, month, start_day)

            if month == 12:
                end = date(year + 1, 1, 1)
            else:
                end = date(year, month + 1, 1)

            current = start
            dates = []

            while current < end:
                dates.append(current.isoformat())
                current += timedelta(days=1)

            return dates

        def human_sleep(min_s=8, max_s=18):
            tempo = random.uniform(min_s, max_s)
            tempo = round(tempo, 1)

            print(f"⏳ Aguardando {tempo}s")

            restante = tempo
            while restante > 0:
                print(f"   ⌛ {restante:.1f}s restantes", end="\r")
                time.sleep(0.5)
                restante -= 0.5

            print("   ✅ continuando...        ")

        # 🔧 CONFIGURA AQUI
        YEAR = 2025
        MONTH = 10  # dezembro

        date = get_month_dates(YEAR, MONTH, start_day=1)
        #
        date = ["2026-01-01"]

        for c in date:
            url = f"{BASE}/sport/basketball/scheduled-events/{c}"
            data = get_json(url)

            allowed_leagues = {
                "nba",
            }

            allowed_countries = {
                "usa",
            }
            try:
                events = [
                    e
                    for e in data["events"]
                    if e["tournament"]["slug"] in allowed_leagues
                    and e["tournament"]["category"]["slug"] in allowed_countries
                ]
                final = []
                flag = False
                # if len(events) > 10:
                #     flag = True

                print(flag, len(events))

                for event in events:
                    stats_url = f"{BASE}/event/{event['id']}/statistics"
                    stats = get_json(stats_url)
                    if flag:
                        human_sleep(5, 10)

                    # standings
                    tournament_id = event["tournament"]["id"]
                    season_id = event["season"]["id"]

                    standings_url = f"{BASE}/tournament/{tournament_id}/season/{season_id}/standings/total"
                    standings = get_json(standings_url)
                    if flag:
                        human_sleep(10, 20)

                    home_id = event["homeTeam"]["id"]
                    away_id = event["awayTeam"]["id"]

                    home_standing = get_team_standing(standings, home_id)
                    away_standing = get_team_standing(standings, away_id)

                    result = generate_insights_basketball(event, stats)
                    result["insights"].extend(generate_deep_insights(stats))

                    # streaks
                    streaks_url = f"{BASE}/event/{event['id']}/team-streaks"
                    streaks_raw = get_json(streaks_url)
                    streaks_analysis = analyze_streaks(streaks_raw)
                    result["streaks"] = streaks_analysis

                    # standings integrados
                    result["standings"] = {
                        "home": home_standing,
                        "away": away_standing,
                        "favorito_tabela": table_favorite(home_standing, away_standing),
                    }
                    prediction = generate_auto_prediction_nba(
                        event, stats, streaks_analysis
                    )

                    result["previsao_automatica"] = prediction

                    # limpa apostas antigas do evento
                    PossibleBet.objects.filter(event_id=event["id"]).delete()

                    markets = prediction.get("mercados_sugeridos_modelo", [])
                    probs = prediction.get("probabilidades", {})

                    best_prob = max(probs.values()) if probs else 50

                    for market in markets:
                        PossibleBet.objects.create(
                            event_id=event["id"],
                            market=market,
                            probability=best_prob,
                            description="Mercado sugerido pelo modelo NBA",
                        )

                    final.append(result)

                    save_sofascore_data_nba(
                        event,
                        result["stats"],  # stats
                        result["insights"],
                        result["streaks"],
                        result["standings"],
                        result["previsao_automatica"],
                        json.dumps(event, ensure_ascii=False),  # ✔ raw_event_json
                        json.dumps(stats, ensure_ascii=False),
                    )
            except Exception as e:
                print(f"erro: {e} {e.__traceback__.tb_lineno}")
                pass
