"""
Shared bracket helpers used by the web app, the seed script and the settler.

All functions take a db handle (the project's get_db() wrapper) so this module
has no Flask dependency and no import cycle with app.py.
"""
from datetime import datetime, timezone

from bracket_skeleton import ROUNDS, ROUND_ORDER, PICK_ROUND_TO_SCORE_ROUND

# Which actual-result round feeds each scoring round's "teams that reached it" set.
# (advancing teams of R32 matches = the teams that actually reached the R16, etc.)
SCORE_ROUND_SOURCE = {v: k for k, v in PICK_ROUND_TO_SCORE_ROUND.items()}
# -> {"R16":"R32","QF":"R16","SF":"QF","FINAL":"SF","CHAMPION":"FINAL"}


def _parse_dt(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# Planned open time shown by the Coming-Soon countdown until the admin confirms.
# Sat Jun 27 2026, 21:00 America/Los_Angeles (PDT, UTC-7) = 2026-06-28T04:00:00Z.
PLANNED_OPEN_AT = "2026-06-28T04:00:00Z"


def ensure_state_row(db):
    """Make sure the single bracket_state row exists. Returns nothing."""
    row = db.execute("SELECT id FROM bracket_state WHERE id=1").fetchone()
    if not row:
        db.execute(
            "INSERT INTO bracket_state (id, status, open_at) VALUES (1, 'coming_soon', %s)",
            (PLANNED_OPEN_AT,)
        )
        db.commit()


def get_state(db):
    ensure_state_row(db)
    return db.execute("SELECT * FROM bracket_state WHERE id=1").fetchone()


def effective_status(state, now=None):
    """
    The authoritative status, factoring in the clock.

    The stored status flips 'open' -> 'locked' automatically once lock_at passes,
    even if no cron has run. This is what server-side write guards must use —
    never trust the UI or a stale stored status.
    """
    now = now or datetime.now(timezone.utc)
    status = state["status"] if state else "coming_soon"
    if status == "open":
        lock_at = _parse_dt(state["lock_at"]) if state["lock_at"] else None
        if lock_at and now >= lock_at:
            return "locked"
    return status


def is_open_for_writes(db, now=None):
    """True only when users may create/edit picks."""
    return effective_status(get_state(db), now) == "open"


def advancing_team(match_row):
    """The team that went through in a settled bracket match, else None."""
    if match_row is None or match_row["home_advances"] is None:
        return None
    return match_row["home_team"] if match_row["home_advances"] == 1 else match_row["away_team"]


def get_bracket_matches(db):
    """All bracket matches keyed by skeleton match_id."""
    rows = db.execute("SELECT * FROM bracket_matches").fetchall()
    return {r["match_id"]: r for r in rows}


def round_is_complete(matches_by_id, round_key):
    """True when every match in `round_key` has a decided winner."""
    ids = ROUNDS[round_key]
    if not all(mid in matches_by_id for mid in ids):
        return False
    return all(advancing_team(matches_by_id[mid]) is not None for mid in ids)


def actual_sets(db):
    """
    The set of teams that ACTUALLY reached each scoring round, derived from
    bracket_matches results. A round is only present (and non-empty) once its
    source round is fully settled.

    Returns {"R16": set, "QF": set, "SF": set, "FINAL": set, "CHAMPION": team|None}
    — only including rounds whose source is complete.
    """
    matches = get_bracket_matches(db)
    out = {}
    for score_round, source_round in SCORE_ROUND_SOURCE.items():
        if not round_is_complete(matches, source_round):
            continue
        teams = {advancing_team(matches[mid]) for mid in ROUNDS[source_round]}
        if score_round == "CHAMPION":
            out["CHAMPION"] = next(iter(teams), None)
        else:
            out[score_round] = teams
    return out
