"""Step 4: Title Rewrite — generate new title via LLM, write via Formily.

The key anti-duplicate step. Title must:
  - Preserve high-CTR keywords from original
  - Be 100-128 characters
  - Differ significantly from source in word order/combination
  - Only modify the English main title (not other languages)
"""

import json
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import TitleGenerationFailed


def step4_rewrite_title(zc: ZClawClient, ctx: ListingContext,
                        new_title: str = None) -> dict:
    """Rewrite the product title.

    Args:
        new_title: If provided, use this title directly.
                   If None, read current title and suggest rewrite.
    """
    # Read current title
    original = zc.execute_script(
        "return (window.__form__ && window.__form__.values.title) || ''"
    )
    if isinstance(original, str):
        original = original.strip()

    if not original:
        raise TitleGenerationFailed("Cannot read current title from form")

    ctx.source_product_name = original
    print(f"  Original: {original[:80]}... ({len(original)} chars)")

    if new_title:
        final_title = new_title
    else:
        # Generate suggestion via AI — for now, apply structural rewrite
        final_title = _generate_title_variant(original)

    # Validate
    if len(final_title) < 100 or len(final_title) > 128:
        raise TitleGenerationFailed(
            f"Generated title is {len(final_title)} chars (need 100-128)"
        )
    if final_title == original:
        raise TitleGenerationFailed("Generated title is identical to original")

    # Write via Formily — target English input specifically
    set_js = f"""
    (function() {{
        var form = window.__form__;
        // Find the English title field (first title input in the form)
        form.setValuesIn('title', {json.dumps(final_title)});
        form.setFieldState('title', function(state) {{
            state.modified = true;
        }});
        return 'ok';
    }})()
    """
    result = zc.execute_script(set_js)

    ctx.new_title = final_title
    print(f"  New: {final_title[:80]}... ({len(final_title)} chars)")
    return {"original": original, "new": final_title, "length": len(final_title)}


def _generate_title_variant(original: str) -> str:
    """Basic structural rewrite preserving keywords.

    Phase 1: rule-based rewrite (no LLM dependency).
    Phase 2: integrate with Claude for quality titles.

    Strategy: extract brand + spec + keywords, reorder.
    """
    # Extract key components
    words = original.replace(",", " ").split()

    # Remove filler words
    filler = {"for", "and", "with", "the", "a", "an", "of", "in", "to", "&"}
    keywords = [w for w in words if w.lower() not in filler]

    if len(keywords) < 5:
        return original  # Too short to meaningfully reorder

    # Simple reorder: move last 3 keywords to front, keep brand first
    brand = keywords[0]
    rest = keywords[1:]
    # Swap middle and end sections
    mid = len(rest) // 2
    reordered = [brand] + rest[mid:] + rest[:mid]

    result = " ".join(reordered)
    # Ensure length is in range
    if len(result) > 128:
        result = result[:125] + "..."
    if len(result) < 100:
        # Pad with category terms
        result += " High Performance Thermal Paste Compound for CPU GPU Cooling"

    return result[:128]


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext(source_product_id="test")
    zc.open_store()
    result = step4_rewrite_title(zc, ctx)
    print(json.dumps(result, indent=2, ensure_ascii=False))
