def parse_ratio(value):
    if "/" not in value:
        return None
    try:
        x, y = value.split("/")
        return int(x) / int(y)
    except Exception:
        return None


def calculate_market_prob(match_data, market_name):
    from .market_rules import MARKET_RULES, MARKET_TYPE_MAP

    market_type = MARKET_TYPE_MAP.get(market_name)
    if not market_type:
        return None

    rules = MARKET_RULES[market_type]

    home_probs = []
    away_probs = []
    h2h_probs = []

    for item in match_data.get("general", []):
        if item["name"].lower() == market_name.lower():
            p = parse_ratio(item["value"])
            if not p:
                continue

            if item["team"] == "home":
                home_probs.append(p)
            elif item["team"] == "away":
                away_probs.append(p)

    for item in match_data.get("head2head", []):
        if item["name"].lower() == market_name.lower():
            p = parse_ratio(item["value"])
            if p:
                h2h_probs.append(p)

    total = 0
    weight_sum = 0

    if home_probs:
        total += (sum(home_probs) / len(home_probs)) * rules["home_weight"]
        weight_sum += rules["home_weight"]

    if away_probs:
        total += (sum(away_probs) / len(away_probs)) * rules["away_weight"]
        weight_sum += rules["away_weight"]

    if h2h_probs:
        total += (sum(h2h_probs) / len(h2h_probs)) * rules["h2h_weight"]
        weight_sum += rules["h2h_weight"]

    if weight_sum == 0:
        return None

    return total / weight_sum


def classify_confidence(model_prob, book_prob):
    diff = model_prob - book_prob

    if diff >= 0.10:
        return "FORTE"
    if diff >= 0.05:
        return "MÉDIO"
    if diff >= 0.02:
        return "FRACO"
    return "SEM VALOR"


def split_market_probs(match_data, market_name):
    def parse_ratio(v):
        if "/" not in v:
            return None
        x, y = v.split("/")
        return int(x) / int(y)

    home = []
    away = []
    h2h = []

    for item in match_data.get("general", []):
        if item["name"].lower() == market_name.lower():
            p = parse_ratio(item["value"])
            if not p:
                continue
            if item["team"] == "home":
                home.append(p)
            elif item["team"] == "away":
                away.append(p)

    for item in match_data.get("head2head", []):
        if item["name"].lower() == market_name.lower():
            p = parse_ratio(item["value"])
            if p:
                h2h.append(p)

    return (
        sum(home) / len(home) if home else None,
        sum(away) / len(away) if away else None,
        sum(h2h) / len(h2h) if h2h else None,
    )
