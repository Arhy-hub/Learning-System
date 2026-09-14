"""LaTeX to Unicode, so maths is readable in a terminal.

opencode's TUI is @opentui (SolidJS in the terminal) and has no maths renderer;
KaTeX ships only in its web bundle, and the plugin API exposes no hook that can
touch assistant text before it is drawn. So `$\\forall \\epsilon > 0$` reaches the
screen verbatim.

This converts what Unicode can express and leaves the rest legible rather than
mangled. It is a display transform only: pages in the brain keep their LaTeX,
because Obsidian and `opencode web` both render it properly.

    >>> to_unicode(r"$\\forall \\epsilon>0\\ \\exists N: |x_n - L| < \\epsilon$")
    '∀ε>0 ∃N: |xₙ - L| < ε'
"""
from __future__ import annotations

import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "pi": "π", "varpi": "ϖ", "rho": "ρ", "varrho": "ϱ", "sigma": "σ",
    "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "ϕ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
}

SYMBOLS = {
    # relations
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃", "cong": "≅",
    "propto": "∝", "ll": "≪", "gg": "≫", "asymp": "≍", "doteq": "≐",
    # operators
    "times": "×", "div": "÷", "pm": "±", "mp": "∓", "cdot": "⋅",
    "ast": "∗", "star": "⋆", "circ": "∘", "bullet": "∙",
    "oplus": "⊕", "ominus": "⊖", "otimes": "⊗", "odot": "⊙",
    "wedge": "∧", "vee": "∨", "land": "∧", "lor": "∨", "neg": "¬", "lnot": "¬",
    # big operators
    "sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬",
    "iiint": "∭", "oint": "∮", "bigcup": "⋃", "bigcap": "⋂",
    "bigoplus": "⨁", "bigotimes": "⨂", "bigvee": "⋁", "bigwedge": "⋀",
    # sets
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆",
    "supset": "⊃", "supseteq": "⊇", "subsetneq": "⊊", "supsetneq": "⊋",
    "cup": "∪", "cap": "∩", "setminus": "∖", "emptyset": "∅",
    "varnothing": "∅", "complement": "∁",
    # logic
    "forall": "∀", "exists": "∃", "nexists": "∄", "therefore": "∴",
    "because": "∵", "top": "⊤", "bot": "⊥", "vdash": "⊢", "models": "⊨",
    # arrows
    "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "Leftrightarrow": "⇔",
    "iff": "⟺", "implies": "⟹", "impliedby": "⟸", "mapsto": "↦",
    "hookrightarrow": "↪", "uparrow": "↑", "downarrow": "↓",
    "longrightarrow": "⟶", "xrightarrow": "→", "rightsquigarrow": "⇝",
    # analysis
    "infty": "∞", "partial": "∂", "nabla": "∇", "surd": "√", "angle": "∠",
    "perp": "⊥", "parallel": "∥", "triangle": "△", "square": "□",
    "aleph": "ℵ", "hbar": "ℏ", "ell": "ℓ", "wp": "℘", "Re": "ℜ", "Im": "ℑ",
    # punctuation and spacing
    "ldots": "…", "cdots": "⋯", "vdots": "⋮", "ddots": "⋱", "dots": "…",
    "quad": "  ", "qquad": "    ", ",": " ", ";": " ", ":": " ", "!": "",
    "langle": "⟨", "rangle": "⟩", "lVert": "‖", "rVert": "‖", "|": "‖",
    "lfloor": "⌊", "rfloor": "⌋", "lceil": "⌈", "rceil": "⌉",
    "prime": "′", "degree": "°", "checkmark": "✓",
    "mid": "∣", "nmid": "∤", "colon": ":", "backslash": "\\",
}

BLACKBOARD = {"R": "ℝ", "C": "ℂ", "N": "ℕ", "Z": "ℤ", "Q": "ℚ", "H": "ℍ",
              "P": "ℙ", "E": "𝔼", "F": "𝔽", "A": "𝔸", "K": "𝕂", "1": "𝟙"}

