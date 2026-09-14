"""The question bank: questions as reusable objects, not throwaway text.

A question that exposed a real misconception is the most valuable thing a
session produces, and the first version of this system discarded it. Here each
question is kept, scored, scheduled and eventually retired.

Two ideas do the work:

*Item-level spacing.* Concept mastery decays, but you forget specific things.
Each question carries its own cooldown, doubling with each consecutive correct
answer and collapsing to a day on a miss (a Leitner ladder). Asking something
answered correctly an hour ago measures recall of that answer, not the idea, so
the selector refuses to.

*Kind balance.* Five definitions in a row is not an assessment. Selection
spreads across definition / application / edge / proof and ramps difficulty to
where calibration actually landed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .text import content_words, jaccard

KINDS = ("definition", "application", "edge", "proof")

# A near-duplicate of an existing question is the same question reworded.
DUPLICATE_AT = 0.80

# Leitner ladder, in days, indexed by consecutive correct answers.
COOLDOWN = (1, 3, 7, 21, 60, 180)

# A question everyone always gets right stops discriminating.
RETIRE_AFTER_CORRECT = 5


def qid(text: str) -> str:
    """Stable short id from the question text."""
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return "q" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:8]


def now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Question:
    id: str
    concept: str
    text: str
    kind: str = "application"
    difficulty: int = 3            # 1..5
    asked: int = 0
    correct: int = 0
    streak: int = 0                # consecutive correct
    last_asked: datetime | None = None
    last_verdict: str = ""
    retired: bool = False
    source: str = "session"        # session | authored

    @property
    def cooldown_days(self) -> int:
        if self.last_verdict == "incorrect":
            return 1
        if self.last_verdict == "partial":
            return 2
        return COOLDOWN[min(self.streak, len(COOLDOWN) - 1)]

    def due_at(self):
        if self.last_asked is None:
            return None
        return self.last_asked + timedelta(days=self.cooldown_days)

    def is_cooling(self, at: datetime | None = None) -> bool:
        """True while it is too soon to ask this again."""
        d = self.due_at()
        return d is not None and (at or now()) < d

    def days_overdue(self, at: datetime | None = None) -> float:
        d = self.due_at()
        if d is None:
            return 0.0
        return max(0.0, ((at or now()) - d).total_seconds() / 86400.0)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "concept": self.concept, "text": self.text,
            "kind": self.kind, "difficulty": self.difficulty,
            "asked": self.asked, "correct": self.correct, "streak": self.streak,
            "last_asked": self.last_asked.isoformat()[:10] if self.last_asked else None,
            "last_verdict": self.last_verdict or None,
            "cooling": self.is_cooling(), "retired": self.retired,
        }


def is_duplicate(text: str, existing: list) -> Question | None:
    """A reworded version of a question already banked, if there is one."""
    w = content_words(text)
    if not w:
        return None
    for q in existing:
        if jaccard(w, content_words(q.text)) >= DUPLICATE_AT:
            return q
    return None


def should_retire(q: Question) -> bool:
    """Retire what no longer discriminates: always right, and asked enough."""
    return q.asked >= RETIRE_AFTER_CORRECT and q.correct == q.asked and q.streak >= RETIRE_AFTER_CORRECT


def select(pool: list, n: int = 5, target_difficulty: int = 3,
           kinds: tuple = KINDS, at: datetime | None = None,
           allow_cooling: bool = False) -> list:
    """Choose the next questions to ask.

    Priority, in order: something previously missed and now due, then unseen
    material, then ordinary review. Anything still cooling is skipped unless
    explicitly allowed, and the result is spread across kinds.
    """
    at = at or now()
    scored = []
    for q in pool:
        if q.retired:
            continue
        if q.is_cooling(at) and not allow_cooling:
            continue
        if q.asked == 0:
            base = 1.0                                  # new ground
        elif q.last_verdict in ("incorrect", "partial"):
            base = 1.8 + min(1.0, q.days_overdue(at) / 14)   # the thing he missed
        else:
            base = 0.7 + min(0.6, q.days_overdue(at) / 30)
        base -= 0.12 * abs(q.difficulty - target_difficulty)
        scored.append((base, q))

    scored.sort(key=lambda t: (-t[0], t[1].id))

    # Spread across kinds without letting balance beat priority: take the
    # highest-scoring question each time, penalising a kind already used. The
    # thing he got wrong still leads; five definitions in a row still cannot.
    out: list = []
    used: set = set()
    per_kind: dict = {}
    while len(out) < n:
        best, best_score = None, None
        for base, q in scored:
            if q.id in used:
                continue
            adjusted = base - 0.55 * per_kind.get(q.kind, 0)
            if best_score is None or adjusted > best_score:
                best, best_score = q, adjusted
        if best is None:
            break
        out.append(best)
        used.add(best.id)
        per_kind[best.kind] = per_kind.get(best.kind, 0) + 1
    return out[:n]


def render_section(questions: list) -> str:
    """The Questions block on a concept page, for reading in Obsidian."""
    live = [q for q in questions if not q.retired]
    dead = [q for q in questions if q.retired]
    if not live and not dead:
        return "_none banked yet_"
    lines = ["| id | kind | d | question | asked | ✓ | next |",
             "|---|---|---|---|---|---|---|"]
    for q in sorted(live, key=lambda x: (x.kind, -x.difficulty)):
        nxt = q.due_at()
        when = "now" if not q.is_cooling() else nxt.date().isoformat()
        text = q.text.replace("|", "/")
        text = text if len(text) <= 90 else text[:89] + "…"
        lines.append(f"| `{q.id}` | {q.kind} | {q.difficulty} | {text} "
                     f"| {q.asked} | {q.correct} | {when} |")
    if dead:
        lines.append("")
        lines.append(f"_{len(dead)} retired (consistently correct)._")
    return "\n".join(lines)
