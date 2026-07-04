"""Wrapper around the Xpdf `pdftotext` binary.

We use the external tool instead of a Python PDF library because the only
Python options that handle these PDFs cleanly (pdfplumber/pdfminer) now pull
in `cryptography`, which has no prebuilt wheel for Windows ARM64.

The binary is installed locally at
`%LOCALAPPDATA%\\xpdf-tools\\xpdf-tools-win-4.06\\bin64\\pdftotext.exe`.
If it's missing we raise a clear error pointing the user at the installer.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_DEFAULT_LOCATIONS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "xpdf-tools" / "xpdf-tools-win-4.06" / "bin64" / "pdftotext.exe",
    Path(os.environ.get("ProgramFiles", "")) / "xpdf-tools" / "bin64" / "pdftotext.exe",
]


def _find_pdftotext() -> Path:
    env = os.environ.get("PDFTOTEXT_EXE")
    if env and Path(env).exists():
        return Path(env)
    on_path = shutil.which("pdftotext")
    if on_path:
        return Path(on_path)
    for candidate in _DEFAULT_LOCATIONS:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "pdftotext.exe not found. Install Xpdf command-line tools "
        "(https://www.xpdfreader.com/download.html) or set PDFTOTEXT_EXE."
    )


def _extract_with_pypdf(pdf_path: Path) -> str:
    """Fallback extractor using pure-Python pypdf (no external binary).

    Used when Xpdf's ``pdftotext`` isn't installed. Layout fidelity is lower
    than Xpdf's ``-layout`` output, which is fine for indexing map/newsletter
    text but is why the WDFW rules parsers still prefer the binary.
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise FileNotFoundError(
            "Neither pdftotext.exe nor pypdf is available. Install Xpdf tools "
            "(https://www.xpdfreader.com/download.html) or run: pip install pypdf"
        ) from e
    reader = PdfReader(str(pdf_path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 - skip unreadable pages, keep the rest
            continue
    return "\n".join(parts).strip()


def extract_text(pdf_path: Path, *, layout: bool = True, allow_pypdf: bool = False) -> str:
    """Extract text from *pdf_path*.

    Uses the Xpdf ``pdftotext`` binary (best layout fidelity). The WDFW rules
    parsers depend on its ``-layout`` column output, so they leave
    ``allow_pypdf=False`` and raise if the binary is missing (the caller then
    keeps the last good parse). The map importer passes ``allow_pypdf=True`` to
    fall back to pure-Python ``pypdf`` when the binary isn't installed.
    """
    try:
        exe = _find_pdftotext()
    except FileNotFoundError:
        if allow_pypdf:
            return _extract_with_pypdf(pdf_path)
        raise
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
        out_path = Path(tmp.name)
    try:
        args = [str(exe)]
        if layout:
            args.append("-layout")
        args += [str(pdf_path), str(out_path)]
        subprocess.run(args, check=True, capture_output=True)
        return out_path.read_text(encoding="utf-8", errors="replace")
    finally:
        out_path.unlink(missing_ok=True)
