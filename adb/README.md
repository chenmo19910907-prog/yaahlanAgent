# ADB 截图视觉循环（adb/）

通过 **adb 连手机 → 截图 → Agent 读图算坐标 → 点击** 完成 UI 操作。截图目录默认只保留**最新 2 张**。

## 协作原则（Agent / 人工）

### 两阶段（推荐）

| 阶段 | 何时 | 做法 | 截图 |
|------|------|------|------|
| **A 导航** | 当前位置未知 / 不在录制入口 | `flow locate` → 读图 → `flow bootstrap --from <state>` → 再 locate | 仅 locate/bootstrap 边界 |
| **B 录制** | 已对齐 `entry.signals` | `flow run <name>` 执行已录制宏/链 | **默认 0 次**（`--verify` 结束时 1 次） |

详见 [`录制脚本/README.md`](录制脚本/README.md)。

### 单命令快捷

| 场景 | 做法 |
|------|------|
| **路径确定**（已在入口） | `flow run` 或 `macro --no-capture` |
| **路径不确定** | `flow locate` + 知识库 bootstrap，勿每步 `capture` |
| **探索新页面** | `capture` → 读图 → `tap` → … |

不要对每个 `tap` 都截图。

### 截图次数对照（示例：发一条动态）

| 方式 | 截图次数 |
|------|----------|
| 逐步 `capture` + `tap`（旧） | 约 4 次 |
| `macro post-moment --text 1234` | **1 次**（结束时） |
| `macro post-moment --text 1234 --no-capture` | **0 次**（最连贯，不校验画面） |

## 目标 App

自动化默认 **Yaahlan**（`com.immomo.biz.yaahlan`），不是桌面上的 **Yaha**（`com.immomo.yaha`）。`flow bootstrap --from outside_app` 会启动前者。

## 设备型号适配（换机必读）

`tap_pct` 按 **基准设备.json**（默认 1080×2340）录制。

1. `device info` — 按 **设备型号** 查是否已有档案  
2. **已有** → 直接 `macro` / `flow run`（复用已存换算，不重新计算）  
3. **无档案** → `device calibrate` → `set` → `commit`（记入 `档案/` + 型号）  
4. **操作失败** → `device recalibrate` → `commit --reason correction` 更正  

详见 [`录制脚本/设备适配/README.md`](录制脚本/设备适配/README.md)。未建档且分辨率≠基准时 **会拒绝执行** 录制脚本。

## 前置条件

- 已安装 `adb`（Android platform-tools）
- 手机 USB 调试已开启，或 `adb connect <ip>:5555`
- `adb devices` 中状态为 `device`

## 单步命令

```bash
python3 adb/adb_execute.py devices
python3 adb/adb_execute.py capture
python3 adb/adb_execute.py tap 540 1200
python3 adb/adb_execute.py swipe 540 1800 540 600 --duration 400
python3 adb/adb_execute.py key 4    # BACK
python3 adb/adb_execute.py info
python3 adb/adb_execute.py -s <serial> capture
```

## 录制脚本库 `录制脚本/`

```bash
python3 adb/adb_execute.py scripts          # 中文名总目录
python3 adb/adb_execute.py macro 发布纯文本动态 --text 5555
python3 adb/adb_execute.py flow run 发布纯文本动态 --text 5555
```

## 连续操作（推荐）

### 内置宏 `macro`

```bash
# 列出宏
python3 adb/adb_execute.py macros

# 任意底栏页 → 个人资料详情页（仅结束时截一张图）
python3 adb/adb_execute.py macro my-profile

# 无众测弹窗时跳过 Cancel
python3 adb/adb_execute.py macro my-profile --skip dismiss_popup

# 已在 Me 页，只点头像
python3 adb/adb_execute.py macro my-profile-from-me

# 发布纯文本动态（全程一条命令，默认结束时 1 张截图）
python3 adb/adb_execute.py macro post-moment --text 1234

# 完全不截图（Agent 最推荐：路径已验证时）
python3 adb/adb_execute.py macro post-moment --text 1234 --no-capture
```

### 自定义步骤 `chain`

步骤 JSON 见 `adb/录制脚本/片段/`：

```bash
python3 adb/adb_execute.py chain adb/录制脚本/片段/进入个人资料详情页.json
```

步骤类型：

- `sleep_ms`：等待毫秒
- `tap`：`[x, y]` 绝对像素
- `tap_pct`：`[0.9, 0.95]` 相对屏幕宽高（**推荐**，换分辨率仍可用）
- `key`：按键码（4=返回）
- `capture`：链中途强制截屏（少见）
- 文件级 `capture`：`never` | `start` | `end` | `both`（默认 `end`）

## 知识库：进入我的个人主页

回归用例路径（`regression-kb` · 我的帧）：

1. 底部 **Me（我的帧）**
2. 点顶部 **头像** → **个人资料详情页**

对应宏：`macro my-profile`（已按该路径写好相对坐标）。

## 与 Agent 协作示例

**探索新页面**（逐步）：

```text
capture → 读图 → tap → capture → …
```

**已知路径**（一条 macro，中间不截图）：

```bash
# 进个人主页：结束时 1 张图确认
python3 adb/adb_execute.py macro my-profile

# 发动态：0 张图（最快）
python3 adb/adb_execute.py macro post-moment --text 1234 --no-capture
```

## 说明

- 仅支持 **Android + adb**。
- 坐标原点为屏幕左上角；`tap_pct` 与 `wm size` 一致时无需手算像素。
- 可选步骤（如众测弹窗 Cancel）用 `--skip dismiss_popup` 跳过，避免误点。
