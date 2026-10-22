"""Tests for resume PDF verification.

No TeX installation required: fixture PDFs are synthesized in memory with pypdf.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from resume_ats_check import layout, verify
from resume_ats_check import text as pdftext


def _pdf_bytes(pages: int) -> BytesIO:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf


def _text_pdf(*, x: int, y: int, text: str = "Clipped text") -> BytesIO:
    """A real text stream, so geometry tests exercise PDF extraction too."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf {x} {y} Td ({text}) Tj ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    buf = BytesIO()
    writer.write(buf)
    buf.seek(0)
    return buf


# --------------------------- normalize_extracted --------------------------- #


def test_normalize_rejoins_words_broken_across_lines():
    assert "authentication" in pdftext.normalize_extracted("authen-\ntication")


def test_normalize_strips_known_icon_artifacts():
    assert pdftext.normalize_extracted("/github GitHub") == "GitHub"


def test_normalize_keeps_slashed_words_that_are_not_icons():
    """A loose /\\w+ rule would delete the React in TypeScript/React."""
    assert "React" in pdftext.normalize_extracted("TypeScript/React")


def test_normalize_removes_junk_codepoints():
    assert pdftext.normalize_extracted("♂phone ↗") == "phone"


# ------------------------------- count_pages ------------------------------- #


@pytest.mark.parametrize("pages", [1, 2, 5])
def test_count_pages_reads_stream(pages):
    assert pdftext.count_pages(_pdf_bytes(pages)) == pages


# ---------------------------- contact_problems ----------------------------- #


def test_contact_problems_silent_on_clean_header():
    text = "Jane Doe +1 555 010 0199  jane.doe@example.com  LinkedIn"
    assert pdftext.contact_problems(text) == []


def test_contact_problems_detects_glued_email():
    text = "+1 555 010 0199 /envelopejane.doe@example.com"
    assert any("glued" in p for p in pdftext.contact_problems(text))


def test_contact_problems_detects_the_verbatim_shipped_defect():
    """The shape of a real damaged header: icon names fused into phone and email."""
    text = "♂phone+1 555 010 0199 /envel⌢pejane.doe@example.com /linkedinLinkedIn"
    problems = pdftext.contact_problems(text, expected_email="jane.doe@example.com")
    assert any("glued" in p for p in problems)
    assert any("expected" in p for p in problems)


def test_contact_problems_reports_absent_email_and_phone():
    assert len(pdftext.contact_problems("Jane Doe")) == 2


# ------------------------------ tex_body_words ----------------------------- #


def test_tex_body_words_ignores_the_preamble():
    src = r"\usepackage{fancyhdr}" + "\n" + r"\begin{document}" + "\nKafka\n"
    assert "fancyhdr" not in pdftext.tex_body_words(src)


def test_tex_body_words_strips_macro_names():
    """Without the macro strip, \\hfill masquerades as the word 'fill'."""
    words = pdftext.tex_body_words(r"\begin{document}" + "\n" + r"a \hfill b Redis")
    assert "fill" not in words
    assert "redis" in words


def test_tex_body_words_drops_environment_names_and_options():
    src = r"\begin{document}" + "\n" + r"\begin{itemize}[leftmargin=0.15in, nosep]Kafka"
    assert pdftext.tex_body_words(src) == {"kafka"}


def test_tex_body_words_rejects_a_source_with_no_document_body():
    """Silently falling back to the preamble would report phantom missing words."""
    with pytest.raises(ValueError, match="begin"):
        pdftext.tex_body_words(r"\usepackage{fancyhdr}")


def test_tex_body_words_drops_href_urls():
    src = r"\begin{document}" + "\n" + r"\href{https://github.com/Surge77}{DevTrends}"
    words = pdftext.tex_body_words(src)
    assert "devtrends" in words
    assert not any("github" in w for w in words)


# ------------------------------ word_coverage ------------------------------ #


def test_word_coverage_perfect_when_all_words_present():
    src = r"\begin{document}" + "\nKafka Redis PostgreSQL"
    assert pdftext.word_coverage(src, "Kafka Redis PostgreSQL") == (1.0, [])


def test_word_coverage_reports_dropped_words():
    src = r"\begin{document}" + "\nKafka Redis PostgreSQL Testcontainers"
    coverage, missing = pdftext.word_coverage(src, "Kafka Redis")
    assert coverage < 1.0
    assert "testcontainers" in missing


def test_word_coverage_tolerates_kerning_splits():
    """The extractor really does return "F rontend" for "Frontend"."""
    src = r"\begin{document}" + "\nFrontend"
    coverage, _ = pdftext.word_coverage(src, "F rontend")
    assert coverage == 1.0


def test_word_coverage_of_empty_body_is_perfect():
    assert pdftext.word_coverage(r"\begin{document}", "anything") == (1.0, [])


# ----------------------------- missing_keywords ---------------------------- #


def test_missing_keywords_is_case_insensitive():
    assert pdftext.missing_keywords("Built with node.js", ["Node.js"]) == []


def test_missing_keywords_matches_across_a_line_break():
    assert pdftext.missing_keywords("Postgre-\nSQL tuning", ["PostgreSQL"]) == []


def test_missing_keywords_tolerates_kerning_splits():
    assert pdftext.missing_keywords("F rontend: React.js", ["Frontend"]) == []


def test_missing_keywords_lists_absent_terms():
    assert pdftext.missing_keywords("Python only", ["Python", "GraphQL"]) == ["GraphQL"]


# ------------------------------ kerning_splits ----------------------------- #


def test_kerning_splits_reports_broken_words():
    assert pdftext.kerning_splits("F rontend and T esting") == ["F rontend", "T esting"]


