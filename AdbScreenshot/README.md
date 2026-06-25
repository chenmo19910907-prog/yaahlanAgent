# 无线 ADB 整屏截图（AdbScreenshot）

通过 **无线 ADB** 截取 Android 测试机 **整屏画面**（系统 `screencap`，不限于单个 App）。适合偶尔人工验收：产品在 Cursor 发指令，QA 维护设备无线地址登记表。

## 前置条件

| 项 | 要求 |
|----|------|
| 电脑 | 已安装 [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)（`adb` 在 PATH） |
| 手机 | Android 11+ 推荐；已开启 **开发者选项 → 无线调试** |
| 网络 | 电脑与手机在同一内网 / VPN，能访问 `手机IP:端口` |
| 登记表 | `wireless_devices.json`（不入 Git） |

## 1) 一次性配置

```bash
cp AdbScreenshot/wireless_devices.example.json AdbScreenshot/wireless_devices.json
# 编辑 wireless_devices.json，填写 asset_id、wireless（IP:端口）、mmuidv3

cp AdbScreenshot/.env.example AdbScreenshot/.env.local   # 可选
```

### 手机端：开启无线调试

1. **设置 → 开发者选项 → 无线调试** → 开启  
2. 点 **使用配对码配对设备**，记下 `IP:配对端口` 和 6 位配对码  
3. 在电脑上执行（仅需首次或重连后）：

```bash
adb pair 192.168.x.x:37123
# 输入配对码

adb connect 192.168.x.x:5555
adb devices
```

应看到 `192.168.x.x:5555    device`。

> 不同机型「连接端口」与「配对端口」可能不同，以手机界面显示为准。

## 2) CLI 用法

```bash
# 列出登记表
python3 AdbScreenshot/adb_screenshot_execute.py --list-registry

# 当前 adb 在线设备
python3 AdbScreenshot/adb_screenshot_execute.py --adb-devices

# 连接无线设备
python3 AdbScreenshot/adb_screenshot_execute.py --connect 192.168.1.100:5555

# 整屏截图（按资产编号）
python3 AdbScreenshot/adb_screenshot_execute.py \
  --screenshot --asset GZ3025010018

# 按 mmuidv3
python3 AdbScreenshot/adb_screenshot_execute.py \
  --screenshot --mmuid e75bd8f8d89459a58fb16cda276e17d4...

# 直接指定地址
python3 AdbScreenshot/adb_screenshot_execute.py \
  --screenshot --address 192.168.1.100:5555
```

截图默认保存到 `~/Desktop/adb-screenshots/`。

成功时输出 JSON，含 `output_path` 字段。

## 3) Cursor MCP

在 `.cursor/mcp.json` 增加（需先安装依赖）：

```bash
python3 -m venv .cursor/skills/adb-screenshot/mcp_adb_screenshot/venv
.cursor/skills/adb-screenshot/mcp_adb_screenshot/venv/bin/pip install -r \
  .cursor/skills/adb-screenshot/mcp_adb_screenshot/requirements.txt
```

```json
"adb-screenshot": {
  "command": ".cursor/skills/adb-screenshot/mcp_adb_screenshot/venv/bin/python3",
  "args": [".cursor/skills/adb-screenshot/mcp_adb_screenshot/server.py"]
}
```

对 Agent 说：

> 资产编号 GZ3025010018，无线 adb 截屏

或：

> mmuid 是 xxx，截一下当前手机整屏

## 4) 登记表字段

| 字段 | 说明 |
|------|------|
| `asset_id` | 资产编号，与《团队测试机统计表》一致 |
| `name` | 设备名称 |
| `wireless` | 无线 adb 地址 `IP:端口` |
| `mmuidv3` | Android 设备标识，便于按 mmuid 查找 |
| `serial` | 可选；已连接后的 adb serial，默认用 wireless |
| `note` | 备注 |

## 5) 常见问题

| 现象 | 处理 |
|------|------|
| `未找到 adb 命令` | 安装 Platform Tools 或设置 `ADB_BINARY` |
| `unable to connect` | 检查 VPN/同网段、无线调试是否开启、是否需重新 `adb pair` |
| `未找到可用设备` | 先 `--connect`，或 `--adb-devices` 确认状态为 `device` |
| `登记表不存在` | 复制 `wireless_devices.example.json` → `wireless_devices.json` |
| 截到黑屏 | 部分机型锁屏时如此；解锁后再截 |

## 6) 安全说明

- `wireless_devices.json` 含内网 IP，**勿提交 Git**  
- 仅用于 **测试机**；截图可能包含通知、聊天等敏感信息，注意内网传递与及时删除  
- 截图目录建议定期清理  

## 7) 与 Risk 模块的关系

资产编号、`mmuid`/`mmuidv3` 与 [Risk/README.md](../Risk/README.md) 中《团队测试机统计表》一致；无线 IP 需在本模块 `wireless_devices.json` 单独维护（xlsx 通常不含 adb 地址）。
