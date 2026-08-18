"""Handwritten-note ingest: iPad PDF exports → OCR text companion in the vault.

The PDF is the artifact you read; the OCR text exists so semantic search can
find the page. OCR runs fully on-device via the `ocrtext` helper (Apple's
Vision framework — the Live Text engine, which handles handwriting). Equations
and diagrams do not survive OCR; that's acceptable by design.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

from .config import CONFIG_DIR, Config
from .vault import _safe_filename

REPO_ROOT = Path(__file__).resolve().parent.parent

SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".tiff"}

_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def find_ocrtext() -> Path:
    """Locate the ocrtext binary (env var, ~/.meetscribe/bin, or repo build)."""
    candidates = []
    if os.environ.get("MEETSCRIBE_OCRTEXT"):
        candidates.append(Path(os.environ["MEETSCRIBE_OCRTEXT"]))
    candidates.append(CONFIG_DIR / "bin" / "ocrtext")
    candidates.append(REPO_ROOT / "ocr" / ".build" / "release" / "ocrtext")
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError(
        "ocrtext binary not found. Build it with `make build` (or "
        "`cd ocr && swift build -c release`), or set MEETSCRIBE_OCRTEXT."
    )


def ocr_file(path: Path) -> str:
    """OCR a PDF or image; returns text with pages separated by form feeds."""
    result = subprocess.run(
        [str(find_ocrtext()), str(path)], capture_output=True, text=True, timeout=600
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"OCR failed for {path.name}")
    return result.stdout.rstrip("\n")


def parse_inbox_name(
    path: Path, subject_names: list[str]
) -> tuple[str | None, date, str]:
    """Derive (subject, date, title) from a filename like
    "NEU 330 2026-09-02 synaptic plasticity.pdf".

    Subject: longest subject name appearing anywhere in the filename
    (case-insensitive, on word boundaries), or None. Date: first YYYY-MM-DD
    in the name, else the file's mtime. Title: whatever is left, else "Notes".
    """
    stem = path.stem.strip()
    rest = stem

    subject = None
    for name in sorted(subject_names, key=len, reverse=True):
        m = re.search(
            rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", rest, re.IGNORECASE
        )
        if m:
            subject = name
            rest = rest[: m.start()] + rest[m.end():]
            break

    m = _DATE_RE.search(rest)
    if m:
        day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        rest = rest[: m.start()] + rest[m.end():]
    else:
        day = datetime.fromtimestamp(path.stat().st_mtime).date()

    title = re.sub(r"\s+", " ", rest).strip(" -_–—")
    return subject, day, title or "Notes"


def write_handwritten(
    config: Config, subject: str, day: date, title: str, ocr_text: str, pdf_src: Path
) -> Path:
    """File the original ink + its OCR companion into <vault>/Handwritten/<subject>/.

    Re-ingesting the same name overwrites the pair, so a re-export refreshes it.
    Returns the companion note's path.
    """
    folder = config.vault / "Handwritten" / _safe_filename(subject)
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{day.isoformat()} {_safe_filename(title)}"
    artifact = folder / f"{base}{pdf_src.suffix.lower()}"
    note = folder / f"{base}.md"

    artifact.unlink(missing_ok=True)
    shutil.move(str(pdf_src), artifact)

    pages = [p.strip() for p in ocr_text.split("\f")]
    if len(pages) > 1:
        body_text = "\n\n".join(
            f"### Page {i}\n\n{text}" if text else f"### Page {i}\n\n*(no text recognized)*"
            for i, text in enumerate(pages, 1)
        )
    else:
        body_text = pages[0] if pages and pages[0] else "*(no text recognized)*"

    note.write_text(
        f"""---
title: "{title}"
date: {day.isoformat()}
subject: "{subject}"
source: handwritten
tags: [handwritten]
---

# {title}

Subject: [[{_safe_filename(subject)}]]

![[{artifact.name}]]

## OCR text

> Search index only — read the handwriting above. Equations and diagrams are not captured.

{body_text}
"""
    )
    return note
