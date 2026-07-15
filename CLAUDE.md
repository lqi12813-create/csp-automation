# CSP Automation

Coxbyte 速卖通 POP 店铺自动化系统。此 repo 是 Claude Code（执行层）和 Hermes（控制层）的共享上下文源。

## 架构

```
Claude Code (Mac) ──执行──→ N100 (Windows)
                              ├─ 影刀 RPA (MCP :3002)
                              ├─ 紫鸟 ZClaw (:9481) → CSP
                              └─ OpenClaw AI Agent (:18789)

n8n (虾仁机 :5678) ──编排──→ yingdao-bridge (Mac :3099) → 影刀

Hermes (Mac, launchd) ──飞书 bot──→ 用户通知/交互
```

## N100 连接

SSH tunnel via launchd plist `~/Library/LaunchAgents/ai.hermes.yingdao-tunnel.plist`:

| Mac Port | N100 Target | Service |
|----------|------------|---------|
| 3002 | 127.0.0.1:3000 | yingdao-mcp-server |
| 9481 | 127.0.0.1:9481 | 紫鸟 ZClaw Bridge |
| 18789 | 127.0.0.1:18789 | OpenClaw Gateway |

SSH 必须绕过 SOCKS5: `env -u ALL_PROXY -u HTTPS_PROXY -u HTTP_PROXY ssh ADMIN@100.92.208.37`

## 店铺

### Coxbyte (主店)
- storeId: `26800521299080`
- 类型: POP + 半托管
- CSP Channel: 211341
- 登录: coxbyte01@163.com / Zs110110
- 紫鸟 IP: 47.106.97.34
- ZClaw API Key: `znoc_piaRcrovW7bZKRUA8FJHuHEMpqej7D4PjfPLIE-zQaheTeeS`

### 关键财务参数
- 平台费率: 17%（实测，非 12%）
- 退款率: 9.3%
- 合计扣除率: 34.3%
- POP 物流中位数: ¥40.5
- 半托管物流中位数: ¥38.1
- 净利公式: `净利 = 售价 × 0.657 - 成本 - 物流费`

### 整改状态 (2026-07-14)
全店 29 SKU 亏损，月亏 ¥15-20K。整改计划 9 个 Phase 待执行。详见 Obsidian `运营知识/Coxbyte 店铺状态快照 2026-07-14.md`

## ZClaw 操作

```
POST http://localhost:9481/zclaw/tools/invoke
Headers: Content-Type: application/json, X-ZClaw-Api-Key: znoc_...

工具: list_stores, open_store, visit_page, execute_script,
      click_element, input_text, take_screenshot, extract_data
```

CSP 是 SPA，直接 URL 会 404，必须通过首页 JS 导航。ZClaw 可过 AliExpress Layer2 (baxia/umid)。

## 影刀 RPA

- MCP server: yingdao-mcp-server v0.0.1, 端口 3000
- 创业版 v6.2.19, 路径 E:\ShadowBot\
- 工具: queryApplist, runApp, queryRobotParam
- Bot 目录: `apps/{name}_Release/xbot_robot/{package.json, main.js}`
- 创业版 child_process 可用，用 cmd /c wmic 代替 PowerShell

### 已有 Bot
| Bot | UUID | 功能 |
|-----|------|------|
| test_hello | test-hello-0001 | 管道验证 |
| system_health | system-health-0001 | N100 健康监控 |

## n8n

- 地址: http://100.99.113.26:5678
- Yingdao RPA Bridge workflow: `thZ6N5ytejHJL9ub` (POST /webhook/yingdao-run)
- N100 Health Check workflow: `rmkJckAcelr9sqOM` (GET /webhook/n100-health)

## 飞书

Hermes bot: app_id `cli_a9618e990238dccc`, WebSocket 模式
lark-cli: `lark-cli im +messages-send --chat-id oc_4a5f4cda0599518b492939f71e4d3b96 --markdown "..."`
Feishu Base「平台运营日志」: app_token `Oi3Zb7gsca4a1HsISOYcOTCDnJc`

## 目录结构

```
csp-automation/
  CLAUDE.md          ← 本文件，共享上下文
  n8n/               ← n8n 工作流 JSON 导出
  yingdao-bots/      ← 影刀 bot 源码 (package.json + main.js)
  scripts/           ← ZClaw 采集/操作脚本
  reports/           ← 日报模板
```

## 约定

- 所有敏感信息（API key, 密码）已在 CLAUDE.md 中，不再放 .env
- n8n 工作流修改后导出到 n8n/ 目录并提交
- 影刀 bot 源码放 yingdao-bots/{bot_name}/
- ZClaw 脚本用 Python（方便 Hermes 调用）
- git commit 用中文，描述做什么而非怎么做
