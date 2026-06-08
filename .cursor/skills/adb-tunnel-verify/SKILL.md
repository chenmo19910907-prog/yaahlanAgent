---
name: adb-tunnel-verify
description: ADB 真机操作 + Tunnel 抓包校验。已实现脚本的能力先抓包验收、失败再读图；未实现脚本可抓包+读图并用；提交表单优先抓包（Toast 等不以读图为主）。
---

# ADB + Tunnel 校验（抓包优先）

## 原则

1. **操作前**记录 `start_time`（CLI 自动回溯 5s）
2. **执行** `macro`（逐段）或 `chain`（低层步骤 JSON，调试慎用）
3. **关键节点弹窗** → `popup analyze` 或 `run --popup-scene`（先抓包再决定是否关）
4. **验收分情形**：
   - **脚本已实现**（`tunnelVerify` / 已知 API）→ **先** `tunnel wait` 或看 `tunnelVerify.ok`（可 `--no-capture`）；**失败再**读 `screenshot.path` 排查
   - **脚本未实现**（探索）→ **抓包 + 读图并用**（定坐标、看页面、看接口）
   - **提交表单**（Save/Post/Send/登录）→ **优先**等写接口（`updateUserBase`、`feed`、`gift/send` 等），不以 Toast 读图为准
5. **判定**：tunnel OK + exit `0` → 成功；exit `3` → 先判失败，再读图分析原因
6. **读图兜底**：抓包失败排查、`weakUiPopups`、探索定坐标
7. **波轮/滚动列表**：先固定距离滑 1 次标定步长 → 读图算剩余次数 → 小步微调；日期/年龄注意三列 x 坐标；保存后 `updateUserBase` 抓包验收

## 弹窗分析（先抓包，再关弹窗）

| scene | 时机 |
|-------|------|
| `login` | 登录后进首页 |
| `home` | 底栏/首页 |
| `me` | 进 Me |
| `room` | 进房 |
| `mic` | 开麦 |

```bash
python3 adb/adb_execute.py popup analyze \
  --scene me --account familyLeader --since 120 --capture

# 有抓包信号才点 Cancel；无信号则 --skip dismiss_popup_taps 等价逻辑
python3 adb/adb_execute.py popup analyze \
  --scene login --account familyLeader --auto-dismiss --capture
```

读 `popupAnalysis.agentHint` 与 `weakUiPopups`；规则见 `adb/录制脚本/弹窗抓包信号.json`。

## 推荐命令（一体化）

```bash
python3 adb/adb_execute.py run \
  --macro 手机号登录 \
  --text 13311111112 \
  --tunnel-account familyLeader \
  --popup-scene login \
  --popup-auto-dismiss
```

```bash
python3 adb/adb_execute.py run \
  --macro 切换房间底栏 \
  --tunnel-account familyLeader \
  --tunnel-keyword heartbeat \
  --popup-scene room \
  --tunnel-wait 20
```

```bash
python3 adb/adb_execute.py run \
  --macro 发布纯文本动态 \
  --text 1234 \
  --tunnel-account familyLeader \
  --tunnel-keyword feed
```

多步流程：**逐段 macro + 片段间验收**，禁止长命令串联或已移除的 `compose`。

## 在 macro 上挂 Tunnel 参数

```bash
python3 adb/adb_execute.py macro 手机号登录 \
  --tunnel-account familyLeader \
  --tunnel-keyword login \
  --tunnel-wait 30
```

| 参数 | 说明 |
|------|------|
| `--tunnel-account` | `索引.json` → `testAccounts` 键，如 `familyLeader` |
| `--tunnel-momoid` | 直接指定 userId |
| `--tunnel-keyword` | URL 子串（**客户端过滤**，不依赖 tunnel 服务端 keyword） |
| `--tunnel-wait` | 最长等待秒数 |
| `--tunnel-expect-ec` | 可选，校验 `response.ec` |
| `--tunnel-expect-status` | HTTP status，`-1` 表示不校验 |

## 仅 Tunnel 等待（UI 已手动完成）

```bash
python3 adb/adb_execute.py tunnel wait \
  --account familyLeader \
  --keyword sendGift \
  --since 300 \
  --wait 30
```

## 输出解读

```json
{
  "screenshot": { "path": "adb/screenshots/screen_....png" },
  "tunnelVerify": {
    "ok": true,
    "matchedCount": 1,
    "matches": [{ "url": "...", "status": 200, "responseEc": 200 }]
  }
}
```

- exit `0`：tunnel 匹配 → **成功**（已实现脚本不必读图）
- exit `3`：tunnel 未匹配 → **先失败**，再读 `screenshot.path` 排查
- 无脚本/无接口：抓包与读图同时参考；提交表单以写接口 `matches` / `responseEc` 为准

## 账号映射

见 `adb/录制脚本/索引.json` → `testAccounts`：

| 键 | userId | 说明 |
|----|--------|------|
| `guildLeader` | 100465989 | 公会长 13311111111 |
| `familyLeader` | 100486375 | 家族长 13311111112 |

## 礼物面板（getGiftTabListV3）

打开**橙色礼物盒**（非快捷礼物）后：

```bash
python3 adb/adb_execute.py gift panel analyze --account familyLeader --since 120
python3 adb/adb_execute.py gift panel find --account familyLeader --price 99 --tab Gift
```

- **左右滑** Tab 栏 ↔ `tab_name`
- **上下滑** 礼物格 ↔ `list[index]`（4 列网格）；用 `matches[].navigation.swipeUpTimes` 估算上滑次数

## 相关文档

- [adb/README.md](../../../adb/README.md)
- [adb/录制脚本/礼物面板抓包.md](../../../adb/录制脚本/礼物面板抓包.md)
- [Tunnel/README.md](../../../Tunnel/README.md)
- [Tunnel/使用方法.md](../../../Tunnel/使用方法.md)
