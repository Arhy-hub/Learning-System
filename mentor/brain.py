"""The mentor's Obsidian vault: its memory, and its only source of truth.

Everything the mentor knows lives here as markdown. There is no external index
to keep in sync — open the folder in Obsidian and you are looking at the whole
system state. Concepts are pages, prerequisites are frontmatter, relatedness is
wikilinks, and the numbers ride in frontmatter so Dataview can query them.

The model is a wiki, not a log. A concept page is *revised* whenever that
concept comes up, so it always reads as what the mentor currently believes.
Session pages are the exception: they record events and are written once.

Merge rule: the mentor rewrites only the sections it owns. Anything else you
add to a page survives untouched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

from .config import OWNED_SECTIONS
from .text import canon

SLUG_BAD = re.compile(r'[<>:"/\\|?*\[\]#^]')
_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")

APP_JSON = """{
  "alwaysUpdateLinks": true,
  "newLinkFormat": "shortest",
  "useMarkdownLinks": false,
  "attachmentFolderPath": "_attachments"
}"""


# Obsidian's own graph view, configured so state is visible at a glance.
# Written once; if you customise it, the mentor leaves it alone.
GRAPH_JSON = """{
  "collapse-filter": false,
  "search": "",
  "showTags": false,
  "showAttachments": false,
  "hideUnresolved": false,
  "showOrphans": true,
  "collapse-color-groups": false,
  "colorGroups": [
    { "query": "[\\"label\\":\\"solid\\"]",      "color": { "a": 1, "rgb": 889992 } },
    { "query": "[\\"label\\":\\"holding\\"]",    "color": { "a": 1, "rgb": 3890139 } },
    { "query": "[\\"label\\":\\"shaky\\"]",      "color": { "a": 1, "rgb": 11817737 } },
    { "query": "[\\"label\\":\\"needs work\\"]", "color": { "a": 1, "rgb": 12131356 } },
    { "query": "path:Resources",             "color": { "a": 1, "rgb": 8266446 } },
    { "query": "path:Sessions",              "color": { "a": 1, "rgb": 6583435 } }
  ],
  "collapse-display": false,
  "showArrow": true,
  "textFadeMultiplier": -0.5,
  "nodeSizeMultiplier": 1.4,
  "lineSizeMultiplier": 1,
  "collapse-forces": false,
  "centerStrength": 0.4,
  "repelStrength": 12,
  "linkStrength": 0.8,
  "linkDistance": 180,
  "scale": 0.75,
  "close": false
}"""

README = """# Mentor Brain

This is the mentor's memory. It is a normal Obsidian vault — open it.

- `Concepts/` — one page per concept, **revised in place**. Each page is what
  the mentor currently believes about your grasp of that idea: what you know,
  where you slip, which explanation landed, and the full question history.
- `Sessions/` — one page per session, written once. A record of what happened.
- `Resources/` — your library: the books, courses and papers the mentor is
  allowed to point you at. It curates from these; it does not write its own
  explanations.
- `Index.md` — the map of content, regenerated after every session.

Open the graph view (`Ctrl+G`). Nodes are coloured by state — teal solid, blue
holding, amber shaky, red needs-work, uncoloured never tested — with resources
in violet and sessions in grey. Arrows run prerequisite → concept. Prerequisites
named but not yet taught appear as unresolved nodes, which is exactly the list
of things to write next.

The mentor knows only what it has tested. It does not read your personal vault,
and it does not infer understanding from the existence of notes.

