import numpy as np

WEIGHTS = np.arange(0.2, 0.9, 0.05)


def calibrate_weights(decisions, market):
    best_roi = -999
    best_weights = None

    for wh in WEIGHTS:
        for wa in WEIGHTS:
            for w2 in WEIGHTS:
                if wh + wa + w2 == 0:
                    continue

                profit = 0
                stake = 1  # stake fixa

                for d in decisions:
                    if d.market != market:
                        continue

                    probs = []
                    if d.prob_home is not None:
                        probs.append(d.prob_home * wh)
                    if d.prob_away is not None:
                        probs.append(d.prob_away * wa)
                    if d.prob_h2h is not None:
                        probs.append(d.prob_h2h * w2)

                    if not probs:
                        continue

                    p = sum(probs) / (wh + wa + w2)

                    if p > d.book_prob:
                        if d.result:
                            profit += stake * (d.odd - 1)
                        else:
                            profit -= stake

                roi = profit / max(1, len(decisions))

                if roi > best_roi:
                    best_roi = roi
                    best_weights = (wh, wa, w2)

    return best_weights, best_roi
