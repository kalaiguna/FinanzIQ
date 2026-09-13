"""
platforms/antigravity/adapter.py — Gemini extraction adapter.

Uses the google-genai SDK directly (not the `agy` CLI subprocess).
Requires GEMINI_API_KEY — get a free key at aistudio.google.com.

response_schema=ReceiptData guarantees valid JSON at the API level,
eliminating the regex/brace-walk extraction needed for Claude output.

Public interface (identical shape to platforms/claude/adapter.py):
  extract_image(image_path, prompt)  -> str        (valid JSON string)
  extract_pdf_text(text, prompt)     -> str        (valid JSON string)
  extract_pdf_batch(texts)           -> list[dict] (serial; parsed)
"""

import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so core.* resolves correctly
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.schemas import ReceiptData
from core.prompts import RECEIPT_TEXT_PROMPT

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set.\n"
                "  Get a free key at aistudio.google.com (no credit card required).\n"
                "  Then: set GEMINI_API_KEY=AIza..."
            )
        from google import genai
        _client = genai.Client(api_key=api_key)
    return _client


def _mime(image_path: Path) -> str:
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
    }.get(image_path.suffix.lower(), "image/jpeg")


# ── Public interface ───────────────────────────────────────────────────────────

def extract_image(image_path: Path, prompt: str) -> str:
    """Send image to Gemini Vision. Returns valid JSON string (schema-guaranteed).

    response_schema=ReceiptData ensures the response matches the receipt
    structure — no regex or fence-stripping needed on the caller side.
    """
    from google.genai import types

    img_bytes = image_path.read_bytes()
    response = _get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type=_mime(image_path)),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReceiptData,
            temperature=0.1,
        ),
    )
    return response.text


def extract_pdf_text(text: str, prompt: str) -> str:
    """Send pre-extracted PDF text to Gemini. Returns valid JSON string."""
    from google.genai import types

    response = _get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=[f"{prompt}\n\n---\n{text}"],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReceiptData,
            temperature=0.1,
        ),
    )
    return response.text


def extract_pdf_batch(texts: list[str]) -> list[dict]:
    """Serial extraction across multiple PDF texts.

    Gemini API calls are direct (no subprocess overhead), so serial is fast
    enough — batching adds no meaningful benefit here.

    response_schema=ReceiptData enforces single-receipt output per call.
    """
    return [json.loads(extract_pdf_text(t, RECEIPT_TEXT_PROMPT)) for t in texts]
