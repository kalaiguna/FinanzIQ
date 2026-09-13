"""
Unit tests for deterministic logic — no AI calls, no subprocess, no real file I/O.

Covered:
  core/adapter.py          — _auto_detect(), get_adapter()
  parsers/receipt_parser.py — _extract_json(), _extract_json_array(),
                               _build_batch_prompt(), validate_receipt()
  process_payslip.py       — classify_pdf()
  core/schemas.py          — ReceiptItem, ReceiptData (Pydantic validation)
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

# ── core/adapter ──────────────────────────────────────────────────────────────
from core.adapter import _auto_detect, get_adapter

# ── receipt_parser (pure helpers) ─────────────────────────────────────────────
from parsers.receipt_parser import (
    _build_batch_prompt,
    _extract_json,
    _extract_json_array,
    validate_receipt,
)

# ── process_payslip (classify_pdf only) ───────────────────────────────────────
from process_payslip import classify_pdf

# ── Pydantic schemas ──────────────────────────────────────────────────────────
from core.schemas import ReceiptData, ReceiptItem


# =============================================================================
# core/adapter.py — _auto_detect()
# =============================================================================

class TestAutoDetect:

    def test_gemini_api_key_wins(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "key123"}, clear=True):
            with patch("core.adapter.shutil.which", return_value=None):
                assert _auto_detect() == "antigravity"

    def test_anthropic_api_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-123"}, clear=True):
            with patch("core.adapter.shutil.which", return_value=None):
                assert _auto_detect() == "claude"

    def test_claude_on_path(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "core.adapter.shutil.which",
                side_effect=lambda cmd: "/usr/bin/claude" if cmd == "claude" else None,
            ):
                assert _auto_detect() == "claude"

    def test_agy_on_path(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "core.adapter.shutil.which",
                side_effect=lambda cmd: "/usr/bin/agy" if cmd == "agy" else None,
            ):
                assert _auto_detect() == "antigravity"

    def test_ollama_on_path(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "core.adapter.shutil.which",
                side_effect=lambda cmd: "/usr/bin/ollama" if cmd == "ollama" else None,
            ):
                assert _auto_detect() == "ollama"

    def test_nothing_available_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("core.adapter.shutil.which", return_value=None):
                with pytest.raises(RuntimeError, match="No extraction backend"):
                    _auto_detect()

    def test_gemini_key_takes_priority_over_claude_path(self):
        """GEMINI_API_KEY should win even when claude is on PATH."""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "key"}, clear=True):
            with patch("core.adapter.shutil.which", return_value="/usr/bin/claude"):
                assert _auto_detect() == "antigravity"


# =============================================================================
# core/adapter.py — get_adapter()
# =============================================================================

class TestGetAdapter:

    def test_unknown_backend_raises(self):
        with patch.dict(os.environ, {"FINANZIQ_BACKEND": "unknown_xyz"}, clear=True):
            with pytest.raises(ValueError, match="Unknown backend"):
                get_adapter()

    def test_valid_backend_imports_correct_module(self):
        mock_module = MagicMock()
        with patch.dict(os.environ, {"FINANZIQ_BACKEND": "claude"}, clear=True):
            with patch("core.adapter.importlib.import_module", return_value=mock_module) as mock_import:
                result = get_adapter()
                mock_import.assert_called_once_with("platforms.claude.adapter")
                assert result is mock_module

    def test_antigravity_backend(self):
        mock_module = MagicMock()
        with patch.dict(os.environ, {"FINANZIQ_BACKEND": "antigravity"}, clear=True):
            with patch("core.adapter.importlib.import_module", return_value=mock_module) as mock_import:
                get_adapter()
                mock_import.assert_called_once_with("platforms.antigravity.adapter")

    def test_ollama_backend(self):
        mock_module = MagicMock()
        with patch.dict(os.environ, {"FINANZIQ_BACKEND": "ollama"}, clear=True):
            with patch("core.adapter.importlib.import_module", return_value=mock_module) as mock_import:
                get_adapter()
                mock_import.assert_called_once_with("platforms.ollama.adapter")

    def test_backend_env_var_is_case_normalised(self):
        """FINANZIQ_BACKEND value should be lowercased before matching."""
        mock_module = MagicMock()
        with patch.dict(os.environ, {"FINANZIQ_BACKEND": "  Claude  "}, clear=True):
            with patch("core.adapter.importlib.import_module", return_value=mock_module):
                result = get_adapter()
                assert result is mock_module


# =============================================================================
# parsers/receipt_parser.py — _extract_json()
# =============================================================================

class TestExtractJson:

    def test_plain_json_object(self):
        raw = '{"store": "REWE", "total": 10.50}'
        result = _extract_json(raw)
        assert result["store"] == "REWE"
        assert result["total"] == 10.50

    def test_json_in_markdown_fence(self):
        raw = "```json\n{\"store\": \"LIDL\", \"total\": 5.99}\n```"
        result = _extract_json(raw)
        assert result["store"] == "LIDL"

    def test_json_in_plain_fence(self):
        raw = "```\n{\"store\": \"ALDI\"}\n```"
        result = _extract_json(raw)
        assert result["store"] == "ALDI"

    def test_json_with_leading_prose(self):
        raw = "Here is the extracted data:\n{\"store\": \"Herkules\", \"total\": 13.41}"
        result = _extract_json(raw)
        assert result["store"] == "Herkules"
        assert result["total"] == 13.41

    def test_nested_json_extracted_correctly(self):
        raw = '{"store": "X", "items": [{"name": "milk", "total": 1.5}], "total": 1.5}'
        result = _extract_json(raw)
        assert result["items"][0]["name"] == "milk"

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON object"):
            _extract_json("No JSON here at all, just plain text.")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="No JSON object"):
            _extract_json("")


# =============================================================================
# parsers/receipt_parser.py — _extract_json_array()
# =============================================================================

class TestExtractJsonArray:

    def test_plain_array(self):
        raw = '[{"store": "A"}, {"store": "B"}]'
        result = _extract_json_array(raw)
        assert len(result) == 2
        assert result[0]["store"] == "A"
        assert result[1]["store"] == "B"

    def test_array_in_fence(self):
        raw = "```json\n[{\"store\": \"X\"}]\n```"
        result = _extract_json_array(raw)
        assert result[0]["store"] == "X"

    def test_no_array_raises(self):
        with pytest.raises(ValueError, match="No JSON array"):
            _extract_json_array('{"not": "an array"}')

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="No JSON array"):
            _extract_json_array("")


# =============================================================================
# parsers/receipt_parser.py — _build_batch_prompt()
# =============================================================================

class TestBuildBatchPrompt:

    def test_single_text_contains_receipt_marker(self):
        prompt = _build_batch_prompt(["receipt text one"])
        assert "=== RECEIPT 1 ===" in prompt
        assert "receipt text one" in prompt

    def test_two_texts_both_marked(self):
        prompt = _build_batch_prompt(["first receipt", "second receipt"])
        assert "=== RECEIPT 1 ===" in prompt
        assert "=== RECEIPT 2 ===" in prompt
        assert "first receipt" in prompt
        assert "second receipt" in prompt

    def test_count_mentioned_in_header(self):
        prompt = _build_batch_prompt(["a", "b"])
        assert "2" in prompt

    def test_instructs_json_array_output(self):
        prompt = _build_batch_prompt(["receipt"])
        assert "JSON" in prompt or "json" in prompt.lower()

    def test_no_receipt_3_marker_for_two_texts(self):
        prompt = _build_batch_prompt(["a", "b"])
        assert "=== RECEIPT 3 ===" not in prompt

    def test_texts_appear_in_order(self):
        prompt = _build_batch_prompt(["alpha", "beta"])
        assert prompt.index("alpha") < prompt.index("beta")


# =============================================================================
# parsers/receipt_parser.py — validate_receipt()
# =============================================================================

def _make_item(total: float) -> dict:
    return {
        "raw_name": "Item",
        "clean_name": "Item",
        "category": "Other",
        "qty": 1,
        "total": total,
        "vat_rate": "19%",
    }


class TestValidateReceipt:

    def test_exact_match(self):
        data = {"items": [_make_item(5.00), _make_item(5.00)], "total": 10.00}
        ok, note = validate_receipt(data)
        assert ok is True
        assert note == ""

    def test_within_ten_cent_tolerance(self):
        data = {"items": [_make_item(9.95)], "total": 10.00}
        ok, note = validate_receipt(data)
        assert ok is True

    def test_exactly_at_tolerance_boundary(self):
        data = {"items": [_make_item(9.90)], "total": 10.00}
        ok, note = validate_receipt(data)
        assert ok is True  # diff == 0.10, not > 0.10

    def test_exceeds_tolerance(self):
        data = {"items": [_make_item(5.00)], "total": 10.00}
        ok, note = validate_receipt(data)
        assert ok is False
        assert "5.00" in note
        assert "10.00" in note

    def test_no_items_is_valid(self):
        data = {"items": [], "total": 10.00}
        ok, note = validate_receipt(data)
        assert ok is True

    def test_total_none_skips_check(self):
        data = {"items": [_make_item(5.00)], "total": None}
        ok, note = validate_receipt(data)
        assert ok is True

    def test_discount_note_appended(self):
        """When item_sum < receipt_total, no '(discount likely)' hint expected."""
        data = {"items": [_make_item(5.00)], "total": 10.00}
        ok, note = validate_receipt(data)
        assert ok is False
        # item_sum (5) < total (10): no discount hint (hint appears when sum > total)
        assert "discount" not in note

    def test_item_sum_gt_total_hint(self):
        """When items sum exceeds total (discount lines missing), note hints at discount/coupon."""
        data = {"items": [_make_item(20.00)], "total": 15.00}
        ok, note = validate_receipt(data)
        assert ok is False
        assert "discount" in note or "coupon" in note


# =============================================================================
# process_payslip.py — classify_pdf()
# =============================================================================

class TestClassifyPdf:

    def test_brutto(self):
        assert classify_pdf(Path("brutto-netto-2026-07.pdf")) == "payslip"

    def test_netto(self):
        assert classify_pdf(Path("netto_abrechnung.pdf")) == "payslip"

    def test_gehalts(self):
        assert classify_pdf(Path("gehaltsabrechnung_jul26.pdf")) == "payslip"

    def test_abrechnung(self):
        assert classify_pdf(Path("abrechnung_06_2026.pdf")) == "payslip"

    def test_lohn(self):
        assert classify_pdf(Path("lohnabrechnung_2026.pdf")) == "payslip"

    def test_konto(self):
        assert classify_pdf(Path("kontoauszug_2026_07.pdf")) == "bank"

    def test_auszug(self):
        assert classify_pdf(Path("auszug_aug_2026.pdf")) == "bank"

    def test_statement(self):
        assert classify_pdf(Path("bank_statement_jan.pdf")) == "bank"

    def test_unrecognised_defaults_to_bank(self, capsys):
        result = classify_pdf(Path("Jan2024.PDF"))
        assert result == "bank"
        captured = capsys.readouterr()
        assert "bank statement" in captured.out

    def test_case_insensitive_matching(self):
        assert classify_pdf(Path("GEHALTSABRECHNUNG.PDF")) == "payslip"


# =============================================================================
# core/schemas.py — ReceiptItem
# =============================================================================

class TestReceiptItem:

    def test_valid_item(self):
        item = ReceiptItem(
            raw_name="G&G Milch 3,5%",
            clean_name="Whole milk 3.5%",
            category="Dairy",
            qty=2.0,
            unit_price=0.99,
            total=1.98,
            vat_rate="7%",
        )
        assert item.raw_name == "G&G Milch 3,5%"
        assert item.clean_name == "Whole milk 3.5%"
        assert item.qty == 2.0
        assert item.unit_price == 0.99
        assert item.total == 1.98

    def test_default_qty_is_one(self):
        item = ReceiptItem(
            raw_name="Brot",
            clean_name="Bread",
            category="Bakery",
            total=2.50,
            vat_rate="7%",
        )
        assert item.qty == 1.0

    def test_unit_price_optional(self):
        item = ReceiptItem(
            raw_name="Sonderangebot",
            clean_name="Special offer",
            category="Other",
            total=0.99,
            vat_rate="19%",
        )
        assert item.unit_price is None

    def test_missing_raw_name_raises(self):
        with pytest.raises(ValidationError):
            ReceiptItem(
                clean_name="Milk",
                category="Dairy",
                total=1.0,
                vat_rate="7%",
            )

    def test_missing_total_raises(self):
        with pytest.raises(ValidationError):
            ReceiptItem(
                raw_name="Milch",
                clean_name="Milk",
                category="Dairy",
                vat_rate="7%",
            )


# =============================================================================
# core/schemas.py — ReceiptData
# =============================================================================

def _minimal_receipt(**kwargs) -> dict:
    base = dict(
        store="REWE Bad Vilbel",
        store_chain="REWE",
        date="2026-09-01",
        items=[],
        total=0.0,
        payment_method="girocard",
    )
    base.update(kwargs)
    return base


class TestReceiptData:

    def test_minimal_valid(self):
        data = ReceiptData(**_minimal_receipt())
        assert data.store_chain == "REWE"
        assert data.date == "2026-09-01"

    def test_optional_fields_default_none(self):
        data = ReceiptData(**_minimal_receipt())
        assert data.address is None
        assert data.time is None
        assert data.subtotal is None
        assert data.vat is None
        assert data.item_count is None

    def test_vat_none_explicit(self):
        data = ReceiptData(**_minimal_receipt(vat=None))
        assert data.vat is None

    def test_vat_dict_with_pct_keys(self):
        data = ReceiptData(**_minimal_receipt(vat={"7pct": 0.88, "19pct": 0.00}))
        assert data.vat["7pct"] == 0.88
        assert data.vat["19pct"] == 0.00

    def test_items_with_receipt_item(self):
        item = ReceiptItem(
            raw_name="Milch", clean_name="Milk", category="Dairy",
            total=1.09, vat_rate="7%",
        )
        data = ReceiptData(**_minimal_receipt(items=[item], total=1.09))
        assert len(data.items) == 1
        assert data.items[0].clean_name == "Milk"

    def test_missing_store_raises(self):
        d = _minimal_receipt()
        del d["store"]
        with pytest.raises(ValidationError):
            ReceiptData(**d)

    def test_missing_date_raises(self):
        d = _minimal_receipt()
        del d["date"]
        with pytest.raises(ValidationError):
            ReceiptData(**d)
