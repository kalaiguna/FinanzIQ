"""
platforms/ollama/adapter.py — Ollama local model adapter.

Calls the OpenAI-compatible HTTP API at localhost:11434.
No API key — runs 100% locally, no data leaves the machine.

Setup:
    ollama serve
    ollama pull qwen2.5-vl

Configure via env vars:
    OLLAMA_MODEL    — model name (default: qwen2.5-vl)
    OLLAMA_BASE_URL — base URL   (default: http://localhost:11434)

Public interface (identical shape to other adapters):
    extract_image(image_path, prompt)  -> str
    extract_pdf_text(text, prompt)     -> str
    extract_pdf_batch(texts)           -> list[dict]
"""

import base64
import json
import os
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path so core.* resolves correctly
_ROOT = Path(__file__).parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.prompts import RECEIPT_TEXT_PROMPT

OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL",    "qwen2.5-vl")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _image_b64(image_path: Path, max_px: int = 1500) -> tuple[str, str]:
    """Return (base64_str, media_type), resizing to max_px on longest side if needed."""
    try:
        from PIL import Image
        import io
        img = Image.open(image_path)
        if max(img.size) > max_px:
            img.thumbnail((max_px, max_px), Image.LANCZOS)
        buf = io.BytesIO()
        fmt = "JPEG" if image_path.suffix.lower() in (".jpg", ".jpeg") else "PNG"
        img.save(buf, format=fmt, quality=85)
        data = buf.getvalue()
    except ImportError:
        data = image_path.read_bytes()

    suffix = image_path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png",  ".webp": "image/webp",
    }.get(suffix, "image/jpeg")
    return base64.standard_b64encode(data).decode("utf-8"), media_type


def _parse_json(raw: str) -> dict:
    """Extract JSON object from model output (may include markdown fences)."""
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
                    return json.loads(text[start: i + 1])
    raise ValueError(f"No JSON object found in output. First 300 chars:\n{raw[:300]}")


def _chat(messages: list[dict], timeout: int = 300) -> str:
    """POST to Ollama's OpenAI-compatible /v1/chat/completions. Returns response text."""
    import requests
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/v1/chat/completions",
            json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.ConnectionError:
        raise RuntimeError(
            f"Cannot connect to Ollama at {OLLAMA_BASE_URL}.\n"
            "  Start it with: ollama serve\n"
            f"  Pull the model: ollama pull {OLLAMA_MODEL}"
        )
    return response.json()["choices"][0]["message"]["content"]


# ── Public interface ───────────────────────────────────────────────────────────

def extract_image(image_path: Path, prompt: str) -> str:
    """Send image to local Ollama vision model. Returns raw model response text."""
    b64, media_type = _image_b64(image_path)
    return _chat([{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
            {"type": "text", "text": prompt},
        ],
    }])


def extract_pdf_text(text: str, prompt: str) -> str:
    """Send pre-extracted PDF text to local Ollama model. Returns raw model response text."""
    return _chat([{
        "role": "user",
        "content": f"{prompt}\n\n---\n{text}",
    }])


def extract_pdf_batch(texts: list[str]) -> list[dict]:
    """Serial extraction across multiple PDF texts.

    Ollama runs locally so serial API calls are fast enough — batching adds
    no benefit. Uses _parse_json() since Ollama has no response_schema support.
    """
    return [_parse_json(extract_pdf_text(t, RECEIPT_TEXT_PROMPT)) for t in texts]
