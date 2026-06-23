#!/usr/bin/env python3
"""
Settle the Bracket Game. Runs every 30 min alongside the score-game settler.

Two jobs, both idempotent (re-running never double-awards):

  1. Pull finished knockout results from football-data.org and record the
     ADVANCING team for each bracket slot. A penalty shootout still yields an
     advancing team — we take score.winner from the API (HOME_TEAM/AWAY_TEAM),
     which already accounts for shootouts.
  2. For each scoring round whose source round is fully decided, score every
     user's bracket (round-independent set intersection) and write one immutable
     per-round settlement row per user.

Also flips bracket_state 'open' -> 'locked' once the first R32 kickoff passes.

Cron:
  */30 * * * * cd /home/claude/worldcup-game && /usr/bin/python3 scripts/settle_bracket.py >> logs/settle_bracket.log 2>&1
"""
import os
import sys
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# NOTE: .env is loaded lazily inside main(), not at import time, so this module
# can be imported in tests against a local sqlite DB without pulling DATABASE_URL.

from db import get_db
from bracket_skeleton import ROUND_ORDER, ROUNDS, predicted_sets_from_picks
from bracket_core import (get_state, effective_status, actual_sets,
                          get_bracket_matches, round_is_complete, _parse_dt)
from bracket_scoring import score_round, BRACKET_ROUNDS

API_BASE = "https://api.football-data.org/v4"


def fetch_matches():
    headers = {"X-Auth-Token": os.environ["FOOTBALL_DATA_TOKEN"]}
    resp = requests.get(f"{API_BASE}/competitions/WC/matches", headers=headers, timeout=20)
    resp.raise_for_status()
    return {m["id"]: m for m in resp.json().get("matches", [])}


def team_name(side):
    return side.get("shortName") or side.get("name") or None


def record_results(db, api_by_id):
    """Write the actual teams + advancing team for any finished bracket slot.
    Only touches slots not yet settled (settled=0), so it is idempotent."""
    updated = 0
    slots = db.execute(
        "SELECT match_id, api_match_id FROM bracket_matches WHERE settled=0"
    ).fetchall()
    for row in slots:
        api_id = row["api_match_id"]
        if not api_id or api_id not in api_by_id:
            continue
        m = api_by_id[api_id]
        if m.get("status") != "FINISHED":
            continue
        winner = (m.get("score") or {}).get("winner")
        if winner not in ("HOME_TEAM", "AWAY_TEAM"):
            continue  # no decisive result yet (shouldn't happen for FINISHED knockout)
        home = team_name(m["homeTeam"])
        away = team_name(m["awayTeam"])
        if not home or not away:
            continue
        home_advances = 1 if winner == "HOME_TEAM" else 0
        db.execute("""
            UPDATE bracket_matches
            SET home_team=%s, away_team=%s, home_advances=%s, status='FINISHED', settled=1
            WHERE match_id=%s AND settled=0
        """, (home, away, home_advances, row["match_id"]))
        updated += 1
    return updated


def score_users(db):
    """Score every completed round for every user. Idempotent via the
    UNIQUE(user_id, round) constraint — existing settlements are never rewritten."""
    acts = actual_sets(db)
    if not acts:
        return 0

    # All picks grouped by user.
    picks_by_user = {}
    for r in db.execute("SELECT user_id, match_id, picked_team FROM bracket_picks").fetchall():
        picks_by_user.setdefault(r["user_id"], {})[r["match_id"]] = r["picked_team"]

    written = 0
    for user_id, picks in picks_by_user.items():
        predicted = predicted_sets_from_picks(picks)
        for round_key in BRACKET_ROUNDS:
            if round_key not in acts:
                continue
            res = score_round(round_key, predicted.get(round_key), acts.get(round_key))
            cur = db.execute("""
                INSERT INTO bracket_settlements
                    (user_id, round, correct_count, base_points, bonus_points, total_points)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(user_id, round) DO NOTHING
            """, (user_id, round_key, res["correct_count"], res["base_points"],
                  res["bonus_points"], res["total_points"]))
            if getattr(cur, "rowcount", 0):
                written += 1
    return written


def maybe_lock(db):
    state = get_state(db)
    if state["status"] == "open":
        lock_at = _parse_dt(state["lock_at"]) if state["lock_at"] else None
        if lock_at and datetime.now(timezone.utc) >= lock_at:
            db.execute("UPDATE bracket_state SET status='locked' WHERE id=1")
            return True
    return False


def main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] settle_bracket.py starting")

    db = get_db()
    state = get_state(db)
    if state["status"] == "coming_soon":
        print("  Bracket not open yet — nothing to settle.")
        db.close()
        return

    locked = maybe_lock(db)
    if locked:
        print("  🔒 Bracket locked (first R32 kickoff passed).")

    api_by_id = fetch_matches()
    n_results = record_results(db, api_by_id)
    db.commit()
    print(f"  Bracket slots newly settled: {n_results}")

    # Report which rounds are now complete.
    matches = get_bracket_matches(db)
    complete = [rk for rk in ROUND_ORDER if round_is_complete(matches, rk)]
    print(f"  Source rounds fully decided: {complete or '—'}")

    n_settle = score_users(db)
    db.commit()
    print(f"  Per-round settlements written this run: {n_settle}")
    db.close()
    print(f"[{ts}] Done")


if __name__ == "__main__":
    main()
