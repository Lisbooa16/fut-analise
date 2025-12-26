# bet/utils/market_suggest.py

from bet.utils.market_engine import calculate_market_prob


def suggest_best_market(match, odds_by_market):
    suggestions = []

    for market, odd in odds_by_market.items():
        prob = calculate_market_prob(match.streaks_json, market)

        if prob is None:
            print(f"DEBUG: {market} -> prob=None (sem dados no streaks)")
            continue

        book_prob = 1 / float(odd)
        edge = prob - book_prob

        print(
            f"DEBUG: {market} | "
            f"model_prob={round(prob*100,1)}% | "
            f"book_prob={round(book_prob*100,1)}% | "
            f"edge={round(edge*100,1)}%"
        )

        if edge <= 0:
            continue

        suggestions.append(
            {
                "market": market,
                "odd": odd,
                "model_prob": round(prob * 100, 1),
                "book_prob": round(book_prob * 100, 1),
                "edge": round(edge * 100, 1),
            }
        )

    suggestions.sort(key=lambda x: x["edge"], reverse=True)
    return suggestions
