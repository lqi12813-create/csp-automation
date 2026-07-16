"""Step 3: Image Change — delete main image to trigger CSP auto-promote.

The simplest anti-duplicate image strategy: delete the main image
and CSP automatically promotes the next image (product back view)
to become the new main image. No file upload needed.

Risks:
  - If only 1 image exists: skip (no backup to promote)
  - If main and backup are the same image: warn, skip
"""

import json
import time
from zclaw_client import ZClawClient
from listing import ListingContext
from listing.error_handler import ImageOperationFailed


def step3_change_image(zc: ZClawClient, ctx: ListingContext) -> dict:
    """Delete main image, letting CSP auto-promote the backup.

    Returns dict with image_count and changed flag.
    """
    # Step 1: Count images and check backup
    image_info = zc.execute_script("""
    (function() {
        var items = document.querySelectorAll(
            '.mainImageSection .sell-o-image-item, ' +
            '[class*=mainImage] [class*=imageItem], ' +
            '.image-upload-container img'
        );
        if (items.length === 0) {
            items = document.querySelectorAll('[class*=image] img[src]');
        }
        var urls = [];
        items.forEach(function(img, i) {
            urls.push({index: i, src: (img.src || '').substring(0, 100)});
        });
        return JSON.stringify({count: urls.length, images: urls});
    })()
    """)
    info = json.loads(image_info) if isinstance(image_info, str) else {}

    count = info.get("count", 0)
    images = info.get("images", [])

    if count <= 1:
        print("  ⚠ Only 1 image — skipping (no backup to promote)")
        ctx.image_count = count
        return {"changed": False, "reason": "single_image", "count": count}

    # Check if main and backup are the same
    if len(images) >= 2 and images[0].get("src") == images[1].get("src"):
        print("  ⚠ Main and backup images are identical — skipping")
        ctx.image_count = count
        return {"changed": False, "reason": "identical_images", "count": count}

    # Step 2: Delete main image
    result = zc.execute_script("""
    (function() {
        // Find the delete/remove button on first image
        var firstImage = document.querySelector(
            '.mainImageSection .sell-o-image-item:first-child .image-upload-remove, ' +
            '[class*=mainImage] [class*=remove], ' +
            '[class*=image] [class*=delete]'
        );
        if (!firstImage) {
            // Try hover to reveal the delete button
            var img = document.querySelector(
                '.mainImageSection .sell-o-image-item:first-child'
            );
            if (img) {
                img.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
            }
            // Wait a frame then try again
            setTimeout(function() {
                var btn = document.querySelector(
                    '.mainImageSection .image-upload-remove, ' +
                    '[class*=image] [class*=trash], ' +
                    '[class*=image] [class*=delete]'
                );
                if (btn) btn.click();
            }, 300);
            return 'hovered';
        }
        firstImage.click();
        return 'clicked';
    })()
    """)

    time.sleep(1.5)

    # Step 3: Verify image changed
    verify_json = zc.execute_script("""
    (function() {
        var items = document.querySelectorAll(
            '.mainImageSection .sell-o-image-item img, ' +
            '[class*=mainImage] img'
        );
        return JSON.stringify({count: items.length, first_src: items[0]?.src?.substring(0, 80) || 'none'});
    })()
    """)
    verify = json.loads(verify_json) if isinstance(verify_json, str) else {}

    new_count = verify.get("count", 0)
    changed = new_count < count  # We deleted one

    ctx.image_count = new_count
    ctx.image_changed = changed

    if changed:
        print(f"  Image changed: {count} → {new_count} (auto-promoted backup)")
    else:
        raise ImageOperationFailed(
            f"Image deletion didn't reduce count ({count} → {new_count}). "
            "The delete button may not have worked."
        )

    return {"changed": changed, "old_count": count, "new_count": new_count}


if __name__ == "__main__":
    import sys
    zc = ZClawClient()
    ctx = ListingContext(source_product_id="test")
    zc.open_store()
    result = step3_change_image(zc, ctx)
    print(json.dumps(result, indent=2))
