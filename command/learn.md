---
description: Full learning session on a topic - calibrate, read, test, record
agent: mentor
---

Run a complete session on: **$ARGUMENTS**

Follow the five-step spine exactly. Do not skip calibration because the topic
looks familiar — what he knew three weeks ago is a measurement, not a guarantee.

1. **Remember.** `session_start(topic, goal, track, prereqs)`. Read `recall`
   before you say anything. If `first_time`, say so plainly. Note `library` and
   `material` — what you may point at, and what is already assigned.

2. **Calibrate.** Delegate to `@calibrator`. One question at a time. If you
   remembered a slip, probe that first — whether the last fix held is worth more
   than a fresh question.

3. **Assign.** Delegate to `@curator`, record what comes back with
   `assign_material(concept, items)`, then **stop and wait**. He reads. Do not
   pre-empt what he will bring back, and do not explain the material yourself.

4. **Test.** Delegate to `@examiner` with `phase="exam"`. If he wrote code,
   `@reviewer` as well — a rated review is stronger evidence than a verbal answer.

5. **Record.** `session_end(summary, concepts={...})` with `understanding`,
   `slips`, `worked`, `open`, `prereqs`, `track`, `material` per concept. Specific
   over general: "reaches for closed-and-bounded before the open-cover definition"
   is usable, "shaky on compactness" is not.

Between steps, say which step you are on in a few words. Be brief in the
terminal — answer first, detail after.
