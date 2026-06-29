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
    # Standard adjacency — verbatim from the bracket spec (Step 2).
    # R16: adjacent R32 winners (slot 72+N for match N).
    assert FEEDS[89] == (73, 74)    # R16_1 = winner(1)  vs winner(2)
    assert FEEDS[90] == (75, 76)    # R16_2 = winner(3)  vs winner(4)
    assert FEEDS[91] == (77, 78)    # R16_3 = winner(5)  vs winner(6)
    assert FEEDS[92] == (79, 80)    # R16_4 = winner(7)  vs winner(8)
    assert FEEDS[93] == (81, 82)    # R16_5 = winner(9)  vs winner(10)
    assert FEEDS[94] == (83, 84)    # R16_6 = winner(11) vs winner(12)
    assert FEEDS[95] == (85, 86)    # R16_7 = winner(13) vs winner(14)
    assert FEEDS[96] == (87, 88)    # R16_8 = winner(15) vs winner(16)
    # QF
    assert FEEDS[97] == (89, 90)    # QF_1 = R16_1 vs R16_2
    assert FEEDS[98] == (91, 92)    # QF_2 = R16_3 vs R16_4
    assert FEEDS[99] == (93, 94)    # QF_3 = R16_5 vs R16_6
    assert FEEDS[100] == (95, 96)   # QF_4 = R16_7 vs R16_8
    # SF
    assert FEEDS[101] == (97, 98)   # SF_1 = QF_1 vs QF_2 (left half)
    assert FEEDS[102] == (99, 100)  # SF_2 = QF_3 vs QF_4 (right half)
    # Final
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
