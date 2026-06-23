import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bracket_skeleton import (
    ROUNDS, FEEDS, NEXT_SLOT, next_slot, round_of, ALL_SLOTS,
    predicted_sets_from_picks,
)


def test_slot_counts():
    assert len(ROUNDS["R32"]) == 16
    assert len(ROUNDS["R16"]) == 8
    assert len(ROUNDS["QF"]) == 4
    assert len(ROUNDS["SF"]) == 2
    assert len(ROUNDS["FINAL"]) == 1
    assert ROUNDS["R32"] == list(range(73, 89))


def test_third_place_match_absent():
    # id 103 must never appear anywhere in the skeleton.
    assert 103 not in ALL_SLOTS
    assert 103 not in FEEDS
    for h, a in FEEDS.values():
        assert h != 103 and a != 103


def test_every_winner_feeds_exactly_one_slot():
    # Every slot except the Final (104) must feed exactly one downstream slot,
    # and exactly one (downstream, position) pair.
    feeders = [mid for mid in ALL_SLOTS if mid != 104]

    # Each non-final slot has a next slot.
    for mid in feeders:
        assert next_slot(mid) is not None, f"slot {mid} feeds nowhere"

    # Final feeds nowhere.
    assert next_slot(104) is None

    # No two slots feed the same (downstream, position).
    seen = set()
    for mid in feeders:
        ds, pos = next_slot(mid)
        key = (ds, pos)
        assert key not in seen, f"two feeders into {key}"
        seen.add(key)

    # Every downstream slot is fed by exactly two distinct feeders (home+away).
    for downstream in list(ROUNDS["R16"]) + ROUNDS["QF"] + ROUNDS["SF"] + ROUNDS["FINAL"]:
        srcs = [mid for mid in feeders if next_slot(mid)[0] == downstream]
        assert len(srcs) == 2, f"slot {downstream} fed by {srcs}"


def test_round_by_round_feed_integrity():
    # Every R32 winner (73-88) feeds an R16 slot.
    for mid in ROUNDS["R32"]:
        assert round_of(next_slot(mid)[0]) == "R16"
    # Every R16 winner feeds a QF slot.
    for mid in ROUNDS["R16"]:
        assert round_of(next_slot(mid)[0]) == "QF"
    # Every QF winner feeds an SF slot.
    for mid in ROUNDS["QF"]:
        assert round_of(next_slot(mid)[0]) == "SF"
    # Every SF winner feeds the Final.
    for mid in ROUNDS["SF"]:
        assert next_slot(mid)[0] == 104


def test_feeds_match_spec_exactly():
    # Verbatim from the spec.
    assert FEEDS[89] == (74, 77)
    assert FEEDS[90] == (73, 75)
    assert FEEDS[91] == (76, 78)
    assert FEEDS[92] == (79, 80)
    assert FEEDS[93] == (83, 84)
    assert FEEDS[94] == (81, 82)
    assert FEEDS[95] == (86, 88)
    assert FEEDS[96] == (85, 87)
    assert FEEDS[97] == (89, 90)
    assert FEEDS[98] == (93, 94)
    assert FEEDS[99] == (91, 92)
    assert FEEDS[100] == (95, 96)
    assert FEEDS[101] == (97, 98)
    assert FEEDS[102] == (99, 100)
    assert FEEDS[104] == (101, 102)


def test_predicted_sets_from_picks():
    picks = {}
    # R32: 16 distinct winners.
    for i, mid in enumerate(ROUNDS["R32"]):
        picks[mid] = f"R32team{i}"
    # R16: 8 winners.
    for i, mid in enumerate(ROUNDS["R16"]):
        picks[mid] = f"R16team{i}"
    # QF: 4 winners.
    for i, mid in enumerate(ROUNDS["QF"]):
        picks[mid] = f"QFteam{i}"
    # SF: 2 winners.
    for i, mid in enumerate(ROUNDS["SF"]):
        picks[mid] = f"SFteam{i}"
    # FINAL: champion.
    picks[104] = "Champ"

    sets = predicted_sets_from_picks(picks)
    assert len(sets["R16"]) == 16
    assert len(sets["QF"]) == 8
    assert len(sets["SF"]) == 4
    assert len(sets["FINAL"]) == 2
    assert sets["CHAMPION"] == "Champ"


def test_predicted_sets_partial():
    # A partial bracket: only a couple of R32 picks made.
    picks = {73: "A", 74: "B"}
    sets = predicted_sets_from_picks(picks)
    assert sets["R16"] == {"A", "B"}
    assert sets["QF"] == set()
    assert sets["CHAMPION"] is None