CALLIGRAPHIC = {"A": "𝒜", "B": "ℬ", "C": "𝒞", "D": "𝒟", "E": "ℰ", "F": "ℱ",
                "G": "𝒢", "H": "ℋ", "I": "ℐ", "J": "𝒥", "K": "𝒦", "L": "ℒ",
                "M": "ℳ", "N": "𝒩", "O": "𝒪", "P": "𝒫", "Q": "𝒬", "R": "ℛ",
                "S": "𝒮", "T": "𝒯", "U": "𝒰", "V": "𝒱", "W": "𝒲", "X": "𝒳",
                "Y": "𝒴", "Z": "𝒵"}

FRAKTUR = {"A": "𝔄", "B": "𝔅", "C": "ℭ", "D": "𝔇", "E": "𝔈", "F": "𝔉",
           "G": "𝔊", "H": "ℌ", "I": "ℑ", "M": "𝔐", "N": "𝔑", "R": "ℜ",
           "S": "𝔖", "Z": "ℨ", "a": "𝔞", "b": "𝔟", "m": "𝔪", "p": "𝔭"}

SUPERSCRIPT = {**{c: s for c, s in zip("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾", strict=True)},
               **{c: s for c, s in zip(
                   "abcdefghijklmnoprstuvwxyz",
                   "ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ", strict=True)},
               "T": "ᵀ", "n": "ⁿ", "i": "ⁱ", " ": " ", ".": "˙"}

SUBSCRIPT = {**{c: s for c, s in zip("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎", strict=True)},
             **{c: s for c, s in zip("aehijklmnoprstuvx",
                                     "ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ", strict=True)},
             " ": " ", ",": ","}

# Combining marks, applied after the base character.
ACCENTS = {"hat": "\u0302", "bar": "\u0304", "overline": "\u0304",
           "tilde": "\u0303", "vec": "\u20d7", "dot": "\u0307",
           "ddot": "\u0308", "check": "\u030c", "widehat": "\u0302",
           "widetilde": "\u0303"}

# Words that read fine as words.
OPERATORS = ("lim", "limsup", "liminf", "sup", "inf", "max", "min", "arg",
             "det", "dim", "ker", "deg", "gcd", "lcm", "exp", "log", "ln",
             "sin", "cos", "tan", "arcsin", "arccos", "arctan", "sinh",
             "cosh", "tanh", "mod", "bmod", "pmod", "Pr", "tr", "rank",
             "span", "diag", "sgn", "Var", "Cov", "supp")

_OPERATOR_RE = re.compile(
    r"\\(" + "|".join(sorted(OPERATORS, key=len, reverse=True)) + r")(?![A-Za-z])")

_DELIM = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.S)
_CMD = re.compile(r"\\([A-Za-z]+)")
_BRACED = re.compile(r"\{([^{}]*)\}")


def _script(body: str, table: dict) -> str | None:
    """Render a sub/superscript, or None if Unicode cannot express it."""
    if not body:
        return ""
    out = []
    for ch in body:
        if ch not in table:
            return None
        out.append(table[ch])
    return "".join(out)


def _apply_scripts(s: str) -> str:
    """x^2 -> x², a_{ij} -> a_ij subscripted where possible."""
    def repl(m):
        marker, braced, bare = m.group(1), m.group(2), m.group(3)
        body = braced if braced is not None else bare
        table = SUPERSCRIPT if marker == "^" else SUBSCRIPT
        got = _script(body, table)
        if got is not None:
            return got
        # Unicode has no form for this; keep it readable in LaTeX shape.
        return f"{marker}({body})" if len(body) > 1 else f"{marker}{body}"
    return re.sub(r"([\^_])(?:\{([^{}]*)\}|(\w))", repl, s)


def _apply_fonts(s: str) -> str:
    for cmd, table in (("mathbb", BLACKBOARD), ("Bbb", BLACKBOARD),
                       ("mathcal", CALLIGRAPHIC), ("mathfrak", FRAKTUR)):
        def repl(m, t=table):
            body = m.group(1)
            return "".join(t.get(c, c) for c in body)
        s = re.sub(r"\\" + cmd + r"\{([^{}]*)\}", repl, s)
        s = re.sub(r"\\" + cmd + r"\s*(\w)", lambda m, t=table: t.get(m.group(1), m.group(1)), s)
    return s


