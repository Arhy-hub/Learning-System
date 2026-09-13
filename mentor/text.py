"""Text normalisation shared by the syllabus parser and the coverage matcher."""
from __future__ import annotations

import re
import unicodedata

_LATEX_INLINE = re.compile(r"\$\$?.*?\$\$?", re.S)
_CODE_FENCE = re.compile(r"```.*?```", re.S)
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_MDLINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NONWORD = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

# Parenthetical qualifiers in the syllabus, e.g. Tensor products *(later)*
_QUALIFIER = re.compile(r"\*\([^)]*\)\*")

# Maths symbols carry meaning in concept names. Deleting them collapses
# "sigma-algebras" to "algebra" and "Completeness of R" to "completeness of",
# so transliterate before stripping punctuation.
_SYMBOLS = {
    "ℝ": " R ", "ℂ": " C ", "ℕ": " N ", "ℤ": " Z ", "ℚ": " Q ",
    "α": " alpha ", "β": " beta ", "γ": " gamma ", "δ": " delta ",
    "ε": " epsilon ", "ζ": " zeta ", "η": " eta ", "θ": " theta ",
    "λ": " lambda ", "μ": " mu ", "ν": " nu ", "ξ": " xi ",
    "π": " pi ", "ρ": " rho ", "σ": " sigma ", "τ": " tau ",
    "φ": " phi ", "χ": " chi ", "ψ": " psi ", "ω": " omega ",
    "Γ": " Gamma ", "Δ": " Delta ", "Σ": " Sigma ", "Ω": " Omega ",
    "ℒ": " L ", "ℬ": " B ", "ℰ": " E ", "ℱ": " F ",
}
_SYMBOL_RE = re.compile("|".join(map(re.escape, _SYMBOLS)))

# An em/en dash in a concept name introduces a gloss, not part of the name.
_GLOSS_DASH = re.compile(r"\s*[—–]\s+.*$")


def transliterate(s: str) -> str:
    """Greek and blackboard-bold to words, accents folded to ASCII."""
    s = _SYMBOL_RE.sub(lambda m: _SYMBOLS[m.group()], s)
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


_STOP = frozenset({"the", "a", "an", "of", "and", "or", "in", "to", "for", "on", "with"})


def strip_markup(s: str) -> str:
    """Remove LaTeX, code fences and link syntax, keeping link display text."""
    s = _CODE_FENCE.sub(" ", s)
    s = _LATEX_INLINE.sub(" ", s)
    s = _WIKILINK.sub(r"\1", s)
    s = _MDLINK.sub(r"\1", s)
    return s


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z]{2,})")


def decamel(s: str) -> str:
    """StochasticProcesses -> Stochastic Processes, for Obsidian tag names."""
    return _CAMEL.sub(" ", s)


def normalise(s: str) -> str:
    """Lowercase, strip markup and punctuation, collapse whitespace."""
    s = transliterate(decamel(strip_markup(s))).lower()
    s = _NONWORD.sub(" ", s)
    return _WS.sub(" ", s).strip()


def singularise(s: str) -> str:
    """Crude plural stripping, adequate for maths and CS topic names."""
    out = []
    for w in s.split():
        if len(w) > 3 and w.endswith("ies"):
            out.append(w[:-3] + "y")
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            out.append(w[:-1])
        else:
            out.append(w)
    return " ".join(out)


def canon(s: str) -> str:
    """Canonical comparison key for a concept or note title."""
    k = singularise(normalise(_GLOSS_DASH.sub("", _QUALIFIER.sub("", s))))
    # Trim trailing filler ("completeness of" -> "completeness"), but only while
    # there is something before it: a bare stopword IS the name.
    while " " in k and k.rsplit(" ", 1)[-1] in _STOP:
        k = k.rsplit(" ", 1)[0]
    return k


def content_words(s: str) -> frozenset[str]:
    """Significant words of a canonical string, for overlap scoring."""
    return frozenset(w for w in canon(s).split() if w not in _STOP and len(w) > 2)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
