<!--
TEMPLATE - not a live agent. This directory is not loaded by opencode.

To use:
  1. cp templates/agent.md agent/<name>.md   (then copy it to ~/.config/opencode/agent/)
  2. Fill in the frontmatter and the four sections.
  3. Delete this comment block and every <!-- --> hint.
  4. Register the model:  python scripts/models.py  (see "Wiring up" at the end)

The filename is the agent name. `@<name>` delegates to it.
-->
---
description: <!-- One line, written as a trigger, not a title. This is the ONLY thing mentor.md sees when deciding whether to delegate, so say when to use it: "Probes what the user actually understands before any teaching." not "Calibration agent." -->
mode: subagent
# subagent - invoked via @name by another agent. Almost always this.
# primary  - drives the conversation directly. Only mentor.md is primary.
temperature: 0.3
# 0.2 - judgement and rating, where consistency matters most (reviewer)
# 0.3 - planning, curation, orchestration (mentor, cartographer, curator)
# 0.4 - writing questions, where some variety is the point (calibrator, examiner)
color: accent
# primary | accent | info | success | warning
permission:
  edit: deny
  bash: deny
# Deny by default and grant deliberately. An agent that assesses him must not be
# able to edit the record it is measuring. Only curator has web access:
#   websearch: allow
#   webfetch: allow
---

<!-- Open with one sentence naming the single job. If you need "and" here, it is
     two agents. e.g. "You test what the session taught, and you keep the record
     honest." -->
You <single job>.

## Method

<!-- Numbered steps, naming the exact MCP tools to call and in what order. Be
     specific about loops: the one-question-at-a-time rule is enforced by the API
     shape, but say it anyway so a subagent does not batch. -->

1. `<tool>(...)` — what it gives you and what to do with it.
2. **Loop one at a time**: `ask_next(...)` → ask → `answer(...)` → repeat, N times.
3. ...

## Grading
<!-- Only if this agent produces verdicts. Delete otherwise.
     Define all three levels explicitly - `partial` is the one that drifts.
     State what the verdict costs, so it is not inflated out of politeness. -->

- `correct` — <!-- what actually clears the bar -->
- `partial` — <!-- right instinct, specific gap -->
- `incorrect` — <!-- wrong, or a guess -->

## Output

<!-- The exact shape you want back, since the caller has to parse it. Either a
     fixed set of headings (curator returns Core/Read/Do/Skip/Missing/Check) or a
     hard length ("two or three sentences"). Vague output instructions produce
     essays. Say what is already recorded via tools so it is not repeated as prose. -->

## What you do not do

<!-- The prohibitions are load-bearing in this system and belong in the prompt,
     not in someone's memory. The standing ones:
       - never write explanations, derivations, worked examples or definitions
       - never write the fix for code; naming the defect is the lesson
       - never read his personal Obsidian vault (see AGENTS.md)
       - never re-ask a question still cooling
     Keep the ones that apply and say why, briefly. A rule with a reason survives
     an edge case; a bare rule does not. -->

<!--
## Wiring up  (delete this section too)

1. Model — add to the `agent` block of opencode.json, then verify:
       python scripts/models.py

2. Role label — add to ROLES in scripts/models.py, or /model-map shows it blank:
       "<name>": "<three words>",

3. Delegation — if mentor.md should call it, add it to the spine in that file.
   An agent nothing delegates to will never run.

4. Check it loads:
       opencode agent list

5. Tests — tests/test_server.py asserts every `tool(` named in any agent prompt
   actually exists on the server. Run it; a typo'd tool name fails there rather
   than mid-session:
       python -m pytest -q

Global rules in AGENTS.md already apply. Do not restate them here.
-->
