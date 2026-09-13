#!/usr/bin/env python3
"""
receipt_parser.py — Extract structured data from receipt photos using Claude Vision.

Two backends (auto-selected by process_receipts.py):
  sdk — Anthropic SDK (requires ANTHROPIC_API_KEY)
  cli — local `claude` CLI via stream-json stdin (Claude Code subscription, no API key)

Model: claude-haiku-4-5-20251001 (configurable via RECEIPT_MODEL env var, SDK only)
"""

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

RECEIPT_MODEL = os.environ.get("RECEIPT_MODEL", "claude-haiku-4-5-20251001")

RECEIPT_PROMPT = """You are a receipt data extraction assistant. Extract all data from this German store receipt (Kassenbon) photo.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{
  "store": "<full store name as printed>",
  "store_chain": "<chain name, e.g. Herkules, REWE, LIDL>",
  "address": "<store address>",
  "date": "<YYYY-MM-DD>",
  "time": "<HH:MM>",
  "items": [
    {
      "raw_name": "<exactly as printed on receipt>",
      "clean_name": "<English or clean German name>",
      "category": "<one of: Dairy|Produce|Meat|Bakery|Beverages|Snacks|Condiments|Pantry|Household|Clothing|Pfand|Dining|Healthcare|Photos|Discounts|Other>",
      "qty": <number, default 1>,
      "unit_price": <number or null>,
      "total": <number>,
      "vat_rate": "<7% or 19%>"
    }
  ],
  "subtotal": <number or null>,
  "vat": { "7pct": <number or null>, "19pct": <number or null> },
  "total": <number>,
  "payment_method": "<girocard|cash|credit_card|ec|other>",
  "item_count": <integer>
}

Rules:
- German VAT indicators: A = 7% (food/reduced rate), B = 19% (standard rate/non-food). Use these to set vat_rate on each item.
- German number format: 1.234,56 → 1234.56 in JSON (period=thousands separator, comma=decimal).
- If both an itemised Kassenbon and a Terminalbeleg (card terminal slip) are visible, extract data only from the itemised Kassenbon.
- item_count = total number of line items (count each line separately, even if qty > 1).
- If a field is not visible or not present, use null.
- Categories (pick the most specific match):
  Dairy      — milk, cheese, yoghurt, cream, butter, eggs
  Produce    — fresh fruit, fresh vegetables, salad
  Meat       — meat, fish, sausage, deli, cold cuts
  Bakery     — bread, rolls, pastry, cake, baked goods
  Beverages  — drinks, juice, water, coffee, tea, energy drinks, soda
  Snacks     — chips, crisps, sweets, chocolate, candy, biscuits, cookies
  Condiments — mustard (Senf), ketchup, pesto, sauces, vinegar, oil, mayonnaise, spice blends, relish
  Pantry     — sugar, flour, pasta, rice, lentils, beans, canned goods, instant soup, spices, baking ingredients, dry goods, cereal, oats
  Household  — cleaning products, detergent, hygiene, paper, toiletries, cosmetics, non-food household items
  Clothing   — apparel, shoes, accessories, textiles — use for ALL items from clothing stores (Primark, H&M, Zara, etc.)
  Pfand      — bottle deposit (Pfand), can deposit
  Dining     — restaurant or café meals, dishes, drinks ordered at a restaurant or food stall
  Healthcare — medicine, vitamins, supplements, protein powder, pharmacy items, medical devices
  Photos     — photo printing, photo books, picture frames, photography services
  Discounts  — coupons, vouchers, discount lines, cashback, promotional deductions (negative amounts)
  Other      — tobacco, lottery, gift cards, non-categorized items
"""


def _extract_json(raw: str) -> dict:
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


def _image_b64(image_path: Path, max_px: int = 1500) -> tuple[str, str]:
    """Return (base64, media_type), resizing to max_px on the longest side if needed."""
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
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    media_type = media_type_map.get(suffix, "image/jpeg")
    b64 = base64.standard_b64encode(data).decode("utf-8")
    return b64, media_type


def _sdk_extract(image_path: Path) -> str:
    import anthropic
    b64, media_type = _image_b64(image_path)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=RECEIPT_MODEL,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": RECEIPT_PROMPT},
            ],
        }],
    )
    return response.content[0].text