def _apply_accents(s: str) -> str:
    for cmd, mark in ACCENTS.items():
        s = re.sub(r"\\" + cmd + r"\{([^{}]*)\}",
                   lambda m, k=mark: "".join(c + k for c in m.group(1)) or "", s)
        s = re.sub(r"\\" + cmd + r"\s*(\w)", lambda m, k=mark: m.group(1) + k, s)
    return s


def _apply_fracs(s: str) -> str:
    """Nested fractions resolve inside-out; parenthesise only when needed."""
    simple = {("1", "2"): "½", ("1", "3"): "⅓", ("2", "3"): "⅔",
              ("1", "4"): "¼", ("3", "4"): "¾", ("1", "8"): "⅛"}
    pat = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
    for _ in range(6):
        new = pat.sub(lambda m: simple.get((m.group(1).strip(), m.group(2).strip()))
                      or f"{_wrap(m.group(1))}/{_wrap(m.group(2))}", s)
        if new == s:
            break
        s = new
    return s


def _wrap(x: str) -> str:
    x = x.strip()
    return x if re.fullmatch(r"[\w.²³¹⁰⁴-⁹₀-₉α-ωΑ-Ω]+", x) else f"({x})"


def _apply_sqrt(s: str) -> str:
    s = re.sub(r"\\sqrt\s*\[\s*3\s*\]\s*\{([^{}]*)\}", lambda m: f"∛{_wrap(m.group(1))}", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", lambda m: f"√{_wrap(m.group(1))}", s)
    s = re.sub(r"\\sqrt\s*(\w)", lambda m: f"√{m.group(1)}", s)
    return s


def convert(expr: str) -> str:
    """Convert one LaTeX expression (no $ delimiters) to Unicode."""
    s = expr
    # Size modifiers, but not \bigcup / \bigcap / \bigoplus: the lookahead stops
    # \big eating the front of a big operator.
    s = re.sub(r"\\(?:left|right|biggl|biggr|bigl|bigr|Bigl|Bigr|bigg|Bigg|big|Big)"
               r"(?![a-zA-Z])\s*", "", s)
    s = re.sub(r"\\(?:displaystyle|textstyle|scriptstyle|limits|nolimits)\b", "", s)
    s = re.sub(r"\\(?:text|mathrm|mathsf|mathtt|operatorname|textbf|mathbf|textit|mathit)\s*\{([^{}]*)\}",
               r"\1", s)
    s = _apply_fonts(s)
    s = _apply_fracs(s)
    s = _apply_sqrt(s)

    # One alternation pass, not one substitution per name: replacing \max first
    # would turn "\arg\max" into "\argmax" and strand the \arg. \b is no use
    # here either, since these are usually followed by "_", a word character.
    s = _OPERATOR_RE.sub(r"\1", s)

    def sym(m):
        name = m.group(1)
        return GREEK.get(name) or SYMBOLS.get(name) or m.group(0)
    s = _CMD.sub(sym, s)
    # Accents run after symbols so \hat{\theta} decorates θ, not the letters
    # of the word "theta".
    s = _apply_accents(s)

    # An escaped brace is content; a bare brace is grouping. Park the former
    # out of reach before the grouping braces are stripped.
    s = s.replace("\\{", "\x00").replace("\\}", "\x01")
    s = re.sub(r"\\([%&#_$|,;:!])", lambda m: SYMBOLS.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\ ", " ", s)         # \  is a thin space
    s = _apply_scripts(s)
    s = _BRACED.sub(r"\1", s)          # leftover grouping braces
    s = s.replace("\x00", "{").replace("\x01", "}")
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def to_unicode(text: str, strip_delimiters: bool = True) -> str:
    """Convert every LaTeX span in `text`. Prose outside maths is untouched."""
    if not text:
        return text
    if "$" not in text and "\\" not in text:
        return text

    def repl(m):
        body = m.group(1) if m.group(1) is not None else m.group(2)
        out = convert(body)
        return out if strip_delimiters else f"${out}$"

    out = _DELIM.sub(repl, text)
    if "\\" in out:
        # Bare commands written without $ delimiters.
        out = _CMD.sub(lambda m: GREEK.get(m.group(1)) or SYMBOLS.get(m.group(1))
                       or m.group(0), out)
    return out


def has_latex(text: str) -> bool:
    return bool(text) and bool(_DELIM.search(text) or _CMD.search(text))
