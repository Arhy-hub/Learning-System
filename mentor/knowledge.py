"""How well the user knows a concept.

Only one thing here is a measurement: a graded answer. Everything else is
inference, and is kept visibly separate rather than blended away — an untested
concept can never read as "known", however much sits around it.

  tested    graded answers, decayed. The measurement.
  transfer  tested mastery of similar concepts, similarity-weighted.
  support   whether the prerequisites are themselves mastered.
  open      unresolved questions recorded on the page. The negative signal.

Priors alone are capped at PRIOR_CEILING, and every estimate carries a
confidence plus the per-signal breakdown that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Inference alone never reads as mastery.
PRIOR_CEILING = 0.45

WEIGHTS = {"transfer": 0.6, "support": 0.4}
OPEN_PENALTY = 0.12


@dataclass
class Knowledge:
    concept: str
    estimate: float
    confidence: float
    tested: float
    attempts: int
    signals: dict = field(default_factory=dict)
    verified: bool = False

    @property
    def label(self) -> str:
        if not self.verified:
            return "inferred" if self.estimate > 0.12 else "unknown"
        if self.tested >= 0.8:
            return "solid"
        if self.tested >= 0.6:
            return "holding"
        if self.tested >= 0.3:
            return "shaky"
        return "needs work"

    def as_dict(self) -> dict:
        return {"concept": self.concept, "estimate": round(self.estimate, 3),
                "confidence": round(self.confidence, 3),
                "tested": round(self.tested, 3), "verified": self.verified,
                "attempts": self.attempts, "label": self.label,
                "signals": {k: round(v, 3) for k, v in self.signals.items()}}


class KnowledgeModel:
    def __init__(self, engine, similarity=None):
        self.e = engine
        self.g = engine.graph
        self.sim = similarity
        self._cache: dict = {}

    def invalidate(self) -> None:
        self._cache.clear()

    # -- signals -----------------------------------------------------------
    def _transfer(self, cid: str, mastery: dict) -> float:
        """Tested mastery of similar concepts. Never full credit."""
        if self.sim is None:
            return 0.0
        num = den = 0.0
        for s in self.sim.nearest(cid, 8, 0.15):
            m = mastery.get(s.b, 0.0)
            if m > 0:
                num += s.score * m
                den += s.score
        return (num / den) * 0.7 if den else 0.0

    def _support(self, cid: str, mastery: dict) -> float:
        """Mastered prerequisites make the concept more plausible, not known."""
        pres = self.g.prereqs(cid)
        if not pres:
            return 0.0
        return sum(min(1.0, mastery.get(p, 0.0)) for p in pres) / len(pres)

    def _open_penalty(self, cid: str) -> float:
        page = self.e.brain.find(cid)
        if not page:
            return 0.0
        text = page.section("Open questions").strip()
        if not text:
            return 0.0
        n = sum(1 for line in text.splitlines() if line.strip().startswith(("-", "*")))
        return min(0.25, OPEN_PENALTY * max(1, n))

    # -- combination ----------------------------------------------------------
    def of(self, cid: str, mastery: dict | None = None) -> Knowledge:
        if cid in self._cache:
            return self._cache[cid]
        mastery = mastery if mastery is not None else self.e.mastery_map()
        m = self.e.store.get_mastery(cid, self.e.cfg.mastery)
        tested = m.effective()

        sig = {"transfer": self._transfer(cid, mastery),
               "support": self._support(cid, mastery)}
        prior = min(PRIOR_CEILING, sum(WEIGHTS[k] * v for k, v in sig.items()))
        pen = self._open_penalty(cid)
        if pen:
            sig["open"] = -pen

        if m.n_total:
            trust = 1.0 - 0.5 ** m.n_total       # 0.5, 0.75, 0.875 ...
            estimate = trust * tested + (1 - trust) * prior
        else:
            estimate = prior
        estimate = max(0.0, estimate - pen)

        evidence = sum(1 for v in sig.values() if v > 0.05)
        confidence = min(1.0, 0.15 * evidence
                         + (0.45 if m.n_total else 0.0)
                         + min(0.3, 0.1 * m.n_total))

        k = Knowledge(concept=cid, estimate=estimate, confidence=confidence,
                      tested=tested, attempts=m.n_total, signals=sig,
                      verified=bool(m.n_total))
        self._cache[cid] = k
        return k

    def all(self, mastery: dict | None = None) -> dict:
        mastery = mastery if mastery is not None else self.e.mastery_map()
        for cid in self.g.nodes:
            self.of(cid, mastery)
        return dict(self._cache)

    def estimate_map(self, mastery: dict | None = None) -> dict:
        return {c: k.estimate for c, k in self.all(mastery).items()}

    def summary(self) -> dict:
        ks = self.all()
        buckets: dict = {}
        for k in ks.values():
            buckets[k.label] = buckets.get(k.label, 0) + 1
        return {
            "concepts": len(ks),
            "verified": sum(1 for k in ks.values() if k.verified),
            "by_label": dict(sorted(buckets.items(), key=lambda kv: -kv[1])),
            "mean_tested": round(
                sum(k.tested for k in ks.values() if k.verified)
                / max(1, sum(1 for k in ks.values() if k.verified)), 3),
        }
