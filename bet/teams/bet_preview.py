def bet_recommendations(home, away, preview):
    corners_total, corners_line = corners_line_estimate(home, away)
    cards_total, cards_market = cards_estimate(home, away, preview)

    return {
        "first_goal": first_goal_market(home, away),
        "corners_side": corners_side_market(home, away),
        "corners_total": round(corners_total, 1),
        "corners_line": corners_line,
        "cards_total": cards_total,
        "cards_market": cards_market,
    }


def first_goal_market(home, away):
    home_score = (
        home["xg_for"] * 1.2 + home["pressure_index"] * 0.03 - home["xg_against"] * 0.6
    )

    away_score = (
        away["xg_for"] * 1.2 + away["pressure_index"] * 0.03 - away["xg_against"] * 0.6
    )

    if home_score > away_score * 1.15:
        return "Casa"
    elif away_score > home_score * 1.15:
        return "Fora"
    else:
        return "Sem valor"


def corners_side_market(home, away):
    home_score = home["corners_for"] * 0.6 + away["corners_against"] * 0.4
    away_score = away["corners_for"] * 0.6 + home["corners_against"] * 0.4

    if home_score > away_score * 1.15:
        return "Casa"
    elif away_score > home_score * 1.15:
        return "Fora"
    else:
        return "Equilibrado"


def corners_line_estimate(home, away):
    total = (
        home["corners_for"]
        + away["corners_for"]
        + home["corners_against"]
        + away["corners_against"]
    ) / 2

    if total >= 11:
        return total, "Over 9.5 / 10.5"
    elif total >= 9:
        return total, "Over 8.5"
    elif total >= 7:
        return total, "Linha 7.5"
    else:
        return total, "Under"


def cards_estimate(home, away, preview):
    base = 3.5

    # jogos equilibrados
    if abs(home["xg_for"] - away["xg_for"]) < 0.4:
        base += 0.5

    # pressão ofensiva
    if home["pressure_index"] + away["pressure_index"] > 60:
        base += 0.7

    # BTTS alto costuma gerar mais cartões
    if preview["btts"] >= 60:
        base += 0.5

    if base >= 5:
        return round(base, 1), "Over 4.5 cartões"
    elif base >= 4:
        return round(base, 1), "Over 3.5 cartões"
    else:
        return round(base, 1), "Linha baixa"
