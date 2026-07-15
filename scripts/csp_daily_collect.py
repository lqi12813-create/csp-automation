#!/usr/bin/env python3
"""CSP 每日数据采集 → Feishu Base「平台运营日志」

用法:
  python3 csp_daily_collect.py                          # 采集昨日数据
  python3 csp_daily_collect.py --store-id 26800521299080  # 指定店铺
  python3 csp_daily_collect.py --store-id 26842255256009  # Fovnx

依赖: ZClaw Bridge on localhost:9481, Feishu token

ZClaw API Key 和 Feishu token 从环境变量或硬编码读取（内网安全）。
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

ZCLAW_URL = "http://localhost:9481/zclaw/tools/invoke"
ZCLAW_KEY = os.environ["ZCLAW_API_KEY"]

FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
FEISHU_BASE_TOKEN = "Oi3Zb7gsca4a1HsISOYcOTCDnJc"
FEISHU_TABLE_ID = "tbljcXcCkhGH03NW"

# CSP 生意参谋页面
CSP_DATA_URL = "https://csp.aliexpress.com/m_apps/sycm/HomeNew"


def zclaw_call(tool, args, timeout=30):
    """Call ZClaw Bridge API."""
    body = json.dumps({"tool": tool, "args": args}).encode("utf-8")
    req = urllib.request.Request(
        ZCLAW_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-ZClaw-Api-Key": ZCLAW_KEY,
        },
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())


def get_feishu_token():
    """Get Feishu tenant access token."""
    body = json.dumps(
        {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())["tenant_access_token"]


def extract_csp_data(store_id):
    """Navigate to CSP 生意参谋 and extract daily metrics."""
    # Open store
    r = zclaw_call("open_store", {"storeId": store_id})
    if r["ret"] != 0:
        raise RuntimeError(f"open_store failed: {r}")

    # Navigate to data overview
    r = zclaw_call("visit_page", {"storeId": store_id, "url": CSP_DATA_URL})
    if r["ret"] != 0:
        raise RuntimeError(f"visit_page failed: {r}")
    print(f"  Navigated: {r['data'].get('title', '?')}")

    # Wait for SPA to render (poll for "昨日全天")
    for attempt in range(10):
        time.sleep(1)
        r = zclaw_call(
            "execute_script",
            {
                "storeId": store_id,
                "script": "document.body.textContent.indexOf('昨日全天') > -1",
            },
        )
        if r["ret"] == 0 and r["data"]["data"].get("result"):
            print(f"  Page ready after {attempt + 1}s")
            break
    else:
        print("  ⚠ Page not ready after 10s, extracting anyway...")

    # Extract page text
    r = zclaw_call(
        "execute_script",
        {
            "storeId": store_id,
            "script": "document.body.textContent.replace(/\\s+/g, ' ').trim()",
        },
    )
    if r["ret"] != 0:
        raise RuntimeError(f"execute_script failed: {r}")
    text = r["data"]["data"]["result"]

    # Parse data from text
    data = {}

    # Yesterday's full-day data (from 实时概况 → 昨日全天)
    for metric, key, pattern in [
        ("支付金额", "gmv", r"支付金额.*?昨日全天\s*([0-9,.]+)"),
        ("访客数", "visitors", r"访客数.*?昨日全天\s*([0-9,.]+)"),
        ("支付买家数", "buyers", r"支付买家数.*?昨日全天\s*([0-9,.]+)"),
        ("支付订单数", "orders", r"支付订单数.*?昨日全天\s*([0-9,.]+)"),
        ("浏览量", "pageviews", r"浏览量.*?昨日全天\s*([0-9,.]+)"),
    ]:
        m = re.search(pattern, text)
        if m:
            try:
                data[key] = float(m.group(1).replace(",", ""))
            except ValueError:
                data[key] = 0
        else:
            data[key] = 0

    # Store tier info (店铺层级)
    m = re.search(r"近30天支付金额\s*([0-9,.]+)", text)
    data["gmv_30d"] = float(m.group(1).replace(",", "")) if m else 0

    m = re.search(r"排行\s*(\d+)\s*名", text)
    data["rank"] = int(m.group(1)) if m else 0

    m = re.search(r"第\s*(\d+)\s*层级", text)
    data["tier"] = int(m.group(1)) if m else 0

    # Calculated fields
    if data.get("orders", 0) > 0:
        data["aov"] = round(data["gmv"] / data["orders"], 2)
    else:
        data["aov"] = 0

    if data.get("visitors", 0) > 0 and data.get("buyers", 0) > 0:
        data["conversion"] = round(data["buyers"] / data["visitors"], 4)
    else:
        data["conversion"] = 0

    print(f"  Yesterday: ${data['gmv']:.2f}, {int(data['orders'])} orders, "
          f"{int(data['visitors'])} visitors, CVR {data['conversion']:.2%}")
    print(f"  Store: tier {data['tier']}, rank {data['rank']}, "
          f"30d GMV ${data['gmv_30d']:.2f}")

    return data


def write_feishu(token, date_ts, data, store_name="Coxbyte Store", platform="AliExpress"):
    """Write daily metrics to Feishu Base."""
    fields = {
        "日期": date_ts,
        "平台": platform,
        "店铺": store_name,
        "GMV (USD)": data["gmv"],
        "订单量": int(data["orders"]),
        "访客数": int(data["visitors"]),
        "转化率": data["conversion"],
        "行业排名": data["rank"],
        "客单价": data["aov"],
        "广告费 (USD)": 0,
        "数据来源": "CSP自动",
        "备注": f"层级:{data['tier']}, 30天GMV:${data['gmv_30d']:.0f}, ZClaw自动采集",
    }

    body = json.dumps({"fields": fields}).encode("utf-8")
    url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/"
        f"{FEISHU_BASE_TOKEN}/tables/{FEISHU_TABLE_ID}/records"
    )
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    resp = urllib.request.urlopen(req, timeout=10)
    result = json.loads(resp.read())
    if result.get("code") != 0:
        raise RuntimeError(f"Feishu write failed: {result}")
    return result["data"]["record"]["record_id"]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CSP daily data → Feishu Base")
    parser.add_argument(
        "--store-id", default="26800521299080", help="紫鸟 storeId (default: Coxbyte)"
    )
    parser.add_argument(
        "--store-name", default="Coxbyte Store", help="Store display name"
    )
    parser.add_argument(
        "--date-ts", type=int, help="Date timestamp in ms (default: yesterday 00:00 UTC)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Extract only, no write")
    args = parser.parse_args()

    if not args.date_ts:
        # Yesterday at 00:00 UTC (in ms)
        import datetime
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        dt = datetime.datetime(yesterday.year, yesterday.month, yesterday.day)
        args.date_ts = int(dt.timestamp() * 1000)

    print(f"=== CSP Daily Collect ===")
    print(f"  Store: {args.store_name} ({args.store_id})")
    print(f"  Date: {args.date_ts}")

    # Step 1: Extract CSP data
    print("[1/3] Extracting CSP data...")
    data = extract_csp_data(args.store_id)

    if args.dry_run:
        print("[DRY RUN] Data extracted, skipping Feishu write.")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    # Step 2: Get Feishu token
    print("[2/3] Getting Feishu token...")
    token = get_feishu_token()

    # Step 3: Write to Feishu Base
    print("[3/3] Writing to Feishu Base...")
    record_id = write_feishu(token, args.date_ts, data, args.store_name)
    print(f"  Done! record_id: {record_id}")


if __name__ == "__main__":
    main()
