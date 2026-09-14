# Sage

This is my AI learning system. I like learning stuff and I wanted to stop wasting my time with the logistics of learning so I decided to make Sage. I think it is quite useful to view your knowledge with a graph which is why I integrate it with obsidian.
You can probably tailor this to codex or claude etc but I am trying out opencode as it is provider agnostic.
(Please note this is just a work in progress and I am still testing out the various aspects of it) 

## Two rules

My core two rules: 

1) **It knows what it has tested. Nothing else.**
2) **It curates; it does not author.**

When I learn I prefer to not directly learn from AI. This is because it is very easy to fool yourself into believing you have understood something. However, I do believe that AI is great at testing so I get it to test me and curate sources.

## The brain

`data/brain/` is a real Obsidian vault. Open it — it is the whole system state.

```
brain/
├── Concepts/<Track>/<Name>.md   one page per concept, revised in place
├── Sessions/YYYY-MM-DD ....md   one page per session, written once
├── Index.md                     regenerated after every session
└── README.md
```

A concept page is what the mentor currently believes:

```markdown
---
concept: compactness
track: Analysis
prereqs: [Open and closed sets, Sequences]
tested: 0.583      # measured from graded answers
estimate: 0.41     # inferred; capped until something is tested
confidence: 0.95
attempts: 2
label: shaky
---
## Understanding
Holds the open-cover definition; can build the (0,1) counterexample unaided.

## Where he slips
- Reaches for closed-and-bounded first.

## What worked
Asking for a non-compact set in a general metric space.

## Open questions
- Sequential compactness in general metric spaces?

## Prerequisites
[[Open and closed sets]], [[Sequences]]

## History
| date | phase | verdict | question |
```

The markdown **is** the graph: prerequisites are frontmatter, relatedness is
wikilinks. Edit a page in Obsidian and the graph changes. Sections the mentor
does not own are preserved, so your own notes on a page survive.

## Two numbers per concept

1. **tested**   | decayed mastery from graded answers. A measurement. 
2. **estimate** | inferred from similar concepts and mastered prerequisites. Capped at 0.45, and never presented as knowledge. 

Mastery decays: `effective = strength · 2^(-days / half_life)`. A correct answer
stretches the half-life, a miss collapses it — so review timing falls out of the
model rather than a schedule.

## Asking

**One question at a time, enforced by the API.** `ask_next()` returns exactly
one question; `answer(...)` records it and hands back the next. There is no way
to batch, which is deliberate — a numbered list lets him read ahead and answer
out of order, and stops difficulty adapting to the answer just given.

## Code review

For anything he has implemented, `review_submit` records a rating on five
dimensions — correctness, complexity, clarity, idiom, robustness — each 1–5,
plus issues at blocker / major / minor / note severity. The overall maps onto
the same correct / partial / incorrect verdicts and moves mastery at **full
weight**: a review is a real assessment.

It rates and names; it does not repair. No corrected code, no patch — a `fix`
field on an issue is discarded on the way in. Being told `solve()` recomputes
overlapping subproblems is the lesson; being handed the memoised version is not.

## Questions

Questions are kept, not thrown away — a question that exposed a real
misconception is the most valuable thing a session produces.

Each one is banked with a stable id, a kind (definition / application / edge /
proof) and a difficulty, and carries **its own cooldown**: a miss comes back in
a day, a correct answer waits 3, then 7, 21, 60, 180. Concept mastery decays,
but you forget specific things, so spacing runs at item level too.

The selector refuses to offer a question still cooling — re-asking something
answered an hour ago measures recall of that answer, not the idea, and would
inflate mastery on a lie. Priority leads with what was missed; a penalty on
repeated kinds stops five definitions in a row without letting balance override
priority. A near-duplicate of a banked question is treated as the same question
reworded. One answered correctly five times running retires itself: it has
stopped discriminating.

The bank renders onto each concept page, so it is readable and editable in
Obsidian like everything else.

## Viewing the graph

Open the brain in Obsidian and press `Ctrl+G`. The vault ships configured for
it: nodes coloured by state — teal solid, blue holding, amber shaky, red
needs-work, uncoloured never tested — resources in violet, sessions in grey,
arrows running prerequisite → concept. Prerequisites named but never taught show
as unresolved nodes, which is exactly the list of what to write next.

```
mentor open      # first time: "Open folder as vault" on data/brain
```

There is no bespoke visualiser. Obsidian already does this better, and the
markdown is the graph.

## Maths in the terminal

opencode's TUI is `@opentui` (SolidJS in the terminal) and has **no maths
renderer**. KaTeX ships only in opencode's web bundle, and the plugin API has no
hook that can touch assistant text before it is drawn — `chat.message` fires on
*your* messages, `experimental.chat.messages.transform` rewrites what goes *to*
the model. So LaTeX cannot be made to render in the TUI.

Three places it does render: `opencode web` (KaTeX), the brain vault (Obsidian),
and the terminal via `mathtext.py`, which converts to Unicode. That module maps
Greek, blackboard bold, calligraphic, operators, quantifiers, arrows,
sub/superscripts, fractions, roots and accents; where Unicode has no form it
falls back to a readable `∇_θ` rather than mangling. Agents write Unicode to the
terminal and LaTeX to the pages.

    $ mentor math '$\sum_{i=1}^n a_i^2 \leq (\sum a_i)^2$'
    ∑ᵢ₌₁ⁿ aᵢ² ≤ (∑ aᵢ)²

## Similarity

