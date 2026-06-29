"""
The fixed bracket skeleton — "winner advances to the correct next slot".

Slot ids 73..104 are STABLE and hardcoded (only the R32 team names vary by
tournament). When a match's winner is decided they flow into the listed next
slot. The 3rd-place match (id 103) is intentionally absent — the bracket game
ignores it.

This is the part that matters most: a wrong feed edge silently corrupts scoring.
It is encoded once here and unit-tested in tests/test_bracket_skeleton.py.

NOTE: the football-data.org API uses its OWN match ids for the knockout fixtures
(e.g. 537417). scripts/seed_bracket.py maps those API ids onto these skeleton
slot ids; nothing else in the app assumes the API's numbering.
"""

# Slot ids per round, in display order.
ROUNDS = {
    "R32":   list(range(73, 89)),               # 73..88  (16 matches)
    "R16":   [89, 90, 91, 92, 93, 94, 95, 96],  # 8 matches
    "QF":    [97, 98, 99, 100],                  # 4 matches
    "SF":    [101, 102],                         # 2 matches
    "FINAL": [104],                              # 1 match
}

ROUND_ORDER = ["R32", "R16", "QF", "SF", "FINAL"]

ROUND_LABELS = {
    "R32": "Round of 32",
    "R16": "Round of 16",
    "QF": "Quarter-Finals",
    "SF": "Semi-Finals",
    "FINAL": "Final",
}

# For each downstream match: (home_feeder_slot, away_feeder_slot).
# The winner of the home feeder occupies the home slot; the away feeder the away.
#
# STANDARD ADJACENCY: adjacent R32 winners meet in the R16, and so on, with the
# two halves meeting only in the Final. R32 match N lives in slot 72+N, so:
#   R16_1 = winner(1) vs winner(2)  -> slot 89 = (73, 74), etc.
# This mirrors data/bracket_r32.py — slots 73..80 are the LEFT half, 81..88 the
# RIGHT half, and they cannot meet before the Final.
FEEDS = {
    # Round of 16  (each = two adjacent R32 winners)
    89: (73, 74),   # R16_1 = winner(1)  vs winner(2)
    90: (75, 76),   # R16_2 = winner(3)  vs winner(4)
    91: (77, 78),   # R16_3 = winner(5)  vs winner(6)
    92: (79, 80),   # R16_4 = winner(7)  vs winner(8)
    93: (81, 82),   # R16_5 = winner(9)  vs winner(10)
    94: (83, 84),   # R16_6 = winner(11) vs winner(12)
    95: (85, 86),   # R16_7 = winner(13) vs winner(14)
    96: (87, 88),   # R16_8 = winner(15) vs winner(16)
    # Quarter-finals
    97: (89, 90),   # QF_1 = winner(R16_1) vs winner(R16_2)
    98: (91, 92),   # QF_2 = winner(R16_3) vs winner(R16_4)
    99: (93, 94),   # QF_3 = winner(R16_5) vs winner(R16_6)
    100: (95, 96),  # QF_4 = winner(R16_7) vs winner(R16_8)
    # Semi-finals
    101: (97, 98),  # SF_1 = winner(QF_1) vs winner(QF_2)   — LEFT half
    102: (99, 100), # SF_2 = winner(QF_3) vs winner(QF_4)   — RIGHT half
    # Final
    104: (101, 102),
}

# When a pick is made in a round, which scoring-round set does it populate.
# (picks of R32 matches = the 16 teams advanced INTO the R16, etc.)
PICK_ROUND_TO_SCORE_ROUND = {
    "R32": "R16",
    "R16": "QF",
    "QF": "SF",
    "SF": "FINAL",
    "FINAL": "CHAMPION",
}

ALL_SLOTS = [mid for r in ROUND_ORDER for mid in ROUNDS[r]]


def round_of(match_id):
    """Return the round key a slot id belongs to, or None."""
    for r, ids in ROUNDS.items():
        if match_id in ids:
            return r
    return None


# Reverse of FEEDS: feeder_slot -> (downstream_match_id, "home"|"away").
def _build_next_slot():
    nxt = {}
    for downstream, (home_src, away_src) in FEEDS.items():
        nxt[home_src] = (downstream, "home")
        nxt[away_src] = (downstream, "away")
    return nxt


NEXT_SLOT = _build_next_slot()


def next_slot(match_id):
    """Where the winner of `match_id` advances: (downstream_match_id, position)
    or None for the Final (id 104)."""
    return NEXT_SLOT.get(match_id)


def predicted_sets_from_picks(picks: dict) -> dict:
    """
    Derive the scoring-round predicted sets from a user's picks.

    picks: {match_id: picked_team}. Returns a dict keyed by scoring round
    ("R16","QF","SF","FINAL","CHAMPION"). CHAMPION is a single team (or None).
    """
    out = {"R16": set(), "QF": set(), "SF": set(), "FINAL": set(), "CHAMPION": None}
    for pick_round in ROUND_ORDER:
        score_round = PICK_ROUND_TO_SCORE_ROUND[pick_round]
        teams = set()
        for mid in ROUNDS[pick_round]:
            t = picks.get(mid)
            if t:
                teams.add(t)
        if score_round == "CHAMPION":
            out["CHAMPION"] = next(iter(teams), None)
        else:
            out[score_round] = teams
    return out
