"""Check that a resume PDF reads correctly to an applicant tracking system."""

from .glue import glued_words, source_problems
from .layout import edge_problems, text_positions
from .text import (
    contact_problems,
    count_pages,
    extract_text,
    kerning_splits,
    missing_keywords,
    normalize_extracted,
    split_keywords,
    word_coverage,
)
from .verify import verify_pdf

__all__ = [
    "contact_problems",
    "count_pages",
    "edge_problems",
    "extract_text",
    "glued_words",
    "kerning_splits",
    "missing_keywords",
    "normalize_extracted",
    "source_problems",
    "split_keywords",
    "text_positions",
    "verify_pdf",
    "word_coverage",
]
