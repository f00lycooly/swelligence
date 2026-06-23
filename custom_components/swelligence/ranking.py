"""Sport-preference ranking (pure).

A user's sport priority (most-wanted first) nudges ranked views so favoured
sports surface on close calls — e.g. wing/kite over wake when scores are similar
— without hiding anything. The raw suitability score is never mutated; only the
*ranking key* is adjusted.
"""

from __future__ import annotations

DEFAULT_BOOST = 8.0
DEFAULT_STEP = 1.2


def preference_rank(sport: str, priority: list[str] | None) -> int:
    """Index of a sport in the priority list (lower = more wanted).

    Sports not listed sort after listed ones.
    """
    if priority and sport in priority:
        return priority.index(sport)
    return len(priority) if priority else 0


def rank_score(
    raw: float,
    sport: str,
    priority: list[str] | None,
    *,
    boost: float = DEFAULT_BOOST,
    step: float = DEFAULT_STEP,
) -> float:
    """Ranking key = raw score + a small preference bonus.

    The top-priority sport gets +boost, decaying by ``step`` per rank, never
    below 0. With no priority, returns the raw score unchanged.
    """
    if not priority:
        return raw
    bonus = max(0.0, boost - preference_rank(sport, priority) * step)
    return raw + bonus


def order_sports(sports: list[str], priority: list[str] | None) -> list[str]:
    """Return ``sports`` ordered by preference (stable for unlisted)."""
    return sorted(sports, key=lambda s: preference_rank(s, priority))
