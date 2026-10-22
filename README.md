# resume-ats-check

A resume can look perfect in a PDF viewer and still read as garbage to the applicant
tracking system (ATS) that parses it. `resume-ats-check` reads the PDF's **text layer**
— what the ATS actually sees — and fails the file when that text is broken.

```
$ resume-ats-check resume.pdf --tex resume.tex --keywords "Python, React, PostgreSQL" --email jane.doe@example.com
note: 2 word(s) split by kerning: F rontend, T ypeScript
FAIL — 2 problem(s):
  - email 'pejane.doe@example.com' is glued to preceding text — an ATS will misparse it
  - 14 character(s) fall below the 18pt bottom margin (lowest: y=-12.0pt on page 1) — cut content rather than stretching \textheight
```

## What it catches

Each check exists because the failure happened to a real resume:

| Check | The failure |
|---|---|
| **Glued contact block** | Icon fonts (`fontawesome5`) write glyph names like `/envelope` into the text layer. The address extracted as `pejane.doe@example.com`, a mailbox that doesn't exist, while the rendered page looked fine. |
| **Expected email** (`--email`) | Confirms the address extracts exactly as written. |
| **Phone present** | The phone number is gone from the text layer entirely. |
| **Text off the page** | Stretching `\textheight` to "fit one page" gets the page count down to 1 while the last section prints off the sheet. The text is still in the PDF, so text-based checks pass. Only glyph positions show it. |
| **Empty text layer** | Scanned, rasterized, or XeLaTeX/LuaLaTeX builds with no usable Unicode mapping. |
| **Page limit** (`--max-pages`, default 1) | Spilled onto a second page. |
| **Word coverage** (`--tex`) | Fewer than 98% of the words in your LaTeX body appear in the extracted text, which points to dropped glyphs or a broken ToUnicode map. |
| **Glued words** (`--tex`) | A PDF stores no spaces, so extractors guess word breaks from gaps. pypdf makes no guess at a font switch, a right-aligned `\hfill` column, or a math-font glyph. One resume rendered perfectly but extracted as `React2026`, `TechnologySolapur` and `criteriabeforecomputing`, and a substring keyword search still finds "React" in `React2026`. |
| **Text-layer source rules** (`--tex`) | Requires `\pdfinterwordspaceon`, `\pdfgentounicode=1` and `\input{glyphtounicode}`. Rejects a lone math symbol used as text (`$\|$`, `$\sim$`, `$\nearrow$`, `$-$`). |
| **Required keywords** (`--keywords`) | A term from the job posting is missing. A keyword the extractor split at a kerning pair (`F rontend`) fails separately, because an exact-match ATS won't find it. |

## Install

```
pip install git+https://github.com/Surge77/resume-ats-check
```

Python 3.10+. Two dependencies: `pypdf` and `pdfminer.six`. No TeX installation is needed to check a PDF.

## Usage

```
resume-ats-check PDF [--tex FILE] [--keywords "a, b"] [--email ADDR] [--max-pages N]
```

Exit code `0` = clean, `1` = problems found, `2` = bad input. Use `--max-pages 0` to
disable the page limit.

From Python:

```python
from pathlib import Path
from resume_ats_check import verify_pdf

problems = verify_pdf(Path("resume.pdf"), required=["Python", "React"])
```

## If you build with LaTeX

Build with **pdfLaTeX** and keep a glyph-to-Unicode mapping in the preamble:

```latex
\input{glyphtounicode}
\pdfgentounicode=1
\pdfinterwordspaceon   % write a real space at every word gap
```

Keep math-font symbols out of running text. Use `---` or `--` as separators, a plain
`-` for a minus sign (`\textminus` extracts as `=`), and the word "about" instead of
`$\sim$`.

If icon glyphs still leak, map them to nothing with `\pdfglyphtounicode{envelope}{}`
(do the same for `phone`, `linkedin` and `github`).

## Limits

It checks what text the PDF contains, not how a particular vendor's parser will
section it. Two-column layouts, tables and text boxes can extract in the wrong
order even when every word is present. This tool won't flag that.

## License

MIT
