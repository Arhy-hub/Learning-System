"""MCP stdio server: the mentor engine, exposed to opencode agents.

The mentor's memory is its own Obsidian vault. It does not read any personal
vault — it knows only what it has tested, and everything it learns about the
user it writes down here.
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from .engine import Engine
from .mathtext import to_unicode

mcp = MCPServer(
    "mentor",
    instructions=(
        "Learning mentor with its own Obsidian vault as persistent memory. "
        "Concepts are created automatically when first mentioned; the session id "
        "is implicit once a session is open. The mentor knows only what it has "
        "tested, never what it merely has notes about."
    ),
)
_engine: Engine | None = None


def E() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


def _j(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


# ------------------------------------------------------------------ session
@mcp.tool()
def session_start(topic: str, goal: str = "", track: str = "",
                  prereqs: list[str] | None = None) -> str:
    """Open a learning session on a topic.

    Creates the concept (and any prerequisites named) if the mentor has not met
    them. Returns what it already remembers about the topic, the prerequisite
    state, similar concepts, and anything else due for review. `first_time`
    tells you whether this is new ground.
    """
    return _j(E().session_start(topic, goal, track, prereqs or []))


@mcp.tool()
def calibration_submit(items: list[dict]) -> str:
    """Record graded calibration answers; returns the weak spots.

    Each item: {concept, question, response, verdict, note}, verdict one of
    "correct" | "partial" | "incorrect". Unknown concepts are created. Counts
    for less than the exit test.
    """
    return _j(E().calibration_submit(items))


@mcp.tool()
def exam_submit(items: list[dict]) -> str:
    """Record graded exit-test answers at full weight. Same item shape."""
    return _j(E().exam_submit(items))


@mcp.tool()
def session_end(summary: str, concepts: dict | None = None) -> str:
    """Close the session and write what was learned into the mentor's memory.

    `concepts` is keyed by concept name, and is where your judgement goes:
      {"Compactness": {"understanding": "...", "slips": "...",
                       "worked": "...", "open": "...",
                       "prereqs": ["Open sets"], "track": "Analysis"}}
    Each concept page is revised, not appended: write what is true now.
    """
    return _j(E().session_end(summary, concepts or {}))


# ---------------------------------------------------------- asking, one by one
@mcp.tool()
def ask_next(phase: str = "calibration", concept: str = "",
             difficulty: int = 3) -> str:
    """The next single question to put to him.

    One at a time, on purpose. Handing over five at once lets him read ahead and
    answer out of order, and stops the difficulty adapting to the answer just
    given — which is most of what calibration is for. If the bank has nothing
    due, write one question yourself; passing it to answer() banks it.
    """
    return _j(E().ask_next(phase, concept, difficulty))


@mcp.tool()
def answer(verdict: str, question: str = "", response: str = "", note: str = "",
           concept: str = "", kind: str = "", difficulty: int = 3,
           phase: str = "calibration") -> str:
    """Record one answer, and get the next question back.

    verdict: correct | partial | incorrect. kind: definition | application |
    edge | proof. Loop ask_next -> ask him -> answer -> ask him, until you have
    enough. `note` is where the specific misunderstanding goes.
    """
    return _j(E().answer(verdict, question, response, note, concept,
                         kind, difficulty, phase))


# ------------------------------------------------------------------- review
@mcp.tool()
def review_submit(concept: str, ratings: dict, issues: list | None = None,
                  summary: str = "", language: str = "", lines: int = 0) -> str:
    """Record a code review. It rates and names problems; it does not fix them.

    `ratings` scores 1-5 on: correctness, complexity, clarity, idiom,
    robustness. `issues` is a list of {severity, where, what} where severity is
    blocker | major | minor | note — **what is wrong, not how to fix it**. Do
    not include corrected code; a `fix` field is discarded on the way in.

    The overall score maps onto a verdict and moves mastery at full weight, so
    rate honestly: a generous review buys a nasty surprise later.
    """
    return _j(E().submit_review(concept, ratings, issues or [], summary,
                                language, lines))


@mcp.tool()
def reviews(concept: str) -> str:
    """Past code reviews for a concept, with scores and issues."""
    return _j(E().reviews_for(concept))


# ------------------------------------------------------------------- memory
@mcp.tool()
def recall(concept: str) -> str:
    """What the mentor already remembers about a concept. Empty if it is new.
    Call this before teaching anything."""
    return _j(E().brain.recall(concept))


@mcp.tool()
def remember(concept: str, understanding: str = "", slips: str = "",
             worked: str = "", open_questions: str = "",
             prereqs: list[str] | None = None, track: str = "") -> str:
    """Write to memory outside a session, e.g. after an unstructured explanation.

    Revises the concept page in place. Only the fields you pass are changed.
    """
    e = E()
    cid = e.resolve(concept, create=True, track=track)
    body = {"understanding": understanding, "slips": slips, "worked": worked,
            "open": open_questions, "prereqs": prereqs or [], "track": track}
    for p in (prereqs or []):
        e.ensure_concept(p, track, refresh=False)
    e._refresh()
    path = e._write_concept(cid, [], {k: v for k, v in body.items() if v})
    e._write_index()
    e._refresh()
    return _j({"concept": cid, "page": str(path.relative_to(e.brain.root))})


@mcp.tool()
def concept(name: str) -> str:
    """One concept in full: tested mastery, knowledge estimate with its signals,
    prerequisites, dependents, similar concepts, and everything remembered."""
    e = E()
    cid = e.resolve(name)
    if cid is None:
        return _j({"error": f"no concept called {name!r} yet",
                   "hint": "session_start or remember will create it",
                   "search": e.brain.search(name, 5)})
    return _j(e.describe(cid))


@mcp.tool()
def similar(concept: str, k: int = 8) -> str:
    """Concepts closest to this one, with the component that drove each match.
    Useful for testing transfer, and for spotting where knowledge should carry."""
    e = E()
    cid = e.resolve(concept)
    if cid is None:
        return _j({"error": f"no concept called {concept!r} yet"})
    return _j([dict(s.as_dict(), name=e.graph.nodes[s.b].name)
               for s in e.similarity.nearest(cid, k)])


# ----------------------------------------------------------------- library
@mcp.tool()
def resources() -> str:
    """The library: everything the mentor is allowed to point at.

    The mentor curates; it does not write learning content. If a concept needs
    material that is not here, say so and ask for it rather than explaining the
    topic yourself.
    """
    return _j(E().resources())


@mcp.tool()
def resource_add(name: str, kind: str = "book", author: str = "",
                 where: str = "", notes: str = "",
                 covers: list[str] | None = None) -> str:
    """Add something to the library.

    kind: book | course | paper | video | problem-set | notes.
    `where` is how to reach it — a shelf, a path, a URL. `covers` lists the
    concepts it is good for.
    """
    return _j(E().add_resource(name, kind, author, where, notes, covers or []))


@mcp.tool()
def assign_material(concept: str, items: list[str], replace: bool = True) -> str:
    """Point a concept at specific places in the library.

    Items are locators, not explanations: "[[Rudin]] 2.31-2.37",
    "[[Axler]] ch. 5, skip 5.C", "[[Tao 245B]] lecture 3". Be specific about
    section or chapter — "read Rudin" is not curation. Written to the concept
    page, so it is there next time.
    """
    return _j(E().assign_material(concept, items, replace))


@mcp.tool()
def material(concept: str) -> str:
    """What is currently assigned for a concept."""
    return _j({"concept": concept, "material": E().material_for(concept)})


# ----------------------------------------------------------------- questions
@mcp.tool()
def questions(concept: str, n: int = 5, difficulty: int = 3,
              include_prereqs: bool = True) -> str:
    """Which questions to ask next, from the bank, and why.

    Call this before writing any question. It returns questions that are due,
    prioritising ones previously missed, spread across definition / application
    / edge / proof and pitched at `difficulty` (1-5). Anything listed under
    `cooling` was answered recently — re-asking it measures recall of that
    answer rather than understanding, so do not. Write new questions freely
    when the bank is thin; they are banked automatically as you ask them.
    """
    return _j(E().questions_for(concept, n, difficulty, include_prereqs))


@mcp.tool()
def question_bank(concept: str) -> str:
    """Every question banked for a concept, with its record and next due date."""
    return _j(E().question_history(concept))


@mcp.tool()
def question_add(concept: str, text: str, kind: str = "application",
                 difficulty: int = 3) -> str:
    """Bank a good question without asking it now.

    kind: definition | application | edge | proof. Near-duplicates of an
    existing question are rejected and the original returned.
    """
    return _j(E().bank_question(concept, text, kind, difficulty))


# ----------------------------------------------------------------- planning
@mcp.tool()
def frontier(goal: str = "", k: int = 8) -> str:
    """What is learnable next: unmastered concepts whose prerequisites are met."""
    return _j(E().frontier(goal, k))


@mcp.tool()
def path_to(goal: str) -> str:
    """An ordered route to a goal concept, skipping anything already mastered."""
    return _j(E().path_to(goal))


@mcp.tool()
def due(limit: int = 10) -> str:
    """Concepts whose retention has decayed past the review threshold."""
    return _j(E().due(limit))


@mcp.tool()
def report(track: str = "") -> str:
    """Overall picture: mastery, knowledge estimates, brain and store counts."""
    return _j(E().report(track))


# -------------------------------------------------------------------- brain
@mcp.tool()
def brain_search(query: str, limit: int = 8) -> str:
    """Full-text search across the mentor's own notes."""
    return _j(E().brain.search(query, limit))


@mcp.tool()
def brain_page(path: str) -> str:
    """Read one page of the mentor's vault by its relative path."""
    e = E()
    p = e.brain.root / path
    if not p.exists() or p.suffix != ".md":
        return _j({"error": f"no page at {path!r}"})
    return _j({"path": path, "content": p.read_text(encoding="utf-8")})


@mcp.tool()
def status() -> str:
    """Engine health: brain size, graph shape, unresolved prerequisites, cycles."""
    return _j(E().status())


@mcp.tool()
def reindex() -> str:
    """Re-read the brain from disk. Call after editing pages in Obsidian."""
    e = E()
    e._refresh()
    return _j(e.status())


@mcp.tool()
def unicode_math(latex: str) -> str:
    """LaTeX -> Unicode, for maths that has to be read in the terminal.

    The TUI has no maths renderer, so LaTeX source arrives as literal
    characters. Convert anything you are unsure of before writing it.
    """
    return to_unicode(latex)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
