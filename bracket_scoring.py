"""
Bracket Game scoring — pure functions, no DB.

Round-INDEPENDENT scoring via set intersection: each round is scored on its own
by intersecting the set of teams the user PREDICTED would reach that round with
the set of teams that ACTUALLY reached it. A busted early bracket can still score
later rounds.

The five scoring rounds (keyed by the actual set they intersect against):

    "R16"      predicted_R16 (16 teams advanced out of R32)  ∩ actual R16
    "QF"       predicted_QF  (8 teams advanced out of R16)   ∩ actual QF
    "SF"       predicted_SF  (4 teams advanced out of QF)    ∩ actual SF
    "FINAL"    predicted_finalists (2 advanced out of SF)    ∩ actual finalists
    "CHAMPION" predicted_champion (Final pick)               == actual champion

Grand total max = 1700.

Every per-correct value and bonus threshold lives in BRACKET_POINTS below so the
whole game can be tuned without touching logic. Bonuses are ADDITIVE on top of
the per-correct base. Bonus bands are checked in order; the first match wins
(perfect band is listed first), and bands never overlap.
"""

# ── Tunable config — change values here, never the logic below ────────────────

BRACKET_POINTS = {
    "R16": {        # scored from R32 picks: which 16 teams reach the Round of 16
        "counted": 16,
        "per_correct": 10,
        "bonuses": [
            {"label": "Perfect", "min": 16, "max": 16, "points": 90},   # 16/16 -> +90
            {"label": "Sharp",   "min": 13, "max": 15, "points": 30},   # 13-15 -> +30
        ],
    },
    "QF": {         # scored from R16 picks: which 8 teams reach the Quarter-Finals
        "counted": 8,
        "per_correct": 20,
        "bonuses": [
            {"label": "Perfect", "min": 8, "max": 8, "points": 90},     # 8/8 -> +90
            {"label": "Sharp",   "min": 7, "max": 7, "points": 40},     # 7/8 -> +40
        ],
    },
    "SF": {         # scored from QF picks: which 4 teams reach the Semi-Finals
        "counted": 4,
        "per_correct": 50,
        "bonuses": [
            {"label": "Perfect", "min": 4, "max": 4, "points": 100},    # 4/4 -> +100
        ],
    },
    "FINAL": {      # scored from SF picks: which 2 teams reach the Final
        "counted": 2,
        "per_correct": 150,
        "bonuses": [
            {"label": "Perfect", "min": 2, "max": 2, "points": 100},    # 2/2 -> +100
        ],
    },
    "CHAMPION": {   # scored from the Final pick: the actual champion
        "counted": 1,
        "per_correct": 500,
        "bonuses": [],
    },
}

# Order rounds are scored / displayed in.
BRACKET_ROUNDS = ["R16", "QF", "SF", "FINAL", "CHAMPION"]


def _as_set(x):
    """Normalize a prediction/actual value into a set of team names."""
    if x is None:
        return set()
    if isinstance(x, str):
        return {x}
    return set(x)


def score_round(round_key, predicted, actual) -> dict:
    """
    Score a single round by set intersection.

    round_key : one of BRACKET_ROUNDS
    predicted : iterable of team names the user advanced into this round
                (or a single team name / None for CHAMPION)
    actual    : iterable of team names that actually reached this round
                (or a single team name / None for CHAMPION)

    Returns {round, correct_count, base_points, bonus_points, bonus_label, total_points}.
    """
    cfg = BRACKET_POINTS[round_key]
    correct = len(_as_set(predicted) & _as_set(actual))

    base = correct * cfg["per_correct"]

    bonus = 0
    bonus_label = ""
    for band in cfg["bonuses"]:
        if band["min"] <= correct <= band["max"]:
            bonus = band["points"]
            bonus_label = band.get("label", "")
            break

    return {
        "round": round_key,
        "correct_count": correct,
        "base_points": base,
        "bonus_points": bonus,
        "bonus_label": bonus_label,
        "total_points": base + bonus,
    }


def score_bracket(predicted: dict, actual: dict) -> dict:
    """
    Score a full bracket across every round that has actual results available.

    predicted / actual are dicts keyed by round:
        {"R16": <16 teams>, "QF": <8>, "SF": <4>, "FINAL": <2 finalists>,
         "CHAMPION": <team or None>}

    A round is only included in the breakdown if `actual` provides a non-empty
    value for it (i.e. that round's real results are final). Returns
    {"rounds": {round: result, ...}, "total_points": int}.
    """
    breakdown = {}
    total = 0
    for rk in BRACKET_ROUNDS:
        if rk not in actual or not _as_set(actual.get(rk)):
            continue
        res = score_round(rk, predicted.get(rk), actual.get(rk))
        breakdown[rk] = res
        total += res["total_points"]
    return {"rounds": breakdown, "total_points": total}


def round_max(round_key) -> int:
    """Maximum possible points for a round (per-correct * counted + best bonus)."""
    cfg = BRACKET_POINTS[round_key]
    base = cfg["counted"] * cfg["per_correct"]
    best_bonus = max((b["points"] for b in cfg["bonuses"]), default=0)
    return base + best_bonus


def grand_total_max() -> int:
    return sum(round_max(rk) for rk in BRACKET_ROUNDS)
