"""How close two concepts are, from several independent angles.

Sources are the mentor's own pages: what it has written about each concept, the
prerequisite graph, the names, and the wikilinks between pages. Each component
is reported alongside the blended score so it is always clear *why* two things
scored close.

  content     TF-IDF cosine over the mentor's prose for each concept
  structural  same track, plus distance in the prerequisite graph
  lexical     content-word overlap of the names
  link        an explicit wikilink between the two pages
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .text import content_words, jaccard

WEIGHTS = {"content": 0.45, "structural": 0.25, "lexical": 0.15, "link": 0.15}

_WORD = re.compile(r"[a-z][a-z0-9-]{2,}")

# Below this many distinct weighted terms a cosine is noise, not signal.
MIN_TERMS = 12

_STOP = frozenset("""
the and for that with this from are was were will can may not but its
let us we our you your they them then than there here which what when where
who whom whose how why all any some each every both few more most other into
such only own same too very just also because while about above below over
under again further once during before after between out off down upon
def definition theorem proof example lemma corollary axiom remark note notes
say says said given gives take taken taking use used using call called
consider suppose assume assumed hence thus therefore since follows following
show shown shows form forms formed set sets element elements case cases
one two three first second third etc
his him she her they knows know knew understands understand understood
gets got slip slips worked work session concept
""".split()) | frozenset("""
text mathbb mathcal mathrm mathbf boldsymbol operatorname
frac dfrac sqrt cdot cdots ldots dots quad qquad
left right begin end array matrix pmatrix bmatrix cases aligned
times div leq geq neq approx equiv sim cong propto
infty partial nabla forall exists implies mapsto
subset subseteq supset supseteq cup cap setminus emptyset
alpha beta gamma delta epsilon zeta eta theta iota kappa lambda
mu nu rho sigma tau phi varphi chi psi omega
sum prod lim inf sup max min arg
""".split())


def _tokens(text: str) -> list:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


@dataclass(frozen=True)
class Similarity:
    a: str
    b: str
    score: float
    content: float
    structural: float
    lexical: float
    link: float

    @property
    def why(self) -> str:
        return max(("content", self.content), ("structural", self.structural),
                   ("lexical", self.lexical), ("link", self.link),
                   key=lambda t: t[1])[0]

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "score": round(self.score, 4),
                "why": self.why,
                "components": {"content": round(self.content, 4),
                               "structural": round(self.structural, 4),
                               "lexical": round(self.lexical, 4),
                               "link": round(self.link, 4)}}


class SimilarityIndex:
    def __init__(self, graph, brain, weights: dict | None = None):
        self.g = graph
        self.brain = brain
        self.w = dict(WEIGHTS, **(weights or {}))
        self._tfidf: dict = {}
        self._norm: dict = {}
        self._links: set = set()
        self.build()

    def build(self) -> None:
        docs: dict = {}
        for pg in self.brain.concepts():
            cid = pg.id
            if cid not in self.g.nodes:
                continue
            toks = _tokens(pg.preamble)
            for name in ("Understanding", "Where he slips", "What worked",
                         "Open questions"):
                toks += _tokens(pg.section(name))
            toks += _tokens(pg.title) * 3
            toks += _tokens(pg.track) * 2
            if toks:
                docs[cid] = Counter(toks)

        df: Counter = Counter()
        for c in docs.values():
            df.update(c.keys())
        n_docs = max(1, len(docs))
        for cid, tf in docs.items():
            total = sum(tf.values()) or 1
            vec = {}
            for term, k in tf.items():
                if df[term] < 2 and len(docs) > 8:
                    continue
                idf = math.log((1 + n_docs) / (1 + df[term])) + 1.0
                vec[term] = (k / total) * idf
            self._tfidf[cid] = vec
            self._norm[cid] = math.sqrt(sum(v * v for v in vec.values())) or 1.0

        for cid, n in self.g.nodes.items():
            for r in n.related:
                self._links.add((min(cid, r), max(cid, r)))

    # -- components ---------------------------------------------------------
    def content(self, a: str, b: str) -> float:
        va, vb = self._tfidf.get(a), self._tfidf.get(b)
        if not va or not vb:
            return 0.0
        ka, kb = a, b
        if len(vb) < len(va):
            va, vb, ka, kb = vb, va, b, a
        dot = sum(w * vb.get(t, 0.0) for t, w in va.items())
        cos = dot / (self._norm[ka] * self._norm[kb])
        # Thin pages produce spuriously high cosines; scale by evidence present.
        damp = min(1.0, len(va) / MIN_TERMS) * min(1.0, len(vb) / MIN_TERMS)
        return cos * damp

    def structural(self, a: str, b: str) -> float:
        na, nb = self.g.nodes.get(a), self.g.nodes.get(b)
        if not na or not nb:
            return 0.0
        s = 0.4 if na.track == nb.track and na.track != "Unfiled" else 0.0
        if b in na.prereqs or a in nb.prereqs:
            s = max(s, 0.8)
        d = self.g.distance(a, b, cap=4)
        if d is not None:
            s = max(s, 1.0 / (1 + d))
        return s

    def lexical(self, a: str, b: str) -> float:
        na, nb = self.g.nodes.get(a), self.g.nodes.get(b)
        if not na or not nb:
            return 0.0
        return jaccard(content_words(na.name), content_words(nb.name))

    def link(self, a: str, b: str) -> float:
        return 1.0 if (min(a, b), max(a, b)) in self._links else 0.0

    # -- api -----------------------------------------------------------------
    def between(self, a: str, b: str) -> Similarity:
        c, s = self.content(a, b), self.structural(a, b)
        lx, lk = self.lexical(a, b), self.link(a, b)
        score = (self.w["content"] * c + self.w["structural"] * s
                 + self.w["lexical"] * lx + self.w["link"] * lk)
        return Similarity(a, b, score, c, s, lx, lk)

    def nearest(self, cid: str, k: int = 8, min_score: float = 0.08) -> list:
        if cid not in self.g.nodes:
            return []
        out = [self.between(cid, o) for o in self.g.nodes if o != cid]
        out = [s for s in out if s.score >= min_score]
        out.sort(key=lambda s: -s.score)
        return out[:k]

    def stats(self) -> dict:
        return {"pages_with_text": len(self._tfidf),
                "vocabulary": len({t for v in self._tfidf.values() for t in v}),
                "link_pairs": len(self._links)}
