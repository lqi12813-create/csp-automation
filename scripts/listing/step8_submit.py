"""Step 8: Submit Listing — click submit button and navigate two-layer dialog chain.

This is the only truly UI-dependent step. CSP's submit flow has two modals:
  1. "确认绑定货品" → click "确 认" (note: space in button text)
  2. "确认提交" → click "确认提交"

After success, the URL changes to /publish-success with a new productId.

Failure cases are classified via CSP_ERROR_MAP and return typed errors.
"""

import json
import time
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import (
    SubmitRejected, DialogChainBroken, classify_submit_error,
)


def step8_submit(zc: ZClawClient, ctx: ListingContext, max_retries: int = 2) -> dict:
    """Submit the listing. Returns new product ID on success."""

    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"  Retry {attempt}/{max_retries}...")
            time.sleep(2)

        try:
            return _do_submit(zc, ctx)
        except DialogChainBroken:
            if attempt == max_retries:
                raise
            # Clean up stuck modals before retry
            zc.execute_script(
                "document.querySelectorAll('.ait-modal-root, .ait-modal-mask')"
                ".forEach(function(el) { el.remove(); })"
            )
            time.sleep(1)

    raise SubmitRejected("Max retries exhausted", csp_error_code="unknown")


def _do_submit(zc: ZClawClient, ctx: ListingContext) -> dict:
    # Step 1: Click submit button
    submit_clicked = zc.execute_script("""
    (function() {
        var buttons = document.querySelectorAll('button');
        var submit = null;
        for (var i = buttons.length - 1; i >= 0; i--) {
            if (buttons[i].textContent.indexOf('提 交') > -1 ||
                buttons[i].textContent.indexOf('提交') > -1) {
                submit = buttons[i];
                break;
            }
        }
        if (submit) {
            submit.scrollIntoView({block: 'center'});
            submit.click();
            return 'clicked';
        }
        return 'not_found';
    })()
    """)

    if submit_clicked != "clicked":
        raise DialogChainBroken("Submit button not found")

    time.sleep(2)

    # Step 2: Dialog 1 — "确认绑定货品"
    _handle_dialog(zc, "确 认", "确认绑定货品")
    time.sleep(1.5)

    # Step 3: Dialog 2 — "确认提交"
    _handle_dialog(zc, "确认提交", "确认提交")
    time.sleep(3)

    # Step 4: Verify success
    page_state = zc.execute_script("""
    JSON.stringify({
        url: location.href,
        title: document.title,
        body_text: document.body.textContent.substring(0, 500)
    })
    """)
    state = json.loads(page_state) if isinstance(page_state, str) else {}

    body = state.get("body_text", "")
    url = state.get("url", "")

    # Success: URL changes to show the new product ID (different from copy source)
    # or redirects to product management page
    import re
    m = re.search(r'productId=(\d+)', url)
    new_id = m.group(1) if m else None

    if "publish-success" in url or "productManage" in url:
        ctx.new_product_id = new_id or "unknown"
        print(f"  ✅ Submitted! New product ID: {ctx.new_product_id}")
        return {"success": True, "product_id": ctx.new_product_id, "url": url}

    # Success: product ID changed (no redirect but different productId in URL)
    if new_id and new_id != ctx.source_product_id:
        ctx.new_product_id = new_id
        print(f"  ✅ Submitted! New product ID: {new_id}")
        return {"success": True, "product_id": new_id, "url": url}

    # Also check for success message in body
    if "成功" in body and ("发布" in body or "上架" in body):
        print(f"  ✅ Success detected in body text")
        ctx.new_product_id = new_id or "pending_verification"
        return {"success": True, "product_id": ctx.new_product_id, "url": url}

    # Check for error messages
    if any(kw in body for kw in ["CHK_", "error", "失败", "Error"]):
        raise classify_submit_error(body)

    raise SubmitRejected(
        f"Unknown submit result. URL: {url}",
        csp_error_code="unknown",
    )


def _handle_dialog(zc, button_text: str, dialog_name: str):
    """Handle a modal dialog by clicking the confirmation button.

    CSP modals don't use .ait-modal-root — buttons are in generic overlay containers.
    We search all visible buttons on the page for the target text.
    """
    clicked = zc.execute_script(f"""
    (function() {{
        // Search ALL visible buttons for the target text
        var buttons = document.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {{
            if (buttons[i].offsetParent !== null &&
                buttons[i].textContent.indexOf('{button_text}') > -1) {{
                buttons[i].click();
                return 'clicked';
            }}
        }}
        return 'not_found';
    }})()
    """)

    if clicked != "clicked":
        raise DialogChainBroken(
            f"Dialog '{dialog_name}' button '{button_text}' not found. "
            f"JS result: {clicked}"
        )


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext(
        source_product_id=sys.argv[1] if len(sys.argv) > 1 else "test",
    )
    zc.open_store()
    result = step8_submit(zc, ctx)
    print(json.dumps(result, indent=2))
