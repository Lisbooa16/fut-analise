import requests

class BetanoStatsClient:
    BASE_URL = "https://stats.fn.sportradar.com/betano/br/America:Montevideo/gismo"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.betano.com/",
        "Origin": "https://www.betano.com",
    }

    def get_last_matches(self, team_id: int, qty: int = 30):
        url = f"{self.BASE_URL}/stats_team_lastx/{team_id}/{qty}"
        resp = requests.get(url, headers=self.HEADERS, timeout=5)
        resp.raise_for_status()
        return resp.json()


class TeamStats:
    def __init__(self, raw):
        """
        Aqui ajustamos para o formato REAL:

        raw["doc"][0]["data"]["matches"]
        """
        data = raw["doc"][0]["data"]
        self.team = data["team"]["name"]
        self.matches = data["matches"]

    def get_last_results(self):
        results = []

        for m in self.matches:
            results.append({
                "date": m["time"]["date"],
                "home": m["teams"]["home"]["name"],
                "away": m["teams"]["away"]["name"],
                "score": f"{m['result']['home']}:{m['result']['away']}",
                "goals_home": m["result"]["home"],
                "goals_away": m["result"]["away"],
                "winner": m["result"].get("winner")
            })

        return results

    def summary(self):
        total = len(self.matches)
        wins = draws = goals = 0

        for m in self.matches:
            home = m["result"]["home"]
            away = m["result"]["away"]
            goals += home + away

            if home == away:
                draws += 1
            else:
                wins += 1

        avg_goals = round(goals / total, 2)

        return {
            "team": self.team,
            "games": total,
            "wins": wins,
            "draws": draws,
            "avg_goals": avg_goals,
        }

    def trends(self):
        last5 = self.matches[:5]
        over25 = 0
        btts = 0

        for m in last5:
            h = m["result"]["home"]
            a = m["result"]["away"]

            if h + a >= 3:
                over25 += 1
            if h > 0 and a > 0:
                btts += 1

        return {
            "over_25_rate": f"{(over25/5)*100:.0f}%",
            "btts_rate": f"{(btts/5)*100:.0f}%",
        }


def gerar_analise(team_id=2713, jogos=30):
    client = BetanoStatsClient()
    data = client.get_last_matches(team_id, jogos)
    stats = TeamStats(data)

    resumo = stats.summary()
    tendencia = stats.trends()
    resultados = stats.get_last_results()

    print("\n=========================================")
    print(f" ANÁLISE DOS ÚLTIMOS {jogos} JOGOS — {stats.team}")
    print("=========================================\n")

    print(resumo)
    print(tendencia)

    print("\nÚltimos 10 jogos:")
    for r in resultados:
        print(r)

    return {
        "resumo": resumo,
        "tendencia": tendencia,
        "resultados": resultados
    }


if __name__ == "__main__":
    gerar_analise()
