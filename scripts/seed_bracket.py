#!/usr/bin/env python3
"""
Pull the knockout fixtures from football-data.org and write them into
bracket_matches as PROPOSED (not live). Nothing goes live until you click
"Confirm & open bracket" on /admin/bracket.

Idempotent / re-runnable. Run it again after the group stage ends (Sat Jun 27)
to pick up the concrete R32 team names, then verify on /admin/bracket.

    cd /home/claude/worldcup-game && python3 scripts/seed_bracket.py

The API uses its own match ids (e.g. 537417). This maps them onto the hardcoded
skeleton slot ids (73..104) by round + chronological kickoff, and stores the API
id on each slot so the settler can fetch results. Because the API gives no group
placeholders pre-group-stage, the chronological mapping is a STARTING POINT —
verify and hand-correct on /admin/bracket before confirming.
"""
import os
import sys
import argparse
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import get_db, init_db
from bracket_skeleton import ROUNDS, ROUND_LABELS
from bracket_core import ensure_state_row, get_state

TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
API_BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}

# API stage name -> our skeleton round key. THIRD_PLACE is intentionally dropped.
STAGE_MAP = {
    "LAST_32": "R32",
    "LAST_16": "R16",
    "QUARTER_FINALS": "QF",
    "SEMI_FINALS": "SF",
    "FINAL": "FINAL",
}


def fetch_matches():
    resp = requests.get(f"{API_BASE}/competitions/WC/matches", headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def team_name(side):
    return side.get("shortName") or side.get("name") or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite team names even after the bracket is confirmed/open")
    args = ap.parse_args()

    init_db()
    db = get_db()
    ensure_state_row(db)
    state = get_state(db)

    if state["confirmed_at"] and not args.force:
        print("⚠  Bracket already confirmed/open. Re-seeding team names is blocked "
              "to avoid clobbering live data. Use --force to override.")
        # We still allow result-free metadata refresh? No — bail to be safe.
        db.close()
        return

    print("Fetching fixtures from football-data.org …")
    matches = fetch_matches()

    # Bucket API knockout matches by our round, sorted chronologically.
    by_round = {r: [] for r in ROUNDS}
    for m in matches:
        rk = STAGE_MAP.get(m.get("stage"))
        if rk:
            by_round[rk].append(m)
    for rk in by_round:
        by_round[rk].sort(key=lambda x: x.get("utcDate", ""))

    earliest_r32 = None
    total = 0
    concrete = 0

    for rk in ROUNDS:
        slots = ROUNDS[rk]
        api_matches = by_round[rk]
        if len(api_matches) != len(slots):
            print(f"  ⚠  {rk}: API returned {len(api_matches)} matches, "
                  f"skeleton expects {len(slots)} — mapping by position anyway.")
        for slot_id, m in zip(slots, api_matches):
            ht = team_name(m["homeTeam"])
            at = team_name(m["awayTeam"])
            api_id = m["id"]
            status = m.get("status", "SCHEDULED")
            if ht and at:
                concrete += 1
            if rk == "R32":
                kt = m.get("utcDate")
                if kt and (earliest_r32 is None or kt < earliest_r32):
                    earliest_r32 = kt

            db.execute("""
                INSERT INTO bracket_matches
                    (match_id, round, home_team, away_team, api_match_id, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(match_id) DO UPDATE SET
                    round        = EXCLUDED.round,
                    home_team    = EXCLUDED.home_team,
                    away_team    = EXCLUDED.away_team,
                    api_match_id = EXCLUDED.api_match_id,
                    status       = EXCLUDED.status
            """, (slot_id, rk, ht, at, api_id, status))
            total += 1

    # Stash the lock time (first R32 kickoff) so the admin confirm page can show
    # it. Do NOT open the bracket — that's the admin's job.
    if earliest_r32:
        db.execute("UPDATE bracket_state SET lock_at=%s WHERE id=1", (earliest_r32,))

    db.commit()

    print(f"\nSeeded {total} bracket slots ({concrete} with concrete teams, "
          f"{total - concrete} still TBD).")
    if earliest_r32:
        print(f"Lock time (first R32 kickoff): {earliest_r32}")
    print("\nProposed R32 matchups:")
    for r in db.execute(
        "SELECT match_id, home_team, away_team, api_match_id "
        "FROM bracket_matches WHERE round='R32' ORDER BY match_id"
    ).fetchall():
        h = r["home_team"] or "TBD"
        a = r["away_team"] or "TBD"
        print(f"  slot {r['match_id']:>3} (api {r['api_match_id']}):  {h}  vs  {a}")

    print("\nNothing is live yet — review & confirm on /admin/bracket.")
    db.close()


if __name__ == "__main__":
    main()
