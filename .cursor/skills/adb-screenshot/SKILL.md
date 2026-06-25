---
name: adb-screenshot
description: 通过无线 ADB 截取 Android 测试机整屏。支持按资产编号、mmuid、无线地址查找设备。在需要远程查看测试机当前画面、验收 UI 或对照测试用例时使用。
---

# 无线 ADB 整屏截图

## 何时使用

- 需要查看 **Android 测试机当前整屏**（含系统弹窗、通知栏、非 App 界面）
- 用户提供 **资产编号**、**mmuid/mmuidv3** 或 **无线 adb 地址**
- 测试机 **不 USB 连接本机**，但已配置无线调试且网络可达

## 前置条件

1. 本机已安装 `adb`（Android Platform Tools）
2. `AdbScreenshot/wireless_devices.json` 已配置（从 `wireless_devices.example.json` 复制）
3. 手机已开启无线调试；首次需 QA 执行 `adb pair` + `adb connect`
4. MCP `adb-screenshot` 已在 `.cursor/mcp.json` 配置

## MCP 工具

| 工具 | 说明 |
|------|------|
| `list_wireless_devices` | 列出登记表 |
| `adb_devices` | 当前 adb 在线设备 |
| `connect_wireless` | `adb connect host:port` |
| `screenshot` | 整屏截图，返回 JSON + PNG 图片 |

### screenshot 参数（四选一）

- `asset_id`：资产编号，如 `GZ3025010018`
- `mmuid`：mmuid 或 mmuidv3
- `address`：无线地址 `192.168.x.x:5555`
- `name`：设备名称模糊匹配

## CLI 备用

```bash
python3 AdbScreenshot/adb_screenshot_execute.py --screenshot --asset GZ3025010018
```

## 详细文档

见 [AdbScreenshot/README.md](../../../AdbScreenshot/README.md)
