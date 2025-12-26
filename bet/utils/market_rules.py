MARKET_RULES = {
    "goals": {
        "home_weight": 0.6,
        "away_weight": 0.4,
        "h2h_weight": 0.3,
    },
    "btts": {
        "home_weight": 0.6,
        "away_weight": 0.4,
        "h2h_weight": 0.3,
    },
    "corners": {
        "home_weight": 0.5,
        "away_weight": 0.5,
        "h2h_weight": 0.3,
    },
    "cards": {
        "home_weight": 0.5,
        "away_weight": 0.5,
        "h2h_weight": 0.3,
    },
    "first_goal": {
        "home_weight": 0.65,
        "away_weight": 0.35,
        "h2h_weight": 0.3,
    },
}

MARKET_TYPE_MAP = {
    "More than 2.5 goals": "goals",
    "Less than 2.5 goals": "goals",
    "Both teams scoring": "btts",
    "More than 10.5 corners": "corners",
    "Less than 10.5 corners": "corners",
    "More than 4.5 cards": "cards",
    "Less than 4.5 cards": "cards",
    "First to score": "first_goal",
}
