"""Reproducible synthetic feed generator."""
import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def generate(directory: str | Path, records: int = 40, seed: int = 1729) -> dict[str, int]:
    out = Path(directory); out.mkdir(parents=True, exist_ok=True)
    ref = out.parent / "reference"; ref.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed); count_a = (records + 1) // 2; count_b = records // 2
    categories = ["electronics", "home", "apparel", "books"]
    a_rows, b_rows = [], []
    mappings = {}
    product_count = max(1, records // 4) if records else 0
    for i in range(product_count):
        canonical = f"product-{i:06d}"
        mappings[f"supplier_a:A-{i:06d}"] = canonical
        mappings[f"supplier_b:B{i:06d}"] = canonical
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for i in range(count_a):
        product = i % max(1, records // 4)
        a_rows.append({"source_record_id": f"A-{i:07d}", "sku": f"A-{product:06d}", "name": f"Item {product:04d}", "category": categories[product % 4], "price": f"{round(rng.uniform(2, 500), 2)}", "currency": "USD", "updated_at": (start + timedelta(minutes=i)).isoformat().replace("+00:00", "Z")})
    for i in range(count_b):
        product = i % max(1, records // 4)
        b_rows.append({"source_record_id": f"B-{i:07d}", "item_code": f"B{product:06d}", "title": f"Item {product:04d}", "department": categories[(product + (i % 5 == 0)) % 4], "amount": round(rng.uniform(2, 500), 2), "currency": "USD", "updated_at": (start + timedelta(minutes=count_a + i)).isoformat().replace("+00:00", "Z")})
    with (out / "supplier_a.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(a_rows[0]) if a_rows else ["source_record_id", "sku", "name", "category", "price", "currency", "updated_at"])
        writer.writeheader(); writer.writerows(a_rows)
    (out / "supplier_b.json").write_text(json.dumps(b_rows, indent=2) + "\n", encoding="utf-8")
    (ref / "product_mappings.json").write_text(json.dumps(mappings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"supplier_a": len(a_rows), "supplier_b": len(b_rows), "input_records": len(a_rows) + len(b_rows), "expected_unique_products": len(set(mappings.values()))}
