"""One verdict for a resume PDF: every reason it is not ready to submit."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from . import glue, layout, text

DEFAULT_MAX_PAGES = 1
MIN_TEXT_CHARS = 1500
WORD_COVERAGE_FLOOR = 0.98


def verify_pdf(
    pdf: Path,
    tex_source: str | None = None,
    *,
    required: Sequence[str] = (),
    expected_email: str | None = None,
    max_pages: int | None = DEFAULT_MAX_PAGES,
) -> list[str]:
    """Every reason this PDF is not submission-ready. Empty list means clean.

    ``tex_source`` is optional: without it the word-coverage check is skipped, since
    there is nothing to compare the text layer against.
    """
    problems: list[str] = []
    pages = text.count_pages(pdf)
    if max_pages is not None and pages > max_pages:
        problems.append(f"{pages} pages — must be {max_pages}")
    extracted = text.extract_text(pdf)
    if len(extracted) < MIN_TEXT_CHARS:
        problems.append(
            f"text layer is only {len(extracted)} chars (<{MIN_TEXT_CHARS}) — "
            "the PDF may have no machine-readable text"
        )
    problems.extend(layout.edge_problems(layout.text_positions(pdf)))
    problems.extend(text.contact_problems(extracted, expected_email=expected_email))
    if tex_source is not None:
        coverage, missing = text.word_coverage(tex_source, extracted)
        if coverage < WORD_COVERAGE_FLOOR:
            sample = ", ".join(missing[:8])
            problems.append(
                f"word coverage {coverage:.1%} (<{WORD_COVERAGE_FLOOR:.0%}); missing: {sample}"
            )
        glued = glue.glued_words(tex_source, text.haystacks(extracted)[0])
        if glued:
            problems.append(
                "words glued together in the text layer (an ATS reads each as one "
                "token): " + ", ".join(glued[:8])
            )
        problems.extend(glue.source_problems(tex_source))
    absent = text.missing_keywords(extracted, required)
    if absent:
        problems.append("required keywords absent: " + ", ".join(absent))
    # Escalated from the advisory `kerning_splits` warning: a split anywhere on the
    # page is cosmetic, but a split through a keyword the posting asks for costs the
    # exact match the keyword was there for.
    split = text.split_keywords(extracted, required)
    if split:
        problems.append(
            "required keywords broken by a kerning split (an exact-match ATS will "
            "miss these): " + ", ".join(split)
        )
    return problems
