#!/usr/bin/env python3
"""
receipt_parser.py — Receipt JSON parsing helpers and PDF text extraction.

Prompts and batch-prompt builder live in core/prompts.py (shared with adapters).
AI extraction is handled by the platform adapter (core/adapter.py + platforms/).

Exports used by process_receipts.py:
  RECEIPT_PROMPT         — image extraction prompt
  RECEIPT_TEXT_PROMPT    — text (PDF) extraction prompt
  _build_batch_prompt    — multi-receipt CLI batch prompt builder
  _extract_json          — parse a JSON object from raw model output
  _pdf_text              — extract text from a PDF via pdfplumber
  validate_receipt       — check item sum vs receipt total (±€0.10)
  PDF_BATCH_SIZE         — max PDFs per Claude CLI batch call
"""

import json
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path so core.prompts resolves correctly
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.prompts import RECEIPT_PROMPT, RECEIPT_TEXT_PROMPT, _build_batch_prompt  # noqa: F401

# ── Constants ─────────────────────────────────────────────────────────────────

PDF_BATCH_SIZE  = 5        # max PDFs per Claude CLI call
MAX_PER_RECEIPT = 2_500    # chars of receipt text per slot
MAX_BATCH_CHARS = 15_000   # combined text budget per batch call

# ── JSON parsing ──────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """Extract the first JSON object from model output (handles fences and prose)."""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()

    start = text.find("{")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start : i + 1])

    raise ValueError(f"No JSON object found in model output. First 300 chars:\n{raw[:300]}")


def _extract_json_array(raw: str) -> list:
    """Extract the first JSON array from model output (handles fences)."""
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if m:
            text = m.group(1).strip()

    start = text.find("[")
    if start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    result = json.loads(text[start : i + 1])
                    if isinstance(result, list):
                        return result

    raise ValueError(f"No JSON array found in model output. First 300 chars:\n{raw[:300]}")


# ── PDF text extraction ───────────────────────────────────────────────────────

def _pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("pdfplumber not installed. Run: pip install pdfplumber")
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


# ── Validation ────────────────────────────────────────────────────────────────

def validate_receipt(data: dict) -> tuple[bool, str]:
    """Check that item totals sum to the receipt total (±€0.10 tolerance)."""
    items = data.get("items") or []
    if not items:
        return True, ""

    item_sum = sum(item.get("total") or 0 for item in items)
    receipt_total = data.get("total")

    if receipt_total is None:
        return True, ""

    diff = abs(item_sum - receipt_total)
    if diff > 0.10:
        hint = " (discount/coupon likely)" if item_sum > receipt_total else ""
        note = f"item sum {item_sum:.2f} != total {receipt_total:.2f}{hint}"
        return False, note

    return True, ""
