#!/usr/bin/env python3
"""
End-to-end smoke test of the Bracket Game through the Flask app, on a throwaway
sqlite DB. Exercises: coming-soon -> admin confirm -> open fill (with cascade)
-> fake early lock (writes rejected) -> settle -> leaderboard.

Run:  python3 tests/smoke_bracket.py
"""
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

_TMP = tempfile.mktemp(suffix=".db")
os.environ["DB_PATH"] = _TMP
os.environ.pop("DATABASE_URL", None)
os.environ["SECRET_KEY"] = "smoke-secret"
os.environ["ADMIN_KEY"] = "smoke-admin"

_BASE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _BASE)
sys.path.insert(0, os.path.join(_BASE, "scripts"))

import db as dbmod
dbmod.DB_PATH = _TMP

import app as appmod
from db import get_db
from bracket_skeleton import ROUNDS, FEEDS
from settle_bracket import score_users

OK = "✅"; BAD = "❌"
fails = []
def check(name, cond):
    print(f"  {OK if cond else BAD} {name}")
    if not cond:
        fails.append(name)


def signup(client, team, pin):
    return client.post("/signup", data={"team_name": team, "pin": pin},
                       follow_redirects=True)


def main():
    if os.path.exists(_TMP):
        os.remove(_TMP)
    with appmod.app.app_context():
        from db import init_db
        init_db()

    client = appmod.app.test_client()

    print("\n1. Coming-soon state")
    signup(client, "Alice", "1234")
    r = client.get("/bracket")
    check("/bracket shows Coming Soon", b"Coming Soon" in r.data or b"Bracket Challenge" in r.data)
    r = client.get("/predict")
    check("/predict shows bracket banner (coming_soon)", b"bracket-banner-coming_soon" in r.data)

    print("\n2. Seed proposed matchups (simulating seed_bracket) + admin gate")
    db = get_db()
    teams = [f"Team{i}" for i in range(32)]
    for i, mid in enumerate(ROUNDS["R32"]):
        db.execute("INSERT INTO bracket_matches (match_id, round, home_team, away_team, "
                   "api_match_id, status) VALUES (%s,'R32',%s,%s,%s,'TIMED')",
                   (mid, teams[2*i], teams[2*i+1], 500000 + mid))
    for rk in ["R16", "QF", "SF", "FINAL"]:
        for mid in ROUNDS[rk]:
            db.execute("INSERT INTO bracket_matches (match_id, round, api_match_id, status) "
                       "VALUES (%s,%s,%s,'TIMED')", (mid, rk, 500000 + mid))
    db.execute("UPDATE bracket_state SET lock_at=%s WHERE id=1",
               ("2030-01-01T00:00:00Z",))
    db.commit()

    r = client.get("/admin/bracket")
    check("admin page blocked without key", r.status_code == 403)
    r = client.get("/admin/bracket?key=smoke-admin")
    check("admin page loads with key", r.status_code == 200 and b"Bracket Admin" in r.data)

    print("\n3. Confirm & open")
    r = client.post("/admin/bracket?key=smoke-admin",
                    data={"key": "smoke-admin", "action": "confirm"}, follow_redirects=True)
    check("confirm opens bracket", b"now OPEN" in r.data)
    st = get_db().execute("SELECT status FROM bracket_state WHERE id=1").fetchone()
    check("state == open", st["status"] == "open")

    print("\n4. Fill with cascade")
    r = client.get("/bracket")
    check("/bracket renders fill view", b"Your Bracket" in r.data)
    # R32 slot 75 = teams[4] vs teams[5]; slot 76 = teams[6] vs teams[7].
    # Standard adjacency: FEEDS[90] = (75, 76) -> slot 90 = winner(75) vs winner(76).
    r1 = client.post("/api/bracket/pick", json={"match_id": 75, "picked_team": teams[4]})
    r2 = client.post("/api/bracket/pick", json={"match_id": 76, "picked_team": teams[6]})
    j2 = r2.get_json()
    slot90 = j2["slot_teams"]["90"]
    check("cascade: slot 90 = winners of 75 & 76",
          set(slot90) == {teams[4], teams[6]})

    # Pick the winner of 90 to be teams[4] (advance further).
    r3 = client.post("/api/bracket/pick", json={"match_id": 90, "picked_team": teams[4]})
    check("can pick downstream winner", r3.get_json().get("ok"))

    # Now change the upstream pick (75 -> teams[5]); downstream pick of 90 (teams[4]) must clear.
    r4 = client.post("/api/bracket/pick", json={"match_id": 75, "picked_team": teams[5]})
    j4 = r4.get_json()
    check("changing upstream clears stale downstream pick", "90" not in j4["picks"])
    check("slot 90 now shows new upstream winner",
          set(j4["slot_teams"]["90"]) == {teams[5], teams[6]})

    # Invalid pick rejected.
    rbad = client.post("/api/bracket/pick", json={"match_id": 73, "picked_team": "Nonexistent"})
    check("invalid team rejected (400)", rbad.status_code == 400)

    print("\n5. Fake early lock — writes rejected")
    db = get_db()
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    db.execute("UPDATE bracket_state SET lock_at=%s WHERE id=1", (past,))
    db.commit()
    rlock = client.post("/api/bracket/pick", json={"match_id": 74, "picked_team": teams[2]})
    check("write rejected after lock (403)", rlock.status_code == 403)
    r = client.get("/bracket")
    check("/bracket shows locked view", b"locked" in r.data.lower())

    print("\n6. Settle results + leaderboard")
    db = get_db()
    # Mark all R32 finished: home advances everywhere.
    for i, mid in enumerate(ROUNDS["R32"]):
        db.execute("UPDATE bracket_matches SET home_advances=1, settled=1, status='FINISHED' "
                   "WHERE match_id=%s", (mid,))
    db.commit()
    n = score_users(db)
    db.commit()
    check("settlement rows written for R16 round", n >= 1)
    row = db.execute("SELECT total_points FROM bracket_settlements "
                     "WHERE user_id=1 AND round='R16'").fetchone()
    # Alice's surviving R32 picks are slot 75 -> teams[5] (away, did NOT advance)
    # and slot 76 -> teams[6] (home, advanced). So at least 1 correct in R16.
    check("Alice has an R16 settlement", row is not None)

    r = client.get("/bracket/leaderboard")
    check("leaderboard renders", b"Bracket Standings" in r.data)

    print("\n" + ("ALL SMOKE CHECKS PASSED " + OK if not fails
                  else f"{BAD} FAILURES: {fails}"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
