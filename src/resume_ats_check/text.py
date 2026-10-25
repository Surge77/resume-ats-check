"""Read a resume PDF's text layer the way an applicant tracking system does.

A resume can look perfect on screen and still be broken for the ATS that parses it:
icon glyph names leak into the text, kerning splits words, and a contact block can
extract as an address that does not exist. Everything here is pure analysis — no
subprocess, no compilation, no network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import IO, Iterable

from pypdf import PdfReader

_MIN_WORD_LEN = 4

# Icon glyph names pdfTeX writes verbatim into the text layer when a font offers no
# Unicode mapping (fontawesome5 is the usual source). Stripped by exact name: a loose
# ``/\w+`` rule would eat the "React" in "TypeScript/React".
_ICON_NAMES = ("phone", "envelope", "linkedin", "github", "map-marker", "mapmarker")
_ICON_RE = re.compile(r"/(?:" + "|".join(_ICON_NAMES) + r")\b", re.IGNORECASE)
# Junk codepoints seen in damaged text layers, plus U+2197 (the ``\nearrow``
# external-link marker — deliberate in the source, noise when matching keywords).
_JUNK_CHARS = str.maketrans({"\u2642": " ", "\u2322": " ", "\u00b6": " ", "\u2197": " "})

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.\w+")
_PHONE_RE = re.compile(r"\+?\d[\d\s-]{7,}\d")


def normalize_extracted(text: str) -> str:
    """Collapse a PDF text layer into a form safe to match keywords against.

    Undoes line-break hyphenation, drops known icon artifacts, and flattens
    whitespace. Without this, ``authentication`` split as ``authen-\\ntication``
    reads as a missing keyword.
    """
    text = re.sub(r"-\n", "", text)
    text = _ICON_RE.sub(" ", text)
    text = text.translate(_JUNK_CHARS)
    return re.sub(r"\s+", " ", text).strip()


def count_pages(source: Path | IO[bytes]) -> int:
    """Page count. Accepts a stream so tests need no filesystem writes."""
    return len(PdfReader(source).pages)


def extract_text(source: Path | IO[bytes]) -> str:
    """Raw text layer, pages joined by newline."""
    reader = PdfReader(source)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def contact_problems(text: str, *, expected_email: str | None = None) -> list[str]:
    """Problems with the contact block's machine-readability. Empty means clean.

    Takes RAW extracted text, unlike its neighbours here, which normalize first.
    That is deliberate and load-bearing: ``normalize_extracted`` strips the very
    icon-glyph debris this function needs in order to see that something ran into
    the address. Normalizing first would make the guard pass on the exact bug it
    was written to catch.
    """
    problems: list[str] = []
    match = _EMAIL_RE.search(text)
    if match is None:
        problems.append("no email address found in the text layer")
    else:
        found = match.group(0)
        # Anything other than whitespace before the address means a neighbouring
        # glyph ran into it. Testing for an alnum neighbour is not enough: a real
        # defect read "/envel<U+2322>pejane@example.com", where the match began
        # mid-word and the preceding character was punctuation.
        if match.start() > 0 and not text[match.start() - 1].isspace():
            problems.append(
                f"email {found!r} is glued to preceding text — an ATS will misparse it"
            )
        if expected_email is not None and found != expected_email:
            problems.append(f"email extracted as {found!r}, expected {expected_email!r}")
    if _PHONE_RE.search(text) is None:
        problems.append("no phone number found in the text layer")
    return problems


def tex_body(tex_source: str) -> str:
    """Everything after ``\\begin{document}``, comments removed."""
    _head, marker, body = tex_source.partition(r"\begin{document}")
    if not marker:
        # Splitting on a missing marker would silently hand back the preamble as
        # "words the reader should see", turning every package name into a phantom
        # missing word. Fail loudly rather than emit a nonsense coverage figure.
        raise ValueError(r"no \begin{document} in source — not a LaTeX document?")
    return re.sub(r"(?<!\\)%.*", " ", body)


def typeset_text(tex_source: str) -> str:
    """The .tex body reduced to the characters a reader sees.

    ``\\href`` URLs (an argument, never typeset), environment names,
    optional-argument groups, and macro names are dropped. Skipping the macro strip
    makes ``\\hfill`` masquerade as "fill".
    """
    body = tex_body(tex_source)
    body = re.sub(r"\\href\{[^}]*\}", " ", body)
    # Without these, \begin{center} and [leftmargin=0.15in, nosep] look like words.
    body = re.sub(r"\\(?:begin|end)\{[^}]*\}", " ", body)
    body = re.sub(r"\[[^\]]*\]", " ", body)
    body = re.sub(r"\\[a-zA-Z]+", " ", body)
    # An empty group is a kerning break inside one word ("DevT{}rends"), not a space.
    body = body.replace("{}", "")
    return re.sub(r"[{}\[\]$~\\]", " ", body)


def tex_body_words(tex_source: str) -> set[str]:
    """Words a reader should see, taken from the .tex body (letters only)."""
    pattern = rf"[A-Za-z][A-Za-z.+#-]{{{_MIN_WORD_LEN - 1},}}"
    return {w.lower().strip(".-") for w in re.findall(pattern, typeset_text(tex_source))}


def haystacks(text: str) -> tuple[str, str]:
    """The normalized text layer, plus a space-free copy of it.

    pdfTeX kerning between pairs like ``Fr`` and ``Te`` is read by extractors as a
    word space, so "Frontend" arrives as "F rontend". Matching against the
    space-free copy too keeps that from reading as missing content;
    ``kerning_splits`` surfaces the split itself.
    """
    normalized = normalize_extracted(text).lower()
    return normalized, re.sub(r"\s+", "", normalized)


def word_coverage(tex_source: str, text: str) -> tuple[float, list[str]]:
    """Fraction of source body words present in the text layer, plus the misses.

    Catches damage page-counting cannot see: a dropped glyph, a broken ToUnicode
    CMap, or a line silently pushed off the page.
    """
    words = tex_body_words(tex_source)
    if not words:
        return 1.0, []
    spaced, packed = haystacks(text)
    missing = sorted(
        w for w in words if w not in spaced and re.sub(r"\s+", "", w) not in packed
    )
    return (len(words) - len(missing)) / len(words), missing


def keyword_state(spaced: str, packed: str, keyword: str) -> str:
    """One keyword's standing in a text layer: "present", "split" or "absent".

    "split" means the term is only there once every space is removed — an extractor
    broke it at a kerning pair ("F rontend"). The page looks perfect and a lenient
    parser copes, but an ATS matching the literal string will not find it.
    """
    needle = keyword.strip().lower()
    if not needle:
        return "present"
    if needle in spaced:
        return "present"
    return "split" if re.sub(r"\s+", "", needle) in packed else "absent"


def missing_keywords(text: str, required: Iterable[str]) -> list[str]:
    """Required keywords absent from the normalized text layer.

    A kerning-split term counts as present here — the content IS on the page.
    `split_keywords` reports it separately as the weaker, ATS-only problem it is.
    """
    spaced, packed = haystacks(text)
    return [k for k in required if keyword_state(spaced, packed, k) == "absent"]


def split_keywords(text: str, required: Iterable[str]) -> list[str]:
    """Required keywords present only as a kerning split — invisible to exact matching."""
    spaced, packed = haystacks(text)
    return [k for k in required if keyword_state(spaced, packed, k) == "split"]


def kerning_splits(text: str) -> list[str]:
    """Words an extractor has broken at a kerning pair, e.g. "F rontend".

    Not a failure — the page renders correctly and most parsers cope — but an ATS
    doing exact keyword matching will miss these tokens, so they are worth seeing.
    """
    # "a" and "I" stand alone legitimately; anything else orphaned before a word
    # fragment is a split rather than English.
    matches = re.findall(r"\b([B-HJ-Zb-hj-z]) ([a-z]{2,})\b", normalize_extracted(text))
    return sorted({f"{head} {tail}" for head, tail in matches})
