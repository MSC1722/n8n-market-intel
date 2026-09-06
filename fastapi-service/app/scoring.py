"""Deterministic relevance scoring.

The LLM gives one subjective number (impact 0-10). That number alone is a bad
routing signal: it drifts between runs, it ignores how stale the article is,
it does not know that Reuters is a better source than an aggregator, and it
will happily re-score the fourth retelling of the same story as a fresh 9.

This module folds the LLM's opinion together with signals the LLM cannot see —
publication age, source reputation, resolved entity weight, cluster novelty —
into one reproducible 0-100 score, and returns the breakdown so a human can
audit any alert.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

# Weights sum to 1.0. Tuned so that a mega-cap earnings surprise from a tier-1
# wire clears the alert threshold, while a stale opinion piece never does.
#
# Novelty is deliberately NOT in this dict. It is applied as a multiplier
# afterwards, because a retelling is not "a slightly less relevant article" —
# it is the same article, and it should be scaled down, not nudged down.
WEIGHTS = {
    "impact": 0.35,
    "entity": 0.28,
    "recency": 0.22,
    "source": 0.15,
}

# Exponential decay: an article is worth half as much after this many hours.
RECENCY_HALF_LIFE_HOURS = 8.0

SOURCE_WEIGHTS = {
    "reuters": 1.00,
    "bloomberg": 1.00,
    "wsj": 0.95,
    "ft": 0.95,
    "cnbc": 0.85,
    "marketwatch": 0.75,
    "yahoo_finance": 0.65,
    "investing_com": 0.60,
    "seeking_alpha": 0.55,
    "unknown": 0.50,
}

HIGH_THRESHOLD = 70.0
MEDIUM_THRESHOLD = 45.0


def recency_signal(published_at: datetime | None, now: datetime | None = None) -> float:
    if published_at is None:
        return 0.5  # unknown age: neutral, neither rewarded nor punished
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_hours = max((now - published_at).total_seconds() / 3600.0, 0.0)
    return round(math.pow(0.5, age_hours / RECENCY_HALF_LIFE_HOURS), 4)


def source_signal(source: str) -> float:
    return SOURCE_WEIGHTS.get((source or "").lower(), SOURCE_WEIGHTS["unknown"])


NOVELTY_FLOOR = 0.35


def novelty_signal(is_followup: bool, cluster_size: int) -> float:
    """First telling of a story is worth full marks; each retelling decays.

    Without this the pipeline pages you five times for one Fed decision.
    Decay is 1/sqrt(n) rather than 1/n so that the second outlet covering a
    genuinely big story still reaches the medium tier.
    """
    if not is_followup or cluster_size <= 1:
        return 1.0
    return round(max(NOVELTY_FLOOR, 1.0 / math.sqrt(cluster_size)), 4)


def score(
    *,
    impact_score: float,
    entity_signal_value: float,
    published_at: datetime | None,
    source: str,
    is_followup: bool,
    cluster_size: int,
    now: datetime | None = None,
) -> tuple[float, dict[str, float], str]:
    parts = {
        "impact": round(min(max(impact_score, 0.0), 10.0) / 10.0, 4),
        "entity": round(min(max(entity_signal_value, 0.0), 1.0), 4),
        "recency": recency_signal(published_at, now),
        "source": source_signal(source),
    }
    base = sum(WEIGHTS[k] * v for k, v in parts.items())
    novelty = novelty_signal(is_followup, cluster_size)
    total = round(100.0 * base * novelty, 2)
    parts["novelty"] = novelty

    ranked = sorted(WEIGHTS.items(), key=lambda kv: parts[kv[0]] * kv[1])
    weakest, strongest = ranked[0][0], ranked[-1][0]
    reason = (
        f"top contributor: {strongest} ({parts[strongest]:.2f}), "
        f"weakest: {weakest} ({parts[weakest]:.2f})"
    )
    if novelty < 1.0:
        reason += f"; x{novelty:.2f} repeat-story penalty (cluster of {cluster_size})"
    return total, parts, reason


def priority_of(total: float) -> str:
    if total >= HIGH_THRESHOLD:
        return "high"
    if total >= MEDIUM_THRESHOLD:
        return "medium"
    return "low"
