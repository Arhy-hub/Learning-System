"""The engine: one object over the brain, the graph and the session store.

Designed so an agent never does bookkeeping. Concepts come into existence the
moment they are mentioned, the session id is implicit, and the graph is
re-derived whenever the brain changes. The agent supplies judgement — verdicts
and prose. The engine supplies everything computable.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import questions as qbank
from . import review as rv
from .brain import Brain, slug
from .config import Config, get_config
from .graph import ConceptGraph
from .knowledge import KnowledgeModel
from .mastery import apply_result, summarise
from .similarity import SimilarityIndex
from .store import Store
from .text import canon

CALIBRATION_WEIGHT = 0.6   # a probe is weaker evidence than a worked exit answer
EXAM_WEIGHT = 1.0


class Engine:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or get_config()
        self.cfg.ensure_dirs()
        self.store = Store(self.cfg.db_path)
        self.brain = Brain(self.cfg.brain_dir)
        self.load()

    def load(self) -> None:
        self.graph = ConceptGraph(self.brain)
        self.similarity = SimilarityIndex(self.graph, self.brain)
        self.knowledge = KnowledgeModel(self, self.similarity)

    _refresh = load

    # -- concepts ------------------------------------------------------------
    def ensure_concept(self, name: str, track: str = "",
                       prereqs: list | None = None, refresh: bool = True) -> str:
        """Create the concept page if the mentor has not met it. Returns its id."""
        cid = canon(name)
        if not cid:
            raise ValueError("concept name is empty")
        page = self.brain.find(name)
        if page is not None:
            if prereqs:
                merged = list(dict.fromkeys(list(page.prereqs) + list(prereqs)))
                if merged != page.prereqs:
                    self.brain.write(page.path, page.title, {"prereqs": merged}, {})
                    if refresh:
                        self._refresh()
            return page.id

        fm = {
            "concept": cid, "track": track or "Unfiled",
            "prereqs": list(prereqs or []),
            "estimate": 0.0, "tested": 0.0, "confidence": 0.0,
            "attempts": 0, "correct": 0, "label": "unknown",
            "created": date.today().isoformat(),
            "updated": date.today().isoformat(),
            "tags": ["concept"],
        }
        sections = {
            "Material": self._render_material([]),
            "Understanding": "_Not yet assessed._",
            "History": "| date | phase | verdict | question |\n|---|---|---|---|",
        }
        self.brain.write(self.brain.concept_path(name, track), name, fm, sections)
        # A named prerequisite is a concept too. Create it now so the graph is
        # complete immediately rather than only after it is first tested.
        for p in (prereqs or []):
            if canon(p) != cid and self.brain.find(p) is None:
                self.ensure_concept(p, track, refresh=False)
        if refresh:
            self._refresh()
        return cid

    def resolve(self, name: str, create: bool = False, track: str = ""):
        n = self.graph.get(name)
        if n:
            return n.id
        page = self.brain.find(name)
        if page:
            return page.id
        return self.ensure_concept(name, track) if create else None

    def mastery_map(self) -> dict:
        return self.store.effective_map()

    def describe(self, cid: str, deep: bool = True) -> dict:
        n = self.graph.nodes.get(cid)
        if n is None:
            return {}
        m = self.store.get_mastery(cid, self.cfg.mastery)
        k = self.knowledge.of(cid)
        out = {
            "id": cid, "name": n.name, "track": n.track, "page": n.path,
            "tested": m.effective(), "strength": m.strength,
            "half_life_days": m.half_life, "attempts": m.n_total,
            "correct": m.n_correct,
            "last_tested": m.last_tested.isoformat() if m.last_tested else None,
            "due": m.is_due(self.cfg.mastery),
            "mastered": m.is_mastered(self.cfg.mastery),
            "knowledge": k.as_dict(),
        }
        if deep:
            nm = lambda i: self.graph.nodes[i].name if i in self.graph.nodes else i
            mm = self.mastery_map()
            out["prereqs"] = [{"id": p, "name": nm(p), "tested": mm.get(p, 0.0)}
                              for p in self.graph.prereqs(cid)]
            out["dependents"] = [{"id": d, "name": nm(d)}
                                 for d in self.graph.dependents(cid)][:12]
            out["similar"] = [{"id": s.b, "name": nm(s.b),
                               "score": round(s.score, 3), "why": s.why}
                              for s in self.similarity.nearest(cid, 6)]
            out["recall"] = self.brain.recall(n.name)
        return out

    # -- resources -------------------------------------------------------------
    def add_resource(self, name: str, kind: str = "book", author: str = "",
                     where: str = "", notes: str = "", covers=None) -> dict:
        """Declare something in the library the mentor may point at."""
        covers = list(covers or [])
        existing = self.brain.find_resource(name)
        # Keep the original date: "added" means when it entered the library,
        # and re-registering a book must not make it look new.
        added = existing.frontmatter.get("added") if existing else None
        fm = {
            "resource": name, "kind": kind, "author": author or None,
            "where": where or None, "covers": covers or None,
            "added": added or date.today().isoformat(),
            "tags": ["resource", slug(kind).lower() or "resource"],
        }
        sections = {"Notes": notes} if notes else {}
        path = self.brain.write(self.brain.resource_path(name), name, fm, sections)
        return {"resource": name, "page": str(path.relative_to(self.brain.root))}

    def resources(self) -> list:
        out = []
        for pg in self.brain.resources():
            f = pg.frontmatter
            out.append({
                "name": pg.title, "kind": f.get("kind", "book"),
                "author": f.get("author"), "where": f.get("where"),
                "covers": f.get("covers") or [],
                "notes": pg.section("Notes"),
                "page": str(pg.path.relative_to(self.brain.root)),
            })
        return sorted(out, key=lambda d: d["name"])

    def material_for(self, concept: str) -> list:
        page = self.brain.find(concept)
        if page is None:
            return []
        v = page.frontmatter.get("material") or []
        return [str(x) for x in (v if isinstance(v, list) else [v])]

    def assign_material(self, concept: str, items: list, replace: bool = True) -> dict:
        """Point a concept at specific places in the library.

        Items are locators, e.g. "[[Rudin]] 2.31-2.37" or
        "[[Axler]] ch. 5, skip 5.C". The mentor curates; it does not author.
        """
        cid = self.resolve(concept, create=True)
        page = self.brain.find(cid)
        current = self.material_for(cid)
        items = [str(i).strip() for i in items if str(i).strip()]
        merged = items if replace else list(dict.fromkeys(current + items))
        self.brain.write(page.path, page.title, {"material": merged},
                         {"Material": self._render_material(merged)})
        self._refresh()
        return {"concept": cid, "material": merged}

    @staticmethod
    def _render_material(items: list) -> str:
        if not items:
            return ("_Nothing assigned. The mentor curates from `Resources/`; "
                    "add to the library and it will point you at it._")
        return "\n".join(f"- {i}" for i in items)

    # -- question bank -------------------------------------------------------
    def _bank(self, cid: str, text: str, kind=None, difficulty=None):
        """Find or create the banked question for this text."""
        existing = self.store.questions_for(cid)
        dup = qbank.is_duplicate(text, existing)
        if dup is not None:
            return dup
        q = qbank.Question(
            id=qbank.qid(text), concept=cid, text=text,
            kind=(kind if kind in qbank.KINDS else "application"),
            difficulty=int(difficulty) if difficulty else 3)
        self.store.save_question(q)
        return q

    def _score_question(self, q, verdict: str) -> None:
        q.asked += 1
        if verdict == "correct":
            q.correct += 1
            q.streak += 1
        else:
            q.streak = 0
        q.last_verdict = verdict
        q.last_asked = qbank.now()
        if qbank.should_retire(q):
            q.retired = True
        self.store.save_question(q)

    def bank_question(self, concept: str, text: str, kind: str = "application",
                      difficulty: int = 3) -> dict:
        """Author a question without asking it, so a good one is never lost."""
        cid = self.resolve(concept, create=True)
        existing = self.store.questions_for(cid)
        dup = qbank.is_duplicate(text, existing)
        if dup is not None:
            return {"question": dup.as_dict(), "duplicate_of": dup.id,
                    "note": "a near-identical question was already banked"}
        q = qbank.Question(id=qbank.qid(text), concept=cid, text=text,
                           kind=kind if kind in qbank.KINDS else "application",
                           difficulty=int(difficulty), source="authored")
        self.store.save_question(q)
        return {"question": q.as_dict()}

    def questions_for(self, concept: str, n: int = 5, difficulty: int = 3,
                      include_prereqs: bool = False) -> dict:
        """Which questions to ask next, and why each was chosen."""
        cid = self.resolve(concept)
        if cid is None:
            return {"error": f"no concept called {concept!r} yet"}
        ids = [cid] + (self.graph.prereqs(cid) if include_prereqs else [])
        pool = [q for i in ids for q in self.store.questions_for(i)]
        picked = qbank.select(pool, n, difficulty)
        cooling = [q.as_dict() for q in pool
                   if q.is_cooling() and not q.retired]
        return {
            "concept": cid,
            "banked": len([q for q in pool if not q.retired]),
            "ask": [q.as_dict() for q in picked],
            "cooling": cooling,
            "retired": len([q for q in pool if q.retired]),
            "note": ("Ask these. Anything cooling was answered recently — "
                     "re-asking it measures recall of the answer, not the idea. "
                     "If you need more, write new ones; they are banked as you ask them."),
        }

    def question_history(self, concept: str) -> list:
        cid = self.resolve(concept)
        if cid is None:
            return []
        return [q.as_dict() for q in
                sorted(self.store.questions_for(cid),
                       key=lambda x: (x.retired, x.kind, -x.difficulty))]

    # -- sessions ---------------------------------------------------------------
    def _sid(self, session_id=None):
        if session_id:
            return session_id
        a = self.store.active_session()
        return a["id"] if a else None

    def session_start(self, topic: str, goal: str = "", track: str = "",
                      prereqs: list | None = None) -> dict:
        """Open a session. The concept is created if the mentor has not met it."""
        known = self.brain.find(topic) is not None
        cid = self.ensure_concept(topic, track, prereqs)
        node = self.graph.nodes[cid]

        mm = self.mastery_map()
        pres = self.graph.prereqs(cid)
        weak = [p for p in pres if mm.get(p, 0.0) < self.cfg.mastery.mastered_at]
        targets = list(dict.fromkeys([cid] + weak[:3]))

        sid = self.store.open_session(node.name, targets, goal or None)
        return {
            "session_id": sid, "topic": node.name, "topic_id": cid,
            "first_time": not known, "goal": goal or None,
            "targets": [self.describe(t, deep=False) for t in targets],
            "prerequisites": [self.describe(p, deep=False) for p in pres],
            "recall": self.brain.recall(node.name),
            "similar": [{"name": self.graph.nodes[s.b].name,
                         "score": round(s.score, 3), "why": s.why}
                        for s in self.similarity.nearest(cid, 5)],
            "material": self.material_for(cid),
            "library": self.resources(),
            "questions": self.questions_for(node.name, 6, include_prereqs=True),
            "due_elsewhere": self.due(3),
            "prior_sessions": [{"topic": s["topic"], "started": s["started_at"][:10],
                                "summary": s["summary"]}
                               for s in self.store.recent_sessions(4)],
        }

    def _record(self, sid: int, phase: str, items: list, weight: float) -> dict:
        applied, created = [], []
        for it in items:
            raw = str(it.get("concept", "")).strip()
            if not raw:
                continue
            cid = self.resolve(raw)
            if cid is None:
                cid = self.ensure_concept(raw, str(it.get("track", "")))
                created.append(raw)
            verdict = str(it.get("verdict", "incorrect")).lower()
            if verdict not in ("correct", "partial", "incorrect"):
                verdict = "incorrect"
            text = str(it.get("question", "")).strip()
            q = self._bank(cid, text, it.get("kind"), it.get("difficulty")) if text else None
            if q is not None:
                self._score_question(q, verdict)
            self.store.add_response(sid, phase, cid, text, it.get("response"),
                                    verdict, it.get("note"),
                                    question_id=q.id if q else None)
            before = self.store.get_mastery(cid, self.cfg.mastery)
            after = apply_result(before, verdict, self.cfg.mastery, weight=weight)
            self.store.save_mastery(after)
            applied.append({
                "concept": cid,
                "name": self.graph.nodes[cid].name if cid in self.graph.nodes else cid,
                "verdict": verdict,
                "tested_before": before.effective(),
                "tested_after": after.effective(),
                "half_life_days": after.half_life,
            })
        self.knowledge.invalidate()
        return {"applied": applied, "concepts_created": created}

    def calibration_submit(self, items: list, session_id=None) -> dict:
        sid = self._sid(session_id)
        if not sid:
            return {"error": "no open session; call session_start first"}
        out = self._record(sid, "calibration", items, CALIBRATION_WEIGHT)
        self.store.set_phase(sid, "exploring")
        weak = [a["concept"] for a in out["applied"] if a["verdict"] != "correct"]
        out.update({"session_id": sid, "phase": "exploring",
                    "weak": [self.describe(c, deep=False) for c in weak]})
        return out

    def exam_submit(self, items: list, session_id=None) -> dict:
        sid = self._sid(session_id)
        if not sid:
            return {"error": "no open session; call session_start first"}
        out = self._record(sid, "exam", items, EXAM_WEIGHT)
        self.store.set_phase(sid, "examining")
        out.update({"session_id": sid, "phase": "examining"})
        return out

    # -- one question at a time ------------------------------------------
    def ask_next(self, phase: str = "calibration", concept: str = "",
                 difficulty: int = 3) -> dict:
        """The next single question to put to him.

        Deliberately one at a time. Handing over five questions at once lets him
        read ahead and answer out of order, and it stops the difficulty adapting
        to the answer just given, which is most of the point of calibrating.
        """
        sid = self._sid()
        if not sid:
            return {"error": "no open session; call session_start first"}
        srec = self.store.session(sid)
        targets = json.loads(srec["targets"] or "[]")
        cid = self.resolve(concept) if concept else (targets[0] if targets else None)
        if cid is None:
            return {"error": "no target concept for this session"}

        asked = [r["question_id"] for r in self.store.responses(sid, phase)
                 if r["question_id"]]
        pool = [q for i in ([cid] + self.graph.prereqs(cid))
                for q in self.store.questions_for(i)
                if q.id not in asked]
        picked = qbank.select(pool, 1, difficulty)
        n_asked = len(self.store.responses(sid, phase))
        base = {"session_id": sid, "phase": phase, "concept": cid,
                "asked_so_far": n_asked}
        if picked:
            q = picked[0]
            return {**base, "question": q.as_dict(), "from_bank": True,
                    "instruction": "Ask exactly this, then call answer()."}
        return {**base, "question": None, "from_bank": False,
                "instruction": ("The bank has nothing due for this concept. Write "
                                "one question, ask it, and pass its text to "
                                "answer() — it is banked automatically."),
                "cooling": [q.as_dict() for q in pool if q.is_cooling()]}

    def answer(self, verdict: str, question: str = "", response: str = "",
               note: str = "", concept: str = "", kind: str = "",
               difficulty: int = 3, phase: str = "calibration") -> dict:
        """Record one answer and hand back the next question."""
        sid = self._sid()
        if not sid:
            return {"error": "no open session"}
        srec = self.store.session(sid)
        targets = json.loads(srec["targets"] or "[]")
        cid = self.resolve(concept, create=bool(concept)) if concept else (
            targets[0] if targets else None)
        if cid is None:
            return {"error": "no concept for this answer"}
        weight = CALIBRATION_WEIGHT if phase == "calibration" else EXAM_WEIGHT
        out = self._record(sid, phase, [{
            "concept": self.graph.nodes[cid].name if cid in self.graph.nodes else cid,
            "question": question, "response": response, "verdict": verdict,
            "note": note, "kind": kind, "difficulty": difficulty}], weight)
        self.store.set_phase(sid, "exploring" if phase == "calibration" else "examining")
        applied = out["applied"][0] if out["applied"] else {}
        nxt = self.ask_next(phase, concept or "", difficulty)
        return {"recorded": applied, "next": nxt}

    # -- code review --------------------------------------------------------
    def submit_review(self, concept: str, ratings: dict, issues=None,
                      summary: str = "", language: str = "", lines: int = 0) -> dict:
        """Record a code review as evidence. It rates; it does not repair."""
        cid = self.resolve(concept, create=True)
        clean = rv.clean_ratings(ratings)
        if not clean:
            return {"error": "no valid ratings",
                    "dimensions": list(rv.DIMENSIONS)}
        review = rv.Review(id=None, concept=cid, language=language,
                           ratings=clean, issues=rv.clean_issues(issues),
                           summary=summary, lines=int(lines or 0))
        sid = self._sid()
        review.id = self.store.add_review(review, sid)

        before = self.store.get_mastery(cid, self.cfg.mastery)
        after = apply_result(before, review.verdict, self.cfg.mastery,
                             weight=EXAM_WEIGHT)
        self.store.save_mastery(after)
        self.knowledge.invalidate()
        if sid:
            self.store.add_response(
                sid, "review", cid,
                f"code review ({language or 'code'}, {review.lines} lines)",
                summary, review.verdict, f"overall {review.overall}/5")
        self._write_concept(cid, [], {})
        self._write_index()
        self._refresh()
        return {**review.as_dict(),
                "tested_before": before.effective(),
                "tested_after": after.effective(),
                "scale": rv.SCALE}

    def reviews_for(self, concept: str) -> list:
        cid = self.resolve(concept)
        return [r.as_dict() for r in self.store.reviews_for(cid)] if cid else []

    def session_end(self, summary: str, concepts: dict | None = None,
                    session_id=None) -> dict:
        """Close the session and revise the mentor's memory.

        `concepts` carries the agent's judgements, keyed by concept name:
          {"Compactness": {"understanding": ..., "slips": ..., "worked": ...,
                           "open": ..., "prereqs": [...], "track": ...}}
        """
        sid = self._sid(session_id)
        if not sid:
            return {"error": "no open session"}
        srec = self.store.session(sid)
        self.store.close_session(sid, summary)
        res = self.store.responses(sid)
        self.knowledge.invalidate()

        judgements = {}
        for name, body in (concepts or {}).items():
            judgements[self.resolve(name, create=True)] = body or {}
        for body in judgements.values():
            for p in (body.get("prereqs") or []):
                self.ensure_concept(p, refresh=False)
        self._refresh()

        touched = list(dict.fromkeys([r["concept"] for r in res] + list(judgements)))
        pages = [str(self._write_concept(c, res, judgements.get(c, {}))
                     .relative_to(self.brain.root)) for c in touched]
        spath = self._write_session(sid, srec, res, summary)
        self._write_index()
        self._refresh()

        return {"session_id": sid, "topic": srec["topic"], "responses": len(res),
                "correct": sum(1 for r in res if r["verdict"] == "correct"),
                "brain": {"root": str(self.brain.root),
                          "session": str(spath.relative_to(self.brain.root)),
                          "concepts": pages}}

    # -- brain writing -----------------------------------------------------------
    def _write_concept(self, cid: str, res: list, judgement: dict) -> Path:
        node = self.graph.nodes.get(cid)
        name = node.name if node else cid
        track = judgement.get("track") or (node.track if node else "Unfiled")
        page = self.brain.find(name)
        path = page.path if page else self.brain.concept_path(name, track)

        d = self.describe(cid, deep=False)
        k = self.knowledge.of(cid)
        prereq_names = list(judgement.get("prereqs") or
                            [self.graph.nodes[p].name for p in self.graph.prereqs(cid)])
        similar = "\n".join(
            f"- [[{self.graph.nodes[s.b].name}]] — {s.score:.2f} ({s.why})"
            for s in self.similarity.nearest(cid, 5)) or "_none yet_"

        rows = [r for r in res if r["concept"] == cid]
        prior = page.section("History") if page else ""
        header = "| date | phase | verdict | question |\n|---|---|---|---|"
        body = "\n".join(
            "| {} | {} | {} | {} |".format(
                r["asked_at"][:10], r["phase"], r["verdict"],
                r["question"][:70].replace("|", "/")) for r in rows)
        history = ((prior.rstrip() if prior and "|" in prior else header)
                   + (("\n" + body) if body else ""))

        def keep(section: str, key: str) -> str:
            got = (judgement.get(key) or "").strip()
            return got or (page.section(section) if page else "")

        material = list(judgement.get("material") or self.material_for(cid))
        sections = {
            "Material": self._render_material(material),
            "Understanding": keep("Understanding", "understanding"),
            "Where he slips": keep("Where he slips", "slips"),
            "What worked": keep("What worked", "worked"),
            "Open questions": keep("Open questions", "open"),
            "Prerequisites": ", ".join(f"[[{p}]]" for p in prereq_names) or "_none_",
            "Similar": similar,
            "Questions": qbank.render_section(self.store.questions_for(cid)),
            "Reviews": rv.render_section(self.store.reviews_for(cid)),
            "History": history,
        }
        fm = {
            "concept": cid, "track": track, "prereqs": prereq_names,
            "material": material or None,
            "estimate": round(k.estimate, 3), "tested": round(d["tested"], 3),
            "confidence": round(k.confidence, 3),
            "attempts": d["attempts"], "correct": d["correct"],
            "half_life_days": round(d["half_life_days"], 2),
            "last_tested": (d["last_tested"] or "")[:10],
            "label": k.label, "updated": date.today().isoformat(),
            "tags": ["concept", slug(track).lower().replace(" ", "-") or "unfiled"],
        }
        return self.brain.write(path, name, fm, sections)

    def _write_session(self, sid: int, srec: dict, res: list, summary: str) -> Path:
        touched = [c for c in dict.fromkeys(r["concept"] for r in res)
                   if c in self.graph.nodes]
        L = [f"# {srec['topic']} — session {sid}", "",
             f"- Started: {srec['started_at'][:19]}",
             f"- Goal: {srec['goal'] or '—'}",
             "- Concepts: " + (", ".join(f"[[{self.graph.nodes[c].name}]]"
                                         for c in touched) or "—"), ""]
        for phase in ("calibration", "exam"):
            rows = [r for r in res if r["phase"] == phase]
            if not rows:
                continue
            L += [f"## {phase.title()}", ""]
            for r in rows:
                nm = (self.graph.nodes[r["concept"]].name
                      if r["concept"] in self.graph.nodes else r["concept"])
                mark = {"correct": "x", "partial": "~", "incorrect": " "}.get(
                    r["verdict"], " ")
                L.append(f"- [{mark}] **[[{nm}]]** — {r['question']}")
                if r["response"]:
                    L.append(f"\t- answered: {r['response']}")
                if r["note"]:
                    L.append(f"\t- {r['note']}")
            L.append("")
        L += ["## Summary", "", summary, "", "## After", ""]
        for cid in dict.fromkeys(r["concept"] for r in res):
            d = self.describe(cid, deep=False)
            k = self.knowledge.of(cid)
            L.append(f"- [[{d['name']}]] — tested {d['tested']:.2f} "
                     f"({k.label}), half-life {d['half_life_days']:.1f}d")
        return self.brain.write_session(
            self.brain.session_path(sid, srec["topic"]), "\n".join(L))

    def _write_index(self) -> Path:
        pages = self.brain.concepts()
        by_track: dict = {}
        for pg in pages:
            by_track.setdefault(pg.track, []).append(pg)
        sessions = sorted(self.brain.pages("Sessions"), reverse=True)
        L = ["# Index", "",
             f"_{len(pages)} concepts across {len(by_track)} tracks, "
             f"{len(sessions)} sessions. Updated {date.today().isoformat()}._", ""]
        for track in sorted(by_track):
            L += [f"## {track}", "",
                  "| concept | tested | estimate | attempts | state |",
                  "|---|---|---|---|---|"]
            for pg in sorted(by_track[track], key=lambda p: p.title):
                f = pg.frontmatter
                L.append(f"| [[{pg.path.stem}]] | {f.get('tested', 0)} | "
                         f"{f.get('estimate', 0)} | {f.get('attempts', 0)} | "
                         f"{f.get('label', '—')} |")
            L.append("")
        if sessions:
            L += ["## Recent sessions", ""] + [f"- [[{p.stem}]]" for p in sessions[:15]]
        path = self.brain.root / "Index.md"
        path.write_text("\n".join(L) + "\n", encoding="utf-8")
        return path

    # -- planning ------------------------------------------------------------------
    def frontier(self, goal: str = "", k: int = 8) -> list:
        ids = self.graph.frontier(self.mastery_map(), goal or None, k,
                                  self.cfg.mastery.mastered_at)
        return [self.describe(i, deep=False) for i in ids]

    def path_to(self, goal: str) -> dict:
        n = self.graph.get(goal)
        if n is None:
            return {"error": f"no concept called {goal!r} yet",
                    "known": [x.name for x in list(self.graph.nodes.values())[:20]]}
        ids = self.graph.path_to(n.id, self.mastery_map(), self.cfg.mastery.mastered_at)
        return {"goal": n.name, "steps": len(ids),
                "path": [self.describe(i, deep=False) for i in ids]}

    def due(self, limit: int = 10) -> list:
        p = self.cfg.mastery
        rows = [self.describe(c, deep=False)
                for c, m in self.store.all_mastery().items()
                if m.is_due(p) and c in self.graph.nodes]
        rows.sort(key=lambda d: d["tested"])
        return rows[:limit]

    def report(self, track: str = "") -> dict:
        states = self.store.all_mastery()
        rows = []
        for cid, m in states.items():
            n = self.graph.nodes.get(cid)
            if not n or (track and canon(track) != canon(n.track)):
                continue
            rows.append({"id": cid, "name": n.name, "track": n.track,
                         "tested": m.effective(), "attempts": m.n_total})
        rows.sort(key=lambda r: -r["tested"])
        return {"mastery": summarise(states, self.cfg.mastery),
                "knowledge": self.knowledge.summary(),
                "brain": self.brain.stats(), "store": self.store.stats(),
                "concepts": rows[:40]}

    def status(self) -> dict:
        return {"brain": self.brain.stats(), "graph": self.graph.stats(),
                "similarity": self.similarity.stats(), "store": self.store.stats(),
                "unresolved_prereqs": self.graph.unresolved[:10],
                "cycles": [[self.graph.nodes[c].name for c in cyc]
                           for cyc in self.graph.cycles[:3]]}
