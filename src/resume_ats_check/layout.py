"""Where the text actually sits on the paper.

Page counts and text extraction both pass a PDF whose content runs off the sheet:
the characters stay in the content stream — extractable, counted, invisible — while
the printed page cuts them off. Only the glyph geometry shows it.
"""

from __future__ import annotations

from io import IOBase
from pathlib import Path
from typing import IO, NamedTuple, Sequence, cast

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTComponent, LTContainer

# A quarter inch is 18 PDF points. Check rendered character bounds on every edge.
MIN_EDGE_MARGIN_PT = 18.0


class TextPos(NamedTuple):
    """Character and page bounds in PDF points."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    page_x0: float
    page_y0: float
    page_x1: float
    page_y1: float


def text_positions(source: Path | IO[bytes]) -> list[TextPos]:
    """Character bounds, including the actual width of each printed glyph."""
    positions: list[TextPos] = []
    pdf_source = str(source) if isinstance(source, Path) else cast(IOBase, source)
    for index, page in enumerate(extract_pages(pdf_source)):
        pending: list[LTComponent] = [page]
        while pending:
            item = pending.pop()
            if isinstance(item, LTChar):
                if item.get_text().strip():
                    positions.append(TextPos(index, *item.bbox, *page.bbox))
            elif isinstance(item, LTContainer):
                pending.extend(item)
    return positions


def edge_problems(
    positions: Sequence[TextPos], *, margin: float = MIN_EDGE_MARGIN_PT
) -> list[str]:
    """Text sitting outside the printable area on any side of a page.

    Stretching ``\\textheight`` past the paper is the classic way to "fit one page":
    the page count drops to 1 and the bottom section silently prints off the sheet.
    """
    problems: list[str] = []
    below = [p for p in positions if p.y0 < p.page_y0 + margin]
    if below:
        worst = min(below, key=lambda p: p.y0 - p.page_y0)
        problems.append(
            f"{len(below)} character(s) fall below the {margin:.0f}pt bottom margin "
            f"(lowest: y={worst.y0:.1f}pt on page {worst.page + 1}) — "
            "cut content rather than stretching \\textheight"
        )
    above = [p for p in positions if p.y1 > p.page_y1 - margin]
    if above:
        worst = max(above, key=lambda p: p.y1 - p.page_y1)
        problems.append(
            f"{len(above)} character(s) rise above the {margin:.0f}pt top margin "
            f"(highest: y={worst.y1:.1f}pt on page "
            f"{worst.page + 1}) — raise \\topmargin"
        )
    left = [p for p in positions if p.x0 < p.page_x0 + margin]
    if left:
        worst = min(left, key=lambda p: p.x0 - p.page_x0)
        problems.append(
            f"{len(left)} character(s) fall outside the {margin:.0f}pt left margin "
            f"(leftmost: x={worst.x0:.1f}pt on page {worst.page + 1})"
        )
    right = [p for p in positions if p.x1 > p.page_x1 - margin]
    if right:
        worst = max(right, key=lambda p: p.x1 - p.page_x1)
        problems.append(
            f"{len(right)} character(s) fall outside the {margin:.0f}pt right margin "
            f"(rightmost: x={worst.x1:.1f}pt on page {worst.page + 1})"
        )
    return problems
