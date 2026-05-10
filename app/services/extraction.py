"""Text extraction for PDF / DOCX / plain text. Returns (text, page_map)."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("liwang.extraction")


def extract_text(
    path: Path,
    mime: str | None,
    original_name: str | None = None,
) -> tuple[str, list[tuple[int, str]]]:
    """Returns (combined_text, list of (page_no, page_text)).
    page_no is 1-indexed for PDFs; 0 for non-paginated formats.
    `original_name` is used to recover the file extension when `path` is a
    UUID-named blob in storage."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    name = (original_name or p.name).lower()
    suffix = Path(name).suffix
    m = (mime or "").lower()

    if "pdf" in m or suffix == ".pdf":
        return _extract_pdf(p)
    if "wordprocessingml" in m or suffix == ".docx":
        return _extract_docx(p)
    if m.startswith("text/") or suffix in (".txt", ".md", ".markdown"):
        return _extract_plain(p)
    # fallback — try utf-8
    try:
        return _extract_plain(p)
    except Exception:
        raise ValueError(f"unsupported mime/extension: mime={mime} name={name}")


def _extract_pdf(p: Path) -> tuple[str, list[tuple[int, str]]]:
    from pypdf import PdfReader

    reader = PdfReader(str(p))
    pages: list[tuple[int, str]] = []
    parts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            t = page.extract_text() or ""
        except Exception as ex:
            log.warning("pdf page %s extract failed: %s", i, ex)
            t = ""
        if t.strip():
            pages.append((i, t))
            parts.append(t)
    return "\n\n".join(parts), pages


def _extract_docx(p: Path) -> tuple[str, list[tuple[int, str]]]:
    from docx import Document

    doc = Document(str(p))
    text = "\n".join(par.text for par in doc.paragraphs if par.text.strip())
    return text, [(0, text)]


def _extract_plain(p: Path) -> tuple[str, list[tuple[int, str]]]:
    text = p.read_text(encoding="utf-8", errors="replace")
    return text, [(0, text)]
