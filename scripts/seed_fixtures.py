#!/usr/bin/env python3
"""One-time (re-runnable / idempotent) pull of all WC 2026 fixtures."""
import os
import sys
import sqlite3
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "app.db")
API_BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}


def fetch_all_matches():
    matches = []
    url = f"{API_BASE}/competitions/WC/matches"
    while url:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        matches.extend(data.get("matches", []))
        # free tier doesn't paginate, but handle it defensively
        next_page = data.get("nextPage")
        url = f"{API_BASE}/competitions/WC/matches?page={next_page}" if next_page else None
    return matches


def upsert_match(cur, m):
    match_id = m["id"]
    kickoff = m.get("utcDate", "")
    stage = m.get("stage", "")
    group_label = m.get("group")
    home_team = m["homeTeam"].get("shortName") or m["homeTeam"].get("name") or "TBD"
    away_team = m["awayTeam"].get("shortName") or m["awayTeam"].get("name") or "TBD"
    status = m.get("status", "SCHEDULED")

    score = m.get("score", {})
    # Group stage: use fullTime; knockout: use regularTime
    if stage and "GROUP" in stage.upper():
        s = score.get("fullTime", {})
    else:
        s = score.get("regularTime") or score.get("fullTime") or {}

    home_score = s.get("home")
    away_score = s.get("away")

    cur.execute("""
        INSERT INTO matches (id, kickoff_utc, stage, group_label, home_team, away_team,
                             home_score, away_score, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            kickoff_utc  = excluded.kickoff_utc,
            stage        = excluded.stage,
            group_label  = excluded.group_label,
            home_team    = excluded.home_team,
            away_team    = excluded.away_team,
            home_score   = excluded.home_score,
            away_score   = excluded.away_score,
            status       = excluded.status
        -- never overwrite settled flag here
    """, (match_id, kickoff, stage, group_label, home_team, away_team,
          home_score, away_score, status))


def init_db(con):
    schema = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    with open(schema) as f:
        con.executescript(f.read())


def main():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    init_db(con)

    print("Fetching fixtures from football-data.org …")
    matches = fetch_all_matches()
    print(f"  Got {len(matches)} matches")

    cur = con.cursor()
    for m in matches:
        upsert_match(cur, m)
    con.commit()

    rows = cur.execute(
        "SELECT id, kickoff_utc, stage, home_team, away_team, status FROM matches ORDER BY kickoff_utc LIMIT 5"
    ).fetchall()
    print("\nFirst 5 fixtures in DB:")
    print(f"  {'ID':>8}  {'Kickoff (UTC)':<22}  {'Stage':<30}  {'Home':<20}  {'Away':<20}  Status")
    print("  " + "-" * 115)
    for r in rows:
        print(f"  {r['id']:>8}  {r['kickoff_utc']:<22}  {r['stage']:<30}  {r['home_team']:<20}  {r['away_team']:<20}  {r['status']}")

    total = cur.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    print(f"\nTotal matches in DB: {total}")
    con.close()


if __name__ == "__main__":
    main()
