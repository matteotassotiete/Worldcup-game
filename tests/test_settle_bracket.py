import os
import sys
import tempfile

# Use a throwaway sqlite DB and never touch Postgres.
_TMP = tempfile.mktemp(suffix=".db")
os.environ["DB_PATH"] = _TMP
os.environ.pop("DATABASE_URL", None)

_BASE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _BASE)
sys.path.insert(0, os.path.join(_BASE, "scripts"))

import db as dbmod
dbmod.DB_PATH = _TMP  # force, in case it imported with a different default

from db import init_db, get_db
from bracket_skeleton import ROUNDS
from settle_bracket import score_users, record_results, maybe_lock


def _setup():
    if os.path.exists(_TMP):
        os.remove(_TMP)
    init_db()
    db = get_db()
    db.execute("INSERT INTO bracket_state (id, status, lock_at) VALUES (1, 'open', %s)",
               ("2020-01-01T00:00:00Z",))

    # Two users.
    db.execute("INSERT INTO users (id, team_name, pin_hash) VALUES (1, 'Alice', 'x')")
    db.execute("INSERT INTO users (id, team_name, pin_hash) VALUES (2, 'Bob', 'x')")

    # Build a deterministic finished tournament. home always advances.
    advancers = {}  # round -> list of advancing teams in slot order

    # R32: 16 matches, advancers T0,T2,...,T30
    r32_adv = []
    for i, mid in enumerate(ROUNDS["R32"]):
        home, away = f"T{2*i}", f"T{2*i+1}"
        db.execute("INSERT INTO bracket_matches (match_id, round, home_team, away_team, "
                   "home_advances, settled) VALUES (%s,'R32',%s,%s,1,1)", (mid, home, away))
        r32_adv.append(home)
    advancers["R16"] = set(r32_adv)  # teams reaching R16

    def fill(round_key, adv_list):
        for j, mid in enumerate(ROUNDS[round_key]):
            home = adv_list[j]
            away = f"L{round_key}{j}"
            db.execute(f"INSERT INTO bracket_matches (match_id, round, home_team, away_team, "
                       f"home_advances, settled) VALUES (%s,'{round_key}',%s,%s,1,1)",
                       (mid, home, away))

    r16_adv = [r32_adv[k] for k in (0, 2, 4, 6, 8, 10, 12, 14)]   # 8 teams
    fill("R16", r16_adv);  advancers["QF"] = set(r16_adv)
    qf_adv = [r16_adv[k] for k in (0, 2, 4, 6)]                    # 4 teams
    fill("QF", qf_adv);    advancers["SF"] = set(qf_adv)
    sf_adv = [qf_adv[k] for k in (0, 2)]                           # 2 teams
    fill("SF", sf_adv);    advancers["FINAL"] = set(sf_adv)
    fill("FINAL", [sf_adv[0]])                                     # champion
    champion = sf_adv[0]

    # Alice picks a perfect bracket.
    def set_picks(uid, by_round):
        for round_key, teams in by_round.items():
            for mid, team in zip(ROUNDS[round_key], teams):
                if team is None:
                    continue
                db.execute("INSERT INTO bracket_picks (user_id, match_id, picked_team) "
                           "VALUES (%s,%s,%s)", (uid, mid, team))

    set_picks(1, {
        "R32": r32_adv, "R16": r16_adv, "QF": qf_adv, "SF": sf_adv, "FINAL": [champion],
    })
    # Bob: partial / imperfect — only first 8 R32 right, picks champion wrong.
    bob_r32 = r32_adv[:8] + ["WRONG"] * 8
    set_picks(2, {"R32": bob_r32, "FINAL": ["NOBODY"]})

    db.commit()
    return db, champion


def _totals(db):
    rows = db.execute("SELECT user_id, round, total_points FROM bracket_settlements "
                      "ORDER BY user_id, round").fetchall()
    return [(r["user_id"], r["round"], r["total_points"]) for r in rows]


def test_score_users_idempotent():
    db, champion = _setup()

    n1 = score_users(db); db.commit()
    snap1 = _totals(db)
    count1 = db.execute("SELECT COUNT(*) AS n FROM bracket_settlements").fetchone()["n"]

    # Alice perfect = 1700 across 5 rounds.
    alice = {r: p for (u, r, p) in snap1 if u == 1}
    assert alice == {"R16": 250, "QF": 250, "SF": 300, "FINAL": 400, "CHAMPION": 500}
    assert sum(alice.values()) == 1700

    # Bob: 8/16 R16 -> 80; champion wrong -> 0.
    bob = {r: p for (u, r, p) in snap1 if u == 2}
    assert bob["R16"] == 80
    assert bob["CHAMPION"] == 0

    # Run again — no double-award, identical totals.
    n2 = score_users(db); db.commit()
    snap2 = _totals(db)
    count2 = db.execute("SELECT COUNT(*) AS n FROM bracket_settlements").fetchone()["n"]

    assert n2 == 0
    assert snap1 == snap2
    assert count1 == count2


def test_record_results_idempotent():
    db, _ = _setup()
    # Slot with an API id, not yet settled.
    db.execute("INSERT INTO bracket_matches (match_id, round, api_match_id, settled) "
               "VALUES (200, 'R32', 999, 0)")
    db.commit()
    api = {999: {"status": "FINISHED",
                 "homeTeam": {"shortName": "Brazil"},
                 "awayTeam": {"shortName": "Serbia"},
                 "score": {"winner": "HOME_TEAM"}}}

    n1 = record_results(db, api); db.commit()
    row1 = db.execute("SELECT home_team, home_advances, settled FROM bracket_matches "
                      "WHERE match_id=200").fetchone()
    assert n1 == 1
    assert row1["home_team"] == "Brazil" and row1["home_advances"] == 1 and row1["settled"] == 1

    # Re-run: already settled -> skipped, unchanged.
    n2 = record_results(db, api); db.commit()
    row2 = db.execute("SELECT home_team, home_advances, settled FROM bracket_matches "
                      "WHERE match_id=200").fetchone()
    assert n2 == 0
    assert dict(row2) == dict(row1)


def test_maybe_lock_flips_once():
    db, _ = _setup()  # lock_at in the past, status 'open'
    assert maybe_lock(db) is True
    db.commit()
    assert db.execute("SELECT status FROM bracket_state WHERE id=1").fetchone()["status"] == "locked"
    # Already locked -> no further flip.
    assert maybe_lock(db) is False
