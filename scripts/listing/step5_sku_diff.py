"""Step 5: SKU Code Differentiation — append suffix to all SKU codes via Formily.

This step uses Formily API (window.__form__) to bulk-modify SKU codes,
bypassing the virtual scroll issue entirely. Also adjusts pricing
if not locked by campaigns.

Formily API operations:
  - form.values.sku                → read full SKU array (all variants)
  - form.setValuesIn('sku', [...]) → write modified array
  - form.setFieldState('sku', fn)  → mark field as modified
"""

import json
import time
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import SkuDiffFailed


def step5_sku_diff(zc: ZClawClient, ctx: ListingContext,
                   price_increase_pct: float = 0.06,
                   stock_increase: int = 5) -> dict:
    """Append suffix to all SKU codes, optionally adjust prices and stock.

    Args:
        price_increase_pct: Percentage to increase prices (default 6%)
        stock_increase: Units to add to stock (never decrease)
    """
    suffix = ctx.sku_suffix

    # Step 1: Read current SKU state
    # CSP Formily uses: skuPrice, skuStock/skuTotalStock, cargoPrice, salePrice
    sku_state_json = zc.execute_script("""
    (function() {
        var form = window.__form__;
        if (!form) return JSON.stringify({error: 'Formily not ready'});
        var skus = form.values.sku || [];
        var summary = skus.map(function(s, i) {
            return {
                index: i,
                skuOuterId: s.skuOuterId || '',
                price: s.skuPrice || s.salePrice || 0,
                stock: s.skuStock || s.skuTotalStock || 0,
                priceDisabled: !!document.querySelector('[class*=price][disabled]')
            };
        });
        return JSON.stringify({total: skus.length, skus: summary});
    })()
    """)
    sku_data = json.loads(sku_state_json) if isinstance(sku_state_json, str) else {}

    if "error" in sku_data:
        raise SkuDiffFailed(f"Cannot read SKU data: {sku_data['error']}")

    total = sku_data.get("total", 0)
    if total == 0:
        raise SkuDiffFailed("No SKUs found in form — corrupted copy?")

    print(f"  Found {total} SKUs")

    # Step 2: Build modified SKU array
    # We pass the suffix to JS to avoid re-serializing the entire array
    modify_js = f"""
    (function() {{
        var form = window.__form__;
        var skus = form.values.sku;
        var changed = 0;
        var skipPrice = false;

        skus.forEach(function(sku) {{
            // Only modify SKU codes that don't already have this suffix
            if (sku.skuOuterId && !sku.skuOuterId.endsWith('{suffix}')) {{
                sku.skuOuterId = sku.skuOuterId + '{suffix}';
                changed++;
            }}
            // Adjust price if not locked (CSP uses skuPrice/salePrice)
            var priceField = sku.skuPrice || sku.salePrice;
            if (!document.querySelector('[class*=price][disabled]') && priceField > 0) {{
                var newPrice = Math.ceil(priceField * {1 + price_increase_pct} * 100) / 100;
                if (sku.skuPrice !== undefined) sku.skuPrice = newPrice;
                // Remove salePrice — B-type products don't support promotional pricing
                if (sku.salePrice !== undefined) delete sku.salePrice;
            }} else {{
                skipPrice = true;
            }}
            // Increase stock (CSP uses skuStock/skuTotalStock, never decrease)
            if (sku.skuStock !== undefined) {{
                sku.skuStock = (sku.skuStock || 0) + {stock_increase};
            }} else if (sku.skuTotalStock !== undefined) {{
                sku.skuTotalStock = (sku.skuTotalStock || 0) + {stock_increase};
            }}
        }});

        form.setValuesIn('sku', skus.map(function(s) {{ return {{...s}}; }}));
        form.setFieldState('sku', function(state) {{ state.modified = true; }});

        return JSON.stringify({{changed: changed, total: skus.length, skipPrice: skipPrice}});
    }})()
    """
    result_json = zc.execute_script(modify_js)
    result = json.loads(result_json) if isinstance(result_json, str) else {}

    changed = result.get("changed", 0)
    if changed < total:
        print(f"  ⚠ {total - changed} SKUs unchanged (may already have suffix)")

    if result.get("skipPrice"):
        print("  ⚠ Price adjustment skipped (campaign lock detected)")

    # Step 3: Verify changes persisted
    time.sleep(0.5)
    verify_json = zc.execute_script(f"""
    (function() {{
        var form = window.__form__;
        var skus = form.values.sku;
        var ok = skus.every(function(s) {{
            return (s.skuOuterId || '').endsWith('{suffix}');
        }});
        return JSON.stringify({{ok: ok, total: skus.length}});
    }})()
    """)
    verify = json.loads(verify_json) if isinstance(verify_json, str) else {}

    if not verify.get("ok"):
        raise SkuDiffFailed(
            f"SKU suffix verification failed. "
            f"Expected all {total} SKUs to end with '{suffix}'."
        )

    print(f"  {total} SKUs differentiated (suffix: {suffix})")
    return {"sku_count": total, "suffix": suffix, "codes_modified": changed}


if __name__ == "__main__":
    import sys
    from listing import ListingContext
    zc = ZClawClient()
    ctx = ListingContext(
        source_product_id=sys.argv[1] if len(sys.argv) > 1 else "test",
        sku_suffix=sys.argv[2] if len(sys.argv) > 2 else "-R1",
    )
    zc.open_store()
    zc.visit_page(f"/ait/cn_pop/item_product/product_publish?copyPublish=1&productId={ctx.source_product_id}")
    time.sleep(3)
    result = step5_sku_diff(zc, ctx)
    print(json.dumps(result, indent=2))
