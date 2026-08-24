from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

DEFAULT_MAX_PAGES = 6
DEFAULT_MAX_CHARS = 6000
HEAD_CHARS = 1800
WINDOW_CHARS = 1800

SECTION_MARKERS = (
    "considerando",
    "se resuelve",
    "decreta",
    "artículo 1",
    "articulo 1",
    "disposiciones complementarias",
    "disposición complementaria",
    "disposicion complementaria",
)


def normalize_pdf_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[\t\r ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _normalized_for_search(text: str) -> str:
    import unicodedata

    value = unicodedata.normalize("NFKD", text)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.casefold()


def select_legal_excerpt(text: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> str | None:
    """Select useful legal sections without blindly taking only the PDF prefix."""
    cleaned = normalize_pdf_text(text)
    if not cleaned:
        return None

    safe_limit = max(1000, int(max_chars))
    if len(cleaned) <= safe_limit:
        return cleaned

    searchable = _normalized_for_search(cleaned)
    spans: list[tuple[int, int]] = [(0, min(len(cleaned), HEAD_CHARS))]

    for marker in SECTION_MARKERS:
        normalized_marker = _normalized_for_search(marker)
        start = 0
        while True:
            index = searchable.find(normalized_marker, start)
            if index < 0:
                break
            spans.append((index, min(len(cleaned), index + WINDOW_CHARS)))
            start = index + len(normalized_marker)
            if len(spans) >= 8:
                break
        if len(spans) >= 8:
            break

    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1] + 120:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))

    pieces: list[str] = []
    remaining = safe_limit
    for start, end in merged:
        if remaining <= 0:
            break
        piece = cleaned[start:end].strip()
        if not piece:
            continue
        piece = piece[:remaining]
        pieces.append(piece)
        remaining -= len(piece)

    excerpt = "\n…\n".join(pieces).strip()
    return excerpt or cleaned[:safe_limit]


def extract_pdf_excerpt(
    pdf_path: str | Path,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Extract a bounded text excerpt from a text-based PDF.

    OCR is deliberately not attempted here. Scanned PDFs simply return no
    useful excerpt and remain in the conservative `review` path.
    """
    path = Path(pdf_path)
    if not path.exists() or not path.is_file():
        return None

    reader = PdfReader(str(path))
    pages: list[str] = []
    for page in reader.pages[: max(1, int(max_pages))]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text.strip():
            pages.append(text)

    if not pages:
        return None
    return select_legal_excerpt("\n".join(pages), max_chars=max_chars)
