"""CSP Listing Orchestrator — coordinates 8-step listing flow via ZClaw.

The FSM ensures linear progression through steps with checkpoint saves at each transition.
Interrupted listings can be resumed from the last saved state.

Usage:
  python3 -m listing.listing_orchestrator --product-id 1005002225761891
  python3 -m listing.listing_orchestrator --source-sku TG30-4g
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from zclaw_client import ZClawClient


# ── State Machine ──────────────────────────────────────────────

class ListingState(Enum):
    INIT = "init"
    PRODUCT_SELECTED = "product_selected"
    COPY_OPENED = "copy_opened"
    IMAGE_CHANGED = "image_changed"
    TITLE_REWRITTEN = "title_rewritten"
    SKU_DIFFED = "sku_diffed"
    HS_CODE_FIXED = "hs_code_fixed"
    VALIDATED = "validated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    FAILED = "failed"
    CANCELLED = "cancelled"


TRANSITIONS = {
    ListingState.INIT: [ListingState.PRODUCT_SELECTED],
    ListingState.PRODUCT_SELECTED: [ListingState.COPY_OPENED],
    ListingState.COPY_OPENED: [ListingState.IMAGE_CHANGED, ListingState.FAILED],
    ListingState.IMAGE_CHANGED: [ListingState.TITLE_REWRITTEN],
    ListingState.TITLE_REWRITTEN: [ListingState.SKU_DIFFED],
    ListingState.SKU_DIFFED: [ListingState.HS_CODE_FIXED],
    ListingState.HS_CODE_FIXED: [ListingState.VALIDATED],
    ListingState.VALIDATED: [ListingState.AWAITING_CONFIRMATION],
    ListingState.AWAITING_CONFIRMATION: [ListingState.SUBMITTING, ListingState.CANCELLED],
    ListingState.SUBMITTING: [ListingState.SUBMITTED, ListingState.FAILED],
    ListingState.FAILED: [ListingState.INIT],  # Can retry from scratch
    ListingState.CANCELLED: [ListingState.INIT],
}


# ── Listing Context ─────────────────────────────────────────────

@dataclass
class ListingContext:
    store_id: str = "26800521299080"
    store_name: str = "Coxbyte Store"
    channel_id: str = "211341"

    # Product
    source_product_id: str = ""
    source_product_name: str = ""
    copy_page_url: str = ""

    # Anti-duplicate
    new_title: str = ""
    sku_suffix: str = "-R1"
    image_count: int = 0
    image_changed: bool = False

    # Validation
    hs_code_status: str = "unknown"
    validation_errors: list = field(default_factory=list)
    validation_checks: dict = field(default_factory=dict)

    # Profit
    projected_margin: float = 0.0
    projected_net_profit: float = 0.0

    # State
    state: str = "init"
    created_at: str = ""
    updated_at: str = ""
    errors: list = field(default_factory=list)

    # Result
    new_product_id: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def touch(self):
        self.updated_at = datetime.now().isoformat()

    def to_dict(self):
        return asdict(self)


# ── Orchestrator ────────────────────────────────────────────────

class ListingOrchestrator:
    def __init__(self, store_id: str = "26800521299080",
                 checkpoint_dir: str = None):
        self.zc = ZClawClient(store_id=store_id)
        self.ctx = ListingContext(store_id=store_id)
        self._state = ListingState.INIT
        self.checkpoint_dir = os.path.expanduser(
            checkpoint_dir or "~/.csp-actions"
        )

    @property
    def state(self) -> ListingState:
        return self._state

    def _transition(self, to_state: ListingState):
        if to_state not in TRANSITIONS.get(self._state, []):
            raise ValueError(
                f"Invalid transition: {self._state.value} → {to_state.value}"
            )
        self._state = to_state
        self.ctx.state = to_state.value
        self.ctx.touch()
        self._save_checkpoint()

    def _save_checkpoint(self):
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        path = os.path.join(
            self.checkpoint_dir,
            f"listing_{self.ctx.source_product_id or 'new'}.json"
        )
        with open(path, "w") as f:
            json.dump(self.ctx.to_dict(), f, indent=2, ensure_ascii=False)

    def _mark_failed(self, error: Exception):
        self.ctx.errors.append({
            "state": self._state.value,
            "error": str(error),
            "time": datetime.now().isoformat(),
        })
        self._state = ListingState.FAILED
        self.ctx.state = self._state.value
        self._save_checkpoint()
        print(f"  ❌ Failed at {self._state.value}: {error}")

    def run_step(self, step_name: str, step_fn, *args, **kwargs):
        """Execute a step with error handling and state transition."""
        print(f"[{step_name}] Running...")
        try:
            result = step_fn(self.zc, self.ctx, *args, **kwargs)
            print(f"[{step_name}] ✅ OK")
            return result
        except Exception as e:
            self._mark_failed(e)
            raise

    def load_checkpoint(self, product_id: str) -> bool:
        path = os.path.join(
            self.checkpoint_dir, f"listing_{product_id}.json"
        )
        if not os.path.exists(path):
            return False
        with open(path) as f:
            data = json.load(f)
        self.ctx = ListingContext(**data)
        self._state = ListingState(data.get("state", "init"))
        print(f"Resumed from checkpoint: {self._state.value}")
        return True


# ── Convenience runner ──────────────────────────────────────────

def run_listing(source_product_id: str,
                store_id: str = "26800521299080",
                sku_suffix: str = "-R1",
                new_title: str = None,
                skip_image: bool = False,
                dry_run: bool = False):
    """Run a full listing flow from init to submit.

    This is the entry point for the complete 8-step listing workflow.
    """
    from listing.step1_select import step1_select_product
    from listing.step2_copy import step2_copy_product
    from listing.step3_image import step3_change_image
    from listing.step4_title import step4_rewrite_title
    from listing.step5_sku_diff import step5_sku_diff
    from listing.step6_hs_code import step6_hs_code_fix
    from listing.step7_validate import step7_validate
    from listing.step8_submit import step8_submit
    from listing.error_handler import ListingError

    orch = ListingOrchestrator(store_id=store_id)

    # Check for existing checkpoint
    if orch.load_checkpoint(source_product_id):
        print(f"Resumed listing for product {source_product_id}")
    else:
        orch.ctx.source_product_id = source_product_id
        orch.ctx.sku_suffix = sku_suffix

    try:
        # Open store
        orch.zc.open_store()

        # Run steps in sequence
        orch.zc.open_store()
        state = orch.state

        if state in (ListingState.INIT,):
            print("\n-- Step 1: Select Product --")
            orch.run_step("step1", step1_select_product)
            orch._transition(ListingState.PRODUCT_SELECTED)
            state = orch.state

        if state == ListingState.PRODUCT_SELECTED:
            print("\n-- Step 2: Copy Product --")
            orch.run_step("step2", step2_copy_product)
            orch._transition(ListingState.COPY_OPENED)
            state = orch.state

        if state == ListingState.COPY_OPENED:
            if not skip_image:
                print("\n-- Step 3: Change Image --")
                orch.run_step("step3", step3_change_image)
            else:
                print("\n-- Step 3: Change Image -- [SKIPPED]")
            orch._transition(ListingState.IMAGE_CHANGED)
            state = orch.state

        if state == ListingState.IMAGE_CHANGED:
            print("\n-- Step 4: Rewrite Title --")
            orch.run_step("step4", step4_rewrite_title, new_title=new_title)
            orch._transition(ListingState.TITLE_REWRITTEN)
            state = orch.state

        if state == ListingState.TITLE_REWRITTEN:
            print("\n-- Step 5: SKU Differentiation --")
            orch.run_step("step5", step5_sku_diff)
            orch._transition(ListingState.SKU_DIFFED)
            state = orch.state

        if state == ListingState.SKU_DIFFED:
            print("\n-- Step 6: HS Code Fix --")
            orch.run_step("step6", step6_hs_code_fix)
            orch._transition(ListingState.HS_CODE_FIXED)
            state = orch.state

        if state == ListingState.HS_CODE_FIXED:
            print("\n-- Step 7: Validation --")
            orch.run_step("step7", step7_validate)
            orch._transition(ListingState.VALIDATED)
            state = orch.state

        if state == ListingState.VALIDATED:
            orch._transition(ListingState.AWAITING_CONFIRMATION)
            print(f"\n{'='*50}")
            print(f"READY TO SUBMIT")
            print(f"  Product: {orch.ctx.source_product_name[:60]}")
            print(f"  Title: {orch.ctx.new_title[:80]}")
            print(f"  SKU suffix: {orch.ctx.sku_suffix}")
            print(f"  HS Code: {orch.ctx.hs_code_status}")
            print(f"  Validation: {'PASS' if not orch.ctx.validation_errors else 'WARNINGS'}")
            print(f"{'='*50}")

            if dry_run:
                print("[DRY RUN] Stopping before submit.")
                return orch

            print("\n-- Step 8: Submit --")
            orch.run_step("step8", step8_submit)
            orch._transition(ListingState.SUBMITTED)
            print(f"\n[OK] LISTING COMPLETE!")
            print(f"  New product ID: {orch.ctx.new_product_id}")

    except ListingError as e:
        orch._mark_failed(e)
        print(f"\n❌ LISTING FAILED: {e}")
        if e.action == "retry":
            print("  → Retryable. Run again to resume from checkpoint.")
        elif e.action == "manual":
            print(f"  → Manual fix needed: {getattr(e, 'detail_hint', '')}")
        raise

    return orch


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CSP Listing Orchestrator")
    parser.add_argument("--product-id", required=True, help="Source product ID to clone")
    parser.add_argument("--store-id", default="26800521299080")
    parser.add_argument("--suffix", default="-R1", help="SKU code suffix")
    parser.add_argument("--skip-image", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_listing(
        source_product_id=args.product_id,
        store_id=args.store_id,
        sku_suffix=args.suffix,
        skip_image=args.skip_image,
        dry_run=args.dry_run,
    )
