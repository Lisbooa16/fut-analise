import json
from decimal import Decimal

from django.db import models

from bet.models import Bet, MatchModelEvaluation


def generate_bankroll_alerts(bankroll):
    alerts = []

    last_bets = Bet.objects.filter(bankroll=bankroll).order_by("-created_at")[:20]

    if not last_bets:
        return ["📘 Ainda não há histórico suficiente para análise da banca."]

    reds = 0
    for bet in last_bets:
        if bet.result == "RED":
            reds += 1
        else:
            break

    if reds >= 3:
        alerts.append(
            f"⚠️ Atenção! Você está em sequência de {reds} reds seguidos. "
            "Reduza a stake para proteger a banca."
        )

    profit = bankroll.balance - bankroll.initial_balance

    if profit < 0:
        alerts.append(
            f"❗ Você está no prejuízo: R$ {abs(profit):.2f}. "
            "Mantenha disciplina e reduza a exposição."
        )

        avg_green = Bet.objects.filter(bankroll=bankroll, result="GREEN").aggregate(
            avg=models.Avg("potential_profit")
        )["avg"]

        if avg_green and avg_green > 0:
            needed = abs(profit) / avg_green
            alerts.append(
                f"📈 Para voltar ao positivo, você precisa de aproximadamente "
                f"{needed:.1f} greens na média das suas vitórias."
            )
    else:
        alerts.append(
            f"✅ Sua banca está positiva: +R$ {profit:.2f}. "
            "Continue seguindo sua gestão atual."
        )

    stakes = [b.stake for b in last_bets if b.stake > 0]
    if stakes:
        avg_stake = sum(stakes) / len(stakes)
        percent = avg_stake / bankroll.balance * 100

        if percent >= 5:
            alerts.append(
                "🔥 Sua stake média está acima de 5% da banca — isso é agressivo e aumenta risco de quebra."
            )
        elif percent <= 1:
            alerts.append(
                "🧊 Sua stake média está bem conservadora (≤1%). Excelente para longo prazo."
            )

    return alerts


class SofaStatParser:
    """Ajuda a extrair dados limpos do JSON complexo do SofaScore."""

    def __init__(self, stats_json):
        self.data = stats_json.get("statistics", [])

    def get_stats(self, period="ALL"):

        period_group = next(
            (item for item in self.data if item["period"] == period), None
        )
        if not period_group:
            return {}

        stats = {}

        key_map = {
            "expectedGoals": "xg",
            "ballPossession": "possession",
            "bigChanceCreated": "big_chances",
            "totalShotsOnGoal": "shots",
            "shotsOnGoal": "shots_on_target",
            "cornerKicks": "corners",
            "fouls": "fouls",
            "yellowCards": "yellow_cards",
            "redCards": "red_cards",
            "goalkeeperSaves": "saves",
            "totalTackle": "tackles",
            "interceptionWon": "interceptions",
            "totalClearance": "clearances",
            "finalThirdEntries": "final_third",
            "touchesInOppBox": "box_touches",
            "accurateCross": "crosses",
            "duelWonPercent": "duels_won_pct",
        }

        for group in period_group.get("groups", []):
            for item in group.get("statisticsItems", []):
                key = item.get("key")
                if key in key_map:
                    clean_key = key_map[key]
                    stats[f"{clean_key}_home"] = float(item.get("homeValue", 0))
                    stats[f"{clean_key}_away"] = float(item.get("awayValue", 0))
        return stats