Frontmatter carries the numbers (`estimate`, `tested`, `confidence`,
`attempts`, `prereqs`), so Dataview works. Edit any page freely — the mentor
rewrites only the sections it owns and leaves the rest alone.
"""


def slug(name: str) -> str:
    s = SLUG_BAD.sub("", str(name)).strip().rstrip(".")
    return (s or "untitled")[:80]


@dataclass
class Page:
    path: Path
    title: str
    frontmatter: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    order: list = field(default_factory=list)
    preamble: str = ""
    body: str = ""

    def section(self, name: str, default: str = "") -> str:
        return self.sections.get(name, default)

    @property
    def id(self) -> str:
        return canon(self.frontmatter.get("concept") or self.title)

    @property
    def links(self) -> list:
        return list(dict.fromkeys(_WIKILINK.findall(self.body)))

    @property
    def prereqs(self) -> list:
        v = self.frontmatter.get("prereqs") or []
        if isinstance(v, str):
            v = [x.strip() for x in v.strip("[]").split(",") if x.strip()]
        return [str(x) for x in v]

    @property
    def track(self) -> str:
        return str(self.frontmatter.get("track") or "Unfiled")


def parse(path: Path) -> Page:
    text = path.read_text(encoding="utf-8", errors="ignore")
    fm: dict = {}
    body = text
    m = _FM.search(text)
    if m:
        body = text[m.end():]
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        if not isinstance(fm, dict):
            fm = {}
    title = path.stem
    h1 = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    if h1:
        title = h1.group(1).strip()
    sections: dict = {}
    order: list = []
    marks = list(_SECTION.finditer(body))
    pre = body[:marks[0].start()] if marks else body
    pre = re.sub(r"^#\s+.*$", "", pre, count=1, flags=re.M).strip()
    for i, mk in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        sections[mk.group(1).strip()] = body[mk.end():end].strip()
        order.append(mk.group(1).strip())
    return Page(path=path, title=title, frontmatter=fm, sections=sections,
                order=order, preamble=pre, body=body)


def render_fm(fm: dict) -> str:
    if not fm:
        return ""
    clean = {k: v for k, v in fm.items() if v is not None and v != ""}
    dumped = yaml.safe_dump(clean, sort_keys=False, allow_unicode=True,
                            default_flow_style=False).rstrip()
    return f"---\n{dumped}\n---\n"


class Brain:
    """The mentor's writable Obsidian vault."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.ensure()

    # -- setup -------------------------------------------------------------
    def ensure(self) -> None:
        for d in ("Concepts", "Sessions", "Resources", ".obsidian"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        app = self.root / ".obsidian" / "app.json"
        if not app.exists():
            app.write_text(APP_JSON, encoding="utf-8")
        graph = self.root / ".obsidian" / "graph.json"
        if not graph.exists():
            graph.write_text(GRAPH_JSON, encoding="utf-8")
        rd = self.root / "README.md"
        if not rd.exists():
            rd.write_text(README, encoding="utf-8")

    # -- paths --------------------------------------------------------------
    def concept_path(self, name: str, track: str = "") -> Path:
        existing = self.find(name)
        if existing is not None:
            return existing.path          # never move a page a human may have filed
        folder = self.root / "Concepts" / slug(track or "Unfiled")
        return folder / f"{slug(name)}.md"

    def resource_path(self, name: str) -> Path:
        existing = self.find_resource(name)
        if existing is not None:
            return existing.path
        return self.root / "Resources" / f"{slug(name)}.md"

    def resources(self) -> list:
        return [parse(p) for p in self.pages("Resources")]

    def find_resource(self, name: str):
        want = canon(name)
        for pg in self.resources():
            if canon(pg.title) == want or canon(pg.frontmatter.get("resource") or "") == want:
                return pg
        return None

    def session_path(self, sid: int, topic: str, when: date | None = None) -> Path:
        d = (when or date.today()).isoformat()
        return self.root / "Sessions" / f"{d} {slug(topic)} #{sid}.md"

    # -- reading -------------------------------------------------------------
    def pages(self, sub: str = "") -> list:
        base = self.root / sub if sub else self.root
        if not base.exists():
            return []
        return sorted(p for p in base.rglob("*.md") if ".obsidian" not in p.parts)

    def concepts(self) -> list:
        return [parse(p) for p in self.pages("Concepts")]

    def find(self, name: str):
        """A concept page by name, id or alias, wherever it was filed."""
        want = canon(name)
        if not want:
            return None
        for p in self.pages("Concepts"):
            page = parse(p)
            if page.id == want or canon(page.title) == want:
                return page
            aliases = page.frontmatter.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            if any(canon(a) == want for a in aliases):
                return page
        return None

    def recall(self, name: str) -> dict:
        """What the mentor already believes about a concept. Empty if new."""
        page = self.find(name)
        if page is None:
            return {}
        return {
            "path": str(page.path.relative_to(self.root)),
            "title": page.title,
            "frontmatter": page.frontmatter,
            "understanding": page.section("Understanding"),
            "slips": page.section("Where he slips"),
            "worked": page.section("What worked"),
            "open_questions": page.section("Open questions"),
            "history": page.section("History"),
        }

    def search(self, query: str, limit: int = 8) -> list:
        q = query.lower().strip()
        terms = [t for t in re.split(r"\W+", q) if len(t) > 2]
        if not terms:
            return []
        out = []
        for p in self.pages():
            txt = p.read_text(encoding="utf-8", errors="ignore")
            low = txt.lower()
            score = 4.0 * (q in p.stem.lower()) + 0.1 * sum(low.count(t) for t in terms)
            if score > 0:
                out.append({"path": str(p.relative_to(self.root)), "title": p.stem,
                            "score": round(score, 2), "excerpt": txt[:280]})
        out.sort(key=lambda d: -d["score"])
        return out[:limit]

    # -- writing ---------------------------------------------------------------
    def write(self, path: Path, title: str, frontmatter: dict,
              sections: dict, preamble: str = "") -> Path:
        """Write a page, preserving any section the mentor does not own."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = parse(path) if path.exists() else Page(path=path, title=title)

        merged = dict(existing.sections)
        for k, v in sections.items():
            if v is None:
                merged.pop(k, None)
            elif str(v).strip():
                merged[k] = str(v).strip()

        order = [h for h in OWNED_SECTIONS if h in merged]
        order += [h for h in existing.order if h in merged and h not in order]
        order += [h for h in merged if h not in order]

        fm = dict(existing.frontmatter)
        fm.update({k: v for k, v in frontmatter.items() if v is not None})

        parts = [render_fm(fm), f"# {title}\n"]
        pre = (preamble or existing.preamble).strip()
        if pre:
            parts.append("\n" + pre + "\n")
        for h in order:
            parts.append(f"\n## {h}\n\n{merged[h]}\n")
        path.write_text("".join(parts), encoding="utf-8")
        return path

    def write_session(self, path: Path, text: str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        return path

    def delete(self, name: str) -> bool:
        page = self.find(name)
        if page is None:
            return False
        page.path.unlink()
        return True

    # -- stats -------------------------------------------------------------------
    def stats(self) -> dict:
        cs = self.concepts()
        return {
            "root": str(self.root),
            "concepts": len(cs),
            "sessions": len(self.pages("Sessions")),
            "resources": len(self.pages("Resources")),
            "tracks": len({c.track for c in cs}),
            "tested": sum(1 for c in cs if int(c.frontmatter.get("attempts") or 0) > 0),
            "prereq_edges": sum(len(c.prereqs) for c in cs),
        }
