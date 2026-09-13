"""
core/schemas.py — Shared Pydantic models for receipt extraction.

Imported by all platform adapters (claude, antigravity, ollama) so the
data contract is defined once. The structure mirrors the JSON the model
is asked to return in RECEIPT_PROMPT.
"""

from pydantic import BaseModel


class ReceiptItem(BaseModel):
    raw_name: str
    clean_name: str
    category: str
    qty: float = 1.0
    unit_price: float | None = None
    total: float
    vat_rate: str


class ReceiptData(BaseModel):
    store: str
    store_chain: str
    address: str | None = None
    date: str
    time: str | None = None
    items: list[ReceiptItem]
    subtotal: float | None = None
    vat: dict | None = None        # {"7pct": float | null, "19pct": float | null}
    total: float
    payment_method: str
    item_count: int | None = None
