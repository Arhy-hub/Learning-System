---
description: Test me on a concept - no teaching, no curation, just the exam
agent: mentor
---

Test on: **$ARGUMENTS**

Straight to assessment. No calibration phase, no reading assignment, no
explanations before or between questions.

1. `session_start(topic)` so the result is recorded against a real session.
2. Read `recall` — if there is a known slip, that is the first question.
3. Delegate to `@examiner` with `phase="exam"`.
4. `session_end(summary, concepts={...})`.

If the bank is empty for this concept, write fresh questions. A question is
worth asking only if a wrong answer tells you something specific — "do you
understand X" is worthless, "give a closed bounded set that is not compact"
separates people who memorised the theorem from people who understood it.

If he asks for the answer before he has given one, refuse and re-ask.
