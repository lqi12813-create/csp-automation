"""ZClaw Bridge API client — reusable wrapper for all CSP automation scripts.

Usage:
  from zclaw_client import ZClawClient
  zc = ZClawClient(store_id="26800521299080")
  zc.open_store()
  zc.visit_page("/m_apps/sycm/HomeNew")
  result = zc.execute_script("document.title")
"""

import json
import os
import subprocess
import time
from typing import Optional


class ZClawError(Exception):
    pass


class ZClawClient:
    def __init__(self, store_id: str = "26800521299080"):
        self.store_id = store_id
        self.base_url = "http://localhost:9481"
        self.api_key = self._load_api_key()
        self._opened = False

    def _load_api_key(self) -> str:
        # Try env var first, then config file
        key = os.environ.get("ZCLAW_API_KEY")
        if key:
            return key
        config_path = os.path.expanduser("~/.zclaw/config.json")
        if os.path.exists(config_path):
            with open(config_path) as f:
                return json.load(f)["ZCLAW_API_KEY"]
        raise ZClawError("ZCLAW_API_KEY not found in env or ~/.zclaw/config.json")

    def _invoke(self, tool: str, args: dict, timeout: int = 30) -> dict:
        body = json.dumps({"tool": tool, "args": {**args, "storeId": self.store_id}})
        r = subprocess.run(
            [
                "curl", "-s", "-X", "POST",
                f"{self.base_url}/zclaw/tools/invoke",
                "-H", "Content-Type: application/json",
                "-H", f"X-ZClaw-Api-Key: {self.api_key}",
                "-d", body,
                "--max-time", str(timeout),
            ],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        try:
            result = json.loads(r.stdout)
        except json.JSONDecodeError:
            raise ZClawError(f"ZClaw returned non-JSON: {r.stdout[:200]}")
        if result.get("ret") != 0:
            raise ZClawError(f"ZClaw error: {result.get('msg', result)}")
        return result

    def open_store(self, launch_url: Optional[str] = None):
        args = {"storeId": self.store_id}
        if launch_url:
            args["launchUrl"] = launch_url
        self._invoke("open_store", args, timeout=60)
        self._opened = True

    def visit_page(self, path_or_url: str):
        url = path_or_url if path_or_url.startswith("http") else f"https://csp.aliexpress.com{path_or_url}"
        if "channelId" not in url and "?" not in url:
            url += "?channelId=211341"
        elif "channelId" not in url:
            url += "&channelId=211341"
        result = self._invoke("visit_page", {
            "storeId": self.store_id,
            "url": url,
        })
        title = result.get("data", {}).get("title", "?")
        print(f"  Navigated: {title}")
        return result

    def execute_script(self, script: str, timeout: int = 30):
        """Run arbitrary JS in the CSP page. Returns parsed result."""
        result = self._invoke("execute_script", {
            "storeId": self.store_id,
            "script": script,
        }, timeout=timeout)
        return result["data"]["data"]["result"]

    def click_element(self, selector_or_text: str, timeout: int = 30):
        """Click an element by CSS selector or visible text."""
        result = self._invoke("click_element", {
            "storeId": self.store_id,
            "selector": selector_or_text,
        }, timeout=timeout)
        return result

    def input_text(self, selector: str, text: str, timeout: int = 30):
        """Type text into an input field."""
        result = self._invoke("input_text", {
            "storeId": self.store_id,
            "selector": selector,
            "text": text,
        }, timeout=timeout)
        return result

    def take_screenshot(self) -> str:
        """Return base64-encoded PNG screenshot."""
        result = self._invoke("take_screenshot", {"storeId": self.store_id})
        return result.get("data", {}).get("data", {}).get("image", "")

    def list_stores(self):
        return self._invoke("list_stores", {})

    def extract_data(self, script: Optional[str] = None, timeout: int = 30):
        """Extract structured data from page."""
        args = {"storeId": self.store_id}
        if script:
            args["script"] = script
        return self._invoke("extract_data", args, timeout=timeout)


# Quick self-test
if __name__ == "__main__":
    zc = ZClawClient()
    stores = zc.list_stores()
    print(f"Connected. {len(stores.get('data', {}).get('stores', []))} stores available.")
    print("ZClaw client ready.")
