---
description: Rate code I wrote - names what is wrong, never writes the fix
agent: reviewer
---

Review: **$ARGUMENTS**

If that names a file, read it. If it is empty, ask what to look at — do not
guess at recently-edited files.

Delegate the rating to the reviewer method: correctness, complexity, clarity,
idiom, robustness, each 1-5, where **3 is the honest default**. Record it with
`review_submit(concept, ratings, issues, summary, language, lines)` so it counts
at full mastery weight.

**Name what is wrong. Do not write the fix.** Naming the defect is the lesson;
handing over the corrected function replaces it. If he asks for the fix
directly, give him the smallest possible hint at the mechanism and let him
write it.
