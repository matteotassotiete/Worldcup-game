#!/usr/bin/env python3
"""
Pull finished matches, write scores, score all predictions. Idempotent.
Cron: */30 * * * * cd /home/claude/worldcup-game && /usr/bin/python3 scripts/settle.py >> logs/settle.log 2>&1

Only settles matches that kicked off at least 2 hours ago, so we never
touch a game that might still be in progress. With the 30-min cron, scores
appear within ~30 minutes of the game ending.
"""
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import get_db
from scoring import score_prediction

TOKEN = os.environ["FOOTBALL_DATA_TOKEN"]
API_BASE = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": TOKEN}

SETTLE_AFTER_HOURS = 2.5


def fetch_finished():
    resp = requests.get(f"{API_BASE}/competitions/WC/matches?status=FINISHED",
                        headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json().get("matches", [])


def extract_scores(m):
    stage = m.get("stage", "")
    score = m.get("score", {})
    if stage and "GROUP" in stage.upper():
        s = score.get("fullTime", {})
    else:
        s = score.get("regularTime") or score.get("fullTime") or {}
    return s.get("home"), s.get("away")


def settle_match(db, match_id, home_score, away_score):
    db.execute(
        "UPDATE matches SET home_score=%s, away_score=%s, status='FINISHED', settled=1 "
        "WHERE id=%s AND settled=0",
        (home_score, away_score, match_id)
    )

    preds = db.execute("""
        SELECT p.id, p.home_pred, p.away_pred FROM predictions p
        WHERE p.match_id=%s
          AND p.id NOT IN (SELECT prediction_id FROM settlements)
    """, (match_id,)).fetchall()

    for pred in preds:
        result = score_prediction(
            pred["home_pred"], pred["away_pred"],
            home_score, away_score
        )
        labels_str = ",".join(result["bonus_labels"])
        db.execute("""
            INSERT INTO settlements (prediction_id, base_points, bonus_points, bonus_labels, total_points)
            VALUES (%s, %s, %s, %s, %s)
        """, (pred["id"], result["base"], result["bonus"], labels_str, result["total"]))

    return len(preds)


def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] settle.py starting")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=SETTLE_AFTER_HOURS)

    db = get_db()
    matches = fetch_finished()
    print(f"  {len(matches)} finished matches from API")

    total_scored = 0
    skipped = 0
    for m in matches:
        kickoff_str = m.get("utcDate", "")
        if kickoff_str:
            kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00"))
            if kickoff > cutoff:
                skipped += 1
                continue

        hs, as_ = extract_scores(m)
        if hs is None or as_ is None:
            continue
        n = settle_match(db, m["id"], hs, as_)
        total_scored += n

    if skipped:
        print(f"  Skipped {skipped} match(es) — kicked off less than {SETTLE_AFTER_HOURS}h ago (may still be in progress)")
    db.commit()
    print(f"  Predictions scored this run: {total_scored}")
    db.close()
    print(f"[{ts}] Done")


if __name__ == "__main__":
    main()
