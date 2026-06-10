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
    assert r["base"] == 20

def test_zero_base():
    # 2-1 pred, 0-3 actual → completely wrong
    r = score_prediction(2, 1, 0, 3)
    assert r["base"] == 0

def test_brave_call_bonus():
    r = score_prediction(0, 0, 1, 1)
    assert r["base"] == 60
    assert "Brave Call" in r["bonus_labels"]
    assert r["bonus"] >= 10

def test_clean_sheet_caller_bonus():
    r = score_prediction(2, 0, 1, 0)
    assert r["base"] == 40
    assert "Clean Sheet Caller" in r["bonus_labels"]

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
    # 3-1 pred, 2-2 actual → different results (home win vs draw), totals both 4
    # one-goal-away: |3-2|+|1-2|=1+1=2, base=0...
    # Actually let's do 2-0 pred, 1-1 actual: totals both 2 but different result
    # one-goal-away check: |2-1|+|0-1|=1+1=2, not one away → base=0
    # Try 3-0 pred, 2-1 actual: same result (home win), margin 3 vs 1 → base=50, totals differ
    # Try 2-1 pred, 3-0 actual: base=50, totals 3 vs 3 → Sharp Total!
    r = score_prediction(2, 1, 3, 0)
    assert r["base"] == 40
    assert "Sharp Total" in r["bonus_labels"]

def test_clean_sheet_away_side():
    r = score_prediction(0, 2, 0, 1)
    assert r["base"] == 40
    assert "Clean Sheet Caller" in r["bonus_labels"]

def test_clean_sheet_not_awarded_if_wrong_result():
    # 2-0 pred (home win, away CS), 0-1 actual (away win) → base=0, no bonuses
    r = score_prediction(2, 0, 0, 1)
    assert r["base"] == 0
    assert "Clean Sheet Caller" not in r["bonus_labels"]

def test_exact_with_clean_sheet_bonus():
    # 2-0 pred, 2-0 actual → exact (100) + Clean Sheet (away) = 115
    r = score_prediction(2, 0, 2, 0)
    assert r["base"] == 100
    assert "Clean Sheet Caller" in r["bonus_labels"]
    assert r["total"] == 115

def test_exact_with_brave_call_bonus():
    # 0-0 pred, 0-0 actual → exact (100) + Brave Call = 110 + Clean Sheet x2?
    # Both sides keep clean sheet → only one Clean Sheet label per match
    r = score_prediction(0, 0, 0, 0)
    assert r["base"] == 100
    assert "Brave Call" in r["bonus_labels"]

def test_zero_base_no_bonuses():
    r = score_prediction(3, 0, 0, 3)
    assert r["base"] == 0
    assert r["bonus"] == 0
    assert r["total"] == 0

def test_one_goal_away_no_bonuses():
    r = score_prediction(2, 1, 1, 1)
    assert r["base"] == 20
    assert r["bonus"] == 0
