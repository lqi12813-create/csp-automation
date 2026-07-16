"""Error classes and recovery strategies for CSP listing workflow.

Each error type has a specific recovery action. The orchestrator
uses this to decide: retry, skip, abort, or manual fix.
"""

from typing import Optional


class ListingError(Exception):
    """Base class for listing workflow errors."""
    recoverable: bool = True
    retry: bool = False
    action: str = "abort"

    def __init__(self, message: str, detail: Optional[dict] = None):
        super().__init__(message)
        self.detail = detail or {}


class NavigationError(ListingError):
    """Page didn't load, store not open, or wrong page."""
    retry = True
    action = "retry"


class FormilyNotReady(ListingError):
    """window.__form__ is null — SPA not loaded."""
    retry = True
    action = "retry"


class CopyDataCorruption(ListingError):
    """SKU rows missing data after copy — bad source product."""
    action = "retry_alternate"
    detail_hint = "Pick a different source product with fewer SKUs"


class ImageOperationFailed(ListingError):
    """Main image deletion failed or auto-promote didn't work."""
    action = "skip"
    detail_hint = "Skip image change, rely on title + SKU diff for anti-duplicate"


class TitleGenerationFailed(ListingError):
    """LLM title rewrite failed."""
    action = "manual"
    detail_hint = "User must provide a custom title"


class SkuDiffFailed(ListingError):
    """SKU code modification via Formily failed."""
    recoverable = False
    action = "abort"


class HSCodeFixFailed(ListingError):
    """Both UI and Formily approaches for HS Code failed."""
    action = "manual"
    detail_hint = "Check HS Code manually before submitting"


class ValidationFailed(ListingError):
    """Pre-submit checks found blocking issues."""
    action = "report"
    def __init__(self, message: str, failures: list):
        super().__init__(message)
        self.failures = failures


class ProfitGateRejected(ListingError):
    """Projected margin < 0 — listing would lose money."""
    action = "adjust_pricing"
    def __init__(self, message: str, breakeven_prices: dict):
        super().__init__(message)
        self.breakeven_prices = breakeven_prices


class SubmitRejected(ListingError):
    """CSP rejected the submission with a specific error code."""
    action = "fix_and_retry"
    def __init__(self, message: str, csp_error_code: str):
        super().__init__(message)
        self.csp_error_code = csp_error_code


class DialogChainBroken(ListingError):
    """Modal dialog didn't appear or button not clickable."""
    retry = True
    action = "retry"


# Known CSP error codes and their recovery actions
CSP_ERROR_MAP = {
    "CHK_HS_CODE_IS_NULL": ("hs_code", "hs_code_fix"),
    "CHK_NOT_ALLOW_STOCK_REDUCE": ("stock", "restore_stock"),
    "similar_product": ("anti_duplicate", "manual_review"),
    "price_below_threshold": ("pricing", "adjust_price_up"),
}


def classify_submit_error(error_text: str) -> ListingError:
    """Parse CSP submit error and return typed error."""
    for code, (dimension, action) in CSP_ERROR_MAP.items():
        if code in error_text:
            return SubmitRejected(
                f"CSP rejected: {code}",
                csp_error_code=code,
            )
    return SubmitRejected(f"Unknown CSP error: {error_text[:200]}", csp_error_code="unknown")
