"""Command line access to the mentor engine.

    mentor status              brain and graph health
    mentor concepts            everything the mentor knows, with state
    mentor concept <name>      one concept in detail
    mentor recall <name>       what it remembers, as written
    mentor similar <name>      nearest concepts and why
    mentor frontier [goal]     what is learnable next
    mentor path <goal>         ordered route to a goal
    mentor due                 what needs review
    mentor sessions            session history
    mentor open                open the brain in Obsidian (Ctrl+G for the graph)
    mentor math <latex>        LaTeX to Unicode, for terminals that cannot render it
"""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from urllib.parse import quote

from .engine import Engine
from .mathtext import to_unicode


def _p(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_status(e, a):
    s = e.status()
    b, g = s["brain"], s["graph"]
    print(f"brain          {b['root']}")
    print(f"concepts       {g['concepts']} across {g['tracks']} tracks")
    print(f"tested         {g['tested']}")
    print(f"prereq edges   {g['prereq_edges']}   related {g['related_edges']}")
    print(f"sessions       {b['sessions']}")
    print(f"cycles         {g['cycles']}")
    if s["unresolved_prereqs"]:
        print("\nprereqs named but not yet written:")
        for u in s["unresolved_prereqs"]:
            print(f"  {u['concept']} -> {u['prereq']}")
    if not g["concepts"]:
        print("\nThe brain is empty. Start a session and it fills itself.")


def cmd_concepts(e, a):
    rows = [e.describe(c, deep=False) for c in e.graph.nodes]
    rows.sort(key=lambda d: (d["track"], -d["tested"], d["name"]))
    if not rows:
        print("nothing learned yet")
        return
    track = None
    for d in rows:
        if d["track"] != track:
            track = d["track"]
            print(f"\n{track}")
        k = d["knowledge"]
        print(f"  {d['tested']:.2f}  est {k['estimate']:.2f}  "
              f"{d['attempts']:>2d}x  {d['name'][:40]:42s}{k['label']}")


def cmd_concept(e, a):
    cid = e.resolve(a.name)
    if not cid:
        _p({"error": f"no concept called {a.name!r}",
            "search": e.brain.search(a.name, 5)})
        return 1
    _p(e.describe(cid))


def cmd_recall(e, a):
    r = e.brain.recall(a.name)
    if not r:
        print(f"nothing remembered about {a.name!r} yet")
        return
    print(f"# {r['title']}   ({r['path']})\n")
    for key, head in (("understanding", "Understanding"),
                      ("slips", "Where he slips"),
                      ("worked", "What worked"),
                      ("open_questions", "Open questions")):
        if r.get(key):
            # The page keeps its LaTeX; the terminal cannot render it, so the
            # display pass converts to Unicode on the way out.
            print(f"## {head}\n{to_unicode(r[key])}\n")


def cmd_similar(e, a):
    cid = e.resolve(a.name)
    if not cid:
        print(f"no concept called {a.name!r}")
        return 1
    for s in e.similarity.nearest(cid, a.k):
        c = s.as_dict()["components"]
        print(f"  {s.score:.3f}  {e.graph.nodes[s.b].name[:36]:38s}"
              f"content={c['content']:.2f} struct={c['structural']:.2f} "
              f"lex={c['lexical']:.2f} link={c['link']:.0f}")


def cmd_frontier(e, a):
    rows = e.frontier(a.goal or "", a.k)
    if not rows:
        print("nothing ready — the brain may be empty, or everything is mastered")
        return
    for d in rows:
        print(f"  est {d['knowledge']['estimate']:.2f}  {d['name'][:40]:42s}{d['track']}")


def cmd_path(e, a):
    r = e.path_to(a.goal)
    if "error" in r:
        _p(r)
        return 1
    print(f"{r['goal']}  ({r['steps']} steps)")
    for i, d in enumerate(r["path"], 1):
        print(f"  {i:2d}. {d['name'][:42]:44s}tested {d['tested']:.2f}")


def cmd_due(e, a):
    rows = e.due(a.k)
    if not rows:
        print("nothing due")
        return
    for d in rows:
        print(f"  {d['tested']:.2f}  {d['name'][:40]:42s}"
              f"last {d['last_tested'] or '—'}")


def cmd_sessions(e, a):
    for s in e.store.recent_sessions(a.k):
        print(f"  #{s['id']:<4d} {s['started_at'][:10]}  {s['topic'][:34]:36s}"
              f"{s['phase']}")
        if s["summary"]:
            print(f"        {s['summary'][:100]}")


def cmd_math(e, a):
    print(to_unicode(" ".join(a.text)))


def cmd_open(e, a):
    uri = f"obsidian://open?path={quote(str(e.cfg.brain_dir))}"
    print(uri)
    webbrowser.open(uri)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mentor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("concepts").set_defaults(fn=cmd_concepts)
    sub.add_parser("open").set_defaults(fn=cmd_open)
    s = sub.add_parser("math"); s.add_argument("text", nargs="+"); s.set_defaults(fn=cmd_math)

    s = sub.add_parser("concept"); s.add_argument("name"); s.set_defaults(fn=cmd_concept)
    s = sub.add_parser("recall"); s.add_argument("name"); s.set_defaults(fn=cmd_recall)
    s = sub.add_parser("similar"); s.add_argument("name")
    s.add_argument("-k", type=int, default=8); s.set_defaults(fn=cmd_similar)
    s = sub.add_parser("frontier"); s.add_argument("goal", nargs="?", default="")
    s.add_argument("-k", type=int, default=8); s.set_defaults(fn=cmd_frontier)
    s = sub.add_parser("path"); s.add_argument("goal"); s.set_defaults(fn=cmd_path)
    s = sub.add_parser("due"); s.add_argument("-k", type=int, default=10); s.set_defaults(fn=cmd_due)
    s = sub.add_parser("sessions"); s.add_argument("-k", type=int, default=15)
    s.set_defaults(fn=cmd_sessions)

    a = ap.parse_args(argv)
    return a.fn(Engine(), a) or 0


if __name__ == "__main__":
    sys.exit(main())
