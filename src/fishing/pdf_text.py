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


def extract_text(pdf_path: Path, *, layout: bool = True) -> str:
    """Run pdftotext on *pdf_path* and return its text output."""
    exe = _find_pdftotext()
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
