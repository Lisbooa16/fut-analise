import json
import re
import time
from datetime import datetime, timedelta

import requests
from django.db.models import Avg, F
from django.utils import timezone

from bet.models import PossibleBet
from jogos.models import League, LiveSnapshot, Match, MatchStats, Season, Team
from jogos.utils import save_sofascore_data

BASE = "https://www.sofascore.com/api/v1"
headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
allowed_leagues = {
    "premier-league",
    "laliga",
    "serie-a",
    "conmebol-libertadore",
    "brasileirao-serie-a",
    "ligue-1",
    "bundesliga",
    "trendyol-super-lig",
    "primera-lpf-clausura-playoffs",
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
    "argentina",
}


class SofaScore:
    def __init__(self, date: list = None):
        self.date = date
        self.session = requests.Session()
        self._captcha_token = None
        self._captcha_expire_ts = 0

    def _extract_js_files(self, html):
        """
        Extrai qualquer script JS da página, considerando vários formatos:
        - <script src="...">
        - <script type="module" src="...">
        - <script async src="...">
        - caminhos _next/static/...js
        """

        patterns = [
            r'src="([^"]+\.js)"',
            r"src='([^']+\.js)'",
            r'src="([^"]+/_next/[^"]+\.js)"',
            r"(/_next/static[^\"']+\.js)",
            r"(/build[^\"']+\.js)",
        ]

        js_files = set()

        for p in patterns:
            matches = re.findall(p, html)
            for m in matches:
                if m.startswith("//"):
                    m = "https:" + m
                elif m.startswith("/"):
                    m = "https://www.sofascore.com" + m
                js_files.add(m)

        return list(js_files)

    def _fetch_new_captcha(self):
        """
        Busca token x-captcha da homepage, igual o navegador faz.
        O token aparece embutido no HTML/JS.
        """
        url = "https://www.sofascore.com"
        r = self.session.get(url, headers={"User-Agent": "Mozilla/5.0"})
        html = r.text
        js_files = self._extract_js_files(html)
        if not js_files:
            raise Exception(
                "Nenhum arquivo JS encontrado na homepage (nova estrutura)."
            )

            # 2) tentar extrair JWT de cada script
        for js_url in js_files:
            try:
                js = self.session.get(
                    js_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5
                ).text
                token_match = re.search(
                    r"(eyJ[^\"\'\s]+?\.[^\"\'\s]+?\.[^\"\'\s]+)", js
                )

                if token_match:
                    token = token_match.group(1)
                    print(f"✔️ Token encontrado: {token[:30]}...")

                    self._captcha_token = token
                    self._captcha_expire_ts = time.time() + 20
                    return token
            except:
                pass

        # Regex que encontra qualquer JWT começando com eyJ
        match = re.search(r'"(eyJ[^\"]+)"', html)

        if not match:
            raise Exception("Não consegui extrair x-captcha da página.")

        token = match.group(1)

        # Token dura entre 20 e 60 segundos
        self._captcha_token = token
        self._captcha_expire_ts = time.time() + 20
        return token

    def _get_captcha_token(self):
        if not self._captcha_token or time.time() >= self._captcha_expire_ts:
            return self._fetch_new_captcha()
        return self._captcha_token

    @staticmethod
    def generate_deep_insights(stats):
        if not stats or "statistics" not in stats or not stats["statistics"]:
            return []

        ALL = next((p for p in stats["statistics"] if p.get("period") == "ALL"), None)
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

    @staticmethod
    def generate_insights(event, stats, match: Match):
        try:

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

            home = match.home_team.name
            away = match.away_team.name

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
                "eventId": match.external_id,
                "slug": match.slug,
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
        except Exception as e:
            print(e.__traceback__.tb_lineno)

    def get_json(self, url):
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

        try:
            r = requests.get(url, cookies=cookies, headers=headers)
            r.raise_for_status()
            return r.json()
        except:
            return {}

    @staticmethod
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
                return f"{team.capitalize()} tem tendência moderada: {name} ({pct}%)."
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

    @staticmethod
    def calculate_momentum(snap, last):
        # Deltas principais
        dxg = snap.xg_home - last.xg_home
        dshots_on = snap.shots_on_home - last.shots_on_home
        dtouches = snap.touches_box_home - last.touches_box_home
        dthird = snap.final_third_entries_home - last.final_third_entries_home
        dpossession = snap.possession_home - last.possession_home

        # Evitar momentum negativo (não existe "momento negativo", apenas zero)
        dxg = max(dxg, 0)
        dshots_on = max(dshots_on, 0)
        dtouches = max(dtouches, 0)
        dthird = max(dthird, 0)
        dpossession = max(dpossession, 0)

        # Pesos calibrados (padrão profissional)
        momentum = (
            dxg * 120  # xG recente vale MUITO
            + dshots_on * 15  # chute no alvo recente
            + dtouches * 3  # toques na área = pressão
            + dthird * 2  # entradas no terço final
            + dpossession * 0.4  # posse agressiva influência menor
        )

        return float(momentum)

    @staticmethod
    def parse_sofascore_stats(raw):
        """
        Converte o JSON de estatísticas do SofaScore no formato usado pelo LiveSnapshot.
        Usa os dados do período 'ALL'.
        """

        # 1) Lista de períodos
        stats_list = raw.get("statistics", [])

        if not isinstance(stats_list, list):
            raise ValueError(
                "Formato inválido: raw['statistics'] deveria ser uma lista."
            )

        # 2) Pega o período ALL
        period_all = None
        for block in stats_list:
            if block.get("period") == "ALL":
                period_all = block
                break

        if not period_all:
            raise ValueError("Período 'ALL' não encontrado no JSON.")

        groups = period_all.get("groups", [])

        # Helper para pegar estatística pelo key do SofaScore
        def get_stat(key, default=0):
            for group in groups:
                for item in group.get("statisticsItems", []):
                    if item.get("key") == key:
                        try:
                            return float(item.get("homeValue", default)), float(
                                item.get("awayValue", default)
                            )
                        except Exception:
                            return default, default
            return default, default

        # ====== OFENSIVO PRINCIPAL ======
        xg_home, xg_away = get_stat("expectedGoals")
        shots_total_home, shots_total_away = get_stat("totalShotsOnGoal")
        shots_on_home, shots_on_away = get_stat("shotsOnGoal")
        possession_home, possession_away = get_stat("ballPossession")
        corners_home, corners_away = get_stat("cornerKicks")

        # ====== PROFUNDIDADE OFENSIVA ======
        touches_box_home, touches_box_away = get_stat("touchesInOppBox")
        final_third_entries_home, final_third_entries_away = get_stat(
            "finalThirdEntries"
        )
        big_chances_home, big_chances_away = get_stat("bigChanceCreated")
        big_chances_missed_home, big_chances_missed_away = get_stat("bigChanceMissed")
        shots_inside_box_home, shots_inside_box_away = get_stat("totalShotsInsideBox")
        shots_outside_box_home, shots_outside_box_away = get_stat(
            "totalShotsOutsideBox"
        )

        # ====== DEFENSIVO ======
        interceptions_home, interceptions_away = get_stat("interceptionWon")
        clearances_home, clearances_away = get_stat("totalClearance")
        recoveries_home, recoveries_away = get_stat("ballRecovery")
        # tackles vencidos = % * total_tackles (se quiser algo mais preciso)
        total_tackles_home, total_tackles_away = get_stat("totalTackle")
        tackles_pct_home, tackles_pct_away = get_stat("wonTacklePercent")
        tackles_won_home = (
            int(round(total_tackles_home * (tackles_pct_home / 100.0)))
            if total_tackles_home
            else 0
        )
        tackles_won_away = (
            int(round(total_tackles_away * (tackles_pct_away / 100.0)))
            if total_tackles_away
            else 0
        )

        # ====== GOALKEEPING ======
        saves_home, saves_away = get_stat("goalkeeperSaves")
        goals_prevented_home, goals_prevented_away = get_stat("goalsPrevented")

        # ====== DISCIPLINA ======
        fouls_home, fouls_away = get_stat("fouls")
        yellow_home, yellow_away = get_stat("yellowCards")
        # Vermelho não tá nesse JSON, mas já deixo preparado:
        red_home, red_away = 0, 0

        # Retorno 100% alinhado com o modelo LiveSnapshot
        return {
            "xg_home": xg_home,
            "xg_away": xg_away,
            "shots_total_home": shots_total_home,
            "shots_total_away": shots_total_away,
            "shots_on_home": shots_on_home,
            "shots_on_away": shots_on_away,
            "possession_home": possession_home,
            "possession_away": possession_away,
            "corners_home": corners_home,
            "corners_away": corners_away,
            "touches_box_home": touches_box_home,
            "touches_box_away": touches_box_away,
            "final_third_entries_home": final_third_entries_home,
            "final_third_entries_away": final_third_entries_away,
            "big_chances_home": int(big_chances_home),
            "big_chances_away": int(big_chances_away),
            "big_chances_missed_home": int(big_chances_missed_home),
            "big_chances_missed_away": int(big_chances_missed_away),
            "shots_inside_box_home": int(shots_inside_box_home),
            "shots_inside_box_away": int(shots_inside_box_away),
            "shots_outside_box_home": int(shots_outside_box_home),
            "shots_outside_box_away": int(shots_outside_box_away),
            "interceptions_home": int(interceptions_home),
            "interceptions_away": int(interceptions_away),
            "clearances_home": int(clearances_home),
            "clearances_away": int(clearances_away),
            "recoveries_home": int(recoveries_home),
            "recoveries_away": int(recoveries_away),
            "tackles_won_home": tackles_won_home,
            "tackles_won_away": tackles_won_away,
            "saves_home": int(saves_home),
            "saves_away": int(saves_away),
            "goals_prevented_home": goals_prevented_home,
            "goals_prevented_away": goals_prevented_away,
            "fouls_home": int(fouls_home),
            "fouls_away": int(fouls_away),
            "yellow_home": int(yellow_home),
            "yellow_away": int(yellow_away),
            "red_home": int(red_home),
            "red_away": int(red_away),
        }

    @staticmethod
    def get_team_standing(standings, team_id):
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

    @staticmethod
    def calculate_minute(event_raw):
        event = event_raw.get("event", {})
        status = event.get("status", {})

        # 1. Se existir minute no clock, usa
        if "clock" in status and "minute" in status["clock"]:
            return status["clock"]["minute"]

        # 2. Caso não exista, tentamos estimar pelo timestamp do período atual
        period_start_ts = event.get("currentPeriodStartTimestamp")
        if period_start_ts:
            now_ts = int(time.time())
            minute = (now_ts - period_start_ts) // 60

            # Evita minuto negativo
            if minute < 0:
                minute = 0
            return minute

        # 3. Caso nada exista, retorna 0
        return 0

    @staticmethod
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

    def _safe_get(self, d, path, default=None):
        """Helper para navegar em dicts aninhados com segurança."""
        cur = d
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    def _extract_stat_from_stats_json(self, stats_json, key, default=0.0):
        """
        Procura uma estatística pelo campo 'key' no JSON do SofaScore (statistics endpoint).
        Ex: key='expectedGoals', 'attacks', 'dangerousAttacks', etc.
        """
        try:
            for block in stats_json.get("statistics", []):
                for group in block.get("groups", []):
                    for item in group.get("statisticsItems", []):
                        if item.get("key") == key:
                            # muitos vêm como homeValue/awayValue
                            return float(item.get("homeValue", 0.0)), float(
                                item.get("awayValue", 0.0)
                            )
        except Exception:
            pass
        return default, default

    @staticmethod
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

    def analyze_last_snapshots(self, match, window=10):
        qs = LiveSnapshot.objects.filter(match=match).order_by("-minute")[:window]
        snaps = list(reversed(qs))  # agora em ordem cronológica

        if len(snaps) < 2:
            return {
                "pressure_home": False,
                "pressure_away": False,
                "goal_warning": "Dados insuficientes",
                "over_15_signal": False,
                "over_25_trend": "Sem tendência",
                "corners_signal": "",
                "pressure_reason_home": "",
                "pressure_reason_away": "",
            }

        # DIFERENÇAS ENTRE PRIMEIRO E ÚLTIMO SNAP
        print(snaps[-1].xg_home - snaps[0].xg_home)
        delta_xg_home = snaps[-1].xg_home - snaps[0].xg_home
        delta_xg_away = snaps[-1].xg_away - snaps[0].xg_away

        delta_shots_on_home = snaps[-1].shots_on_home - snaps[0].shots_on_home
        delta_shots_on_away = snaps[-1].shots_on_away - snaps[0].shots_on_away

        delta_corners_home = snaps[-1].corners_home - snaps[0].corners_home
        delta_corners_away = snaps[-1].corners_away - snaps[0].corners_away

        # MOMENTUM MÉDIO
        avg_momentum = sum(s.momentum_score for s in snaps) / len(snaps)

        # Regras (pode ajustar depois)
        pressure_home = delta_xg_home >= 0.20 or delta_shots_on_home >= 2
        pressure_away = delta_xg_away >= 0.20 or delta_shots_on_away >= 2

        corners_spike = (delta_corners_home + delta_corners_away) >= 3

        goal_incoming = pressure_home or pressure_away or avg_momentum >= 0.70
        match.analise = {
            "pressure_home": pressure_home,
            "pressure_away": pressure_away,
            "pressure_reason_home": (
                f"Home criou {delta_xg_home:.2f} xG e {delta_shots_on_home} finalizações no gol nos últimos {window} snapshots."
                if pressure_home
                else ""
            ),
            "pressure_reason_away": (
                f"Away criou {delta_xg_away:.2f} xG e {delta_shots_on_away} finalizações no gol nos últimos {window} snapshots."
                if pressure_away
                else ""
            ),
            "corners_signal": (
                f"{delta_corners_home + delta_corners_away} cantos nos últimos {window} snapshots."
                if corners_spike
                else ""
            ),
            # As chaves abaixo já usam ternário corretamente para definir o VALOR:
            "goal_warning": (
                "ALTO risco de gol nos próximos minutos"
                if goal_incoming
                else "Jogo moderado"
            ),
            "over_15_signal": goal_incoming or corners_spike,
            "over_25_trend": (
                "Ritmo crescendo"
                if (delta_xg_home + delta_xg_away) >= 0.30
                else "Normal"
            ),
        }
        match.save(update_fields=["analise"])

        return {
            "pressure_home": pressure_home,
            "pressure_away": pressure_away,
            "pressure_reason_home": (
                f"Home criou {delta_xg_home:.2f} xG e {delta_shots_on_home} finalizações no gol nos últimos {window} snapshots."
                if pressure_home
                else ""
            ),
            "pressure_reason_away": (
                f"Away criou {delta_xg_away:.2f} xG e {delta_shots_on_away} finalizações no gol nos últimos {window} snapshots."
                if pressure_away
                else ""
            ),
            "corners_signal": (
                f"{delta_corners_home + delta_corners_away} cantos nos últimos {window} snapshots."
                if corners_spike
                else ""
            ),
            "goal_warning": (
                "ALTO risco de gol nos próximos minutos"
                if goal_incoming
                else "Jogo moderado"
            ),
            "over_15_signal": goal_incoming or corners_spike,
            "over_25_trend": (
                "Ritmo crescendo"
                if (delta_xg_home + delta_xg_away) >= 0.30
                else "Normal"
            ),
        }

    def get_events(self):
        BASE = "https://www.sofascore.com/api/v1"
        cookies = {
            "_gcl_au": "1.1.749561030.1764753513",
            "_ga": "GA1.1.301697650.1764753513",
            "panoramaId_expiry": "1764839942998",
            "_cc_id": "e66109d69e600fa7d045753fd1c08da7",
            "__gads": "ID=b19e2af804df34f6:T=1764753544:RT=1764753544:S=ALNI_Mb774vAMtsBLP4s6VQjOoKd3YZNLw",
            "__gpi": "UID=000012a96e395a7b:T=1764753544:RT=1764753544:S=ALNI_MZ0MxICjdnU5Nq0va2o9Yv6QxaXLg",
            "__eoi": "ID=a44ab7d32d94bf0e:T=1764753544:RT=1764753544:S=AA-AfjYGzo1PCV-NEccU8ri4Ortc",
            "cto_bundle": "W0md0V9IV00lMkJiekx5WnpabUNweHZDZTIlMkZHamFUbU44ZXFueXFCZmljeU12MUVwU1drVDdZY0tiSUtPU3ZoRjNuQ05XdDFtUm1NQXJHdWxhRm9aRGJ2SWhrSTZGMUtOcWJ0aG5mSFBwN2k4cDAwSSUyRndWY2VHN2c4VHg1bXBFMjhLU1NvdVJNNDVmR1JXZyUyQlFUY2t2UnAzdTdZQSUzRCUzRA",
            "cto_bidid": "_RDW419XUUlxMlZTa0RnbElrUGh1c2dISCUyRmF3TTV1U3N5R1BFaTdrdyUyRkxqcVowaDlpTGNHd1F6WFVuZktvZ0VYJTJGUkRBeHFZJTJCU1EycSUyRndKZFBPYWF3Z2pMcnBab0E5cmdGN1BmclVvcmllWERKdzAlM0Q",
            "cto_dna_bundle": "4-dbil9IV00lMkJiekx5WnpabUNweHZDZTIlMkZHdjJXekw5Z2clMkZTWG9lQVAwRGI1VHZGJTJCZmw3S1BoZlVwSXRrJTJCQTJtY0RDQ3Vnb2NqekZiNE1zM1hEbDFwM0x6RXclM0QlM0Q",
            "FCCDCF": "%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22477a8ff6-936e-4b5d-80b7-8e13a051ee83%5C%22%2C%5B1764753512%2C120000000%5D%5D%22%5D%5D%5D",
            "FCNEC": "%5B%5B%22AKsRol944nQG5wkdFdgpzEqQ9bd8wYj_gbM09X2ehrsPjOGDMVqr7wDDGEdzBrC0rSZXF7qPmFxBVYXzoy4a-rZ-vfEEwH3jQQOUWiXvnXZEgGKWtpNmNIKGFoXT2kR7gi4sMDf8LkvMpbWbd-tMraeKPu2UdW43Jg%3D%3D%22%5D%5D",
            "_ga_HNQ9P9MGZR": "GS2.1.s1764753512$o1$g1$t1764753822$j56$l0$h0",
        }

        headers = {
            "accept": "*/*",
            "accept-language": "pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "baggage": "sentry-environment=production,sentry-release=ZMb4MO5Soo7RxrQZhzoTo,sentry-public_key=d693747a6bb242d9bb9cf7069fb57988,sentry-trace_id=55c12f9e285e553f442d207357976a77",
            "cache-control": "max-age=0",
            "priority": "u=1, i",
            "referer": "https://www.sofascore.com/pt/",
            "sec-ch-ua": '"Chromium";v="142", "Microsoft Edge";v="142", "Not_A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sentry-trace": "55c12f9e285e553f442d207357976a77-a0f4d4f79b1b5667",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
            "x-captcha": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3NjQ4Mzk5NDB9.xazTKY9kMYS9TBqnLRltvorpr3ZS7kPWp6aPZhImEQs",
            "x-requested-with": "7e8cbc",
            # 'cookie': '_gcl_au=1.1.749561030.1764753513; _ga=GA1.1.301697650.1764753513; panoramaId_expiry=1764839942998; _cc_id=e66109d69e600fa7d045753fd1c08da7; __gads=ID=b19e2af804df34f6:T=1764753544:RT=1764753544:S=ALNI_Mb774vAMtsBLP4s6VQjOoKd3YZNLw; __gpi=UID=000012a96e395a7b:T=1764753544:RT=1764753544:S=ALNI_MZ0MxICjdnU5Nq0va2o9Yv6QxaXLg; __eoi=ID=a44ab7d32d94bf0e:T=1764753544:RT=1764753544:S=AA-AfjYGzo1PCV-NEccU8ri4Ortc; cto_bundle=W0md0V9IV00lMkJiekx5WnpabUNweHZDZTIlMkZHamFUbU44ZXFueXFCZmljeU12MUVwU1drVDdZY0tiSUtPU3ZoRjNuQ05XdDFtUm1NQXJHdWxhRm9aRGJ2SWhrSTZGMUtOcWJ0aG5mSFBwN2k4cDAwSSUyRndWY2VHN2c4VHg1bXBFMjhLU1NvdVJNNDVmR1JXZyUyQlFUY2t2UnAzdTdZQSUzRCUzRA; cto_bidid=_RDW419XUUlxMlZTa0RnbElrUGh1c2dISCUyRmF3TTV1U3N5R1BFaTdrdyUyRkxqcVowaDlpTGNHd1F6WFVuZktvZ0VYJTJGUkRBeHFZJTJCU1EycSUyRndKZFBPYWF3Z2pMcnBab0E5cmdGN1BmclVvcmllWERKdzAlM0Q; cto_dna_bundle=4-dbil9IV00lMkJiekx5WnpabUNweHZDZTIlMkZHdjJXekw5Z2clMkZTWG9lQVAwRGI1VHZGJTJCZmw3S1BoZlVwSXRrJTJCQTJtY0RDQ3Vnb2NqekZiNE1zM1hEbDFwM0x6RXclM0QlM0Q; FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22477a8ff6-936e-4b5d-80b7-8e13a051ee83%5C%22%2C%5B1764753512%2C120000000%5D%5D%22%5D%5D%5D; FCNEC=%5B%5B%22AKsRol944nQG5wkdFdgpzEqQ9bd8wYj_gbM09X2ehrsPjOGDMVqr7wDDGEdzBrC0rSZXF7qPmFxBVYXzoy4a-rZ-vfEEwH3jQQOUWiXvnXZEgGKWtpNmNIKGFoXT2kR7gi4sMDf8LkvMpbWbd-tMraeKPu2UdW43Jg%3D%3D%22%5D%5D; _ga_HNQ9P9MGZR=GS2.1.s1764753512$o1$g1$t1764753822$j56$l0$h0',
        }

        def get_json(url):
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

            try:
                r = requests.get(url, cookies=cookies, headers=headers)
                r.raise_for_status()
                return r.json()
            except:
                return {}

        for c in self.date:
            url = f"{BASE}/sport/football/scheduled-events/{c}"
            data = get_json(url)

            events = [
                e
                for e in data["events"]
                if e["tournament"]["slug"] in allowed_leagues
                and e["tournament"]["category"]["slug"] in allowed_countries
            ]

            for event in events:
                league_name = event["tournament"]["name"]
                league_country = event["tournament"]["category"]["name"]

                league_obj, _ = League.objects.get_or_create(
                    name=league_name,
                    defaults={"country": league_country},
                )

                tournament_id = event["tournament"]["id"]
                season_id = event["season"]["id"]
                home_id = event["homeTeam"]["id"]
                away_id = event["awayTeam"]["id"]
                # -------------------------
                # SEASON
                # -------------------------
                season_name = event["season"]["name"]

                season_obj, _ = Season.objects.get_or_create(
                    name=season_name,
                    league=league_obj,
                )

                # -------------------------
                # TEAMS
                # -------------------------
                home_team, _ = Team.objects.get_or_create(
                    name=event["homeTeam"]["name"],
                    defaults={"league": league_obj},
                )

                away_team, _ = Team.objects.get_or_create(
                    name=event["awayTeam"]["name"],
                    defaults={"league": league_obj},
                )
                ts = event.get("startTimestamp")
                date_obj = datetime.fromtimestamp(ts) if ts else None
                stadings = self.get_stadings(event["id"])
                match_obj, created = Match.objects.update_or_create(
                    external_id=event["id"],
                    defaults={
                        "season": season_obj,
                        "home_team": home_team,
                        "away_team": away_team,
                        "date": date_obj,
                        "tournament_id": tournament_id,
                        "season_ids": season_id,
                        "away_id": away_id,
                        "home_id": home_id,
                        "finalizado": (event["status"]["type"] == "finished"),
                        "event_json": event,
                        "stading_json": stadings,
                    },
                )
                self.get_analyze_streaks(event["id"])

    def get_stats(self, event_id=None):
        if event_id:
            matchs = Match.objects.filter(id=event_id)
        else:
            matchs = Match.objects.filter(finalizado=False)

        last_snapshot = None

        for match in matchs:
            try:
                stats_url = f"{BASE}/event/{match.external_id}/statistics"
                raw = self.get_json(stats_url)
                event_raw = self.get_json(f"{BASE}/event/{match.external_id}")
                match.stats_json = raw
                match.save(update_fields=["stats_json"])
                minute = self.calculate_minute(event_raw)
                stats = self.parse_sofascore_stats(raw)

                last_snap = (
                    LiveSnapshot.objects.filter(match=match).order_by("-minute").first()
                )

                result = self.generate_insights(event_raw, raw, match)
                result["insights"].extend(self.generate_deep_insights(stats))

                snapshot = LiveSnapshot.objects.create(
                    match=match, minute=minute, **stats
                )

                if last_snap:
                    snapshot.momentum_score = self.calculate_momentum(
                        snapshot, last_snap
                    )
                    snapshot.save(update_fields=["momentum_score"])
                else:
                    snapshot.momentum_score = 0
                    snapshot.save(update_fields=["momentum_score"])

                last_snapshot = snapshot

            except Exception as e:
                print(
                    f"Erro processando match {match.id}: {e} {e.__traceback__.tb_lineno}"
                )

        return last_snapshot  # <-- RETORNA O SNAPSHOT

    def get_stadings(
        self, season_id=None, tournament_id=None, home_id=None, away_id=None
    ):
        standings_url = (
            f"{BASE}/tournament/{tournament_id}/season/{season_id}/standings/total"
        )
        standings = self.get_json(standings_url)

        home_standing = self.get_team_standing(standings, home_id)
        away_standing = self.get_team_standing(standings, away_id)
        result = {}

        result["standings"] = {
            "home": home_standing,
            "away": away_standing,
            "favorito_tabela": self.table_favorite(home_standing, away_standing),
        }

        return result

    def get_analyze_streaks(self, event_id):
        try:
            streaks_url = f"{BASE}/event/{event_id}/team-streaks"
            streaks_raw = self.get_json(streaks_url)
            streaks_analysis = self.analyze_streaks(streaks_raw)
            if event_id:
                matchs = Match.objects.filter(external_id=event_id).first()
                matchs.streaks_json = streaks_raw
                matchs.save(update_fields=["streaks_json"])

            return streaks_analysis
        except:
            pass

    def get_analise_event(self, match):
        """
        Versão PRO:
        - Usa event_json + stats_json (+ histórico, se disponível)
        - Integra xG
        - Calcula pressão ofensiva
        - Usa modelo de gols tipo Poisson/Bayes simplificado
        - Retorna estrutura compatível com o template
        """
        try:
            event = match.event_json or {}
            standings = match.stading_json or {}

            # Se você tiver raw_statistics_json no Match:
            try:
                import json

                stats_json = json.loads(
                    getattr(match, "raw_statistics_json", "") or "{}"
                )
            except Exception:
                stats_json = {}

            # ---------------------------------------------------------------------
            # INFO BÁSICA
            # ---------------------------------------------------------------------
            home = self._safe_get(event, ["homeTeam", "name"], str(match.home_team))
            away = self._safe_get(event, ["awayTeam", "name"], str(match.away_team))

            hg = self._safe_get(
                event, ["homeScore", "current"], match.home_team_score or 0
            )
            ag = self._safe_get(
                event, ["awayScore", "current"], match.away_team_score or 0
            )
            total_goals = (hg or 0) + (ag or 0)

            # ---------------------------------------------------------------------
            # MINUTO DE JOGO
            # ---------------------------------------------------------------------
            now_ts = datetime.now(timezone.utc).timestamp()
            start_ts = event.get("startTimestamp")

            if start_ts:
                minute = int((now_ts - start_ts) // 60)
                minute = max(0, min(minute, 100))
            else:
                # fallback: se já finalizou, assume 90; se não, tenta usar date
                if match.finalizado:
                    minute = 90
                else:
                    minute = None

            # Faixa de tempo (para heurísticas)
            if minute is None:
                fase_jogo = "desconhecido"
            elif minute < 15:
                fase_jogo = "início"
            elif minute < 35:
                fase_jogo = "primeiro_meio"
            elif minute < 60:
                fase_jogo = "intervalo_inicio_2t"
            elif minute < 75:
                fase_jogo = "meio_2t"
            else:
                fase_jogo = "fim"

            # ---------------------------------------------------------------------
            # GOL RECENTE
            # ---------------------------------------------------------------------
            gol_recente = False
            tempo_desde_gol = None
            changes = event.get("changes") or {}

            if isinstance(changes, dict) and "changeTimestamp" in changes:
                last_change = changes["changeTimestamp"]
                tempo_desde_gol = now_ts - last_change
                if tempo_desde_gol < 300:  # menos de 5min
                    gol_recente = True

            # ---------------------------------------------------------------------
            # xG, ATAQUES, FINALIZAÇÕES, ESCANTEIOS, ETC (stats_json)
            # ---------------------------------------------------------------------
            xg_home, xg_away = self._extract_stat_from_stats_json(
                stats_json, "expectedGoals", 0.0
            )
            attacks_home, attacks_away = self._extract_stat_from_stats_json(
                stats_json, "attacks", 0.0
            )
            dang_att_home, dang_att_away = self._extract_stat_from_stats_json(
                stats_json, "dangerousAttacks", 0.0
            )
            shots_home, shots_away = self._extract_stat_from_stats_json(
                stats_json, "shotsTotal", 0.0
            )
            shots_on_home, shots_on_away = self._extract_stat_from_stats_json(
                stats_json, "shotsOnTarget", 0.0
            )
            corners_home, corners_away = self._extract_stat_from_stats_json(
                stats_json, "cornerKicks", 0.0
            )

            # Se você já tiver MatchStats preenchido, pode fazer um override:
            try:
                ms = MatchStats.objects.filter(match=match).first()
            except Exception:
                ms = None

            if ms:
                if ms.xg_home is not None and ms.xg_away is not None:
                    xg_home, xg_away = float(ms.xg_home), float(ms.xg_away)

                # se quiser, pode sobrescrever também shots, corners etc.
                # shots_home, shots_away = ms.shots_home, ms.shots_away, ...

            # ---------------------------------------------------------------------
            # PRESSÃO OFENSIVA (0–100)
            # ---------------------------------------------------------------------
            def calc_pressao(att, dang_att, shots, xg, minute):
                if not minute or minute <= 0:
                    minute = 1
                # normaliza por minuto
                att_pm = att / minute
                dang_pm = dang_att / minute
                shots_pm = shots / minute
                xg_pm = xg / minute

                # pesos arbitrários – você pode tunar depois
                score = att_pm * 0.8 + dang_pm * 1.4 + shots_pm * 2.0 + xg_pm * 20.0
                # clamp 0–100
                return max(0.0, min(score, 100.0))

            pressure_home = calc_pressao(
                attacks_home, dang_att_home, shots_home, xg_home, minute or 1
            )
            pressure_away = calc_pressao(
                attacks_away, dang_att_away, shots_away, xg_away, minute or 1
            )

            # métrica única de momento
            momentum_raw = pressure_home - pressure_away
            # se quiser usar momentum em outro lugar:
            # momentum_score = momentum_raw (pode normalizar depois)

            # ---------------------------------------------------------------------
            # BASE BAYESIANA: MÉDIA DE GOLS DA LIGA + FORÇA HISTÓRICA
            # ---------------------------------------------------------------------
            try:
                league_qs = Match.objects.filter(
                    season=match.season,
                    finalizado=True,
                    home_team__isnull=False,
                    away_team__isnull=False,
                )

                league_aggs = league_qs.aggregate(
                    avg_goals=Avg(F("home_team_score") + F("away_team_score")),
                )
                league_avg_goals = league_aggs["avg_goals"] or 2.5
            except Exception:
                league_avg_goals = 2.5

            # histórico recente dos times (últimos 10 jogos)
            def build_team_strength(team, as_home=True, as_away=True):
                qs = Match.objects.filter(finalizado=True)
                if as_home:
                    qs = qs.filter(home_team=team) | Match.objects.filter(
                        away_team=team, finalizado=True
                    )
                else:
                    qs = qs.filter(home_team=team, finalizado=True)

                qs = qs.order_by("-date")[:10]

                if not qs:
                    return 1.0, 1.0  # ataque, defesa neutros

                total_scored = 0
                total_conceded = 0
                count = 0

                for m in qs:
                    if m.home_team == team:
                        s = m.home_team_score or 0
                        c = m.away_team_score or 0
                    else:
                        s = m.away_team_score or 0
                        c = m.home_team_score or 0
                    total_scored += s
                    total_conceded += c
                    count += 1

                if count == 0:
                    return 1.0, 1.0

                avg_scored = total_scored / count
                avg_conceded = total_conceded / count

                # força relativa vs média da liga
                attack_strength = (
                    (avg_scored / (league_avg_goals / 2))
                    if league_avg_goals > 0
                    else 1.0
                )
                defense_strength = (
                    (avg_conceded / (league_avg_goals / 2))
                    if league_avg_goals > 0
                    else 1.0
                )

                # clamp para não explodir
                attack_strength = max(0.5, min(attack_strength, 1.8))
                defense_strength = max(0.5, min(defense_strength, 1.8))

                return attack_strength, defense_strength

            try:
                atk_home, def_home = build_team_strength(match.home_team)
                atk_away, def_away = build_team_strength(match.away_team)
            except Exception:
                atk_home = def_home = atk_away = def_away = 1.0

            # ---------------------------------------------------------------------
            # LAMBDAS ESPERADAS (tipo Poisson)
            # ---------------------------------------------------------------------
            base_home = league_avg_goals * 0.55
            base_away = league_avg_goals * 0.45

            lam_home = base_home * atk_home * def_away
            lam_away = base_away * atk_away * def_home

            # Ajuste com xG – se xG está muito alto vs gols, aumenta levemente
            if xg_home + xg_away > 0:
                ratio_home = xg_home / max(hg, 0.5)
                ratio_away = xg_away / max(ag, 0.5)
                lam_home *= max(0.7, min(ratio_home, 1.4))
                lam_away *= max(0.7, min(ratio_away, 1.4))

            # Ajuste pela fase do jogo:
            if fase_jogo in ("início", "primeiro_meio"):
                lam_home *= 0.9
                lam_away *= 0.9
            elif fase_jogo in ("meio_2t", "fim"):
                lam_home *= 1.1
                lam_away *= 1.1

            # ---------------------------------------------------------------------
            # PROJEÇÃO DE GOLS FUTUROS / PLACAR ESTIMADO
            # ---------------------------------------------------------------------
            # projeção de gols totais finais
            remaining_factor = 1.0
            if minute and minute > 0 and minute < 90:
                remaining_factor = (90 - minute) / 90

            exp_fut_home = lam_home * remaining_factor
            exp_fut_away = lam_away * remaining_factor

            est_home = hg + exp_fut_home
            est_away = ag + exp_fut_away

            projected_score = f"{est_home:.1f} x {est_away:.1f}"

            # ---------------------------------------------------------------------
            # PROBABILIDADES (heurísticas usando tudo isso)
            # ---------------------------------------------------------------------
            prob = {
                "over_1_5": 50,
                "over_2_5": 40,
                "btts": 30,
                "goal_h2": 45,
            }

            # base por lambda total
            lam_total = lam_home + lam_away
            if lam_total >= 3.0:
                prob["over_2_5"] = 75
                prob["over_1_5"] = 90
            elif lam_total >= 2.3:
                prob["over_2_5"] = 65
                prob["over_1_5"] = 85
            elif lam_total <= 1.5:
                prob["over_2_5"] = 35
                prob["over_1_5"] = 60

            # considerar gols já feitos
            if total_goals >= 2:
                prob["over_1_5"] = 97
                prob["over_2_5"] = max(prob["over_2_5"], 75)
            elif total_goals == 1:
                prob["over_1_5"] = max(prob["over_1_5"], 70)

            # BTTS – se ambos marcando + xG bom dos dois lados
            if hg > 0 and ag > 0:
                prob["btts"] = 75
            elif xg_home > 0.7 and xg_away > 0.7:
                prob["btts"] = 65

            # Gol no 2º tempo (ou gol daqui pra frente, se você quiser)
            if fase_jogo in ("intervalo_inicio_2t", "meio_2t"):
                prob["goal_h2"] = 60
            if fase_jogo == "fim":
                prob["goal_h2"] -= 10

            if gol_recente:
                prob["over_2_5"] += 5
                prob["goal_h2"] += 8
                prob["btts"] += 5

            # clamp 1–99
            for k in prob:
                prob[k] = max(1, min(int(round(prob[k])), 99))

            # ---------------------------------------------------------------------
            # ODDS JUSTAS
            # ---------------------------------------------------------------------
            odds = {
                "over_2_5": round(100 / prob["over_2_5"], 2),
                "btts": round(100 / prob["btts"], 2),
                "goal_h2": round(100 / prob["goal_h2"], 2),
            }

            # ---------------------------------------------------------------------
            # INSIGHTS
            # ---------------------------------------------------------------------
            insights = []

            insights.append(f"Liga com média de {league_avg_goals:.2f} gols por jogo.")
            insights.append(f"xG: {home} {xg_home:.2f} x {xg_away:.2f} {away}.")
            insights.append(
                f"Pressão: {home} {pressure_home:.1f} x {pressure_away:.1f} {away}."
            )

            if gol_recente:
                insights.append("Gol recente — momento de alta volatilidade.")

            if momentum_raw > 10:
                insights.append(f"{home} pressiona mais no momento.")
            elif momentum_raw < -10:
                insights.append(f"{away} pressiona mais no momento.")

            if fase_jogo == "fim":
                insights.append("Minutos finais — jogos tendem a ficar caóticos.")

            # ---------------------------------------------------------------------
            # RECOMENDAÇÃO FINAL
            # ---------------------------------------------------------------------
            if prob["over_2_5"] >= 70:
                recommendation = "Over 2.5"
                confidence = prob["over_2_5"]
            elif prob["btts"] >= 65:
                recommendation = "BTTS (Ambas Marcam)"
                confidence = prob["btts"]
            else:
                recommendation = "Gol no 2º tempo"
                confidence = prob["goal_h2"]

            return {
                "score": f"{home} {hg} x {ag} {away}",
                "minute": minute,
                "gol_recente": gol_recente,
                "tempo_desde_gol": tempo_desde_gol,
                "probabilities": prob,
                "odds": odds,
                "projected_score": projected_score,
                "insights": insights,
                "recommendation": recommendation,
                "confidence": confidence,
            }

        except Exception as e:
            print("Erro ao processar match:", match.id, e)
            return None

    def analyze_streaks(self, streaks, home_name="Home", away_name="Away"):
        """
        streaks = {
            "general": [...],
            "head2head": [...]
        }
        """

        insights = []
        impact = {
            "goals_over": 0,
            "goals_under": 0,
            "btts": 0,
            "cards_over": 0,
            "corners_over": 0,
            "momentum_home": 0,
            "momentum_away": 0,
        }

        # Helper para porcentagem de "X/Y"
        def ratio(v):
            if "/" in v:
                a, b = v.split("/")
                if b == "0":
                    return 0
                return int(a) / int(b)
            return float(v) if v.isdigit() else 0

        # ================================
        # GENERAL STREAKS
        # ================================
        for item in streaks.get("general", []):
            name = item["name"]
            team = item["team"]
            value = item["value"]
            pct = ratio(value)

            # ------------------------------
            # NO LOSSES
            # ------------------------------
            if name == "No losses":
                streak = int(value)
                insights.append(
                    f"{home_name if team == 'home' else away_name} está há {streak} jogos sem perder — forte consistência."
                )
                if team == "home":
                    impact["momentum_home"] += 5
                else:
                    impact["momentum_away"] += 5

            # ------------------------------
            # WITHOUT CLEAN SHEET
            # ------------------------------
            elif name == "Without clean sheet":
                streak = int(value)
                insights.append(
                    f"{away_name if team == 'away' else home_name} tomou gol nos últimos {streak} jogos — favorece BTTS."
                )
                impact["btts"] += 10

            # ------------------------------
            # MORE THAN 2.5 GOALS
            # ------------------------------
            elif name == "More than 2.5 goals":
                insights.append(
                    f"{team.title()} em {value} jogos com mais de 2.5 gols — tendência forte de Over."
                )
                if pct >= 0.7:
                    impact["goals_over"] += 15
                else:
                    impact["goals_over"] += 7

            # ------------------------------
            # CARDS (+4.5)
            # ------------------------------
            elif name == "More than 4.5 cards":
                insights.append(
                    f"Cartões: {value} jogos tiveram +4.5 — tendência clara de Over cards."
                )
                impact["cards_over"] += 12 if pct >= 0.7 else 5

            # ------------------------------
            # CORNERS (+10.5)
            # ------------------------------
            elif name == "More than 10.5 corners":
                insights.append(
                    f"Cantos: {value} jogos acima de 10.5 — jogo tende a ser movimentado."
                )
                impact["corners_over"] += 10

        # ================================
        # HEAD-TO-HEAD (H2H)
        # ================================
        for item in streaks.get("head2head", []):
            name = item["name"]
            team = item["team"]
            value = item["value"]
            pct = ratio(value)

            # WINS H2H
            if name == "Wins":
                wins = int(value)
                insights.append(
                    f"{home_name if team == 'home' else away_name} venceu {wins} confrontos diretos recentes."
                )
                if team == "home":
                    impact["momentum_home"] += 8
                else:
                    impact["momentum_away"] += 8

            # NO LOSSES H2H
            elif name == "No losses":
                streak = int(value)
                insights.append(
                    f"Nos confrontos diretos, {home_name if team == 'home' else away_name} está há {streak} jogos sem perder."
                )
                if team == "home":
                    impact["momentum_home"] += 10
                else:
                    impact["momentum_away"] += 10

            # BTTS via clean sheet
            elif name == "Without clean sheet":
                insights.append(
                    f"No H2H, {team} tomou gol nos últimos {value} jogos — ótimo sinal para BTTS."
                )
                impact["btts"] += 10

            # CARDS H2H
            elif name == "More than 4.5 cards":
                impact["cards_over"] += 10
                insights.append("Histórico de cartões altos nos confrontos diretos.")

            # CORNERS H2H
            elif name == "Less than 10.5 corners":
                impact["corners_over"] -= 7
                insights.append("Confrontos diretos com tendência de poucos cantos.")

        # ================================
        # NORMALIZAÇÃO FINAL
        # ================================
        for k in impact:
            if impact[k] > 25:
                impact[k] = 25
            if impact[k] < -25:
                impact[k] = -25

        return {"insights": insights, "impact": impact}

    def analyze_live_snapshots(self, match, window=15):
        """
        Gera análise dos últimos X minutos do LiveSnapshot.
        Retorna insights sobre gols, escanteios e disciplina.
        """

        snapshots = LiveSnapshot.objects.filter(match=match).order_by("-minute")[
            :window
        ]
        if not snapshots:
            return {"insights": [], "analysis": {}, "suggestions": []}

        snapshots = list(snapshots)[::-1]  # ordena crescente minuto

        insights = []
        suggestions = []
        analysis = {}

        # ============================
        # MÉDIAS E TOTAIS RECENTES
        # ============================

        total_corners = snapshots[-1].corners_home + snapshots[-1].corners_away
        total_shots = snapshots[-1].shots_total_home + snapshots[-1].shots_total_away
        total_yellow = snapshots[-1].yellow_home + snapshots[-1].yellow_away

        # crescimento recente
        first = snapshots[0]
        last = snapshots[-1]

        delta_corners = (last.corners_home + last.corners_away) - (
            first.corners_home + first.corners_away
        )
        delta_shots = (last.shots_total_home + last.shots_total_away) - (
            first.shots_total_home + first.shots_total_away
        )
        delta_big = (last.big_chances_home + last.big_chances_away) - (
            first.big_chances_home + first.big_chances_away
        )
        delta_fouls = (last.fouls_home + last.fouls_away) - (
            first.fouls_home + first.fouls_away
        )

        # momentum
        momentum = last.momentum_score

        # ============================
        # INSIGHTS AUTOMÁTICOS
        # ============================

        # ---- ESCANTEIOS ----
        if delta_corners >= 2:
            insights.append(
                f"Nos últimos {window} minutos saíram {delta_corners} escanteios — forte tendência de mais cantos."
            )
            suggestions.append("Over escanteios em linha ao vivo")

        if total_corners >= 8 and last.minute < 70:
            insights.append(
                f"O jogo já tem {total_corners} escanteios — ritmo forte para Over 10.5."
            )
            suggestions.append("Over 10.5 escanteios")

        # ---- GOLS ----
        if delta_shots >= 5:
            insights.append(
                f"Volume ofensivo crescente: {delta_shots} finalizações recentes — aumenta chance de gol."
            )
            suggestions.append("Gol próximo (Over 0.5 live)")

        if delta_big >= 1:
            insights.append(
                f"Gerou {delta_big} grande chance nos últimos minutos — risco altíssimo de gol."
            )
            suggestions.append("Gol no próximo trecho do jogo")

        if last.xg_home + last.xg_away >= 2.5:
            insights.append(
                f"xG acumulado muito alto ({last.xg_home + last.xg_away:.2f}) — jogo aberto com tendência de gol."
            )
            suggestions.append("Over em gols")

        # ---- DISCIPLINA (CARTÕES) ----
        if delta_fouls >= 5:
            insights.append(
                f"Jogo ficou mais físico: {delta_fouls} faltas recentes — tendência de cartão."
            )
            suggestions.append("Cartão nos próximos minutos")

        if total_yellow >= 4 and last.minute < 75:
            insights.append(
                f"{total_yellow} cartões já aplicados — risco elevado de mais disciplina."
            )
            suggestions.append("Over cartões")

        # ---- MOMENTUM ----
        if momentum > 5:
            insights.append(
                "Mandante domina o momento — tendência de pressão e oportunidades."
            )
        elif momentum < -5:
            insights.append("Visitante cresceu no jogo — possível virada ou gol fora.")

        # ============================
        # OUTPUT FINAL
        # ============================

        analysis = {
            "minute": last.minute,
            "corners_total": total_corners,
            "corners_recent": delta_corners,
            "shots_recent": delta_shots,
            "big_chances_recent": delta_big,
            "fouls_recent": delta_fouls,
            "yellow_total": total_yellow,
            "momentum": momentum,
        }

        return {
            "analysis": analysis,
            "insights": insights,
            "suggestions": list(
                dict.fromkeys(suggestions)
            ),  # remove duplicatas mantendo ordem
        }
