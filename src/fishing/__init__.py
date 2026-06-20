"""MCP Fishing knowledge-base package."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KB_DIR = ROOT / "kb"
SOURCES = {
    "keyfacts": ROOT / "Key facts.docx",
    "gear_workbook": ROOT / "Fishing Gear.xlsx",
    "rules_current_pdf": ROOT / "Washington State Rules.pdf",
    "rules_proposed_pdf": ROOT / "Proposed State Plan.pdf",
}
