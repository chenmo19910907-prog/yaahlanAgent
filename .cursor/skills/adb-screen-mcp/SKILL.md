---
name: adb-screen-mcp
description: >-
  通过 MCP adb-screen 读真机屏幕：adb_observe / adb_observe_wait 返回 Activity、
  ui.clickables 与 PNG 截图；tap/swipe 后接 observe_wait。设备须 USB 连接且 adb devices 为 device。
---

# ADB Screen MCP（Cursor 读屏）

## 何时使用

- 真机探索、页面学习、验证 macro 落点
- 需要 **Cursor 直接看到屏幕**（MCP 返回 JSON + PNG），不必手动 `capture` 再 Read 文件
- `tap` / `macro` 之后用 **`adb_observe_wait`** 等界面稳定

## 前置

1. 手机已连接：`adb devices` → `device`
2. MCP 已配置（见 `adb/mcp_adb_screen/mcp_config_example.json`）
3. 首次安装依赖：

```bash
cd adb/mcp_adb_screen
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

将 `mcp_config_example.json` 合并到 Cursor **Settings → MCP**（或 `~/.cursor/mcp.json`），改 `command` 为本机 `.venv/bin/python3` 绝对路径。

## 工具

| MCP 工具 | 作用 |
|----------|------|
| `adb_devices` | 列设备 |
| `adb_observe` | Activity + ui.clickables + 截图 |
| `adb_observe_wait` | 等界面变化后再 observe |
| `adb_activity` | 仅 Activity（快） |
| `adb_tap` / `adb_swipe` | 单步操作 |

## Agent 工作流

```text
adb_observe（默认 fast、无截图，~0.5s）
  → 原生页：读 ui.clickables
  → WebView：includeImage=true
adb_tap / macro
  → adb_observe_wait（timeoutSec 5–8）
```

## 与 CLI 等价

| MCP | CLI |
|-----|-----|
| `adb_observe` | `observe` 或 `observe --fast` |
| `adb_observe` + 截图 | `observe --image` |
| `adb_observe_wait` | `observe --wait 8` |

## 更多

- 页面学习流程：技能 `adb-page-learn`
- 抓包验收：技能 `adb-tunnel-verify`
