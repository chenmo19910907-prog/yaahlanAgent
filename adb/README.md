# ADB 截图视觉循环（adb/）

通过 **adb 连手机 → 截图 → Agent 读图算坐标 → 点击** 完成 UI 操作。截图目录默认只保留**最新 2 张**。

## 协作原则（Agent / 人工）

### 积木 + 组合

| 层级 | 目录 | 命令 | 说明 |
|------|------|------|------|
| **片段（积木）** | `录制脚本/片段/<一级模块>/` | `macro <中文名>` | 按发版回归模块分子目录；调用仍用中文名 |
| **组合（配方）** | `录制脚本/组合/<一级模块>/` | `compose <中文名>` | 按模块分子目录；调用仍用中文名 |

路径不确定时：Agent **读图** 判断当前页，再选一块积木或一条组合；不要对每个 `tap` 都截图。

**成功即落库**：真机探索并最终验收成功的操作，须写入 `录制脚本/`（片段 + 索引 + 必要时组合）。细则见 [`录制脚本/README.md`](录制脚本/README.md#成功即落库agent-必做)。

### 截图策略

| 场景 | 做法 |
|------|------|
| **路径确定** | `macro` / `compose` + `--no-capture`（0 张） |
| **需要核对结果** | 默认 `capture: end` 或 `--verify`（结束时 1 张） |
| **探索新页面** | `capture` → 读图 → `tap` → … |

### 截图次数对照（示例：发一条动态）

| 方式 | 截图次数 |
|------|----------|
| 逐步 `capture` + `tap`（旧） | 约 4 次 |
| `macro 发布纯文本动态 --text 1234` | **1 次**（结束时，可 `--no-capture` 为 0） |
| `compose 发布纯文本动态 --text 1234 --no-capture` | **0 次** |

## 目标 App

自动化默认 **Yaahlan**（`com.immomo.biz.yaahlan`），不是 **Yaha**（`com.immomo.yaha`）。片段 **启动Yaahlan** 会 force-stop Yaha 后以 LAUNCHER 启动前者。

**开屏广告**：组合 **冷启动登录** 含 **跳过开屏广告**。无跳过按钮时用 `--skip dismiss_splash_ad`。详见 [`录制脚本/README.md`](录制脚本/README.md#开屏广告约-5s)。

**未登录**：`compose 冷启动登录` 或 `macro 手机号登录`。默认 **+86**、验证码 **000000**、QA 手机 **13311111115**（见 [`录制脚本/KB对照.md`](录制脚本/KB对照.md)）。

## 设备型号适配（换机必读）

`tap_pct` 按 **基准设备.json**（默认 1080×2340）录制。

1. `device info` — 查是否已有档案  
2. **已有** → 直接 `macro` / `compose`  
3. **无档案** → `device calibrate` → `commit`  
4. **操作失败** → `device recalibrate` → `commit --reason correction`  

详见 [`录制脚本/设备适配/README.md`](录制脚本/设备适配/README.md)。

## 前置条件

- 已安装 `adb`（Android platform-tools）
- 手机 USB 调试已开启，或 `adb connect <ip>:5555`
- `adb devices` 中状态为 `device`

## 单步命令

```bash
python3 adb/adb_execute.py devices
python3 adb/adb_execute.py capture
python3 adb/adb_execute.py tap 540 1200
python3 adb/adb_execute.py key 4    # BACK
python3 adb/adb_execute.py info
```

## 录制脚本库 `录制脚本/`

```bash
python3 adb/adb_execute.py scripts      # 片段 + 组合目录
python3 adb/adb_execute.py composes     # 仅组合

python3 adb/adb_execute.py macro 发布纯文本动态 --text 5555 --no-capture
python3 adb/adb_execute.py compose 冷启动登录
python3 adb/adb_execute.py compose 发布纯文本动态 --text 5555 --no-capture
```

## 连续操作

### 片段 `macro`

```bash
python3 adb/adb_execute.py macro 进入个人资料详情页
python3 adb/adb_execute.py macro 发布纯文本动态 --text 1234 --no-capture
python3 adb/adb_execute.py macro 手机号登录 --skip login_lang
```

### 组合 `compose`

```bash
python3 adb/adb_execute.py compose 冷启动登录
python3 adb/adb_execute.py compose 进入个人资料详情页 --verify
```

### 自定义 `chain`

```bash
python3 adb/adb_execute.py chain adb/录制脚本/片段/我的帧/进入个人资料详情页.json
```

步骤类型：`sleep_ms`、`tap` / `tap_pct`、`swipe`、`key`、`text`、`launch_app`、`run_script`（嵌套片段）。

## 与 Agent 协作示例

**探索新页面**：`capture` → 读图 → `tap` → …

**已知路径**：

```bash
python3 adb/adb_execute.py compose 冷启动登录
python3 adb/adb_execute.py macro post-moment --text 1234 --no-capture
```

## 说明

- 仅支持 **Android + adb**。
- 可选 `--skip`：`dismiss_splash_ad`、`login_lang`、`dismiss_popup_taps` 等（见各片段 `skip_key`）。
- **偶发弹窗**：登录、发动态、进 Me 等流程会执行 **关闭常见弹窗**（先 BACK，再点常见 Cancel）。稳定页且确认无弹窗时可 `--skip dismiss_popup_taps` 只保留 BACK 关层。
