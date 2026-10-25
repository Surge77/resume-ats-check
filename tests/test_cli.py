"""The command line and the options it adds on top of the checks."""

from __future__ import annotations

from pypdf import PdfWriter

from resume_ats_check import cli, verify
from resume_ats_check import text as pdftext


def _blank_pdf(path, pages=1):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


def _readable(monkeypatch):
    """A text layer that passes every content check, so only the option under test can fail."""
    body = "x" * 2000 + " +1 555 010 0199 jane.doe@example.com Python React"
    monkeypatch.setattr(pdftext, "extract_text", lambda _: body)


def test_verify_without_tex_skips_word_coverage(tmp_path, monkeypatch):
    _readable(monkeypatch)
    assert verify.verify_pdf(_blank_pdf(tmp_path / "r.pdf")) == []


def test_verify_with_tex_reports_words_missing_from_the_page(tmp_path, monkeypatch):
    _readable(monkeypatch)
    tex = r"\begin{document} Kubernetes Terraform Ansible \end{document}"
    problems = verify.verify_pdf(_blank_pdf(tmp_path / "r.pdf"), tex)
    assert any("word coverage" in p for p in problems)


def test_verify_with_tex_fails_words_glued_in_the_text_layer(tmp_path, monkeypatch):
    """Renders as "React  2026"; extracts as one token, so "React" never matches."""
    monkeypatch.setattr(pdftext, "extract_text", lambda _: "x" * 2000 + " React2026")
    problems = verify.verify_pdf(_blank_pdf(tmp_path / "r.pdf"), r"\begin{document} React \hfill 2026")
    assert any("glued" in p and "react2026" in p for p in problems)
    assert any("pdfinterwordspaceon" in p for p in problems)


def test_max_pages_none_disables_the_page_limit(tmp_path, monkeypatch):
    _readable(monkeypatch)
    pdf = _blank_pdf(tmp_path / "r.pdf", pages=3)
    assert any("3 pages" in p for p in verify.verify_pdf(pdf))
    assert verify.verify_pdf(pdf, max_pages=None) == []


def test_cli_exits_2_for_a_missing_file(tmp_path):
    assert cli.main([str(tmp_path / "nope.pdf")]) == 2


def test_cli_exits_1_and_lists_problems(tmp_path, capsys):
    assert cli.main([str(_blank_pdf(tmp_path / "r.pdf"))]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_exits_0_on_a_clean_pdf(tmp_path, monkeypatch, capsys):
    _readable(monkeypatch)
    pdf = _blank_pdf(tmp_path / "r.pdf")
    assert cli.main([str(pdf), "--keywords", "Python, React", "--email", "jane.doe@example.com"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_cli_fails_when_a_required_keyword_is_absent(tmp_path, monkeypatch, capsys):
    _readable(monkeypatch)
    pdf = _blank_pdf(tmp_path / "r.pdf")
    assert cli.main([str(pdf), "--keywords", "Kubernetes"]) == 1
    assert "Kubernetes" in capsys.readouterr().out


def test_cli_exits_2_for_a_tex_file_that_is_not_latex(tmp_path, monkeypatch):
    _readable(monkeypatch)
    tex = tmp_path / "r.tex"
    tex.write_text("just prose", encoding="utf-8")
    assert cli.main([str(_blank_pdf(tmp_path / "r.pdf")), "--tex", str(tex)]) == 2
