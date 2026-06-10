#!/usr/bin/env python3
"""
Pull finished matches from football-data.org, write scores, score all predictions.
Idempotent: safe to re-run; never double-awards points.
Cron: */30 * * * * cd /home/claude/worldcup-game && /usr/bin/python3 scripts/settle.py >> logs/settle.log 2>&1
"""
import os
import sys
import sqlite3
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
from scoring import score_prediction

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "app.db")
API_BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}


def fetch_finished():
    url = f"{API_BASE}/competitions/WC/matches?status=FINISHED"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def extract_scores(m):
    stage = m.get("stage", "")
    score = m.get("score", {})
    if stage and "GROUP" in stage.upper():
        s = score.get("fullTime", {})
    else:
        # Knockout: use regularTime (pens don't count)
        s = score.get("regularTime") or score.get("fullTime") or {}
    return s.get("home"), s.get("away")


def settle_match(con, match_id, home_score, away_score):
    cur = con.cursor()
    cur.execute(
        "UPDATE matches SET home_score=?, away_score=?, status='FINISHED', settled=1 WHERE id=? AND settled=0",
        (home_score, away_score, match_id)
    )
    if cur.rowcount == 0:
        # Already settled — skip
        return 0

    # Score every prediction for this match
    preds = cur.execute(
        "SELECT p.id, p.home_pred, p.away_pred FROM predictions p "
        "WHERE p.match_id=? AND p.id NOT IN (SELECT prediction_id FROM settlements)",
        (match_id,)
    ).fetchall()

    for pred in preds:
        result = score_prediction(
            pred["home_pred"], pred["away_pred"],
            home_score, away_score
        )
        labels_str = ",".join(result["bonus_labels"])
        cur.execute("""
            INSERT INTO settlements (prediction_id, base_points, bonus_points, bonus_labels, total_points)
            VALUES (?, ?, ?, ?, ?)
        """, (pred["id"], result["base"], result["bonus"], labels_str, result["total"]))

    con.commit()
    return len(preds)


def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] settle.py starting")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")

    matches = fetch_finished()
    print(f"  {len(matches)} finished matches from API")

    settled = 0
    scored = 0
    for m in matches:
        hs, as_ = extract_scores(m)
        if hs is None or as_ is None:
            continue
        n = settle_match(con, m["id"], hs, as_)
        if n is not None:
            settled += (1 if n >= 0 else 0)
            scored += n

    print(f"  Newly settled: {settled}  Predictions scored: {scored}")
    con.close()
    print(f"[{ts}] Done")


if __name__ == "__main__":
    main()
