"""
Asserts the bracket advancement wiring matches the spec (Step 2): adjacent
winners meet each round, the two halves only meet in the Final, and the hardcoded
R32 matchups are well-formed. This is the test that guards against the matchup /
advancement mis-wiring that was being fixed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bracket_skeleton import ROUNDS, FEEDS, next_slot, round_of
from data.bracket_r32 import R32_MATCHUPS, matchups_by_slot, slot_for_match, all_teams


# ── Step 2: explicit wiring ──────────────────────────────────────────────────

def test_r16_pairs_adjacent_r32_winners():
    # R16_k is fed by R32 matches (2k-1, 2k). Slot for match N is 72+N.
    r16 = ROUNDS["R16"]
    for k, r16_slot in enumerate(r16, start=1):
        m_a, m_b = 2 * k - 1, 2 * k
        assert FEEDS[r16_slot] == (slot_for_match(m_a), slot_for_match(m_b))


def test_each_winner_feeds_exactly_one_next_slot():
    # R32 winners -> exactly one R16 slot each; R16 -> one QF; QF -> one SF;
    # both SF -> the Final. (Bijection per round, no slot fed twice.)
    chain = [("R32", "R16"), ("R16", "QF"), ("QF", "SF"), ("SF", "FINAL")]
    for src, dst in chain:
        targets = []
        for mid in ROUNDS[src]:
            ds, pos = next_slot(mid)
            assert round_of(ds) == dst, f"{src} slot {mid} feeds {dst}? got {round_of(ds)}"
            targets.append((ds, pos))
        # No two feeders collide on the same (slot, position).
        assert len(set(targets)) == len(targets)
        # Every dst slot is fed by exactly two feeders.
        for dslot in ROUNDS[dst]:
            assert sum(1 for ds, _ in targets if ds == dslot) == 2

    # Both SF winners feed the single Final slot.
    assert {next_slot(s)[0] for s in ROUNDS["SF"]} == {ROUNDS["FINAL"][0]}


def _semifinal_of(r32_slot):
    """Trace an R32 slot forward to the semifinal slot it funnels into."""
    mid = r32_slot
    while round_of(mid) != "SF":
        mid = next_slot(mid)[0]
    return mid


def test_halves_only_meet_in_final():
    # Left half = matches 1..8 (slots 73..80); right half = 9..16 (slots 81..88).
    left = [slot_for_match(n) for n in range(1, 9)]
    right = [slot_for_match(n) for n in range(9, 17)]

    left_sf = {_semifinal_of(s) for s in left}
    right_sf = {_semifinal_of(s) for s in right}

    # Each half collapses into exactly one (distinct) semifinal — so no two
    # same-half teams can meet before the Final, and cross-half teams can only
    # meet in the Final.
    assert len(left_sf) == 1
    assert len(right_sf) == 1
    assert left_sf.isdisjoint(right_sf)


# ── Step 1: hardcoded R32 data integrity ─────────────────────────────────────

def test_r32_has_16_matchups_and_32_distinct_teams():
    assert sorted(R32_MATCHUPS) == list(range(1, 17))
    teams = all_teams()
    assert len(teams) == 32
    assert len(set(teams)) == 32, "duplicate team in data/bracket_r32.py"


def test_r32_slots_align_with_skeleton():
    assert sorted(matchups_by_slot()) == ROUNDS["R32"]
