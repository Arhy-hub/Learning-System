"""Per-concept mastery: a strength that decays, and a half-life that adapts.

Deliberately driven by test performance only. Owning a note on a topic means
exposure, not understanding, so indexing never moves these numbers -- only a
graded answer does. Coverage is a separate signal, reported alongside.

    effective(t) = strength * 2 ** (-days_since_test / half_life)

A correct answer raises strength toward 1 and stretches the half-life; a miss
drops strength and collapses the half-life back toward the floor. This is the
familiar spaced-repetition shape (SM-2 / FSRS), kept small and inspectable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from .config import MasteryParams

Verdict = str  # "correct" | "partial" | "incorrect"

VERDICT_SCORE = {"correct": 1.0, "partial": 0.5, "incorrect": 0.0}


def now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Mastery:
    concept: str
    strength: float
    half_life: float           # days
    last_tested: datetime | None = None
    n_correct: int = 0
    n_total: int = 0

    def effective(self, at: datetime | None = None, p: MasteryParams | None = None) -> float:
        """Strength after decay. Untested concepts read 0."""
        if self.last_tested is None or self.n_total == 0:
            return 0.0
        at = at or now()
        days = max(0.0, (at - self.last_tested).total_seconds() / 86400.0)
        return round(self.strength * (2.0 ** (-days / max(self.half_life, 1e-6))), 6)

    def is_mastered(self, p: MasteryParams, at: datetime | None = None) -> bool:
        return self.effective(at) >= p.mastered_at

    def is_due(self, p: MasteryParams, at: datetime | None = None) -> bool:
        """Due for review: previously learned, now decayed past the threshold."""
        return self.n_total > 0 and self.effective(at) < p.due_at

    def days_until_due(self, p: MasteryParams, at: datetime | None = None) -> float | None:
        if self.last_tested is None or self.strength <= 0:
            return None
        if p.due_at <= 0 or self.strength < p.due_at:
            return 0.0
        total = self.half_life * math.log2(self.strength / p.due_at)
        at = at or now()
        elapsed = (at - self.last_tested).total_seconds() / 86400.0
        return round(max(0.0, total - elapsed), 3)


def initial(concept: str, p: MasteryParams) -> Mastery:
    return Mastery(concept=concept, strength=p.initial_strength,
                   half_life=p.initial_half_life, last_tested=None)


def apply_result(m: Mastery, verdict: Verdict, p: MasteryParams,
                 at: datetime | None = None, weight: float = 1.0) -> Mastery:
    """Fold one graded answer into a concept's mastery state.

    `weight` scales the update for lower-stakes evidence (a calibration probe
    counts for less than a full exit-test item).
    """
    at = at or now()
    score = VERDICT_SCORE.get(verdict, 0.0)
    base = m.effective(at) if m.n_total else m.strength

    if score >= 1.0:
        strength = base + (1.0 - base) * p.strength_gain * weight
        half_life = m.half_life * (1.0 + (p.success_growth - 1.0) * weight)
    elif score <= 0.0:
        strength = base * (1.0 - p.strength_loss * weight)
        half_life = m.half_life * (1.0 - (1.0 - p.failure_shrink) * weight)
    else:
        # Partial credit: nudge up, leave scheduling roughly where it was.
        strength = base + (1.0 - base) * p.strength_gain * 0.4 * weight
        half_life = m.half_life * (1.0 + 0.15 * weight)

    return replace(
        m,
        strength=round(min(1.0, max(0.0, strength)), 6),
        half_life=round(min(p.max_half_life, max(p.min_half_life, half_life)), 4),
        last_tested=at,
        n_correct=m.n_correct + (1 if score >= 1.0 else 0),
        n_total=m.n_total + 1,
    )


def summarise(states: dict, p: MasteryParams, at: datetime | None = None) -> dict:
    at = at or now()
    eff = {c: m.effective(at) for c, m in states.items()}
    tested = [c for c, m in states.items() if m.n_total > 0]
    return {
        "tracked": len(states),
        "tested": len(tested),
        "mastered": sum(1 for c in tested if eff[c] >= p.mastered_at),
        "due": sum(1 for c in tested if eff[c] < p.due_at),
        "mean_effective": round(sum(eff[c] for c in tested) / len(tested), 4) if tested else 0.0,
    }
