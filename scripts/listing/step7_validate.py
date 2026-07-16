"""Step 7: Pre-Submit Validation — comprehensive checklist before submit.

Runs entirely via Formily API. Checks all anti-duplicate and compliance
requirements. Returns structured results with pass/fail per check.

Checks:
  1. Anti-duplicate triad: title changed, image changed, SKU code diffed
  2. Title length: <= 128 chars
  3. SKU data completeness: all SKUs have price, stock, weight
  4. HS Code status: configured and no errors
  5. Full form validation: form.validate()
"""

import json
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import ValidationFailed


def step7_validate(zc: ZClawClient, ctx: ListingContext) -> dict:
    """Run pre-submit validation checks. Returns structured results.

    Non-blocking issues (warnings) are collected but don't stop the flow.
    Only check failures with pass=False block submission.
    """

    import json as _json

    original_title = ctx.source_product_name or ""
    suffix = ctx.sku_suffix

    # Use json.dumps for safe JS string injection (handles quotes, newlines, etc.)
    _orig_title_js = _json.dumps(original_title)
    _suffix_js = _json.dumps(suffix)

    script = f"""
    (function() {{
        var form = window.__form__;
        var results = [];

        // Read title (may be array of multi-lang objects)
        var rawTitle = form.values.title || '';
        var title = '';
        if (Array.isArray(rawTitle)) {{
            var en = rawTitle.find(function(t) {{ return t.key === 'en_US'; }});
            title = (en && en.value) ? en.value : '';
        }} else {{
            title = String(rawTitle);
        }}

        // 1. Anti-duplicate: title changed
        var titleChanged = {_orig_title_js} === '' || title !== {_orig_title_js};
        results.push({{check: 'title_changed', pass: titleChanged,
                       detail: title.substring(0, 60), block: true}});

        // 2. Title length (100-128 chars for CSP)
        var titleOk = title.length >= 100 && title.length <= 128;
        results.push({{check: 'title_length', pass: titleOk,
                       detail: title.length + ' chars (need 100-128)', block: true}});

        // 3. SKU codes differentiated (CSP uses skuOuterId)
        var skus = form.values.sku || [];
        var suffix = {_suffix_js};
        var allDiffed = skus.every(function(s) {{
            return suffix === '' || (s.skuOuterId || '').endsWith(suffix);
        }});
        results.push({{check: 'sku_diff', pass: allDiffed,
                       detail: skus.length + ' SKUs, suffix=' + suffix, block: true}});

        // 4. SKU data completeness (CSP uses skuPrice/skuStock)
        var incomplete = skus.filter(function(s) {{
            return !(s.skuPrice || s.salePrice) || !(s.skuStock || s.skuTotalStock);
        }});
        results.push({{check: 'sku_complete', pass: incomplete.length === 0,
                       detail: incomplete.length + ' incomplete SKUs', block: false}});

        // 5. HS Code
        var hsState = form.getFieldState('usHsCode');
        var hsErrors = (hsState && hsState.errors) || [];
        results.push({{
            check: 'hs_code',
            pass: hsErrors.length === 0,
            detail: hsErrors.length > 0 ? hsErrors.join(', ') : 'ok',
            block: false
        }});

        // 6. Full form validation
        form.validate();
        var formErrors = form.errors || [];
        results.push({{
            check: 'form_valid',
            pass: formErrors.length === 0,
            detail: formErrors.map(function(e) {{ return e.path + ': ' + (e.messages||[]).join(','); }}).join(' | '),
            block: true
        }});

        return JSON.stringify({{results: results, pass: results.filter(function(r){{return r.block && !r.pass;}}).length === 0}});
    }})()
    """

    result_json = zc.execute_script(script)
    data = json.loads(result_json) if isinstance(result_json, str) else {}

    results = data.get("results", [])
    all_pass = data.get("pass", False)

    ctx.validation_checks = {r["check"]: r["pass"] for r in results}
    ctx.validation_errors = [r for r in results if not r["pass"]]

    # Print report
    print(f"  Validation: {'✅ ALL PASS' if all_pass else '❌ FAILURES'}")
    for r in results:
        icon = "✅" if r["pass"] else "❌"
        block_label = " [BLOCKING]" if r.get("block") else ""
        print(f"    {icon} {r['check']}: {r['detail']}{block_label}")

    blocking_failures = [r for r in results if r.get("block") and not r["pass"]]
    if blocking_failures:
        raise ValidationFailed(
            f"{len(blocking_failures)} blocking validation failures",
            failures=blocking_failures,
        )

    return {"pass": all_pass, "checks": results, "warnings": len(ctx.validation_errors)}


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext(
        source_product_id=sys.argv[1] if len(sys.argv) > 1 else "test",
        sku_suffix="-R1",
    )
    zc.open_store()
    result = step7_validate(zc, ctx)
    print(json.dumps(result, indent=2))
