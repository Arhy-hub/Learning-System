"""Show or change which model each opencode agent runs on.

The map lives in the "agent" block of opencode.json. This edits that block in
place and touches nothing else.

    python scripts/models.py              # current map
    python scripts/models.py list         # every model available
    python scripts/models.py list claude  # filtered
    python scripts/models.py set examiner anthropic/claude-haiku-4-5
    python scripts/models.py set default anthropic/claude-opus-5

Edits the "agent" block of your opencode.json in place and touches nothing else.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Your live opencode config - not a file in this repo. Override with
# OPENCODE_CONFIG if yours lives somewhere else.
CONFIG = Path(os.environ.get(
    "OPENCODE_CONFIG", Path.home() / ".config" / "opencode" / "opencode.json"))
CATALOGUE = Path.home() / ".cache" / "opencode" / "models.json"
AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"

ROLES = {
    "mentor": "orchestrator, writes memory",
    "cartographer": "graph planning",
    "reviewer": "rates code",
    "curator": "picks and verifies sources",
    "calibrator": "opening probe loop",
    "examiner": "exit test loop",
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mine() -> set[str]:
    """Providers he is actually signed in to, plus any declared in opencode.json."""
    names = set()
    if AUTH.exists():
        names |= set(load(AUTH))
    names |= set(load(CONFIG).get("provider", {}))
    return names


def available(everything: bool = False) -> dict[str, list[str]]:
    if not CATALOGUE.exists():
        return {}
    keep = None if everything else mine()
    out = {}
    for provider, body in load(CATALOGUE).items():
        if keep is not None and provider not in keep:
            continue
        models = sorted(body.get("models", {}))
        if models:
            out[provider] = models
    return out


def known_ids(everything: bool = False) -> set[str]:
    ids = {f"{p}/{m}" for p, ms in available(everything).items() for m in ms}
    # Providers declared locally in opencode.json are real too.
    cfg = load(CONFIG)
    for p, body in cfg.get("provider", {}).items():
        for m in body.get("models", {}):
            ids.add(f"{p}/{m}")
    return ids


def cmd_show() -> int:
    if not CONFIG.exists():
        print(f"No opencode config at {CONFIG}.")
        print("Set OPENCODE_CONFIG, or copy opencode.example.json into place first.")
        return 1
    cfg = load(CONFIG)
    agents = cfg.get("agent", {})
    width = max((len(a) for a in agents), default=6)
    print(f"{'AGENT'.ljust(width)}  {'MODEL'.ljust(34)}  ROLE")
    for name, body in agents.items():
        model = body.get("model", "(inherits default)")
        print(f"{name.ljust(width)}  {model.ljust(34)}  {ROLES.get(name, '')}")
    print()
    print(f"{'default'.ljust(width)}  {cfg.get('model', '(unset)')}")
    print(f"{'small'.ljust(width)}  {cfg.get('small_model', '(unset)')}")
    print()
    print("Change one:  python scripts/models.py set <agent> <provider/model>")
    return 0


def cmd_list(pattern: str = "", everything: bool = False) -> int:
    avail = available(everything)
    if not avail:
        print(f"No catalogue at {CATALOGUE}. Start opencode once to populate it.")
        return 1
    rx = re.compile(pattern, re.I) if pattern else None
    for provider in sorted(avail):
        hits = [m for m in avail[provider] if not rx or rx.search(m)]
        if not hits:
            continue
        print(f"=== {provider} ({len(hits)}) ===")
        for m in hits:
            print(f"   {provider}/{m}")
    if not everything:
        print("\n(signed-in providers only; `list --all` for every provider)")
    return 0


def cmd_set(agent: str, model: str) -> int:
    cfg = load(CONFIG)

    if model not in known_ids():
        print(f"Unknown model {model!r}.")
        stem = model.split("/")[-1]
        near = sorted(i for i in known_ids() if stem.split("-")[0].lower() in i.lower())
        if near:
            print("Did you mean:")
            for n in near[:12]:
                print(f"   {n}")
        print("\nSee all:  python scripts/models.py list")
        return 1

    raw = CONFIG.read_text(encoding="utf-8")

    if agent in ("default", "model"):
        old = cfg.get("model", "(unset)")
        new = re.sub(r'("model"\s*:\s*)"[^"]*"', rf'\1"{model}"', raw, count=1)
        label = "default"
    elif agent in ("small", "small_model"):
        old = cfg.get("small_model", "(unset)")
        new = re.sub(r'("small_model"\s*:\s*)"[^"]*"', rf'\1"{model}"', raw, count=1)
        label = "small_model"
    else:
        if agent not in cfg.get("agent", {}):
            print(f"No agent {agent!r}. Known: {', '.join(cfg.get('agent', {}))}")
            return 1
        old = cfg["agent"][agent].get("model", "(unset)")
        # Rewrite only this agent's line, leaving the rest of the file byte-identical.
        pat = re.compile(rf'("{re.escape(agent)}"\s*:\s*\{{[^}}]*?"model"\s*:\s*)"[^"]*"')
        new, n = pat.subn(rf'\1"{model}"', raw, count=1)
        if n != 1:
            print(f"Could not locate the model line for {agent!r}; edit opencode.json by hand.")
            return 1
        label = agent

    json.loads(new)  # never write a file that does not parse
    with open(CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)
    print(f"{label}: {old} -> {model}")
    print("Restart opencode to pick it up.")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        return cmd_show()
    cmd, rest = argv[0], argv[1:]
    if cmd in ("show", "map"):
        return cmd_show()
    if cmd in ("list", "models"):
        everything = "--all" in rest
        rest = [r for r in rest if r != "--all"]
        return cmd_list(rest[0] if rest else "", everything)
    if cmd == "set":
        if len(rest) != 2:
            print("usage: models.py set <agent|default|small> <provider/model>")
            return 1
        return cmd_set(*rest)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
