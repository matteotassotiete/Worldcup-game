#!/usr/bin/env python3
"""
Manually award tournament bonus points after the final.
Usage:
  python3 scripts/award_tournament.py --champion "Argentina" --top-scorer "Mbappe"
Idempotent: running twice for the same picks has no extra effect.
"""
import os
import sys
import argparse
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "app.db")

CHAMPION_POINTS = 250
TOP_SCORER_POINTS = 150


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--champion", required=True, help="Winning team name")
    parser.add_argument("--top-scorer", required=True, help="Top scorer name")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # Ensure tournament_awards table exists
    con.execute("""
        CREATE TABLE IF NOT EXISTS tournament_awards (
            user_id INTEGER PRIMARY KEY,
            champion_points INTEGER NOT NULL DEFAULT 0,
            top_scorer_points INTEGER NOT NULL DEFAULT 0,
            awarded_at TEXT DEFAULT (datetime('now'))
        )
    """)

    users = con.execute("SELECT id, team_name, champion_pick, top_scorer_pick FROM users").fetchall()

    champion_winners = [u for u in users if u["champion_pick"] and u["champion_pick"].lower() == args.champion.lower()]
    scorer_winners = [u for u in users if u["top_scorer_pick"] and u["top_scorer_pick"].lower() == args.top_scorer.lower()]

    print(f"Champion '{args.champion}': {len(champion_winners)} winner(s)")
    for u in champion_winners:
        print(f"  {u['team_name']} (+{CHAMPION_POINTS})")

    print(f"Top scorer '{args.top_scorer}': {len(scorer_winners)} winner(s)")
    for u in scorer_winners:
        print(f"  {u['team_name']} (+{TOP_SCORER_POINTS})")

    if args.dry_run:
        print("Dry run — no changes made.")
        return

    for u in champion_winners:
        con.execute("""
            INSERT INTO tournament_awards (user_id, champion_points)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET champion_points=excluded.champion_points
        """, (u["id"], CHAMPION_POINTS))

    for u in scorer_winners:
        con.execute("""
            INSERT INTO tournament_awards (user_id, top_scorer_points)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET top_scorer_points=excluded.top_scorer_points
        """, (u["id"], TOP_SCORER_POINTS))

    con.commit()
    print("Awards written.")
    con.close()


if __name__ == "__main__":
    main()
