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
        base = 15
    else:
        base = 0

    bonus = 0
    bonus_labels = []

    if 0 < base < 100:
        # +5 Sharp Total: predicted total goals == actual total goals
        if hp + ap == ha + aa:
            bonus += 5
            bonus_labels.append("Sharp Total")

        # +5 Clean Sheet Caller: predicted correct team to keep a clean sheet
        if pred_result == actual_result:
            if ap == 0 and aa == 0:
                bonus += 5
                bonus_labels.append("Clean Sheet Caller")
            elif hp == 0 and ha == 0:
                bonus += 5
                bonus_labels.append("Clean Sheet Caller")

    return {
        "base": base,
        "bonus": bonus,
        "bonus_labels": bonus_labels,
        "total": base + bonus,
    }
