import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from scoring import score_prediction


# ── Canonical cases from the spec ────────────────────────────────────────────

def test_exact_score():
    r = score_prediction(2, 1, 2, 1)
    assert r["base"] == 100
    assert r["total"] >= 100

def test_result_and_margin():
    r = score_prediction(2, 1, 1, 0)
    assert r["base"] == 60

def test_draw_same_margin():
    r = score_prediction(1, 1, 2, 2)
    assert r["base"] == 60

def test_result_only():
    r = score_prediction(2, 1, 3, 0)
    assert r["base"] == 40

def test_one_goal_away():
    r = score_prediction(2, 1, 1, 1)
    assert r["base"] == 15

def test_zero_base():
    # 2-1 pred, 0-3 actual → completely wrong
    r = score_prediction(2, 1, 0, 3)
    assert r["base"] == 0

def test_brave_call_removed():
    r = score_prediction(0, 0, 1, 1)
    assert r["base"] == 60
    assert "Brave Call" not in r["bonus_labels"]

def test_clean_sheet_caller_bonus():
    r = score_prediction(2, 0, 1, 0)
    assert r["base"] == 40
    assert "Clean Sheet Caller" in r["bonus_labels"]
    assert r["bonus"] == 5

def test_sharp_total_no_apply_when_base_zero():
    # 1-2 pred, 2-1 actual → different results, not one-goal-away (|1-2|+|2-1|=1+1=2)
    # base == 0, Sharp Total must NOT apply
    r = score_prediction(1, 2, 2, 1)
    assert r["base"] == 0
    assert "Sharp Total" not in r["bonus_labels"]
    assert r["bonus"] == 0


# ── Additional edge cases ─────────────────────────────────────────────────────

def test_exact_score_no_sharp_total_double_pay():
    # Exact score: Sharp Total condition is true but base==100 so it's suppressed
    r = score_prediction(2, 1, 2, 1)
    assert "Sharp Total" not in r["bonus_labels"]

def test_sharp_total_applies():
    r = score_prediction(2, 1, 3, 0)
    assert r["base"] == 40
    assert "Sharp Total" in r["bonus_labels"]
    assert r["bonus"] == 5

def test_clean_sheet_away_side():
    r = score_prediction(0, 2, 0, 1)
    assert r["base"] == 40
    assert "Clean Sheet Caller" in r["bonus_labels"]

def test_clean_sheet_not_awarded_if_wrong_result():
    # 2-0 pred (home win, away CS), 0-1 actual (away win) → base=0, no bonuses
    r = score_prediction(2, 0, 0, 1)
    assert r["base"] == 0
    assert "Clean Sheet Caller" not in r["bonus_labels"]

def test_exact_no_bonuses():
    # Exact score: bonuses never apply, total stays at 100
    r = score_prediction(2, 0, 2, 0)
    assert r["base"] == 100
    assert r["bonus"] == 0
    assert r["total"] == 100

    r2 = score_prediction(0, 0, 0, 0)
    assert r2["base"] == 100
    assert r2["bonus"] == 0
    assert r2["total"] == 100

def test_zero_base_no_bonuses():
    r = score_prediction(3, 0, 0, 3)
    assert r["base"] == 0
    assert r["bonus"] == 0
    assert r["total"] == 0

def test_one_goal_away_no_bonuses():
    r = score_prediction(2, 1, 1, 1)
    assert r["base"] == 15
    assert r["bonus"] == 0

def test_bonus_never_exceeds_ten():
    cases = [
        (2, 1, 3, 0), (1, 0, 2, 0), (0, 1, 0, 2),
        (1, 1, 2, 2), (0, 0, 1, 1),
    ]
    for args in cases:
        r = score_prediction(*args)
        assert r["bonus"] <= 10, f"bonus exceeded 10 for {args}: {r}"
