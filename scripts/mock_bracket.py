#!/usr/bin/env python3
"""
LOCAL-ONLY mock bracket for end-to-end testing.

This NEVER touches production: it forcibly ignores DATABASE_URL and uses a local
sqlite file (mock_bracket.db) instead, so you can play with the whole flow while
the live site stays in "Coming Soon" for everyone else.

Commands:
  python3 scripts/mock_bracket.py open       # build a guessed R32 + open the bracket
  python3 scripts/mock_bracket.py lock       # lock it (read-only, like after kickoff)
  python3 scripts/mock_bracket.py simulate   # fake the whole tournament + score everyone
  python3 scripts/mock_bracket.py reset      # wipe back to a clean "coming soon"
  python3 scripts/mock_bracket.py status     # show current state + your picks/scores

Typical session:
  python3 scripts/mock_bracket.py open
  ./run_local.sh                 # serve on http://localhost:8000 against the mock DB
  # -> sign up, open the Bracket tab, fill it out
  python3 scripts/mock_bracket.py simulate   # invent results, score it
  ./run_local.sh                 # revisit Bracket + Standings to see your score
"""
import os
import sys
import random
from datetime import datetime, timezone

_BASE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _BASE)
sys.path.insert(0, os.path.join(_BASE, "scripts"))

# Force a local sqlite DB — make it impossible to hit production.
os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("DB_PATH", os.path.abspath(os.path.join(_BASE, "mock_bracket.db")))

import db as dbmod
dbmod.DB_PATH = os.environ["DB_PATH"]

from db import get_db, init_db
from bracket_skeleton import ROUNDS, ROUND_ORDER, ROUND_LABELS, FEEDS
from bracket_core import ensure_state_row, advancing_team
from settle_bracket import score_users

# 32 plausible nations for a mock Round of 32.
TEAMS = [
    "Argentina", "France", "Brazil", "England", "Spain", "Portugal",
    "Netherlands", "Germany", "Belgium", "Croatia", "Uruguay", "Italy",
    "USA", "Mexico", "Canada", "Morocco",
    "Japan", "South Korea", "Senegal", "Switzerland", "Denmark", "Colombia",
    "Australia", "Poland", "Serbia", "Ecuador", "Ghana", "Nigeria",
    "Cameroon", "Saudi Arabia", "Norway", "Egypt",
]

FAR_FUTURE = "2030-01-01T00:00:00Z"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _wipe(db):
    db.execute("DELETE FROM bracket_settlements")
    db.execute("DELETE FROM bracket_picks")
    db.execute("DELETE FROM bracket_matches")


def cmd_open(db):
    _wipe(db)
    # 16 matchups: strong half vs the other half.
    for i, mid in enumerate(ROUNDS["R32"]):
        home, away = TEAMS[i], TEAMS[i + 16]
        db.execute("INSERT INTO bracket_matches (match_id, round, home_team, away_team, status) "
                   "VALUES (%s,'R32',%s,%s,'TIMED')", (mid, home, away))
    for rk in ["R16", "QF", "SF", "FINAL"]:
        for mid in ROUNDS[rk]:
            db.execute("INSERT INTO bracket_matches (match_id, round, status) "
                       "VALUES (%s,%s,'TIMED')", (mid, rk))
    db.execute("UPDATE bracket_state SET status='open', open_at=%s, confirmed_at=%s, lock_at=%s WHERE id=1",
               (_now(), _now(), FAR_FUTURE))
    db.commit()
    print("✅ Mock bracket is OPEN with 16 guessed R32 matchups.")
    print("   Run ./run_local.sh, sign up, and fill out the Bracket tab.")


def cmd_lock(db):
    db.execute("UPDATE bracket_state SET status='locked' WHERE id=1")
    db.commit()
    print("🔒 Mock bracket LOCKED (read-only). Run 'simulate' to score it.")


def _decide(db, mid):
    """Randomly advance one side of a match."""
    db.execute("UPDATE bracket_matches SET home_advances=%s, settled=1, status='FINISHED' "
               "WHERE match_id=%s", (random.choice([1, 0]), mid))


def cmd_simulate(db):
    random.seed()  # different result each run
    # R32 winners.
    for mid in ROUNDS["R32"]:
        _decide(db, mid)
    # Propagate actual winners forward, deciding each downstream match.
    for rk in ["R16", "QF", "SF", "FINAL"]:
        for mid in ROUNDS[rk]:
            hsrc, asrc = FEEDS[mid]
            mh = db.execute("SELECT * FROM bracket_matches WHERE match_id=%s", (hsrc,)).fetchone()
            ma = db.execute("SELECT * FROM bracket_matches WHERE match_id=%s", (asrc,)).fetchone()
            db.execute("UPDATE bracket_matches SET home_team=%s, away_team=%s WHERE match_id=%s",
                       (advancing_team(mh), advancing_team(ma), mid))
            _decide(db, mid)
    db.execute("UPDATE bracket_state SET status='locked' WHERE id=1")
    db.commit()

    # Clear old settlements so re-simulating re-scores against the new results.
    db.execute("DELETE FROM bracket_settlements")
    db.commit()
    n = score_users(db)
    db.commit()

    champ = advancing_team(db.execute(
        "SELECT * FROM bracket_matches WHERE match_id=104").fetchone())
    print(f"🎲 Simulated a full tournament. Actual champion: {champ}")
    print(f"   Wrote {n} settlement rows.")
    cmd_status(db)


def cmd_reset(db):
    _wipe(db)
    db.execute("UPDATE bracket_state SET status='coming_soon', confirmed_at=NULL WHERE id=1")
    db.commit()
    print("♻️  Reset to 'coming_soon'. Run 'open' to start again.")


def cmd_status(db):
    st = db.execute("SELECT * FROM bracket_state WHERE id=1").fetchone()
    print(f"\nState: {st['status']}  (open_at={st['open_at']}, lock_at={st['lock_at']})")
    users = db.execute("SELECT id, team_name FROM users ORDER BY id").fetchall()
    if not users:
        print("No users yet — sign up via ./run_local.sh first.")
        return
    for u in users:
        npicks = db.execute("SELECT COUNT(*) AS n FROM bracket_picks WHERE user_id=%s",
                            (u["id"],)).fetchone()["n"]
        setts = db.execute("SELECT round, total_points FROM bracket_settlements "
                           "WHERE user_id=%s", (u["id"],)).fetchall()
        total = sum(s["total_points"] for s in setts)
        detail = ", ".join(f"{s['round']}={s['total_points']}" for s in setts) or "not scored yet"
        print(f"  • {u['team_name']}: {npicks} picks · {total} pts ({detail})")


COMMANDS = {"open": cmd_open, "lock": cmd_lock, "simulate": cmd_simulate,
            "reset": cmd_reset, "status": cmd_status}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    init_db()
    db = get_db()
    ensure_state_row(db)
    print(f"(using local DB: {os.environ['DB_PATH']})")
    COMMANDS[cmd](db)
    db.close()


if __name__ == "__main__":
    main()
