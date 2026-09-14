---
description: Health of the mentor's brain - graph shape, unresolved prereqs, cycles
agent: mentor
---

Report on the state of the brain itself, not on him.

1. `status()` — brain size, graph shape, unresolved prerequisites, cycles.
2. `report()` — mastery picture across tracks.

Flag, in order of importance:
- **Cycles** in the prerequisite graph. A cycle means something is listed as its
  own ancestor and the topological route through it is meaningless. Name the
  concepts involved.
- **Unresolved prerequisites** — concepts named as a prereq but never written.
  These are usually the honest next targets, but a cluster of them can also mean
  a page was renamed and the references were left dangling, since prereqs are
  matched by canonical name.
- **Concepts with `attempts: 0`** — present in the graph but never actually
  tested. The mentor cannot vouch for these.
- Anything **due**.

If he has been editing pages in Obsidian, call `reindex()` first so you are
reading from disk rather than from a stale in-memory graph.
