from decimal import Decimal, InvalidOperation

from typing import Optional

from bet.models import Bet
from django.db import models


def generate_bankroll_alerts(bankroll):
    alerts = []

    # 1) Histórico das últimas apostas
    last_bets = Bet.objects.filter(bankroll=bankroll).order_by("-created_at")[:20]

    # Se não houver apostas ainda
    if not last_bets:
        return ["📘 Ainda não há histórico suficiente para análise da banca."]

    # 2) Sequência de reds
    reds = 0
    for bet in last_bets:
        if bet.result == "RED":
            reds += 1
        else:
            break

    if reds >= 3:
        alerts.append(f"⚠️ Atenção! Você está em sequência de {reds} reds seguidos. "
                      "Reduza a stake para proteger a banca.")

    # 3) Lucro total da banca
    profit = bankroll.balance - bankroll.initial_balance

    if profit < 0:
        alerts.append(
            f"❗ Você está no prejuízo: R$ {abs(profit):.2f}. "
            "Mantenha disciplina e reduza a exposição."
        )

        # Quantos greens seriam necessários para recuperar?
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

    # 4) Stake média — alerta de agressividade
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


def parse_decimal_input(raw_value: Optional[str]) -> Decimal:
    """Parseia valores numéricos vindos de formulários.

    Aceita vírgulas ou pontos como separador decimal e levanta ``ValueError``
    quando o valor for vazio ou inválido. Mantemos a responsabilidade de
    tratar o erro no chamador para permitir mensagens específicas.
    """

    if raw_value is None:
        raise ValueError("Valor ausente")

    try:
        cleaned_value = raw_value.replace(",", ".").strip()
        return Decimal(cleaned_value)
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("Valor inválido") from exc


class SofaStatParser:
    """Ajuda a extrair dados limpos do JSON complexo do SofaScore."""

    def __init__(self, stats_json):
        self.data = stats_json.get('statistics', [])

    def get_stats(self, period="ALL"):
        # Encontrar o grupo do período correto
        period_group = next((item for item in self.data if item["period"] == period), None)
        if not period_group:
            return {}

        stats = {}
        # Mapeamento: Chave do JSON -> Nome da nossa variável interna
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
            "duelWonPercent": "duels_won_pct"
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

    # =========================================================================
    # 1. ANÁLISE DE STREAKS (HISTÓRICO/PRÉ-JOGO) - O método que faltava
    # =========================================================================
    def analyze_streaks(self, streaks_data):
        """
        Analisa tendências históricas e H2H com pesos diferentes.
        Retorna insights e fatores de impacto para ajuste de odds.
        """
        analyzed = {"general": [], "head2head": [], "impact": {"goals_over": 0, "btts": 0, "momentum": 0}}

        # Pesos: H2H vale mais
        impact_weights = {"general": 1.0, "head2head": 1.5}

        def parse_ratio(v):
            if isinstance(v, (int, float)): return float(v)
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

                # Lógica de impacto
                weight = impact_weights.get(group, 1.0)
                if ratio >= 0.70:
                    if "over 2.5" in name or "goals" in name:
                        analyzed["impact"]["goals_over"] += (1 * weight)
                    if "btts" in name or "both teams" in name:
                        analyzed["impact"]["btts"] += (1 * weight)

                analyzed[group].append({
                    "name": item.get("name"),
                    "team": team,
                    "ratio": ratio,
                    "hot_streak": ratio >= 0.80,
                    "text": f"{team.capitalize()}: {item.get('name')} ({int(ratio * 100)}%)"
                })

        return analyzed

    # =========================================================================
    # 2. CÁLCULO DE PRESSÃO (AUXILIAR)
    # =========================================================================
    def calculate_advanced_pressure(self, stats):
        """Calcula pressão 0-100 baseada em métricas avançadas."""

        def calc_team_pressure(xg, shots, corners, final_third, box_touches, possession):
            score = 0
            score += xg * 40
            score += shots * 2
            score += corners * 3
            score += final_third * 0.5
            score += box_touches * 1.5
            if possession > 65: score += 10
            return min(score, 100)

        p_home = calc_team_pressure(
            stats.get('xg_home', 0), stats.get('shots_home', 0),
            stats.get('corners_home', 0), stats.get('final_third_home', 0),
            stats.get('box_touches_home', 0), stats.get('possession_home', 0)
        )

        p_away = calc_team_pressure(
            stats.get('xg_away', 0), stats.get('shots_away', 0),
            stats.get('corners_away', 0), stats.get('final_third_away', 0),
            stats.get('box_touches_away', 0), stats.get('possession_away', 0)
        )

        # Normalização percentual para barra de progresso
        total = p_home + p_away
        if total == 0: return 50, 50
        return round((p_home / total) * 100), round((p_away / total) * 100)

    # =========================================================================
    # 3. ANÁLISE AO VIVO (JSON) - O método novo
    # =========================================================================
    def analyze_json_data(self, stats_json, event_json):
        """Analisa o jogo ao vivo usando os JSONs salvos no banco."""
        parser = SofaStatParser(stats_json)
        stats = parser.get_stats(period="ALL")

        if not stats:
            return {"insights": [], "suggestions": [], "pressure_index": {"home": 50, "away": 50}}

        # Tenta pegar placar
        try:
            home_score = event_json.get('homeScore', {}).get('current', 0)
            away_score = event_json.get('awayScore', {}).get('current', 0)
            # Tentar achar minuto no status ou changes (fallback)
            minute = 0
            if 'status' in event_json:
                # Depende de como vem o JSON, às vezes vem description "85'"
                pass
        except:
            home_score = 0
            away_score = 0

        # Pressão
        pressure_h, pressure_a = self.calculate_advanced_pressure(stats)

        insights = []
        suggestions = []

        # -- Lógica de Insights --

        # 1. Domínio Territorial
        if stats.get('final_third_home', 0) > stats.get('final_third_away', 0) * 1.5:
            if stats.get('xg_home', 0) < 0.5:
                insights.append(f"{self.home_name} tem domínio territorial, mas cria pouco perigo real.")

        # 2. xG vs Gols (Azar)
        if (stats.get('xg_home', 0) - home_score) > 1.0:
            insights.append(f"🔥 {self.home_name} merece o gol! xG alto ({stats['xg_home']}) sem marcar.")
            suggestions.append("Gol Home")

        if (stats.get('xg_away', 0) - away_score) > 1.0:
            insights.append(f"🔥 {self.away_name} merece o gol! xG alto ({stats['xg_away']}) sem marcar.")
            suggestions.append("Gol Away")

        # 3. Jogo Aberto
        total_final_third = stats.get('final_third_home', 0) + stats.get('final_third_away', 0)
        if total_final_third > 70:
            insights.append("Jogo aberto: Muitas chegadas no ataque de ambos os lados.")

        return {
            "pressure_index": {"home": pressure_h, "away": pressure_a},
            "stats_window": {
                "corners": int(stats.get('corners_home', 0) + stats.get('corners_away', 0)),
                "shots": int(stats.get('shots_home', 0) + stats.get('shots_away', 0)),
                "xg_home": stats.get('xg_home', 0),
                "xg_away": stats.get('xg_away', 0)
            },
            "insights": insights,
            "suggestions": list(set(suggestions))
        }