---
description: Quick spaced-repetition drill on whatever has decayed
agent: mentor
---

1. `due(limit=5)`. If nothing is due, say so in one line and stop — do not
   invent a drill to fill the time.
2. Otherwise open a session, and for each due item ask **one** question via
   `ask_next` / `answer` with `phase="exam"`.
3. `session_end` with a two-line summary.

This is the five-minute version. No curation, no explanations, no new concepts.
Mark the verdict honestly — an inflated pass here resets the decay clock on
something he does not actually hold, which is worse than not drilling at all.
