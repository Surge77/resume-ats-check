"""Words the text layer runs together, and the LaTeX source that causes it.

A PDF stores no space characters: extractors infer word breaks from glyph gaps, and
pypdf infers none at a font switch, a right-aligned ``\\hfill`` column, or a glyph
from the math font. A resume can render perfectly and extract as "React2026",
"TechnologySolapur" and "criteriabeforecomputing". A substring-based keyword check
passes all of those, because "react" is inside "react2026".
"""

from __future__ import annotations

import re

from .text import tex_body, typeset_text

_MIN_WORD_LEN = 4
_COMMENT_RE = re.compile(r"(?<!\\)%.*")

# Each one keeps the text layer machine-readable; losing any of them is silent.
_REQUIRED_DIRECTIVES = (
    (re.compile(r"\\input\{glyphtounicode\}"),
     r"\input{glyphtounicode} — glyphs lose their Unicode mapping"),
    (re.compile(r"\\pdfgentounicode\s*=\s*1"),
     r"\pdfgentounicode=1 — glyphs lose their Unicode mapping"),
    (re.compile(r"\\pdfinterwordspaceon\b"),
     r"\pdfinterwordspaceon — extractors glue words at font switches and "
     r"right-aligned columns (TechnologySolapur)"),
)

# A lone symbol in inline math ($|$, $\sim$, $\nearrow$) is set from the math font.
# pypdf drops the word break before it, and it extracts as a lookalike codepoint
# (∼ U+223C, not ~). Real math like $O(n \log n)$ has more than one token.
# For $-$ write a plain hyphen: \textminus is no fix, under OT1 it extracts as "=".
_MATH_SYMBOL_RE = re.compile(r"(?<!\\)\$\s*(\\[A-Za-z]+|[^\s$\\\w])\s*\$")
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9.+#-]*")
_SEPARATOR_RE = re.compile(r"[-./+#]+")


def source_problems(tex_source: str) -> list[str]:
    """pdfLaTeX source constructs that damage the text layer. Empty means clean."""
    uncommented = _COMMENT_RE.sub(" ", tex_source)
    problems = [
        f"missing {why}"
        for pattern, why in _REQUIRED_DIRECTIVES
        if pattern.search(uncommented) is None
    ]
    counts: dict[str, int] = {}
    for match in _MATH_SYMBOL_RE.finditer(tex_body(tex_source)):
        symbol = f"${match.group(1)}$"
        counts[symbol] = counts.get(symbol, 0) + 1
    if counts:
        listed = ", ".join(f"{symbol} ×{n}" for symbol, n in counts.items())
        problems.append(
            f"math-font symbol used as text: {listed} — pypdf glues it to the "
            "preceding word; use a text glyph (---, --, -) or words instead"
        )
    return problems


def glued_words(tex_source: str, spaced: str) -> list[str]:
    """Extracted tokens that fuse a source word with its neighbour ("react2026").

    ``spaced`` is the normalized, lowercased text layer (``text.haystacks``). A
    source word only counts as glued when it never appears as a token of its own —
    so "test" inside "pytest" is fine wherever "test" is also printed alone.
    """
    tokens = {t.strip(".-") for t in _TOKEN_RE.findall(spaced)}
    # A hyphen or dot is a visible separator: "7-endpoint" and "macro-f1" are
    # written that way. Only a fusion with no separator at all is glue.
    parts = {p for t in tokens for p in _SEPARATOR_RE.split(t) if p}
    # Digits stay attached here: "Surge77" is one word, not "surge" glued to "77".
    pattern = rf"[A-Za-z][A-Za-z0-9.+#-]{{{_MIN_WORD_LEN - 1},}}"
    words = {w.lower().strip(".-") for w in re.findall(pattern, typeset_text(tex_source))}
    glued: set[str] = set()
    for word in words:
        if word in tokens or word in parts:
            continue
        glued.update(p for p in parts if word in p and p != word)
    return sorted(glued)
