#!/usr/bin/env python3
"""One-time (re-runnable / idempotent) pull of all WC 2026 fixtures."""
import os
import sys
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import get_db, init_db

TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
API_BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}


def fetch_all_matches():
    resp = requests.get(f"{API_BASE}/competitions/WC/matches", headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def upsert_match(db, m):
    match_id = m["id"]
    kickoff = m.get("utcDate", "")
    stage = m.get("stage", "")
    group_label = m.get("group")
    home_team = m["homeTeam"].get("shortName") or m["homeTeam"].get("name") or "TBD"
    away_team = m["awayTeam"].get("shortName") or m["awayTeam"].get("name") or "TBD"
    status = m.get("status", "SCHEDULED")

    score = m.get("score", {})
    if stage and "GROUP" in stage.upper():
        s = score.get("fullTime", {})
    else:
        s = score.get("regularTime") or score.get("fullTime") or {}

    home_score = s.get("home")
    away_score = s.get("away")

    db.execute("""
        INSERT INTO matches (id, kickoff_utc, stage, group_label, home_team, away_team,
                             home_score, away_score, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(id) DO UPDATE SET
            kickoff_utc  = EXCLUDED.kickoff_utc,
            stage        = EXCLUDED.stage,
            group_label  = EXCLUDED.group_label,
            home_team    = EXCLUDED.home_team,
            away_team    = EXCLUDED.away_team,
            home_score   = EXCLUDED.home_score,
            away_score   = EXCLUDED.away_score,
            status       = EXCLUDED.status
    """, (match_id, kickoff, stage, group_label, home_team, away_team,
          home_score, away_score, status))


def main():
    init_db()
    db = get_db()

    print("Fetching fixtures from football-data.org …")
    matches = fetch_all_matches()
    print(f"  Got {len(matches)} matches")

    for m in matches:
        upsert_match(db, m)
    db.commit()

    rows = db.execute(
        "SELECT id, kickoff_utc, stage, home_team, away_team, status FROM matches ORDER BY kickoff_utc LIMIT 5"
    ).fetchall()

    print("\nFirst 5 fixtures in DB:")
    print(f"  {'ID':>8}  {'Kickoff (UTC)':<22}  {'Stage':<30}  {'Home':<20}  {'Away':<20}  Status")
    print("  " + "-" * 115)
    for r in rows:
        print(f"  {r['id']:>8}  {r['kickoff_utc']:<22}  {r['stage']:<30}  {r['home_team']:<20}  {r['away_team']:<20}  {r['status']}")

    total = db.execute("SELECT COUNT(*) AS n FROM matches").fetchone()["n"]
    print(f"\nTotal matches in DB: {total}")
    db.close()


if __name__ == "__main__":
    main()
