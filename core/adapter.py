"""
core/adapter.py — Platform adapter dispatcher.

Selects the extraction backend at runtime via FINANZIQ_BACKEND env var.
If not set, auto-detects based on available API keys and CLI tools.

Usage:
    from core.adapter import get_adapter
    adapter = get_adapter()
    result = adapter.extract_image(image_path, prompt)

Supported backends: claude | antigravity | ollama
"""

import importlib
import os
import shutil
import sys
from pathlib import Path

# Ensure project root is on sys.path so platforms.* resolves correctly
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_SUPPORTED = {"claude", "antigravity", "ollama"}


def _auto_detect() -> str:
    """Infer the best available backend from environment and installed tools."""
    if os.environ.get("GEMINI_API_KEY"):
        return "antigravity"
    if os.environ.get("ANTHROPIC_API_KEY") or shutil.which("claude"):
        return "claude"
    if shutil.which("agy"):
        return "antigravity"
    if shutil.which("ollama"):
        return "ollama"
    raise RuntimeError(
        "No extraction backend detected. Set one of:\n"
        "  FINANZIQ_BACKEND=claude        (+ ANTHROPIC_API_KEY or Claude Code CLI)\n"
        "  FINANZIQ_BACKEND=antigravity   (+ GEMINI_API_KEY from aistudio.google.com)\n"
        "  FINANZIQ_BACKEND=ollama        (+ ollama serve + ollama pull qwen2.5-vl)"
    )


def get_adapter():
    """Return the platform adapter module for the active backend.

    The returned module exposes:
        extract_image(image_path, prompt)       -> str
        extract_pdf_text(text, prompt)          -> str
        extract_pdf_batch(texts, batch_prompt)  -> list[dict]
    """
    backend = os.environ.get("FINANZIQ_BACKEND", "").strip().lower()
    if not backend:
        backend = _auto_detect()

    if backend not in _SUPPORTED:
        raise ValueError(
            f"Unknown backend '{backend}'. Supported: {', '.join(sorted(_SUPPORTED))}"
        )

    return importlib.import_module(f"platforms.{backend}.adapter")
