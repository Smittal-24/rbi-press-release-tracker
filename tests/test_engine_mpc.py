import copy

from rbi_tracker.engine import compare
from engine_data import *  # noqa: F401,F403


def test_rate_cut_is_priority_in_bps():
    d = compare(MPC_NEW, MPC_PREV)
    c = find(d, "repo_rate")[0]
    assert (c.previous, c.new, c.delta, c.unit, c.priority) == (5.5, 5.25, -25.0, "bps", True)
    assert find(d, "decision")[0].priority


def test_members_who_switched_direction_are_flagged():
    d = compare(MPC_NEW, MPC_PREV)
    switched = {c.key for c in find(d, "member_vote_switch")}
    assert switched == {"Member A", "Member F"}
    assert all(c.priority for c in find(d, "member_vote_switch"))
    assert "Member B (hold)" in d.unchanged


def test_vote_split_change():
    d = compare(MPC_NEW, MPC_PREV)
    c = find(d, "vote_split")[0]
    assert (c.previous, c.new) == ("6 hold", "4 hold, 2 cut")


def test_outlook_shift_numeric_and_language():
    d = compare(MPC_NEW, MPC_PREV)
    assert find(d, "inflation_projection")[0].delta == -0.1
    assert find(d, "inflation_outlook")[0].priority
    assert "GDP growth projection" in d.unchanged
    assert "Growth outlook language" in d.unchanged


def test_identical_minutes_have_no_changes():
    d = compare(MPC_PREV, copy.deepcopy(MPC_PREV))
    assert d.changes == []
    assert "Policy repo rate" in d.unchanged


def test_same_direction_but_different_size_is_a_non_priority_change():
    prev = copy.deepcopy(MPC_NEW)
    new = copy.deepcopy(MPC_NEW)
    new.release_date = "2027-02-06"
    new.rows[0]["vote_bps"] = 50          # Member A: cut 25 -> cut 50
    c = find(compare(new, prev), "member_vote_size", "Member A")[0]
    assert (c.previous, c.new, c.priority) == (25, 50, False)


def test_first_minutes_have_nothing_to_compare():
    d = compare(MPC_NEW, None)
    assert d.changes == [] and not d.has_previous
