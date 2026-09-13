"""
core/prompts.py — Shared receipt extraction prompts used by all platform adapters.
"""

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

RECEIPT_TEXT_PROMPT = RECEIPT_PROMPT + """
The receipt data is provided as extracted text below (not an image).
Parse it the same way — extract all fields and return the same JSON structure.
"""

_BATCH_SCHEMA = """{
  "store": "...", "store_chain": "...", "address": "...", "date": "YYYY-MM-DD",
  "time": "HH:MM", "items": [{"raw_name":"...","clean_name":"...","category":"...","qty":1,"unit_price":0.0,"total":0.0,"vat_rate":"7%"}],
  "subtotal": 0.0, "vat": {"7pct": 0.0, "19pct": 0.0}, "total": 0.0,
  "payment_method": "girocard", "item_count": 0
}"""


def _build_batch_prompt(texts: list[str]) -> str:
    """Build a Claude CLI batch prompt that requests a JSON array of N receipt objects."""
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
