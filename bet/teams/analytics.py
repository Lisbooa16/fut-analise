import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def get_stat(stats: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """
    stats: dict aggregated: {key: {"avg": ..., ...}}
    """
    try:
        return float(stats.get(key, {}).get("avg", default))
    except Exception:
        return default


def label_from_prob(p: float) -> str:
    if p >= 0.70:
        return "Muito alta"
    if p >= 0.60:
        return "Alta"
    if p >= 0.50:
        return "Média"
    if p >= 0.40:
        return "Baixa"
    return "Muito baixa"


@dataclass
class Prediction:
    key: str
    title: str
    prob: float  # 0.0–1.0
    prob_percent: int  # 0–100
    label: str
    note: str


def build_predictions(team_stats: Dict[str, Any]) -> Dict[str, Prediction]:
    """
    Heurística simples: usa apenas estatísticas do time.
    Para ficar realmente bom, depois a gente adiciona stats do adversário + liga.
    """
    xg = get_stat(team_stats, "expectedGoals", 0.0)
    shots_ot = get_stat(team_stats, "shotsOnGoal", 0.0)
    shots_total = get_stat(
        team_stats, "totalShotsOnGoal", 0.0
    )  # no seu dataset o key é esse
    big_created = get_stat(team_stats, "bigChanceCreated", 0.0)
    touches_box = get_stat(team_stats, "touchesInOppBox", 0.0)
    corners = get_stat(team_stats, "cornerKicks", 0.0)

    # --- Over 1.5 (proxy do volume ofensivo)
    # Baseado em xG + finalizações no alvo + big chances + presença na área
    over15_score = (
        (xg - 1.2) * 1.2
        + (shots_ot - 4.0) * 0.25
        + (big_created - 2.0) * 0.35
        + (touches_box - 18.0) * 0.05
    )
    p_over15 = clamp(sigmoid(over15_score))

    # --- Over 2.5 (mais exigente)
    over25_score = (
        (xg - 1.6) * 1.25
        + (shots_ot - 5.0) * 0.22
        + (big_created - 2.5) * 0.40
        + (shots_total - 13.0) * 0.06
    )
    p_over25 = clamp(sigmoid(over25_score))

    # --- BTTS (aqui é fraco sem xGA do adversário / sofrido)
    # Como ainda não temos "xG contra", usamos proxy: jogo aberto tende a BTTS.
    btts_score = (xg - 1.3) * 0.9 + (shots_ot - 4.5) * 0.20 + (corners - 4.5) * 0.10
    p_btts = clamp(
        sigmoid(btts_score) * 0.85
    )  # rebaixa pq está incompleto (sem defesa)

    # --- Over corners 8.5 (bem útil)
    # Se time tem corners alto + toque na área + chutes = tendência de corners
    corners_score = (
        (corners - 4.5) * 0.9
        + (touches_box - 18.0) * 0.04
        + (shots_total - 12.0) * 0.05
    )
    p_corners_over = clamp(sigmoid(corners_score))

    preds = {
        "over_1_5": Prediction(
            key="over_1_5",
            title="Over 1.5 gols",
            prob=p_over15,
            prob_percent=round(p_over15 * 100),
            label=label_from_prob(p_over15),
            note="Baseado em xG, chutes no alvo, big chances e presença na área.",
        ),
        "over_2_5": Prediction(
            key="over_2_5",
            title="Over 2.5 gols",
            prob=p_over25,
            prob_percent=round(p_over15 * 100),
            label=label_from_prob(p_over25),
            note="Mais conservador; exige volume e qualidade ofensiva maiores.",
        ),
        "btts": Prediction(
            key="btts",
            title="BTTS (Ambos marcam)",
            prob=p_btts,
            prob_percent=round(p_over15 * 100),
            label=label_from_prob(p_btts),
            note="Sem stats defensivas do adversário é uma estimativa parcial.",
        ),
        "corners_over": Prediction(
            key="corners_over",
            title="Over 8.5 escanteios (tendência)",
            prob=p_corners_over,
            prob_percent=round(p_over15 * 100),
            label=label_from_prob(p_corners_over),
            note="Boa correlação com pressão ofensiva (toques na área/chutes).",
        ),
    }
    return preds


def extract_xg_for_against(match, team):
    data = match.raw_statistics_json

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return None, None

    if not isinstance(data, dict):
        return None, None

    side = "home" if match.home_team_id == team.id else "away"
    opp_side = "away" if side == "home" else "home"

    for block in data.get("statistics", []):
        if block.get("period") != "ALL":
            continue

        for group in block.get("groups", []):
            for item in group.get("statisticsItems", []):
                if item.get("key") == "expectedGoals":
                    xg_for = item.get(f"{side}Value")
                    xg_against = item.get(f"{opp_side}Value")
                    return xg_for, xg_against

    return None, None


def team_profile(team, matches):
    xg_for, xg_against = [], []
    corners_for, corners_against = [], []
    shots_for, shots_against = [], []
    shots_in_box_for, shots_in_box_against = [], []
    touches_box_for = []

    for match in matches:
        xgf, xga = extract_xg_for_against(match, team)
        if xgf is not None:
            xg_for.append(xgf)
        if xga is not None:
            xg_against.append(xga)

        data = match.raw_statistics_json
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                continue

        if not isinstance(data, dict):
            continue

        side = "home" if match.home_team_id == team.id else "away"
        opp = "away" if side == "home" else "home"

        for block in data.get("statistics", []):
            if block.get("period") != "ALL":
                continue

            for group in block.get("groups", []):
                for item in group.get("statisticsItems", []):

                    key = item.get("key")

                    if key == "cornerKicks":
                        corners_for.append(item.get(f"{side}Value", 0))
                        corners_against.append(item.get(f"{opp}Value", 0))

                    if key == "totalShotsOnGoal":
                        shots_for.append(item.get(f"{side}Value", 0))
                        shots_against.append(item.get(f"{opp}Value", 0))

                    if key == "totalShotsInsideBox":
                        shots_in_box_for.append(item.get(f"{side}Value", 0))
                        shots_in_box_against.append(item.get(f"{opp}Value", 0))

                    if key == "touchesInOppBox":
                        touches_box_for.append(item.get(f"{side}Value", 0))

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    return {
        "xg_for": avg(xg_for),
        "xg_against": avg(xg_against),
        "corners_for": avg(corners_for),
        "corners_against": avg(corners_against),
        "shots_for": avg(shots_for),
        "shots_against": avg(shots_against),
        "shots_in_box_for": avg(shots_in_box_for),
        "shots_in_box_against": avg(shots_in_box_against),
        "touches_box_for": avg(touches_box_for),
        "pressure_index": (avg(touches_box_for) * 0.4 + avg(shots_in_box_for) * 0.4),
    }


def match_preview(home, away):
    expected_goals_total = (
        home["xg_for"] * 0.55
        + away["xg_for"] * 0.45
        + home["xg_against"] * 0.45
        + away["xg_against"] * 0.55
    )

    over25_prob = min(0.9, max(0.1, (expected_goals_total - 1.8) / 1.2))
    btts_prob = min(
        0.85, max(0.15, (home["xg_for"] > 1.0) + (away["xg_for"] > 1.0)) / 2
    )

    corners_total = (
        home["corners_for"]
        + away["corners_for"]
        + home["corners_against"]
        + away["corners_against"]
    ) / 2

    if corners_total >= 9:
        corners_label = "Alta"
        corners_score = 80
    elif corners_total >= 7:
        corners_label = "Média"
        corners_score = 55
    else:
        corners_label = "Baixa"
        corners_score = 30

    return {
        "expected_goals": round(expected_goals_total, 2),
        "over_2_5": round(over25_prob * 100),
        "btts": round(btts_prob * 100),
        "corners_over_8_5": (
            "Alta" if corners_total >= 9 else "Média" if corners_total >= 7 else "Baixa"
        ),
        "corners_score": corners_score,
    }
