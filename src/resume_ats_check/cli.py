"""Command line: ``resume-ats-check resume.pdf [--tex resume.tex] [--keywords ...]``.

Exit 0 means the PDF passed every check, 1 means it has problems, 2 means bad input.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import text
from .verify import DEFAULT_MAX_PAGES, verify_pdf


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resume-ats-check",
        description="Check that a resume PDF reads correctly to an applicant tracking system.",
    )
    parser.add_argument("pdf", type=Path, help="the resume PDF to check")
    parser.add_argument("--tex", type=Path, default=None,
                        help="LaTeX source; enables the word-coverage check")
    parser.add_argument("--keywords", default="",
                        help="comma-separated terms that must appear verbatim")
    parser.add_argument("--email", default=None,
                        help="the address the contact block must extract as")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                        help=f"page limit (default {DEFAULT_MAX_PAGES}; 0 disables)")
    return parser


def _force_utf8_output() -> None:
    """Windows pipes default to cp1252, which turns the em dashes in every message
    into mojibake once a UTF-8 terminal (Git Bash, CI logs) decodes them."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8_output()
    args = _parser().parse_args(argv)
    if not args.pdf.is_file():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 2
    tex_source = args.tex.read_text("utf-8") if args.tex is not None else None
    required = [k.strip() for k in args.keywords.split(",") if k.strip()]
    try:
        problems = verify_pdf(
            args.pdf, tex_source, required=required, expected_email=args.email,
            max_pages=args.max_pages or None,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    splits = text.kerning_splits(text.extract_text(args.pdf))
    if splits:
        print(f"note: {len(splits)} word(s) split by kerning: {', '.join(splits[:10])}")
    if not problems:
        print("PASS — the text layer reads cleanly")
        return 0
    print(f"FAIL — {len(problems)} problem(s):")
    for problem in problems:
        print(f"  - {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
