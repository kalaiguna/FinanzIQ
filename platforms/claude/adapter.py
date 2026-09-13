"""
platforms/claude/adapter.py — Claude extraction adapter.

Supports two sub-backends (auto-selected at runtime):
  sdk — Anthropic SDK (requires ANTHROPIC_API_KEY)
  cli — local `claude` CLI via stream-json (uses Claude Code subscription)

Public interface:
  extract_image(image_path, prompt)        -> str          (raw LLM response)
  extract_pdf_text(text, prompt)           -> str          (raw LLM response)
  extract_pdf_batch(texts, batch_prompt)   -> list[dict]   (parsed; CLI-optimised)
"""

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

RECEIPT_MODEL   = os.environ.get("RECEIPT_MODEL", "claude-haiku-4-5-20251001")
PDF_BATCH_SIZE  = 5
MAX_PER_RECEIPT = 2_500


# ── Sub-backend detection ──────────────────────────────────────────────────────

def _backend() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "sdk"
    if shutil.which("claude"):
        return "cli"
    raise RuntimeError(
        "No Claude backend available.\n"
        "  Option A: set ANTHROPIC_API_KEY and install the anthropic package.\n"
        "  Option B: install Claude Code CLI → https://claude.ai/code"
    )


# ── Image helper ───────────────────────────────────────────────────────────────

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


# ── JSON parsing (Claude output may include markdown fences) ───────────────────

def _parse_json(raw: str) -> dict:
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


def _parse_json_array(raw: str) -> list:
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
                    result = json.loads(text[start: i + 1])
                    if isinstance(result, list):
                        return result
    raise ValueError(f"No JSON array found in output. First 300 chars:\n{raw[:300]}")


# ── SDK sub-backend ────────────────────────────────────────────────────────────

def _sdk_extract_image(image_path: Path, prompt: str) -> str:
    import anthropic
    b64, media_type = _image_b64(image_path)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=RECEIPT_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": prompt},
        ]}],
    )
    return response.content[0].text


def _sdk_extract_text(text: str, prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=RECEIPT_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": f"{prompt}\n\n---\n{text}"}],
    )
    return response.content[0].text


# ── CLI sub-backend ────────────────────────────────────────────────────────────

def _cli_extract_image(image_path: Path, prompt: str) -> str:
    """Send image + prompt to `claude` CLI via --input-format=stream-json."""
    b64, media_type = _image_b64(image_path)
    message = json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        },
    })
    result = subprocess.run(
        ["claude", "-p", "--verbose",
         "--input-format", "stream-json",
         "--output-format", "stream-json"],
        input=message, capture_output=True, text=True,
        timeout=300, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"`claude` CLI returned exit {result.returncode}:\n{result.stderr[:500]}")

    parts = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "content_block_delta":
            delta = ev.get("delta", {})
            if delta.get("type") == "text_delta":
                parts.append(delta.get("text", ""))
        elif ev.get("type") == "result" and isinstance(ev.get("result"), str):
            return ev["result"]
        elif ev.get("type") == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    parts.append(block["text"])

    output = "".join(parts).strip()
    if not output:
        raise RuntimeError("`claude` CLI returned empty output — check that you are logged in")
    return output


def _cli_extract_text(text: str, prompt: str) -> str:
    MAX_TEXT_CHARS = 12_000
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n[... truncated ...]"
    result = subprocess.run(
        ["claude", "-p", f"{prompt}\n\n---\n{text}"],
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"`claude` CLI returned exit {result.returncode}:\n{result.stderr[:500]}")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("`claude` CLI returned empty output")
    return output


def _cli_batch_chunk(texts: list[str], batch_prompt: str) -> list[dict]:
    """One CLI subprocess call for a pre-sized chunk. Returns parsed list aligned with texts."""
    result = subprocess.run(
        ["claude", "-p", batch_prompt],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"`claude` CLI returned exit {result.returncode}:\n{result.stderr[:500]}")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("`claude` CLI batch returned empty output")
    items = _parse_json_array(output)
    if len(items) != len(texts):
        raise ValueError(f"Batch returned {len(items)} results for {len(texts)} receipts")
    return items


# ── Public interface ───────────────────────────────────────────────────────────

def extract_image(image_path: Path, prompt: str) -> str:
    """Extract receipt data from an image. Returns raw LLM response text."""
    backend = _backend()
    return _sdk_extract_image(image_path, prompt) if backend == "sdk" else _cli_extract_image(image_path, prompt)


def extract_pdf_text(text: str, prompt: str) -> str:
    """Extract receipt data from pre-extracted PDF text. Returns raw LLM response text."""
    backend = _backend()
    return _sdk_extract_text(text, prompt) if backend == "sdk" else _cli_extract_text(text, prompt)


def extract_pdf_batch(texts: list[str], batch_prompt: str) -> list[dict]:
    """Batch-extract multiple PDF receipts.

    CLI: sends up to PDF_BATCH_SIZE receipts per subprocess call (efficient).
    SDK: serial calls — SDK latency is low and batching adds no benefit.
    Returns parsed list of dicts aligned with the input texts list.
    """
    backend = _backend()
    if backend == "sdk":
        return [_parse_json(_sdk_extract_text(t, batch_prompt)) for t in texts]

    results = []
    for i in range(0, len(texts), PDF_BATCH_SIZE):
        chunk = texts[i: i + PDF_BATCH_SIZE]
        truncated = [
            t[:MAX_PER_RECEIPT] + "\n[... truncated ...]" if len(t) > MAX_PER_RECEIPT else t
            for t in chunk
        ]
        results.extend(_cli_batch_chunk(truncated, batch_prompt))
    return results