Four components, each reported so a match can be inspected: TF-IDF over the
mentor's own prose, prerequisite-graph distance, name overlap, and explicit
wikilinks. Used to test transfer, to reuse an explanation that worked on a
neighbour, and to infer where knowledge should carry.

## Modules

| | |
|---|---|
| `brain.py` | the Obsidian vault: pages, frontmatter, merge-preserving writes |
| `graph.py` | concepts, prerequisites, cycles, frontier, routes |
| `knowledge.py` | the estimate, its signals and its ceiling |
| `similarity.py` | four-component concept similarity |
| `mathtext.py` | LaTeX to Unicode, so maths reads in a terminal |
| `review.py` | code review as rating: dimensions, severities, verdict mapping |
| `questions.py` | the question bank: ids, cooldowns, selection, retirement |
| `mastery.py` | strength and half-life decay |
| `store.py` | SQLite: sessions and every graded response |
| `engine.py` | session lifecycle; concepts auto-create |
| `server.py` | 28 MCP tools |

## CLI

```
mentor status              brain and graph health
mentor concepts            everything it knows, with state
mentor concept <name>      one concept in detail
mentor recall <name>       what it remembers, as written
mentor similar <name>      nearest concepts and why
mentor frontier [goal]     what is learnable next
mentor path <goal>         ordered route
mentor due                 what needs review
mentor sessions            history
mentor open                open the brain in Obsidian (Ctrl+G = graph)
mentor math <latex>        LaTeX to Unicode
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                     # 108 tests
ruff check .
```

A venv matters here: the MCP server is launched by opencode, not by you, so if
its dependencies live in your global site-packages an unrelated `pip install -U`
can break it. The failure shows up as tools silently missing from the agent,
which is miserable to diagnose. `mcp` is pinned `<3` for the same reason.

Then wire it into opencode:

1. Copy `opencode.example.json` into `~/.config/opencode/opencode.json`, or
   merge its blocks into yours. Replace the interpreter path in `mcp.mentor.command`
   with the `python` inside the venv you just made.
2. Copy `agent/*.md` into `~/.config/opencode/agent/` — the prompt layer.
   `mentor` is the primary agent, the other five are its subagents.
3. Copy `command/*.md` into `~/.config/opencode/command/` for the slash commands.
4. Copy `AGENTS.md` into `~/.config/opencode/` and edit it: it carries the rules
   that bind every agent, including which vault is off-limits and who you are.
5. Start opencode and switch to the `mentor` agent.

`MENTOR_BRAIN` moves the vault, `MENTOR_DATA` moves everything. Both default to
`data/`, which is gitignored: the brain is one person's learning, not source.

## Commands

| | |
|---|---|
| `/learn <topic>` | the full session: calibrate, assign, read, test, record |
| `/test <topic>` | straight to the exit test, no teaching |
| `/next [goal]` | what is due, what is learnable, the route to a goal |
| `/review <file>` | rate code on five dimensions |
| `/due` | five-minute spaced-repetition drill |
| `/brain` | graph health: cycles, unresolved prereqs, untested concepts |
| `/model-map` | see or change which model each agent runs on |

## Choosing models

Each agent runs on its own model, set in one place — the `agent` block of your
`opencode.json`. `scripts/models.py` reads and edits it so you do not have to:

```
python scripts/models.py                                    # the current map
python scripts/models.py list opus                          # what you can pick
python scripts/models.py set examiner anthropic/claude-haiku-4-5
```

It validates ids against opencode's own catalogue, only suggests providers you
are signed in to, rewrites a single line, and refuses to write a file that does
not parse. `/model-map` is the same thing from inside the TUI, and will propose
a whole map if you ask it to make things cheaper.

Rough guide: `calibrator` and `examiner` carry the most turns and need the least
reasoning, so move those down first. `reviewer` and `cartographer` do the actual
thinking. `mentor` writes the pages everything later depends on.

## Tests and CI

```
pytest -q        # 108 tests
ruff check .
```

`tests/test_mentor.py` covers the engine; `tests/test_server.py` covers the MCP
layer, including a check that every tool named in an agent prompt actually
exists on the server — a prompt that calls a tool that was never registered
otherwise fails mid-session, which is how `unicode_math` went unnoticed.

CI runs both on Windows and Linux across 3.11 and 3.12. Locally,
`git config core.hooksPath .githooks` runs the same checks before each commit.

Ruff has `RUF001-003` disabled on purpose: they flag "ambiguous unicode", and
Greek letters, blackboard bold and set operators are this project's subject
matter.

## Writing your own agent

`templates/agent.md` is a starting point with the conventions the six existing
agents follow — trigger-shaped description, deny-by-default permissions,
temperature by job — and the wiring steps that are easy to forget.

## Using it

Just talk to it. Concepts, prerequisites and pages are created as they come up;
there is nothing to configure and no index to maintain.

```
teach me compactness
what should I learn next
review this                 # paste code — you get a rating, not a fix
what do I know about measure theory
```

Then `mentor open` to watch the vault fill, and `Ctrl+G` in Obsidian for the
graph.

## The agents

| | |
|---|---|
| `mentor` | primary; runs the session, holds the memory |
| `calibrator` | finds out what you actually know, one question at a time |
| `curator` | picks what you read and in what order; searches the web when the library is thin |
| `examiner` | the exit test, graded strictly |
| `reviewer` | rates code on five dimensions; names defects, never fixes them |
| `cartographer` | plans routes across the concept graph |

## Licence

MIT — see [LICENSE](LICENSE).
