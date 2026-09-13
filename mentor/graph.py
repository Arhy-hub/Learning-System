"""The concept graph, derived from the brain's own pages.

There is no separate graph store. A concept is a page; a prerequisite is an
entry in that page's frontmatter; relatedness is a wikilink in its body. Editing
the markdown edits the graph, so the whole system state is legible in Obsidian
and there is nothing to keep in sync.

Edges:
  prereq   declared in frontmatter -- asserted dependencies, the real thing
  related  wikilinks between pages -- undirected, never a prerequisite
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from .text import canon


@dataclass
class Node:
    id: str
    name: str
    track: str
    prereqs: list = field(default_factory=list)
    related: list = field(default_factory=list)
    attempts: int = 0
    estimate: float = 0.0
    tested: float = 0.0
    label: str = "no evidence"
    path: str = ""


class ConceptGraph:
    """Nodes and edges read out of the brain."""

    def __init__(self, brain):
        self.brain = brain
        self.nodes: dict = {}
        self.tracks: dict = {}
        self._out: dict = defaultdict(list)   # prereq -> dependents
        self._in: dict = defaultdict(list)    # concept -> prereqs
        self.cycles: list = []
        self.unresolved: list = []            # prereqs named but not yet written
        self.build()

    # -- construction ------------------------------------------------------
    def build(self) -> None:
        self.nodes, self.tracks = {}, {}
        self._out, self._in = defaultdict(list), defaultdict(list)
        self.unresolved = []

        by_id = {}
        for pg in self.brain.concepts():
            n = Node(
                id=pg.id, name=pg.title, track=pg.track,
                attempts=int(pg.frontmatter.get("attempts") or 0),
                estimate=float(pg.frontmatter.get("estimate") or 0.0),
                tested=float(pg.frontmatter.get("tested") or 0.0),
                label=str(pg.frontmatter.get("label") or "no evidence"),
                path=str(pg.path.relative_to(self.brain.root)),
            )
            self.nodes[n.id] = n
            by_id[n.id] = pg
            self.tracks.setdefault(n.track, []).append(n.id)

        for cid, pg in by_id.items():
            for raw in pg.prereqs:
                pid = canon(raw)
                if pid in self.nodes and pid != cid:
                    self.nodes[cid].prereqs.append(pid)
                    self._in[cid].append(pid)
                    self._out[pid].append(cid)
                elif pid:
                    self.unresolved.append({"concept": pg.title, "prereq": raw})
            for raw in pg.links:
                rid = canon(raw)
                if rid in self.nodes and rid != cid:
                    self.nodes[cid].related.append(rid)
                    self.nodes[rid].related.append(cid)

        for n in self.nodes.values():
            n.prereqs = list(dict.fromkeys(n.prereqs))
            n.related = list(dict.fromkeys(x for x in n.related if x not in n.prereqs))
        for k in list(self._in):
            self._in[k] = list(dict.fromkeys(self._in[k]))
        for k in list(self._out):
            self._out[k] = list(dict.fromkeys(self._out[k]))

        self.cycles = self._find_cycles()

    def _find_cycles(self) -> list:
        colour: dict = {}
        stack: list = []
        found: list = []

        def visit(u: str) -> None:
            colour[u] = 1
            stack.append(u)
            for v in self._out.get(u, []):
                if colour.get(v, 0) == 0:
                    visit(v)
                elif colour.get(v) == 1 and v in stack:
                    found.append(stack[stack.index(v):] + [v])
            stack.pop()
            colour[u] = 2

        import sys
        lim = sys.getrecursionlimit()
        sys.setrecursionlimit(max(lim, len(self.nodes) * 4 + 1000))
        try:
            for n in list(self.nodes):
                if colour.get(n, 0) == 0:
                    visit(n)
        finally:
            sys.setrecursionlimit(lim)
        return found

    # -- queries ----------------------------------------------------------
    def get(self, name: str):
        return self.nodes.get(canon(name))

    def prereqs(self, cid: str) -> list:
        return list(self._in.get(cid, []))

    def dependents(self, cid: str) -> list:
        return list(self._out.get(cid, []))

    def ancestors(self, cid: str) -> list:
        out, seen, q = [], {cid}, deque([cid])
        while q:
            for p in self.prereqs(q.popleft()):
                if p not in seen:
                    seen.add(p)
                    out.append(p)
                    q.append(p)
        return out

    def distance(self, src: str, dst: str, cap: int = 8):
        if src == dst:
            return 0
        seen, q = {src}, deque([(src, 0)])
        while q:
            u, d = q.popleft()
            if d >= cap:
                continue
            for v in self._out.get(u, []) + self._in.get(u, []):
                if v == dst:
                    return d + 1
                if v not in seen:
                    seen.add(v)
                    q.append((v, d + 1))
        return None

    def toposort(self, ids: list) -> list:
        s = set(ids)
        indeg = {i: 0 for i in s}
        adj: dict = defaultdict(list)
        for i in s:
            for d in self._out.get(i, []):
                if d in s:
                    adj[i].append(d)
                    indeg[d] += 1
        q = deque(sorted(i for i in s if indeg[i] == 0))
        out = []
        while q:
            u = q.popleft()
            out.append(u)
            for v in sorted(adj[u]):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
        out.extend(sorted(s - set(out)))
        return out

    def frontier(self, mastery: dict, goal: str | None = None, k: int = 8,
                 threshold: float = 0.8) -> list:
        """Unmastered concepts whose prerequisites are all met."""
        scope = None
        gid = canon(goal) if goal else None
        if gid and gid in self.nodes:
            scope = set(self.ancestors(gid)) | {gid}

        out = []
        for cid, n in self.nodes.items():
            if scope is not None and cid not in scope:
                continue
            if mastery.get(cid, 0.0) >= threshold:
                continue
            pres = self.prereqs(cid)
            if pres and not all(mastery.get(p, 0.0) >= threshold for p in pres):
                continue
            score = 0.5 * min(len(self.dependents(cid)), 4) / 4
            score += 0.3 if n.attempts else 0.0
            if gid:
                d = self.distance(cid, gid)
                score += 2.0 / (1 + d) if d is not None else 0.0
            out.append((round(score, 3), cid))
        out.sort(key=lambda t: (-t[0], t[1]))
        return [c for _, c in out[:k]]

    def path_to(self, goal: str, mastery: dict, threshold: float = 0.8) -> list:
        gid = canon(goal)
        if gid not in self.nodes:
            return []
        need = [c for c in self.ancestors(gid) + [gid]
                if mastery.get(c, 0.0) < threshold]
        return self.toposort(need)

    def stats(self) -> dict:
        return {
            "concepts": len(self.nodes),
            "tracks": len(self.tracks),
            "prereq_edges": sum(len(v) for v in self._in.values()),
            "related_edges": sum(len(n.related) for n in self.nodes.values()) // 2,
            "cycles": len(self.cycles),
            "unresolved_prereqs": len(self.unresolved),
            "tested": sum(1 for n in self.nodes.values() if n.attempts),
        }