def _cli_extract(image_path: Path) -> str:
    """Use local `claude` CLI via --input-format=stream-json to send image + prompt."""
    b64, media_type = _image_b64(image_path)
    message = json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                {"type": "text", "text": RECEIPT_PROMPT},
            ],
        },
    })
    result = subprocess.run(
        ["claude", "-p", "--verbose", "--input-format", "stream-json", "--output-format", "stream-json"],
        input=message,
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"`claude` CLI returned exit {result.returncode}:\n{result.stderr[:500]}")

    # Parse stream-json output: collect text from all text_delta and assistant events
    parts = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Streaming delta: {"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}
        if ev.get("type") == "content_block_delta":
            delta = ev.get("delta", {})
            if delta.get("type") == "text_delta":
                parts.append(delta.get("text", ""))
        # Final message: {"type":"result","result":"..."} or {"type":"assistant","message":{...}}
        elif ev.get("type") == "result" and isinstance(ev.get("result"), str):
            return ev["result"]
        elif ev.get("type") == "assistant":
            msg = ev.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "text":
                    parts.append(block["text"])

    output = "".join(parts).strip()
    if not output:
        raise RuntimeError("`claude` CLI returned empty output — check that you are logged in")
    return output


RECEIPT_TEXT_PROMPT = RECEIPT_PROMPT + """

The receipt data is provided as extracted text below (not an image).
Parse it the same way — extract all fields and return the same JSON structure.
"""

# Used for batching multiple PDFs in one CLI call
_BATCH_SCHEMA = """{
  "store": "...", "store_chain": "...", "address": "...", "date": "YYYY-MM-DD",
  "time": "HH:MM", "items": [{"raw_name":"...","clean_name":"...","category":"...","qty":1,"unit_price":0.0,"total":0.0,"vat_rate":"7%"}],
  "subtotal": 0.0, "vat": {"7pct": 0.0, "19pct": 0.0}, "total": 0.0,
  "payment_method": "girocard", "item_count": 0
}"""

def _build_batch_prompt(texts: list[str]) -> str:
    n = len(texts)
    header = (
        f"Extract data from each of the {n} German store receipts (Kassenbons) below.\n"
        f"They are separated by '=== RECEIPT N ==='.\n\n"
        f"Return a JSON ARRAY of exactly {n} objects in the same order, each with this structure:\n"
        f"{_BATCH_SCHEMA}\n\n"
        "Rules:\n"
        "- German VAT: A=7% (food), B=19% (non-food). Set vat_rate on each item accordingly.\n"
        "- German number format: 1.234,56 -> 1234.56\n"
        "- Pfand (bottle deposit) -> category 'Pfand'\n"
        "- item_count = number of line items\n"
        "- Categories: Dairy|Produce|Meat|Bakery|Beverages|Snacks|Condiments|Pantry|Household|Clothing|Pfand|Dining|Healthcare|Photos|Discounts|Other\n"
        "- Condiments: mustard, ketchup, pesto, sauces, oils, vinegar. Pantry: sugar, flour, pasta, rice, instant soup, canned goods, spices, dry goods.\n"
        "- Clothing: ALL items from clothing/fashion stores (Primark, H&M, Zara, etc.). Dining: restaurant/café meals.\n"
        "- Healthcare: medicine, vitamins, supplements, protein powder, pharmacy items. Photos: photo printing/services. Discounts: coupons, vouchers, negative discount lines.\n"
        "- null for missing fields\n\n"
        "Return ONLY the JSON array — no markdown, no explanation.\n\n"
    )
    sections = "\n\n".join(f"=== RECEIPT {i+1} ===\n{t}" for i, t in enumerate(texts))
    return header + sections


def _pdf_text(pdf_path: Path) -> str:
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


def _sdk_extract_pdf(pdf_path: Path) -> str:
    import anthropic
    text = _pdf_text(pdf_path)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=RECEIPT_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": f"{RECEIPT_TEXT_PROMPT}\n\n---\n{text}"}],
    )
    return response.content[0].text


def _cli_extract_pdf(pdf_path: Path) -> str:
    text = _pdf_text(pdf_path)
    # Windows CreateProcess limit ~32 KB — keep prompt + text well under that
    MAX_TEXT_CHARS = 12_000
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n[... truncated ...]"
    full_prompt = f"{RECEIPT_TEXT_PROMPT}\n\n---\n{text}"
    result = subprocess.run(
        ["claude", "-p", full_prompt],
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"`claude` CLI returned exit {result.returncode}:\n{result.stderr[:500]}")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("`claude` CLI returned empty output")
    return output


PDF_BATCH_SIZE = 5          # max PDFs per Claude call
MAX_PER_RECEIPT = 2_500    # chars of receipt text per slot
MAX_BATCH_CHARS = 15_000   # combined text budget per batch


def _cli_extract_pdf_batch_chunk(paths: list[Path]) -> list[dict]:
    """One CLI call for a chunk of PDFs (already sized to fit). Returns list aligned with paths."""
    texts = []
    for p in paths:
        t = _pdf_text(p)
        if len(t) > MAX_PER_RECEIPT:
            t = t[:MAX_PER_RECEIPT] + "\n[... truncated ...]"
        texts.append(t)

    prompt = _build_batch_prompt(texts)
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"`claude` CLI returned exit {result.returncode}:\n{result.stderr[:500]}")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("`claude` CLI batch returned empty output")

    items = _extract_json_array(output)
    if len(items) != len(paths):
        raise ValueError(f"Batch returned {len(items)} results for {len(paths)} receipts")
    return items


def _cli_extract_pdf_batch(paths: list[Path]) -> list[dict]:
    """Batch all PDFs across multiple CLI calls of PDF_BATCH_SIZE each."""
    results = []
    for i in range(0, len(paths), PDF_BATCH_SIZE):
        chunk = paths[i : i + PDF_BATCH_SIZE]
        results.extend(_cli_extract_pdf_batch_chunk(chunk))
    return results


def extract_receipts_pdf_batch(paths: list[Path], backend: str = "sdk") -> list[dict]:
    """Batch-extract multiple PDF receipts (CLI: batched; SDK: serial)."""
    if backend == "sdk" or len(paths) == 1:
        return [_extract_json(_sdk_extract_pdf(p) if backend == "sdk" else _cli_extract_pdf(p)) for p in paths]
    return _cli_extract_pdf_batch(paths)


def extract_receipt(path: Path, backend: str = "sdk") -> dict:
    """Extract receipt data from an image (JPG/PNG/WEBP) or digital PDF."""
    is_pdf = path.suffix.lower() == ".pdf"
    if is_pdf:
        raw = _sdk_extract_pdf(path) if backend == "sdk" else _cli_extract_pdf(path)
    else:
        raw = _sdk_extract(path) if backend == "sdk" else _cli_extract(path)
    return _extract_json(raw)


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
