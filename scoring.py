def _sign(x):
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def score_prediction(hp, ap, ha, aa) -> dict:
    """
    hp, ap = home/away prediction
    ha, aa = home/away actual
    Returns {"base": int, "bonus": int, "bonus_labels": [str], "total": int}
    """
    pred_result = _sign(hp - ap)
    actual_result = _sign(ha - aa)
    pred_margin = hp - ap
    actual_margin = ha - aa

    # Base tiers — first match wins
    if hp == ha and ap == aa:
        base = 100
    elif pred_result == actual_result and pred_margin == actual_margin:
        base = 60
    elif pred_result == actual_result:
        base = 40
    elif abs(hp - ha) + abs(ap - aa) == 1:
        base = 20
    else:
        base = 0

    bonus = 0
    bonus_labels = []

    if base > 0:
        # +10 Sharp Total: predicted total == actual total, but not exact score
        if hp + ap == ha + aa and base < 100:
            bonus += 10
            bonus_labels.append("Sharp Total")

        # +10 Brave Call: predicted a draw and it was a draw
        if pred_result == 0 and actual_result == 0 and base >= 50:
            bonus += 10
            bonus_labels.append("Brave Call")

        # +15 Clean Sheet Caller: predicted correct team to keep a clean sheet
        # "predicted X-0 with correct result, actual was also X-0 shape for that side"
        if pred_result == actual_result:
            # home team kept clean sheet
            if ap == 0 and aa == 0:
                bonus += 15
                bonus_labels.append("Clean Sheet Caller")
            # away team kept clean sheet
            elif hp == 0 and ha == 0:
                bonus += 15
                bonus_labels.append("Clean Sheet Caller")

    return {
        "base": base,
        "bonus": bonus,
        "bonus_labels": bonus_labels,
        "total": base + bonus,
    }
