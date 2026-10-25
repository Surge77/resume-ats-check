"""Glued-word detection and the LaTeX source constructs that cause it."""

from __future__ import annotations

import pytest

from resume_ats_check import glue

_GOOD_PREAMBLE = "\n".join([
    r"\documentclass{article}",
    r"\input{glyphtounicode}",
    r"\pdfgentounicode=1",
    r"\pdfinterwordspaceon",
    r"\begin{document}",
])


def _doc(body: str, preamble: str = _GOOD_PREAMBLE) -> str:
    return f"{preamble}\n{body}\n\\end{{document}}"


# ------------------------------ source_problems ----------------------------- #


def test_a_complete_preamble_and_plain_body_is_clean():
    assert glue.source_problems(_doc("Built a pipeline --- Python, React")) == []


@pytest.mark.parametrize(
    "missing, fragment",
    [
        (r"\pdfinterwordspaceon", "pdfinterwordspaceon"),
        (r"\pdfgentounicode=1", "pdfgentounicode"),
        (r"\input{glyphtounicode}", "glyphtounicode"),
    ],
)
def test_flags_each_missing_text_layer_directive(missing, fragment):
    preamble = _GOOD_PREAMBLE.replace(missing + "\n", "")
    problems = glue.source_problems(_doc("text", preamble))
    assert len(problems) == 1 and fragment in problems[0]


def test_a_directive_that_only_appears_in_a_comment_does_not_count():
    preamble = _GOOD_PREAMBLE.replace(r"\pdfinterwordspaceon", r"% \pdfinterwordspaceon")
    assert any("pdfinterwordspaceon" in p for p in glue.source_problems(_doc("x", preamble)))


@pytest.mark.parametrize("snippet", [r"A $|$ B", r"end, $\sim$12 s", r"Name {\small$\nearrow$}"])
def test_flags_a_math_symbol_used_as_text(snippet):
    problems = glue.source_problems(_doc(snippet))
    assert len(problems) == 1 and "math-font symbol" in problems[0]


def test_counts_every_math_symbol_used_as_text():
    [problem] = glue.source_problems(_doc(r"A $|$ B $|$ C $\sim$1"))
    assert "$|$ ×2" in problem and r"$\sim$ ×1" in problem


def test_real_math_is_not_a_symbol_used_as_text():
    assert glue.source_problems(_doc(r"runs in $O(n \log n)$ time, $x^2$")) == []


def test_math_in_the_preamble_is_ignored():
    """Bullet glyphs are defined in preamble macros; only the body is typeset text."""
    preamble = _GOOD_PREAMBLE.replace(r"\begin{document}", "\\newcommand{\\b}{$\\bullet$}\n\\begin{document}")
    assert glue.source_problems(_doc("text", preamble)) == []


# ------------------------------- glued_words -------------------------------- #


def test_finds_words_fused_with_a_neighbour():
    source = _doc(r"Walchand Institute of Technology \hfill Solapur. React \hfill 2026")
    spaced = "walchand institute of technologysolapur. react2026"
    assert glue.glued_words(source, spaced) == ["react2026", "technologysolapur"]


def test_a_font_switch_that_lost_its_spaces_is_found():
    source = _doc(r"falsification criteria \emph{before} computing anything")
    spaced = "falsification criteriabeforecomputing anything"
    assert glue.glued_words(source, spaced) == ["criteriabeforecomputing"]


def test_a_cleanly_spaced_layer_has_no_glued_words():
    source = _doc(r"Python, \emph{pandas} and pytest")
    assert glue.glued_words(source, "python, pandas and pytest") == []


def test_a_word_inside_a_longer_source_word_is_not_glue():
    """"test" also sits inside "pytest", but it is printed on its own too."""
    source = _doc("pytest and a unit test")
    assert glue.glued_words(source, "pytest and a unit test") == []


@pytest.mark.parametrize(
    "body, spaced",
    [
        ("a 7-endpoint fallback", "a 7-endpoint fallback"),
        ("macro-F1 of 0.46", "macro-f1 of 0.46"),
        (r"DevT{}rends platform", "devtrends platform"),
        ("github.com/Surge77 profile", "github.com/surge77 profile"),
    ],
)
def test_hyphenated_and_brace_broken_words_are_not_glue(body, spaced):
    assert glue.glued_words(_doc(body), spaced) == []


def test_glue_after_a_hyphen_is_still_found():
    source = _doc(r"scikit-learn \emph{pandas}")
    assert glue.glued_words(source, "scikit-learnpandas") == ["learnpandas"]


def test_a_kerning_split_is_not_reported_as_glue():
    """"F rontend" is the opposite failure; `kerning_splits` owns it."""
    source = _doc("Frontend work")
    assert glue.glued_words(source, "f rontend work") == []
