"""Step 1: Clone Candidate Selection — extract and rank products for cloning.

Extracts the product table from CSP management page, scores each candidate
on CVR, SKU complexity, order volume, and margin potential.

Returns ranked list. Top candidate auto-selected when score > threshold.
"""

import json
import time
from zclaw_client import ZClawClient
from listing import ListingContext


MANAGE_URL = "/m_apps/productManage/list-manage"


def step1_select_product(zc: ZClawClient, ctx: ListingContext,
                         limit: int = 5) -> list[dict]:
    """Extract and score clone candidates from product management page.

    Returns ranked list of candidates with scores.
    """
    zc.visit_page(MANAGE_URL)
    time.sleep(3)

    # Extract product table
    products_json = zc.execute_script("""
    (function() {
        var rows = document.querySelectorAll('.ait-table-row, [class*=productRow]');
        if (rows.length === 0) {
            rows = document.querySelectorAll('[class*=table] [class*=row]:not([class*=header])');
        }
        var products = [];
        rows.forEach(function(row) {
            var text = row.textContent.replace(/\\s+/g, ' ').trim();
            if (!text || text.length < 10) return;

            // Extract product ID
            var idMatch = text.match(/ID[:\\s]*\\s*(\\d{10,})/);
            var id = idMatch ? idMatch[1] : '';

            // Extract numeric metrics
            var cvrMatch = text.match(/([\\d.]+)%?\\s*转化/);
            var ordersMatch = text.match(/([\\d,]+)\\s*单/);
            var gmvMatch = text.match(/\\$?([\\d,.]+)\\s*GMV|支付金额\\s*([\\d,.]+)/);

            var name = text.split(/ID[:\\s]*\\d+/)[0].trim().substring(0, 100);

            products.push({
                id: id,
                name: name,
                cvr: cvrMatch ? parseFloat(cvrMatch[1]) / (cvrMatch[1].includes('%') ? 100 : 1) : 0,
                orders: ordersMatch ? parseInt(ordersMatch[1].replace(/,/g, '')) : 0,
                gmv: gmvMatch ? parseFloat((gmvMatch[1] || gmvMatch[2]).replace(/,/g, '')) : 0
            });
        });
        return JSON.stringify(products);
    })()
    """)

    products = json.loads(products_json) if isinstance(products_json, str) else []

    if not products:
        print("  ⚠ No products found on management page")
        return []

    # Score and rank
    scored = []
    for p in products:
        if not p["id"]:
            continue

        # Normalized scores (0-1)
        cvr_score = min(p["cvr"] / 0.05, 1.0)  # 5% CVR = perfect
        orders_score = min(p["orders"] / 50, 1.0)  # 50 orders = perfect
        # SKU simplicity: we extract this elsewhere, default to 0.5
        sku_score = 0.5

        # Weighted composite
        overall = (
            cvr_score * 0.30 +
            orders_score * 0.10 +
            sku_score * 0.20
            # margin_target (30%) and risk (10%) come from cost DB (Phase 2)
        ) / 0.60  # Normalize for missing cost/margin data

        p["score"] = round(overall, 3)
        p["scores"] = {"cvr": round(cvr_score, 2), "orders": round(orders_score, 2)}
        scored.append(p)

    scored.sort(key=lambda x: x["score"], reverse=True)
    scored = scored[:limit]

    print(f"  Top {len(scored)} candidates:")
    for i, p in enumerate(scored):
        print(f"    {i+1}. [{p['id']}] score={p['score']:.2f} "
              f"CVR={p['cvr']:.1%} orders={p['orders']} — {p['name'][:50]}")

    # Auto-select best if score is high enough
    if scored and scored[0]["score"] > 0.5:
        best = scored[0]
        ctx.source_product_id = best["id"]
        ctx.source_product_name = best["name"]
        print(f"  → Auto-selected: {best['name'][:60]}")
    else:
        print("  → No strong candidate found. Manual selection recommended.")

    return scored


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext()
    zc.open_store()
    candidates = step1_select_product(zc, ctx)
    print(json.dumps(candidates, indent=2, ensure_ascii=False))
