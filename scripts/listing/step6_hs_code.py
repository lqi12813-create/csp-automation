"""Step 6: HS Code Fix — reset customs classification after title/image changes.

CSP's HS Code field loses its configuration when title or images change.
This step uses a two-phase fix:
  1. UI: Clear existing tag + click "去设置" to trigger server-side reset
  2. Formily: Verify the reset populated correctly, force re-sync if needed

The Formily API is the definitive fix when the UI approach doesn't sync.
"""

import json
import time
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import HSCodeFixFailed


def step6_hs_code_fix(zc: ZClawClient, ctx: ListingContext) -> dict:
    """Fix HS Code configuration via UI reset + Formily sync."""

    # Step 1: Check current status
    status = zc.execute_script("""
    (function() {
        var form = window.__form__;
        var hsValue = form.getValuesIn('usHsCode');
        var hsState = form.getFieldState('usHsCode');
        var keys = hsValue ? Object.keys(hsValue) : [];
        // Detect stub: has 'version' but no 'hsCode' (real HS code data)
        var isStub = keys.indexOf('hsCode') === -1 && keys.length <= 2;
        return JSON.stringify({
            configured: !!(hsValue && keys.length > 0),
            is_stub: isStub,
            has_errors: !!(hsState && hsState.errors && hsState.errors.length > 0),
            errors: hsState?.errors || []
        });
    })()
    """)
    hs_status = json.loads(status) if isinstance(status, str) else {}

    if hs_status.get("configured") and not hs_status.get("has_errors") and not hs_status.get("is_stub"):
        print("  HS Code already configured and valid — skipping")
        ctx.hs_code_status = "ok"
        return {"fixed": False, "reason": "already_ok"}

    # Step 2: UI — Clear existing tag
    zc.execute_script("""
    (function() {
        var closeBtn = document.querySelector(
            '.struct-usHsCode .ait-tag-close-icon, ' +
            '[class*=hsCode] [class*=close], ' +
            '[class*=hsCode] [class*=remove]'
        );
        if (closeBtn) closeBtn.click();
        return 'cleared';
    })()
    """)
    time.sleep(0.5)

    # Step 3: UI — Click "去设置"
    zc.execute_script("""
    (function() {
        var section = document.querySelector('.struct-usHsCode, [class*=hsCode]');
        if (!section) return 'no_section';
        var buttons = section.querySelectorAll('button');
        var setupBtn = Array.from(buttons).find(function(b) {
            return b.textContent.includes('去设置') || b.textContent.includes('设置');
        });
        if (setupBtn) { setupBtn.click(); return 'clicked'; }
        return 'not_found';
    })()
    """)
    time.sleep(2)

    # Step 4: Formily — Verify and force sync
    verify_js = """
    (function() {
        var form = window.__form__;
        var hsValue = form.getValuesIn('usHsCode');
        if (!hsValue || Object.keys(hsValue).length === 0) {
            return JSON.stringify({error: 'HS Code still empty after UI reset'});
        }

        // Re-sync: force Formily to recognize the updated value
        form.setValuesIn('usHsCode', Object.assign({}, hsValue));
        form.setFieldState('usHsCode', function(state) {
            state.modified = true;
            state.errors = [];
        });
        form.validate('usHsCode');

        var finalState = form.getFieldState('usHsCode');
        var errors = (finalState && finalState.errors) || [];
        return JSON.stringify({
            ok: errors.length === 0,
            errors: errors,
            configured: true
        });
    })()
    """
    result_json = zc.execute_script(verify_js)
    result = json.loads(result_json) if isinstance(result_json, str) else {}

    if result.get("error"):
        raise HSCodeFixFailed(
            f"HS Code fix failed: {result['error']}. "
            "Try manually clearing and re-setting in CSP."
        )

    if not result.get("ok"):
        ctx.hs_code_status = "errors"
        raise HSCodeFixFailed(
            f"HS Code has validation errors after reset: {result.get('errors', [])}"
        )

    ctx.hs_code_status = "ok"
    print("  HS Code: configured and verified")
    return {"fixed": True, "status": "ok"}


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext(source_product_id="test")
    zc.open_store()
    result = step6_hs_code_fix(zc, ctx)
    print(json.dumps(result, indent=2))
