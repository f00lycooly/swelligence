"""Unit tests for sport-preference ranking."""

from __future__ import annotations

from swelligence.ranking import order_sports, preference_rank, rank_score

PRI = ["wingfoil", "kitesurf", "surf", "sup", "wakeboard_inland"]


def test_preference_rank_order():
    assert preference_rank("wingfoil", PRI) == 0
    assert preference_rank("kitesurf", PRI) == 1
    assert preference_rank("wakeboard_inland", PRI) == 4


def test_unlisted_sorts_last():
    assert preference_rank("seaswim", PRI) == len(PRI)


def test_no_priority_is_noop():
    assert rank_score(70, "wakeboard_inland", None) == 70
    assert preference_rank("kitesurf", None) == 0


def test_rank_score_boosts_top_priority():
    # Equal raw scores: wing (rank0) outranks wake (rank4).
    assert rank_score(70, "wingfoil", PRI) > rank_score(70, "wakeboard_inland", PRI)


def test_preference_can_flip_close_scores():
    # Wake slightly higher raw, but wing preferred -> wing ranks above.
    wake = rank_score(72, "wakeboard_inland", PRI)
    wing = rank_score(70, "wingfoil", PRI)
    assert wing > wake


def test_big_gap_not_overridden():
    # A clearly better wake day still beats a mediocre wing day.
    wake = rank_score(90, "wakeboard_inland", PRI)
    wing = rank_score(60, "wingfoil", PRI)
    assert wake > wing


def test_order_sports():
    assert order_sports(["sup", "wingfoil", "surf"], PRI) == ["wingfoil", "surf", "sup"]