def test_kerning_splits_ignores_real_single_letter_words():
    """'a clean design' is English, not a split."""
    assert pdftext.kerning_splits("a clean design I built") == []


# ------------------------------- verify_pdf -------------------------------- #


def test_verify_flags_multi_page_output(tmp_path):
    pdf = tmp_path / "two.pdf"
    pdf.write_bytes(_pdf_bytes(2).getvalue())
    assert any("2 pages" in p for p in verify.verify_pdf(pdf, r"\begin{document}"))


def test_verify_flags_empty_text_layer(tmp_path):
    """A blank page passes the page check but is worthless to an ATS."""
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(_pdf_bytes(1).getvalue())
    assert any("text layer" in p for p in verify.verify_pdf(pdf, r"\begin{document}"))


# ---------------------- keyword_state / split_keywords --------------------- #


@pytest.mark.parametrize(
    "text,keyword,expected",
    [
        ("Built the Frontend", "frontend", "present"),
        ("Built the F rontend", "Frontend", "split"),
        ("Built the backend", "Frontend", "absent"),
        ("Postgre-\nSQL tuning", "PostgreSQL", "present"),
    ],
)
def test_keyword_state_separates_split_from_absent(text, keyword, expected):
    spaced, packed = pdftext.haystacks(text)
    assert pdftext.keyword_state(spaced, packed, keyword) == expected


def test_split_keywords_reports_only_the_broken_ones():
    text = "F rontend work on React"
    assert pdftext.split_keywords(text, ["Frontend", "React", "Vue"]) == ["Frontend"]


def test_a_split_keyword_is_not_also_reported_as_missing():
    """The content IS on the page — reporting it twice would read as two defects."""
    assert pdftext.missing_keywords("F rontend work", ["Frontend"]) == []


def test_verify_escalates_a_split_that_lands_on_a_required_keyword(tmp_path, monkeypatch):
    """A split anywhere is cosmetic; a split through a keyword the posting asks for
    costs the exact match the whole tailoring pass was for."""
    pdf = tmp_path / "one.pdf"
    pdf.write_bytes(_pdf_bytes(1).getvalue())
    monkeypatch.setattr(pdftext, "extract_text", lambda _: "x" * 2000 + " F rontend React")
    problems = verify.verify_pdf(pdf, r"\begin{document}", required=["Frontend", "React"])
    assert any("kerning split" in p and "Frontend" in p for p in problems)
    assert not any("React" in p for p in problems)


# ------------------------------ edge_problems ------------------------------ #


def _pos(y, *, size=10.0, page=0, height=792.0, x=40.0, width=10.0):
    return layout.TextPos(
        page=page, x0=x, y0=y, x1=x + width, y1=y + size,
        page_x0=0.0, page_y0=0.0, page_x1=612.0, page_y1=height,
    )


def test_edge_problems_silent_when_every_line_is_inside_the_printable_area():
    assert layout.edge_problems([_pos(720), _pos(400), _pos(60)]) == []


def test_edge_problems_empty_page_is_clean():
    assert layout.edge_problems([]) == []


def test_edge_problems_flags_a_line_below_the_bottom_margin():
    problems = layout.edge_problems([_pos(400), _pos(8)])
    assert len(problems) == 1
    assert "bottom" in problems[0]


def test_edge_problems_flags_text_pushed_clean_off_the_sheet():
    """The 2026-09-18 IBM build put the Education block at y = -12pt and still
    reported one page, so the page-count gate passed on an unreadable resume."""
    problems = layout.edge_problems([_pos(-12.1)])
    assert problems and "-12.1" in problems[0]


def test_edge_problems_reports_one_problem_per_edge():
    problems = layout.edge_problems([_pos(5), _pos(2), _pos(-1)])
    assert len(problems) == 1
    assert "3 character" in problems[0]


def test_edge_problems_flags_a_heading_running_off_the_top():
    assert layout.edge_problems([_pos(780, size=24)])


def test_edge_problems_uses_font_size_at_the_top_edge():
    """A baseline can clear the margin while the capitals above it do not."""
    assert layout.edge_problems([_pos(765, size=24)])
    assert layout.edge_problems([_pos(765, size=4)]) == []


def test_edge_problems_margin_is_tunable():
    assert layout.edge_problems([_pos(30)]) == []
    assert layout.edge_problems([_pos(30)], margin=40)


def test_edge_problems_names_the_page_it_found_the_overflow_on():
    problems = layout.edge_problems([_pos(-5, page=1)])
    assert "page 2" in problems[0]


def test_verify_fails_a_pdf_whose_text_runs_off_the_page(tmp_path, monkeypatch):
    """Guards the exact hole the page-count rule left: one page, text off the sheet."""
    pdf = tmp_path / "one.pdf"
    pdf.write_bytes(_text_pdf(x=40, y=10).getvalue())
    monkeypatch.setattr(pdftext, "extract_text", lambda _: "x" * 2000)
    problems = verify.verify_pdf(pdf, r"\begin{document}")
    assert any("bottom" in p for p in problems)


@pytest.mark.parametrize(
    "x,y,edge",
    [
        (5, 400, "left"),
        (580, 400, "right"),
        (40, 10, "bottom"),
        (40, 785, "top"),
    ],
)
def test_real_pdf_text_outside_each_edge_is_detected(x, y, edge):
    problems = layout.edge_problems(layout.text_positions(_text_pdf(x=x, y=y)))
    assert any(edge in problem for problem in problems)


def test_real_pdf_text_inside_all_edges_is_clean():
    assert layout.edge_problems(
        layout.text_positions(_text_pdf(x=40, y=400))
    ) == []