class MatchAnalyzer:
    def __init__(self, match):
        self.match = match
        self.home_name = match.home_team.name if match.home_team else "Mandante"
        self.away_name = match.away_team.name if match.away_team else "Visitante"

    def analyze_streaks(self, streaks_data):
        """
        Analisa tendências históricas e H2H com pesos diferentes.
        Retorna insights e fatores de impacto para ajuste de odds.
        """
        analyzed = {
            "general": [],
            "head2head": [],
            "impact": {"goals_over": 0, "btts": 0, "momentum": 0},
        }

        impact_weights = {"general": 1.0, "head2head": 1.5}

        def parse_ratio(v):
            if isinstance(v, (int, float)):
                return float(v)
            if "/" in str(v):
                try:
                    a, b = v.split("/")
                    return float(a) / float(b) if float(b) > 0 else 0
                except:
                    return 0
            return 0

        for group in ["general", "head2head"]:
            items = streaks_data.get(group, [])
            for item in items:
                ratio = parse_ratio(item.get("value", 0))
                name = item.get("name", "").lower()
                team = item.get("team", "")

                weight = impact_weights.get(group, 1.0)
                if ratio >= 0.70:
                    if "over 2.5" in name or "goals" in name:
                        analyzed["impact"]["goals_over"] += 1 * weight
                    if "btts" in name or "both teams" in name:
                        analyzed["impact"]["btts"] += 1 * weight

                analyzed[group].append(
                    {
                        "name": item.get("name"),
                        "team": team,
                        "ratio": ratio,
                        "hot_streak": ratio >= 0.80,
                        "text": f"{team.capitalize()}: {item.get('name')} ({int(ratio * 100)}%)",
                    }
                )

        return analyzed

    def calculate_advanced_pressure(self, stats):
        """Calcula pressão 0-100 baseada em métricas avançadas."""

        def calc_team_pressure(
            xg, shots, corners, final_third, box_touches, possession
        ):
            score = 0
            score += xg * 40
            score += shots * 2
            score += corners * 3
            score += final_third * 0.5
            score += box_touches * 1.5
            if possession > 65:
                score += 10
            return min(score, 100)

        p_home = calc_team_pressure(
            stats.get("xg_home", 0),
            stats.get("shots_home", 0),
            stats.get("corners_home", 0),
            stats.get("final_third_home", 0),
            stats.get("box_touches_home", 0),
            stats.get("possession_home", 0),
        )

        p_away = calc_team_pressure(
            stats.get("xg_away", 0),
            stats.get("shots_away", 0),
            stats.get("corners_away", 0),
            stats.get("final_third_away", 0),
            stats.get("box_touches_away", 0),
            stats.get("possession_away", 0),
        )

        total = p_home + p_away
        if total == 0:
            return 50, 50
        return round((p_home / total) * 100), round((p_away / total) * 100)

    def analyze_json_data(self, stats_json, event_json):
        """Analisa o jogo ao vivo usando os JSONs salvos no banco."""
        parser = SofaStatParser(stats_json)
        stats = parser.get_stats(period="ALL")

        if not stats:
            return {
                "insights": [],
                "suggestions": [],
                "pressure_index": {"home": 50, "away": 50},
            }

        try:
            home_score = event_json.get("homeScore", {}).get("current", 0)
            away_score = event_json.get("awayScore", {}).get("current", 0)

            minute = 0
            if "status" in event_json:

                pass
        except:
            home_score = 0
            away_score = 0

        pressure_h, pressure_a = self.calculate_advanced_pressure(stats)

        insights = []
        suggestions = []

        if stats.get("final_third_home", 0) > stats.get("final_third_away", 0) * 1.5:
            if stats.get("xg_home", 0) < 0.5:
                insights.append(
                    f"{self.home_name} tem domínio territorial, mas cria pouco perigo real."
                )

        if (stats.get("xg_home", 0) - home_score) > 1.0:
            insights.append(
                f"🔥 {self.home_name} merece o gol! xG alto ({stats['xg_home']}) sem marcar."
            )
            suggestions.append("Gol Home")

        if (stats.get("xg_away", 0) - away_score) > 1.0:
            insights.append(
                f"🔥 {self.away_name} merece o gol! xG alto ({stats['xg_away']}) sem marcar."
            )
            suggestions.append("Gol Away")

        total_final_third = stats.get("final_third_home", 0) + stats.get(
            "final_third_away", 0
        )
        if total_final_third > 70:
            insights.append("Jogo aberto: Muitas chegadas no ataque de ambos os lados.")

        return {
            "pressure_index": {"home": pressure_h, "away": pressure_a},
            "stats_window": {
                "corners": int(
                    stats.get("corners_home", 0) + stats.get("corners_away", 0)
                ),
                "shots": int(stats.get("shots_home", 0) + stats.get("shots_away", 0)),
                "xg_home": stats.get("xg_home", 0),
                "xg_away": stats.get("xg_away", 0),
            },
            "insights": insights,
            "suggestions": list(set(suggestions)),
        }


def safe_json(value):
    """Garante que JSONField string vire dict."""
    if isinstance(value, dict) or isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def get_stat(stats_json, key, period="ALL"):
    if not stats_json:
        return None, None

    data = safe_json(stats_json)

    for block in data.get("statistics", []):
        if block.get("period") != period:
            continue

        for group in block.get("groups", []):
            for item in group.get("statisticsItems", []):
                if item.get("key") == key:
                    return item.get("homeValue"), item.get("awayValue")

    return None, None


def get_real_outcome(match):
    home_goals = match.home_team_score if match.home_team_score else 0
    away_goals = match.away_team_score if match.away_team_score else 0

    home_corners, away_corners = get_stat(match.stats_json, "cornerKicks")

    return {
        "result": (
            "home"
            if home_goals > away_goals
            else "away" if away_goals > home_goals else "draw"
        ),
        "over25": (home_goals + away_goals) > 2,
        "under25": (home_goals + away_goals) <= 2,
        "btts": home_goals > 0 and away_goals > 0,
        "corners_over10": ((home_corners or 0) + (away_corners or 0)) > 10,
    }


def evaluate_market(prob, real, positive_label=True):
    """
    positive_label=True:
        prob alta => evento acontece
    positive_label=False:
        prob alta => evento NÃO acontece
    """

    if prob >= 0.60 and real == positive_label:
        return "hit"
    if prob <= 0.40 and real != positive_label:
        return "hit"
    if 0.45 <= prob <= 0.55:
        return "neutral"
    return "miss"


MARKET_CONFIG = {
    "result": {
        "prob_key": "prob_result",
    },
    "over25": {
        "prob_key": "prob_over25",
        "positive_label": True,
    },
    "under25": {
        "prob_key": "prob_under25",
        "positive_label": True,
    },
    "btts": {
        "prob_key": "prob_btts",
        "positive_label": True,
    },
    "corners_over10": {
        "prob_key": "prob_corners_over10",
        "positive_label": True,
    },
}


def evaluate_match_models(match, analysis_v31, analysis_v32):
    real = get_real_outcome(match)

    for model_version, analysis in [
        ("v3.1", analysis_v31),
        ("v3.2", analysis_v32),
    ]:
        for market, config in MARKET_CONFIG.items():

            # -------- probabilidade prevista --------
            if market == "result":
                prob = max(analysis["prob_result"].values())
                real_value = real["result"]

            elif market == "first_goal":
                prob = analysis["prob_first_goal"][real["first_goal"]]
                real_value = real["first_goal"]

            else:
                prob = analysis[config["prob_key"]]
                real_value = str(real[market])

            # -------- avaliar --------
            result = evaluate_market(
                prob=prob,
                real=real[market] if market != "result" else None,
                positive_label=config.get("positive_label", True),
            )

            # -------- salvar (idempotente) --------
            MatchModelEvaluation.objects.update_or_create(
                match=match,
                model_version=model_version,
                market=market,
                defaults={
                    "result": result,
                    "probability": prob,
                    "real_value": real_value,
                },
            )
