---
description: Show or change which model each mentor agent runs on
agent: mentor
---

Manage the per-agent model map in the user's `opencode.json`. Request: `$ARGUMENTS`

The helper lives in this project's `scripts/models.py`. Call it with the path to
wherever the repo is cloned; it edits `~/.config/opencode/opencode.json`
(override with `OPENCODE_CONFIG`).

## What to do

**Empty request** — run `python scripts/models.py` and present the table
readably. Then one line: "`/model-map <agent> <model>` to change one,
`/model-map list` to see options."

**`list`, or asking what is available** — run `python scripts/models.py list <filter>`
and group by provider. `anthropic/*` bills directly; `opencode/*` goes through
the zen gateway and includes free models (suffix `-free`); a local Ollama model
is free but weak. Add `--all` only if they ask about providers they are not
signed in to.

**Names an agent and a model** — e.g. "put the examiner on haiku". Run
`python scripts/models.py set <agent> <provider/model>`. The script validates
the id against the catalogue, rewrites only that one line, and refuses to write
a file that does not parse, so do not hand-edit the JSON. Report its output plus
"restart opencode to pick it up".

**A goal rather than an assignment** — e.g. "make this cheaper", "make testing
sharper". Propose a full map as a table with one line of reasoning per change,
apply it only once they agree, then show the result.

Useful shape when advising:
- `calibrator` and `examiner` carry the most turns and need the least reasoning
  — they ask a banked question and grade against a rubric. Move these first to
  save money.
- `reviewer` and `cartographer` do the actual reasoning. Downgrading them is
  what degrades the system.
- `mentor` writes the memory pages everything later depends on. Cheaping out
  here degrades the record quietly, which is the worst failure mode available.
