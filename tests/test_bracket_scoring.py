import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bracket_scoring import (
    score_round, score_bracket, round_max, grand_total_max, BRACKET_ROUNDS,
)


# Helpers to build predicted/actual sets with a controllable number of overlaps.
def sets_with_overlap(total_actual, n_correct):
    """Return (predicted, actual): two sets of size `total_actual` overlapping in
    exactly n_correct teams."""
    actual = {f"A{i}" for i in range(total_actual)}
    correct = {f"A{i}" for i in range(n_correct)}
    wrong = {f"X{i}" for i in range(total_actual - n_correct)}
    predicted = correct | wrong
    return predicted, actual


# ── R32 → R16 (count 16, +10 each, +30 at 13-15, +90 at 16) ───────────────────

def test_r16_10_correct():
    p, a = sets_with_overlap(16, 10)
    assert score_round("R16", p, a)["total_points"] == 100

def test_r16_13_correct():
    p, a = sets_with_overlap(16, 13)
    r = score_round("R16", p, a)
    assert r["base_points"] == 130 and r["bonus_points"] == 30
    assert r["total_points"] == 160

def test_r16_15_correct():
    p, a = sets_with_overlap(16, 15)
    r = score_round("R16", p, a)
    assert r["base_points"] == 150 and r["bonus_points"] == 30
    assert r["total_points"] == 180

def test_r16_perfect():
    p, a = sets_with_overlap(16, 16)
    r = score_round("R16", p, a)
    assert r["base_points"] == 160 and r["bonus_points"] == 90
    assert r["total_points"] == 250

def test_r16_zero():
    p, a = sets_with_overlap(16, 0)
    assert score_round("R16", p, a)["total_points"] == 0


# ── R16 → QF (count 8, +20 each, +40 at 7, +90 at 8) ──────────────────────────

def test_qf_round_6_correct():
    p, a = sets_with_overlap(8, 6)
    assert score_round("QF", p, a)["total_points"] == 120

def test_qf_round_7_correct():
    p, a = sets_with_overlap(8, 7)
    r = score_round("QF", p, a)
    assert r["base_points"] == 140 and r["bonus_points"] == 40
    assert r["total_points"] == 180

def test_qf_round_perfect():
    p, a = sets_with_overlap(8, 8)
    r = score_round("QF", p, a)
    assert r["base_points"] == 160 and r["bonus_points"] == 90
    assert r["total_points"] == 250


# ── QF → SF (count 4, +50 each, +100 at 4) ────────────────────────────────────

def test_sf_round_3_correct():
    p, a = sets_with_overlap(4, 3)
    assert score_round("SF", p, a)["total_points"] == 150

def test_sf_round_perfect():
    p, a = sets_with_overlap(4, 4)
    r = score_round("SF", p, a)
    assert r["base_points"] == 200 and r["bonus_points"] == 100
    assert r["total_points"] == 300


# ── SF → finalists (count 2, +150 each, +100 at 2) ────────────────────────────

def test_final_1_correct():
    p, a = sets_with_overlap(2, 1)
    assert score_round("FINAL", p, a)["total_points"] == 150

def test_final_perfect():
    p, a = sets_with_overlap(2, 2)
    r = score_round("FINAL", p, a)
    assert r["base_points"] == 300 and r["bonus_points"] == 100
    assert r["total_points"] == 400


# ── Final → champion (count 1, +500) ──────────────────────────────────────────

def test_champion_correct():
    assert score_round("CHAMPION", "Brazil", "Brazil")["total_points"] == 500

def test_champion_wrong():
    assert score_round("CHAMPION", "Brazil", "France")["total_points"] == 0


# ── Maxes ─────────────────────────────────────────────────────────────────────

def test_round_maxes():
    assert round_max("R16") == 250
    assert round_max("QF") == 250
    assert round_max("SF") == 300
    assert round_max("FINAL") == 400
    assert round_max("CHAMPION") == 500

def test_grand_total_max():
    assert grand_total_max() == 1700


# ── One full-bracket fixture: sample actual + sample user bracket ──────────────

def test_full_bracket_fixture():
    # Actual results.
    actual = {
        "R16": {f"T{i}" for i in range(16)},          # T0..T15 reached R16
        "QF":  {f"T{i}" for i in range(8)},           # T0..T7 reached QF
        "SF":  {"T0", "T1", "T2", "T3"},              # reached SF
        "FINAL": {"T0", "T1"},                        # finalists
        "CHAMPION": "T0",                             # champion
    }
    # User bracket:
    #   R16: gets 14/16 right (T0..T13 right, X0/X1 wrong)  -> 140 + 30 = 170
    #   QF : gets 6/8 right  (T0..T5 right, X0/X1 wrong)    -> 120 + 0  = 120
    #   SF : gets 3/4 right  (T0,T1,T2 right, X0 wrong)     -> 150 + 0  = 150
    #   FIN: gets 1/2 right  (T0 right, X0 wrong)           -> 150 + 0  = 150
    #   CHP: T0 right                                       -> 500
    predicted = {
        "R16": {f"T{i}" for i in range(14)} | {"X0", "X1"},
        "QF":  {f"T{i}" for i in range(6)} | {"X0", "X1"},
        "SF":  {"T0", "T1", "T2", "X0"},
        "FINAL": {"T0", "X0"},
        "CHAMPION": "T0",
    }

    result = score_bracket(predicted, actual)
    rounds = result["rounds"]

    assert rounds["R16"]["correct_count"] == 14
    assert rounds["R16"]["total_points"] == 170
    assert rounds["QF"]["correct_count"] == 6
    assert rounds["QF"]["total_points"] == 120
    assert rounds["SF"]["correct_count"] == 3
    assert rounds["SF"]["total_points"] == 150
    assert rounds["FINAL"]["correct_count"] == 1
    assert rounds["FINAL"]["total_points"] == 150
    assert rounds["CHAMPION"]["correct_count"] == 1
    assert rounds["CHAMPION"]["total_points"] == 500

    assert result["total_points"] == 170 + 120 + 150 + 150 + 500  # 1090


def test_score_bracket_skips_unfinished_rounds():
    # Only R16 results are in; later rounds not yet final -> only R16 scored.
    actual = {"R16": {f"T{i}" for i in range(16)}}
    predicted = {
        "R16": {f"T{i}" for i in range(16)},
        "QF": {"T0"}, "SF": {"T0"}, "FINAL": {"T0"}, "CHAMPION": "T0",
    }
    result = score_bracket(predicted, actual)
    assert set(result["rounds"].keys()) == {"R16"}
    assert result["total_points"] == 250
