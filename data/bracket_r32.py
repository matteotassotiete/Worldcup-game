"""
Hardcoded Round-of-32 matchups — the SOURCE OF TRUTH for the bracket game.

The group stage is over and all 32 teams are confirmed, so we no longer infer
matchups from API standings / group-slot logic. This list is authoritative.

  • Match numbers 1..16 map to skeleton slot ids 73..88  (slot = 72 + match_no).
  • (home, away) are just the two teams in each R32 game.
  • The LEFT half (matches 1..8) and RIGHT half (matches 9..16) only meet in the
    Final. The winner-advancement wiring lives in bracket_skeleton.FEEDS (standard
    adjacency: 1&2 -> R16_1, 3&4 -> R16_2, ...).

To correct a team name, edit it on its line below and re-run
    python3 scripts/seed_bracket.py --force
Trivially editable by design — one name per line.
"""

# match_no: (home, away)
R32_MATCHUPS = {
    # ── LEFT HALF (winners flow down the left side to one finalist) ──
    1:  ("Germany",       "Paraguay"),
    2:  ("France",        "Sweden"),
    3:  ("South Africa",  "Canada"),
    4:  ("Morocco",       "Netherlands"),
    5:  ("Portugal",      "Croatia"),
    6:  ("Spain",         "Austria"),
    7:  ("USA",           "Bosnia and Herzegovina"),
    8:  ("Belgium",       "Senegal"),
    # ── RIGHT HALF (winners flow down the right side to the other finalist) ──
    9:  ("Brazil",        "Japan"),
    10: ("Ivory Coast",   "Norway"),
    11: ("Mexico",        "Ecuador"),
    12: ("England",       "DR Congo"),
    13: ("Argentina",     "Cape Verde"),
    14: ("Australia",     "Egypt"),
    15: ("Switzerland",   "Algeria"),
    16: ("Colombia",      "Ghana"),
}

# Skeleton slot id for an R32 match number (matches bracket_skeleton.ROUNDS["R32"]).
SLOT_BASE = 72


def slot_for_match(match_no):
    """R32 match number (1..16) -> skeleton slot id (73..88)."""
    return SLOT_BASE + match_no


def matchups_by_slot():
    """{slot_id: (home, away)} for the 16 R32 slots, keyed by skeleton slot id."""
    return {SLOT_BASE + n: pair for n, pair in R32_MATCHUPS.items()}


def all_teams():
    """The 32 team names, in match order."""
    teams = []
    for n in sorted(R32_MATCHUPS):
        teams.extend(R32_MATCHUPS[n])
    return teams
