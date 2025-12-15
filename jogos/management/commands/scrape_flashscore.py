import calendar
import json
import time

import requests
from django.core.management.base import BaseCommand

from bet.models import PossibleBet
from jogos.utils import save_sofascore_data

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

        def generate_auto_prediction(event, stats, streaks, standings):
            """
            Gera previsão automática usando:
            - streaks (tendências históricas)
            - standings (tabela)
            - stats (xG, finalizações, posse)
            - momento do jogo (minuto)
            """

            home = event["homeTeam"]["name"]
            away = event["awayTeam"]["name"]

            # -----------------------------
            # BASES
            # -----------------------------
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

            # -----------------------------
            # MINUTO / FASE DO JOGO
            # -----------------------------
            start_ts = event.get("startTimestamp")
            current_ts = event.get("time", {}).get("timestamp")

            minute = None
            if start_ts and current_ts:
                # segundo → minuto
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

            # -----------------------------
            # LISTAS DE SINAIS
            # -----------------------------
            under_signals = []
            over_signals = []
            home_signals = []
            away_signals = []

            def is_goal_streak(name: str) -> bool:
                name = name.lower()
                return ("goal" in name) or ("gols" in name) or ("goals" in name)

            # -----------------------------
            # STREAKS (HISTÓRICO)
            # -----------------------------
            for item in streaks_gen + streaks_h2h:
                ratio = item.get("ratio")
                if ratio is None:
                    continue

                name = (item.get("name") or "").lower()
                team = item.get("team")

                # Over/Under apenas quando claramente relacionado a GOLS
                if is_goal_streak(name):
                    if "more than" in name or "mais de" in name:
                        over_signals.append(prob_from_ratio(ratio))
                    if "less than" in name or "menos de" in name:
                        under_signals.append(prob_from_ratio(ratio))

                # Resultado (vitórias/derrotas/etc) pesa pro favorito
                if team == "home" and ratio >= 0.60:
                    home_signals.append(prob_from_ratio(ratio))
                if team == "away" and ratio >= 0.60:
                    away_signals.append(prob_from_ratio(ratio))

            # -----------------------------
            # STANDINGS (TABELA)
            # -----------------------------
            pts_home = home_st.get("points", 0) or 0
            pts_away = away_st.get("points", 0) or 0
            diff_pts = pts_home - pts_away

            if diff_pts > 2:
                home_signals.append(65)
            elif diff_pts < -2:
                away_signals.append(65)

            # -----------------------------
            # STATS AO VIVO → GOLS
            # -----------------------------
            # xG total
            if total_xg >= 2.0:
                over_signals.append(80)
            elif total_xg >= 1.2:
                over_signals.append(70)
            elif total_xg >= 0.8:
                over_signals.append(60)
            elif total_xg <= 0.4 and phase in ("mid", "late"):
                under_signals.append(70)

            # volume de finalizações
            if total_shots >= 18:
                over_signals.append(70)
            elif total_shots >= 10:
                over_signals.append(60)
            elif total_shots <= 4 and phase in ("mid", "late"):
                under_signals.append(65)

            # chutes no alvo
            if total_sot >= 7:
                over_signals.append(75)
            elif total_sot >= 4:
                over_signals.append(65)
            elif total_sot <= 1 and phase in ("mid", "late"):
                under_signals.append(65)

            # fase do jogo: fim de jogo 0x0 puxa mais pro under
            hs = event.get("homeScore", {}) or {}
            as_ = event.get("awayScore", {}) or {}
            score_h = hs.get("current", 0) or 0
            score_a = as_.get("current", 0) or 0
            total_goals = (score_h or 0) + (score_a or 0)

            if phase == "late" and total_goals == 0 and total_xg < 1.0:
                under_signals.append(80)

            # -----------------------------
            # STATS AO VIVO → FAVORITO
            # -----------------------------
            # xG dominando
            if xg_h > xg_a * 1.5 and xg_h > 0.4:
                home_signals.append(70)
            elif xg_a > xg_h * 1.5 and xg_a > 0.4:
                away_signals.append(70)

            # chutes no alvo
            if sot_h >= 3 and sot_h >= sot_a + 2:
                home_signals.append(60)
            if sot_a >= 3 and sot_a >= sot_h + 2:
                away_signals.append(60)

            # posse pode contribuir levemente
            if poss_h >= 60:
                home_signals.append(55)
            elif poss_a >= 60:
                away_signals.append(55)

            # -----------------------------
            # PROBABILIDADES FINAIS
            # -----------------------------
            def avg_or_50(values):
                return int(sum(values) / len(values)) if values else 50

            prob_over = avg_or_50(over_signals)
            prob_under = avg_or_50(under_signals)
            prob_home = avg_or_50(home_signals)
            prob_away = avg_or_50(away_signals)

            # clamp leve
            prob_over = max(5, min(95, prob_over))
            prob_under = max(5, min(95, prob_under))
            prob_home = max(5, min(95, prob_home))
            prob_away = max(5, min(95, prob_away))

            # -----------------------------
            # LEITURA DE GOLS
            # -----------------------------
            diff_gols = prob_over - prob_under

            if diff_gols >= 15:
                leitura_gols = "Jogo com forte tendência de muitos gols."
                mercado_gols = "Over 2.5"
            elif diff_gols >= 8:
                leitura_gols = "Tendência moderada para muitos gols."
                mercado_gols = "Over 1.5"
            elif diff_gols <= -15:
                leitura_gols = "Jogo com forte tendência de poucos gols."
                mercado_gols = "Under 2.5"
            elif diff_gols <= -8:
                leitura_gols = "Tendência moderada de poucos gols."
                mercado_gols = "Under 3.5"
            else:
                leitura_gols = "Cenário equilibrado — sem leitura clara para gols."
                mercado_gols = "Nenhum mercado claro"

            # -----------------------------
            # FAVORITO (tabela + modelo)
            # -----------------------------
            diff_prob = prob_home - prob_away

            score_home = diff_prob * 0.7 + diff_pts * 0.3

            if score_home >= 12:
                leitura_fav = f"{home} aparece como favorito pelo momento."
            elif score_home <= -12:
                leitura_fav = f"{away} aparece como favorito pelo momento."
            else:
                leitura_fav = "Partida equilibrada — sem favorito claro."

            # -----------------------------
            # MERCADO SEGURO
            # -----------------------------
            if mercado_gols.startswith("Under"):
                mercado_seguro = "Under 3.5" if "2.5" in mercado_gols else mercado_gols

            elif mercado_gols.startswith("Over"):
                mercado_seguro = "Over 1.5" if "2.5" in mercado_gols else mercado_gols

            else:
                # 2) Sem leitura clara → usa score_home (bem mais confiável)
                if abs(score_home) < 10:
                    mercado_seguro = "Nenhum mercado seguro"
                else:
                    mercado_seguro = (
                        "Dupla chance mandante"
                        if score_home > 0
                        else "Dupla chance visitante"
                    )

            return {
                "probabilidades": {
                    "under": prob_under,
                    "over": prob_over,
                    "home": prob_home,
                    "away": prob_away,
                },
                "leitura_geral": {
                    "gols": leitura_gols,
                    "favorito": leitura_fav,
                },
                "mercados_sugeridos_modelo": {
                    "principal": mercado_seguro,
                    "gols": mercado_gols,
                },
                "extra_contexto": {
                    "minute": minute,
                    "phase": phase,
                    "xg_home": xg_h,
                    "xg_away": xg_a,
                    "total_xg": total_xg,
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
        def generate_insights(event, stats):
            home = event["homeTeam"]["name"]
            away = event["awayTeam"]["name"]

            hs = event.get("homeScore", {})
            as_ = event.get("awayScore", {})

            ht_home = hs.get("period1", 0)
            ht_away = as_.get("period1", 0)
            ft_home = hs.get("current", 0)
            ft_away = as_.get("current", 0)

            # estatísticas
            xg_home, xg_away = extract_stat(stats, "expectedGoals")
            shots_home, shots_away = extract_stat(stats, "totalShots")
            shots_on_home, shots_on_away = extract_stat(stats, "shotsOnGoal")
            possession_home, possession_away = extract_stat(stats, "ballPossession")

            insights = []

            # domínio xG
            if xg_home > xg_away * 1.4:
                insights.append(f"{home} dominou claramente o jogo.")
            elif xg_away > xg_home * 1.4:
                insights.append(f"{away} dominou claramente o jogo.")
            else:
                insights.append("Jogo equilibrado no geral.")

            # ritmo
            if (ft_home + ft_away) > (ht_home + ht_away):
                insights.append("O jogo acelerou no 2º tempo.")
            else:
                insights.append("O ritmo caiu no 2º tempo.")

            return {
                "eventId": event["id"],
                "slug": event["slug"],
                "tournament": event.get("tournament", {}).get("name"),
                "homeTeam": home,
                "awayTeam": away,
                "placar": f"{ft_home}-{ft_away}",
                "ht": f"{ht_home}-{ht_away}",
                "stats": {
                    "xg": {"home": xg_home, "away": xg_away},
                    "shots": {"home": shots_home, "away": shots_away},
                    "shots_on": {"home": shots_on_home, "away": shots_on_away},
                    "posse": {"home": possession_home, "away": possession_away},
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
        date = ["2025-12-13"]

        for c in date:
            url = f"{BASE}/sport/football/scheduled-events/{c}"
            data = get_json(url)
            time.sleep(4.5)

            allowed_leagues = {"coppa-italia"}
            allowed_countries = {"italy"}

            allowed_leagues = {
                "premier-league",
                "laliga",
                "serie-a",
                "conmebol-libertadores",
                "brasileirao-serie-a",
                "ligue-1",
                "bundesliga",
                "trendyol-super-lig",
                "coppa-italia",
                "copa-del-rey",
                "uefa-champions-league",
                "copa-do-brasil",
                "uefa-europa-league",
                "uefa-conference-league",
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
                "italy",
                "spain",
                "europe",
                "brazil",
                "europe",
                "europe",
            }
            try:
                events = [
                    e
                    for e in data["events"]
                    if e["tournament"]["slug"] in allowed_leagues
                    and e["tournament"]["category"]["slug"] in allowed_countries
                ]
                final = []

                for event in events:
                    stats_url = f"{BASE}/event/{event['id']}/statistics"
                    stats = get_json(stats_url)
                    # time.sleep(4.5)

                    # standings
                    tournament_id = event["tournament"]["id"]
                    season_id = event["season"]["id"]

                    standings_url = f"{BASE}/tournament/{tournament_id}/season/{season_id}/standings/total"
                    # time.sleep(4.5)
                    standings = get_json(standings_url)

                    home_id = event["homeTeam"]["id"]
                    away_id = event["awayTeam"]["id"]

                    home_standing = get_team_standing(standings, home_id)
                    away_standing = get_team_standing(standings, away_id)

                    result = generate_insights(event, stats)
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
                    prediction = generate_auto_prediction(
                        event, stats, streaks_analysis, result["standings"]
                    )

                    result["previsao_automatica"] = prediction

                    # limpa apostas antigas do evento
                    PossibleBet.objects.filter(event_id=event["id"]).delete()

                    # MERCADOS sugeridos
                    markets = prediction.get("mercados_sugeridos_modelo", {})

                    # PROBABILIDADES do modelo
                    probs = prediction.get("probabilidades", {})

                    # 1) Mercado principal
                    if markets.get("principal"):
                        PossibleBet.objects.create(
                            event_id=event["id"],
                            market=markets["principal"],
                            probability=max(probs.values()),  # melhor probabilidade
                            description="Mercado principal sugerido pelo modelo",
                        )

                    # 2) Mercado de gols
                    if markets.get("gols"):
                        PossibleBet.objects.create(
                            event_id=event["id"],
                            market=markets["gols"],
                            probability=probs.get("over") or 50,
                            description="Leitura de gols com base no comportamento do jogo",
                        )

                    final.append(result)

                    save_sofascore_data(
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
                print(f"erro: {e}")
                pass
