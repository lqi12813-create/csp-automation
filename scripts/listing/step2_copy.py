"""Step 2: Copy Product — navigate to copy page and verify it's a true copy.

This is the single most critical navigation step. Opening the wrong URL
would edit the original product instead of creating a copy.

CSP's copy function creates a new product based on the source.
The key verification is that the URL contains copyPublish=1.
"""

import re
import time
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import NavigationError, CopyDataCorruption


MANAGE_URL = "/m_apps/productManage/list-manage"


def step2_copy_product(zc: ZClawClient, ctx: ListingContext) -> dict:
    """Navigate to product management, find source product, click Copy.

    Returns dict with copy_page_url for downstream steps.
    """
    source_id = ctx.source_product_id
    if not source_id:
        raise NavigationError("No source product ID set")

    # Navigate to product list
    zc.visit_page(MANAGE_URL)
    time.sleep(2)

    # Search for the source product
    try:
        zc.input_text('input[placeholder*="商品ID"]', source_id)
        time.sleep(1)
    except Exception:
        # Fallback: try Enter key via JS
        zc.execute_script(
            'document.querySelector(\'input[placeholder*="商品"]\').value = arguments[0];'
            'document.querySelector(\'input[placeholder*="商品"]\').dispatchEvent(new Event("input", {bubbles: true}));'
            .replace('arguments[0]', repr(source_id))
        )
        time.sleep(2)

    # Click "复制" or "发布类似产品" on the target product row
    # CSP product management uses action dropdown on each row
    try:
        zc.click_element('text=复制')
    except Exception:
        # Try the more detailed selector pattern
        zc.execute_script(f"""
        (function() {{
            var rows = document.querySelectorAll('.ait-table-row, [class*=productRow]');
            for (var i = 0; i < rows.length; i++) {{
                if (rows[i].textContent.indexOf('{source_id}') > -1) {{
                    var copyBtn = rows[i].querySelector(
                        'button[class*=copy], a[class*=copy], [aria-label*="复制"], [aria-label*="Copy"]'
                    );
                    if (copyBtn) {{ copyBtn.click(); return 'clicked'; }}
                    // Fallback: click "More" then find "Copy" in dropdown
                    var moreBtn = rows[i].querySelector('button[class*=more], [class*=operation] button');
                    if (moreBtn) {{ moreBtn.click(); }}
                    return 'more_clicked';
                }}
            }}
            return 'not_found';
        }})()
        """)
        time.sleep(1)
        # After opening the dropdown, click the copy menu item
        try:
            zc.click_element('text=发布类似产品')
        except Exception:
            zc.click_element('text=Copy')

    time.sleep(2)

    # Verify we're on the copy page
    url_info = zc.execute_script("JSON.stringify({url: location.href, title: document.title})")
    import json
    page = json.loads(url_info) if isinstance(url_info, str) else url_info

    if "copyPublish=1" not in page.get("url", ""):
        raise NavigationError(
            f"Not on copy page. URL: {page.get('url', '?')}. "
            "Likely opened edit mode instead. Abort to avoid modifying original."
        )

    ctx.copy_page_url = page["url"]
    print(f"  Copy page opened: {page.get('title', '?')}")

    # Verify Formily is ready
    form_ready = zc.execute_script(
        "!!(window.__form__ && window.__form__.values && window.__form__.values.sku)"
    )
    if not form_ready:
        raise FormilyNotReady("Formily form not initialized — page may still be loading")

    # Check SKU data integrity
    sku_check = zc.execute_script("""
    (function() {
        var form = window.__form__;
        var skus = form.values.sku || [];
        var empty = skus.filter(function(s) {
            return !s.price && !s.retailPrice && !s.skuCode;
        });
        return JSON.stringify({total: skus.length, empty: empty.length, ok: empty.length === 0});
    })()
    """)
    sku_info = json.loads(sku_check) if isinstance(sku_check, str) else {"total": 0, "ok": False}

    if not sku_info.get("ok"):
        raise CopyDataCorruption(
            f"{sku_info.get('empty', '?')} of {sku_info.get('total', '?')} SKUs missing data. "
            "Source product may have complex variants. Try a simpler source."
        )

    print(f"  SKUs: {sku_info['total']} total, all data intact")
    return {"copy_page_url": page["url"], "sku_count": sku_info["total"]}


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext(source_product_id=sys.argv[1] if len(sys.argv) > 1 else "1005002225761891")
    zc.open_store()
    result = step2_copy_product(zc, ctx)
    print(json.dumps(result, indent=2, ensure_ascii=False))
