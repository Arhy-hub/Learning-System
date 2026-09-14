# Global rules

These bind every agent, in every session. Individual agent prompts add to them;
nothing overrides them.

Copy this to `~/.config/opencode/AGENTS.md` and reference it from your
`opencode.json` with `"instructions": ["AGENTS.md"]`.

## Your personal notes are off-limits

Do not read, write, index or search the user's personal note vault.

A note proves something was written down, not that it is understood. Treating
notes as evidence of understanding was measured on a real vault and it failed
badly: 8% coverage with confident false positives, matching "Kubernetes" and
"Measure Theory" to a planning note that merely listed them. An agent fed that
signal believes the user understands things they have never demonstrated.

Anything that models what someone knows must earn it by testing, never by
reading. Generated output goes to the mentor's own brain, never into a personal
vault.

If you keep your vault somewhere an agent might wander into, name the path here
so the rule is concrete.

## Maths in the terminal: Unicode, not LaTeX

opencode's TUI has no maths renderer, so LaTeX source arrives as literal
characters. In the terminal write `∀ε > 0` rather than the LaTeX for it.

Use ℝ ℂ ℕ ℤ ℚ, α β γ …, ∈ ∉ ⊆ ∪ ∩ ∅, ∀ ∃, → ↦ ⇒ ⟺, ∫ ∑ ∏ ∂ ∇ ∞ √,
≤ ≥ ≠ ≈ ≡, ‖·‖ ⟨·,·⟩, and sub/superscripts xₙ x² aᵢ ℝⁿ.

The `unicode_math(latex)` tool converts anything you are unsure of.

Where Unicode cannot hold it — a real fraction, a matrix, a multi-line
derivation — use a fenced code block laid out in ASCII.

**In files this does not apply.** Markdown pages are rendered by Obsidian and by
`opencode web`, so write LaTeX normally there. The pages are the durable
artifact; the terminal is only a view.

## The learner

Describe yourself here — field, level, what to assume and what to skip. The
agents read this to pitch questions correctly. The default assumes a maths
undergraduate working at graduate level in places: fluent with proof and
abstraction, no padding.
