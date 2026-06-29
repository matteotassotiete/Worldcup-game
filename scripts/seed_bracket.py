#!/usr/bin/env python3
"""
Seed the bracket from the HARDCODED Round-of-32 matchups in data/bracket_r32.py
(the source of truth now that the group stage is over). The football-data.org API
is used only to attach each R32 slot's api_match_id — by matching the two team
names — so the settler can fetch results. We no longer infer matchups from API
standings / chronological order; that's what was producing wrong matchups.

    cd /home/claude/worldcup-game && python3 scripts/seed_bracket.py

Nothing goes live until you click "Confirm & open bracket" on /admin/bracket.
Idempotent / re-runnable. To re-seed after the bracket is confirmed (e.g. to
correct a name in data/bracket_r32.py), pass --force.

R16/QF/SF/FINAL slots are created empty (teams are derived from each user's picks
in the UI, and filled with real results by the settler as rounds resolve). Their
api_match_id is mapped by round + chronological kickoff, which is safe because
those slots carry no matchup of their own.
"""
import os
import re
import sys
import argparse
import unicodedata
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import get_db, init_db
from bracket_skeleton import ROUNDS
from bracket_core import ensure_state_row, get_state
from data.bracket_r32 import matchups_by_slot

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

# Normalised name -> canonical token, for the handful of names where our hardcoded
# spelling differs from the API's. Keys/values are already normalised (see _norm).
ALIASES = {
    "unitedstates": "usa",
    "cotedivoire": "ivorycoast",
    "bosniaherzegovina": "bosniaandherzegovina",
    "caboverde": "capeverde",
    "congodr": "drcongo",
    "democraticrepublicofcongo": "drcongo",
}


def _norm(name):
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _canon(name):
    n = _norm(name)
    return ALIASES.get(n, n)


def fetch_matches():
    resp = requests.get(f"{API_BASE}/competitions/WC/matches", headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def team_name(side):
    return side.get("shortName") or side.get("name") or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite even after the bracket is confirmed/open")
    args = ap.parse_args()

    init_db()
    db = get_db()
    ensure_state_row(db)
    state = get_state(db)

    if state["confirmed_at"] and not args.force:
        print("⚠  Bracket already confirmed/open. Re-seeding is blocked to avoid "
              "clobbering live data. Use --force to override.")
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

    # Index R32 API matches by the frozenset of their two (canonicalised) teams.
    api_r32_by_pair = {}
    for m in by_round["R32"]:
        h, a = team_name(m["homeTeam"]), team_name(m["awayTeam"])
        if h and a:
            api_r32_by_pair[frozenset({_canon(h), _canon(a)})] = m

    # ── R32: write the hardcoded matchups, attach api ids by team match ──
    hardcoded = matchups_by_slot()
    unmatched = []
    earliest_r32 = None
    for slot_id in sorted(hardcoded):
        home, away = hardcoded[slot_id]
        key = frozenset({_canon(home), _canon(away)})
        m = api_r32_by_pair.get(key)
        api_id = m["id"] if m else None
        status = m.get("status", "SCHEDULED") if m else "SCHEDULED"
        if m is None:
            unmatched.append((slot_id, home, away))
        else:
            kt = m.get("utcDate")
            if kt and (earliest_r32 is None or kt < earliest_r32):
                earliest_r32 = kt
        db.execute("""
            INSERT INTO bracket_matches
                (match_id, round, home_team, away_team, api_match_id, status)
            VALUES (%s, 'R32', %s, %s, %s, %s)
            ON CONFLICT(match_id) DO UPDATE SET
                round        = 'R32',
                home_team    = EXCLUDED.home_team,
                away_team    = EXCLUDED.away_team,
                api_match_id = EXCLUDED.api_match_id,
                status       = EXCLUDED.status
        """, (slot_id, home, away, api_id, status))

    # ── R16/QF/SF/FINAL: empty slots, api ids by round + chronological order ──
    for rk in ["R16", "QF", "SF", "FINAL"]:
        slots = ROUNDS[rk]
        api_matches = by_round[rk]
        if api_matches and len(api_matches) != len(slots):
            print(f"  ⚠  {rk}: API returned {len(api_matches)} matches, "
                  f"skeleton expects {len(slots)} — mapping by position anyway.")
        for i, slot_id in enumerate(slots):
            m = api_matches[i] if i < len(api_matches) else None
            api_id = m["id"] if m else None
            status = m.get("status", "SCHEDULED") if m else "SCHEDULED"
            db.execute("""
                INSERT INTO bracket_matches
                    (match_id, round, home_team, away_team, api_match_id, status)
                VALUES (%s, %s, NULL, NULL, %s, %s)
                ON CONFLICT(match_id) DO UPDATE SET
                    round        = EXCLUDED.round,
                    api_match_id = EXCLUDED.api_match_id,
                    status       = EXCLUDED.status
            """, (slot_id, rk, api_id, status))

    # Lock time = first R32 kickoff (only updates if we found it from the API).
    if earliest_r32:
        db.execute("UPDATE bracket_state SET lock_at=%s WHERE id=1", (earliest_r32,))

    db.commit()

    print(f"\nSeeded 16 hardcoded R32 matchups "
          f"({16 - len(unmatched)} linked to an API fixture, {len(unmatched)} unlinked).")
    if earliest_r32:
        print(f"Lock time (first R32 kickoff): {earliest_r32}")

    print("\nR32 matchups:")
    for r in db.execute(
        "SELECT match_id, home_team, away_team, api_match_id "
        "FROM bracket_matches WHERE round='R32' ORDER BY match_id"
    ).fetchall():
        api = r["api_match_id"] or "NO API MATCH"
        print(f"  slot {r['match_id']:>3} (api {api}):  {r['home_team']}  vs  {r['away_team']}")

    if unmatched:
        print("\n⚠  Could not link these matchups to an API fixture (results won't "
              "settle until fixed). Check the spelling in data/bracket_r32.py against "
              "the API, or add an alias in scripts/seed_bracket.py ALIASES:")
        for slot_id, home, away in unmatched:
            print(f"   slot {slot_id}: {home} vs {away}")

    print("\nNothing is live yet — review & confirm on /admin/bracket.")
    db.close()


if __name__ == "__main__":
    main()
