"""Code review as assessment, not as repair.

A review rates work along fixed dimensions and names what is wrong. It does not
supply the fix — the same rule that stops the mentor writing explanations stops
it writing your corrected code. Being told the recursion recomputes overlapping
subproblems is the lesson; being handed the memoised version is not.

A review is evidence, so it moves mastery exactly as a graded answer does, with
the overall rating mapped onto the same correct / partial / incorrect verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

# Fixed so scores are comparable across reviews and over time.
DIMENSIONS = {
    "correctness": "Does it do the right thing, including at the edges?",
    "complexity": "Time and space; work it does that it need not.",
    "clarity": "Naming, shape, whether the intent is legible.",
    "idiom": "Uses the language as the language is meant to be used.",
    "robustness": "Failure modes, invariants, what happens on bad input.",
}

SCALE = {
    1: "broken",
    2: "works by luck",
    3: "sound but unremarkable",
    4: "good",
    5: "would pass review anywhere",
}

# Where the overall score lands as evidence of understanding.
CORRECT_AT = 4.0
PARTIAL_AT = 2.75


@dataclass
class Review:
    id: int | None
    concept: str
    language: str
    ratings: dict                       # dimension -> 1..5
    issues: list = field(default_factory=list)   # {severity, where, what}
    summary: str = ""
    lines: int = 0
    reviewed_at: datetime | None = None

    @property
    def overall(self) -> float:
        vals = [v for k, v in self.ratings.items() if k in DIMENSIONS]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    @property
    def verdict(self) -> str:
        o = self.overall
        if o >= CORRECT_AT:
            return "correct"
        if o >= PARTIAL_AT:
            return "partial"
        return "incorrect"

    @property
    def weakest(self) -> str:
        if not self.ratings:
            return ""
        return min(self.ratings.items(), key=lambda kv: kv[1])[0]

    def as_dict(self) -> dict:
        return {
            "id": self.id, "concept": self.concept, "language": self.language,
            "ratings": self.ratings, "overall": self.overall,
            "verdict": self.verdict, "weakest": self.weakest,
            "issues": self.issues, "summary": self.summary, "lines": self.lines,
            "reviewed_at": self.reviewed_at.isoformat()[:10] if self.reviewed_at else None,
        }


def clean_ratings(raw: dict) -> dict:
    """Keep known dimensions, clamp to the scale, drop anything else."""
    out = {}
    for k, v in (raw or {}).items():
        key = str(k).strip().lower()
        if key not in DIMENSIONS:
            continue
        try:
            out[key] = max(1, min(5, int(round(float(v)))))
        except (TypeError, ValueError):
            continue
    return out


def clean_issues(raw) -> list:
    """Issues are observations. A `fix` field is dropped on the way in."""
    out = []
    for it in (raw or []):
        if isinstance(it, str):
            out.append({"severity": "note", "where": "", "what": it})
            continue
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity", "note")).lower()
        if sev not in ("blocker", "major", "minor", "note"):
            sev = "note"
        what = str(it.get("what") or it.get("issue") or "").strip()
        if not what:
            continue
        out.append({"severity": sev, "where": str(it.get("where", "")).strip(),
                    "what": what})
    order = {"blocker": 0, "major": 1, "minor": 2, "note": 3}
    out.sort(key=lambda d: order[d["severity"]])
    return out


def render_section(reviews: list) -> str:
    """The Reviews block on a concept page."""
    if not reviews:
        return "_no code reviewed yet_"
    lines = []
    for r in sorted(reviews, key=lambda x: (x.reviewed_at or datetime.min.replace(
            tzinfo=timezone.utc)), reverse=True)[:6]:
        when = r.reviewed_at.date().isoformat() if r.reviewed_at else "—"
        scores = " · ".join(f"{k[:4]} {v}" for k, v in r.ratings.items())
        lines.append(f"**{when}** — {r.language or 'code'}, {r.lines} lines — "
                     f"**{r.overall}/5** ({r.verdict})  \n`{scores}`")
        if r.summary:
            lines.append(f"> {r.summary}")
        for i in r.issues[:5]:
            where = f" *{i['where']}*" if i["where"] else ""
            lines.append(f"- **{i['severity']}**{where} — {i['what']}")
        lines.append("")
    return "\n".join(lines).strip()
