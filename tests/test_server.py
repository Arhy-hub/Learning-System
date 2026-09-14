"""The MCP layer.

The engine is covered thoroughly by test_mentor.py; nothing there imports
server.py, so the tool surface itself was unverified. That gap let
`unicode_math` sit in the mentor's prompt for a while without existing on the
server — an error the agent only discovers mid-session, by calling it.

These tests check the seam: that every tool the prompts name is really exposed,
and that the two tools reaching past the engine API still work.
"""
from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path

import pytest

import mentor.server as server
from mentor.config import Config
from mentor.engine import Engine

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"


def tool_names() -> set[str]:
    r = server.mcp.list_tools()
    if inspect.isawaitable(r):
        r = asyncio.run(r)
    return {t.name for t in r}


@pytest.fixture()
def served(tmp_path, monkeypatch):
    """Point the module-level engine singleton at a throwaway brain."""
    engine = Engine(Config(data_dir=tmp_path))
    monkeypatch.setattr(server, "_engine", engine)
    return engine


class TestToolSurface:
    def test_tools_are_registered(self):
        assert len(tool_names()) >= 28

    def test_every_tool_has_a_docstring(self):
        r = server.mcp.list_tools()
        if inspect.isawaitable(r):
            r = asyncio.run(r)
        undocumented = [t.name for t in r if not (t.description or "").strip()]
        assert not undocumented, f"tools with no description: {undocumented}"

    @pytest.mark.skipif(not AGENT_DIR.is_dir(), reason="agent prompts not alongside")
    def test_every_tool_named_in_a_prompt_exists(self):
        """The check that would have caught the phantom `unicode_math`."""
        names = tool_names()
        # `word(` in backticks is how the prompts write a tool call.
        call = re.compile(r"`(\w+)\(")
        # Prose uses the same shape for things that are not tools: reviewer.md
        # talks about `solve()` as an example of code under review.
        ignore = {"solve", "print", "len", "int", "float", "str", "canon", "f"}
        missing: dict[str, set[str]] = {}
        for md in sorted(AGENT_DIR.glob("*.md")):
            referenced = set(call.findall(md.read_text(encoding="utf-8")))
            gone = {r for r in referenced if r not in names and r not in ignore}
            if gone:
                missing[md.name] = gone
        assert not missing, f"prompts call tools that do not exist: {missing}"


class TestUnicodeMath:
    def test_converts_latex(self):
        out = server.unicode_math(r"$\forall \epsilon>0$")
        assert "∀" in out and "\\forall" not in out

    def test_is_exposed(self):
        assert "unicode_math" in tool_names()


class TestEngineBypassingTools:
    """`remember` and `concept` reach into private Engine methods directly."""

    def test_remember_then_recall(self, served):
        server.remember(
            "Compactness",
            understanding="Open-cover definition, applies it correctly.",
            slips="Reaches for closed-and-bounded first.",
            track="Analysis",
        )
        back = server.recall("Compactness")
        assert "Compactness" in back or "compactness" in back.lower()

    def test_remember_writes_a_page(self, served):
        server.remember("Compactness", understanding="Solid.", track="Analysis")
        # Pages nest by track: Concepts/<Track>/<Name>.md
        pages = list((served.brain.root / "Concepts").rglob("*.md"))
        assert pages, "remember() wrote no concept page"

    def test_concept_miss_is_a_hint_not_a_crash(self, served):
        out = server.concept("Nonexistent Topic")
        assert "error" in out and "hint" in out

    def test_concept_hit(self, served):
        server.remember("Compactness", understanding="Solid.", track="Analysis")
        assert "error" not in server.concept("Compactness")


class TestNoSessionIsAnError:
    def test_answer_without_a_session(self, served):
        assert "error" in server.answer("correct", question="Q?", response="A").lower()


class TestResourceDates:
    def test_re_adding_a_resource_keeps_its_original_added_date(self, served):
        served.add_resource("Rudin", kind="book", author="W. Rudin")
        page = served.brain.find_resource("Rudin")
        first = page.frontmatter["added"]

        page.path.write_text(
            page.path.read_text(encoding="utf-8").replace(first, "2020-01-01"),
            encoding="utf-8")

        served.add_resource("Rudin", kind="book", author="W. Rudin", notes="reread ch 2")
        again = served.brain.find_resource("Rudin").frontmatter["added"]
        assert again == "2020-01-01", "re-registering a resource reset its added date"
