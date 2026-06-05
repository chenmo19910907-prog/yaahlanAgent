# ADB 截图视觉循环（adb/）

通过 **adb 连手机 → 截图 → Agent 读图算坐标 → 点击** 完成 UI 操作。截图目录默认只保留**最新 2 张**。

## 协作原则（Agent / 人工）

### 积木 + 组合

| 层级 | 目录 | 命令 | 说明 |
|------|------|------|------|
| **片段（积木）** | `录制脚本/片段/<一级模块>/` | `macro <中文名>` | 按发版回归模块分子目录；调用仍用中文名 |
| **组合（配方）** | `录制脚本/组合/<一级模块>/` | `compose <中文名>` | 按模块分子目录；调用仍用中文名 |

路径不确定时：Agent **读图** 判断当前页，再选一块积木或一条组合；不要对每个 `tap` 都截图。

### 片段间验收（串联多个 macro 时）

**粒度**：跑完**一个脚本片段**（一次 `macro` / `compose` 里的一块）后再验收；**片段内部的各个 tap 不必逐步验证**。

```text
macro A  →  验收 A 的落点  →  确认 OK  →  macro B  →  验收 B  →  …
```

| 验收方式 | 适用 |
|----------|------|
| `tunnel wait` / 片段 `tunnelVerify` | 有接口信号（登录、进房、送礼、发动态等） |
| `capture` 读图 | 无抓包信号、需确认当前页（底栏、弹窗、是否在房内等） |
| `dumpsys activity` | 快速判断 Activity（如是否仍在 `RoomChatActivity`） |

落点与下一段脚本**前置条件不符**时，先纠偏（补跑片段或 `BACK`），**不要盲连下一段**。

**不确定当前在哪个页面**时，可 **杀进程冷启** 回到已知状态（已登录 → 首页底栏）：

```bash
python3 adb/adb_execute.py macro 冷启动回首页
# 等价：启动Yaahlan（force-stop）→ 跳过开屏广告 → 关闭常见弹窗
```

片段跑完后 `capture` 确认底栏可见，再执行下一段。未登录时会落在登录页，改跑 `公会长手机号登录` 等。

**示例**：`搜索进房` → `退出房间` 后，常落在 **Search 页** 而非房间列表/底栏主页；此时不能直接 `退出登录`（Me 底栏不可达），须先 `macro 搜索页返回房间帧`、或 `macro 冷启动回首页` 重置。

**验证成功 → 自动录制**：探索出新路径后，经验收通过，Agent 自动将步骤落库到 `录制脚本/`（不写进本 README）。流程见 [验证成功自动录制](#验证成功自动录制)。

### 验收策略（抓包优先）

**原则**：能抓包验证的，**不要依赖读图**。Toast、提交成功提示、公屏一闪等短反馈，截图极易漏抓；以 Tunnel 接口 `ec=200` 为准。

#### ① 脚本已实现的能力 → **先抓包，失败再读图**

组合/片段已内嵌 `tunnelVerify`，或已知有关键字（如 `gift/send`、`feed`、`updateUserBase`、`heartbeat`）时：

1. **先** `run` / `compose` / `macro` + `tunnel wait`（可用 `--no-capture`）
2. `tunnelVerify.ok === true` 且退出码 **0** → 判成功，**不必读图**
3. 抓包失败（退出码 **3**）→ **再**读结束截图排查（点位偏了？请求未发出？关键字不对？）

#### ② 脚本尚未覆盖的能力 → **抓包 + 读图并用**

探索新流程、尚无录制脚本时，**同时**用 Tunnel 辅助定位/验收 + 截图分析当前页（定坐标、确认页面状态）。

#### ③ 提交表单类操作 → **优先抓包**

点 **Save / Post / Send / 登录** 等提交后，优先等对应写接口而非读 Toast：

| 操作 | 抓包关键字示例 |
|------|----------------|
| 登录 | `login` |
| 发动态 | `feed` |
| 礼物面板送礼 | `gift/send`（**读 `response.em`**，`ec=200` 才算成功） |
| 编辑资料保存 | `updateUserBase` |
| 进房 | `heartbeat` |

#### 读图适用场景

| 场景 | 做法 |
|------|------|
| **探索定坐标** | `capture` 读图 → `tap`（与结果验收无关） |
| **抓包失败后排查** | 读 `screenshot.path` 分析 UI 异常 |
| **无抓包信号** | `popup analyze` + `weakUiPopups` 读图（见 `弹窗抓包信号.json`） |

### 截图策略

| 场景 | 做法 |
|------|------|
| **路径确定** | `macro` / `compose` + `--no-capture`（0 张） |
| **有 tunnelVerify 的验收** | `--no-capture` 即可；以 `tunnelVerify.ok` 判定 |
| **仅弱 UI / 无接口** | `capture: end` 或 `--verify`（结束时 1 张） |
| **探索新页面** | `capture` → 读图 → `tap` → … |

### 截图次数对照（示例：发一条动态）

| 方式 | 截图次数 |
|------|----------|
| 逐步 `capture` + `tap`（旧） | 约 4 次 |
| `macro 发布纯文本动态 --text 1234` | **1 次**（结束时，可 `--no-capture` 为 0） |
| `compose 发布纯文本动态 --text 1234 --no-capture` | **0 次** |

### 波轮 / 滚动列表：先标定步长，再算距离

年龄、生日、日期等 **滚轮选择器**，以及礼物面板 **上下滑** 礼物格，不要一次盲滑到底。应先 **滑动固定距离 → 读图确认变化量 → 再计算剩余滑动次数**。

```text
① 记录当前值（读图或 uiautomator，如年份 2003、礼物 Tab 内 index）
② 在目标列/区域做一次固定 swipe（如 Δy=350px，duration≈300ms）→ capture 读图
③ 标定：每滑 1 次变化几步（如年份 −2/次、礼物列表约 4 项/次）
④ 计算：剩余步数 = ⌈|目标 − 当前| / 每步变化⌉，按同方向、同距离重复
⑤ 接近目标后改为小步滑动，读图微调；提交后优先 tunnel 验收（如 updateUserBase）
```

**注意**：

| 要点 | 说明 |
|------|------|
| **滑在列中心** | 日期波轮有 Day / Month / Year 三列，x 须落在对应列中心，勿滑错列 |
| **方向先试探** | 上下滑方向因控件而异；先 1 次固定滑动看数值变大还是变小，再定正向 |
| **步长因屏而异** | 换机或换弹窗后重新标定；落库时在 `note` 写列序、方向、标定出的步数 |
| **与抓包结合** | 编辑资料保存 → `updateUserBase`；礼物选择 → `getGiftTabListV3` + `gift/send` |

示例（生日年份 2003 → 1998，标定每滑 1 次约 −2 年）：

```bash
# 标定后：差 5 年 ≈ 3 次同参数 swipe，再 capture 确认 → 点 Save → tunnel wait updateUserBase
adb -s <serial> shell input swipe 900 2050 900 2280 300   # 在 Year 列中心，固定距离
python3 adb/adb_execute.py capture                          # 读图确认年份变化量
```

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

## App 语言与 RTL 镜像

部分语言下，**原生 UI**（非 WebView）会按 **RTL（从右到左）** 布局镜像，常见如 **阿拉伯语**、**中文** 等；**WebView / H5 页** 往往仍按 LTR 或独立排版，**不要假定与原生页一致**。

| 影响 | 说明 |
|------|------|
| **水平坐标** | 返回键、设置、关闭、底栏 Tab 等左右对调；LTR 下 `tap_pct` 的 **x 须镜像**：`x' = 1 − x`（y 不变） |
| **底栏顺序** | Room / Me 等 Tab 左右顺序可能反转，勿死记英文环境下的 x |
| **录制基准** | 片段默认在 **英文 LTR** 下录制；换语言后片段间 **capture 读图**，确认控件在左还是右 |
| **WebView** | 活动页、部分运营 H5 等可能不镜像；以读图为准，不能套用原生页的镜像规则 |

**Agent 流程**：

```text
片段跑完 → capture 读图
  ├─ 布局与录制时一致 → 继续下一段
  ├─ 原生页 RTL 镜像   → 对下一步 tap 的 x 做 1−x，或补跑 RTL 专用片段
  └─ WebView / 混合页  → 单独读图定坐标，勿盲目镜像
```

操作失败且已排除弹窗、分辨率问题时，**优先怀疑语言 RTL**，读图看主操作按钮是否跑到对侧。

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

## ADB + Tunnel 抓包校验（推荐）

将 **UI 操作** 与 **Tunnel 接口核对** 串成一条命令；**以抓包为验收主依据**，避免靠读图判断 Toast、公屏或动效是否成功。

### 一体化 `run`

```bash
python3 adb/adb_execute.py run \
  --macro 切换房间底栏 \
  --tunnel-account familyLeader \
  --tunnel-keyword heartbeat \
  --tunnel-wait 20
```

流程：记录 `start_time` → 执行 ADB → 轮询 [tunnel.wemomo.com](../Tunnel/README.md) 直到 URL 匹配（有 `--tunnel-*` 时仍会结束截图，但**判定以 tunnel 为准**）。

### 挂在 compose / macro 上

```bash
python3 adb/adb_execute.py compose 发布纯文本动态 --text 1234
# 组合 JSON 内可写 tunnelVerify（见 组合/动态帧/发布纯文本动态.json）

python3 adb/adb_execute.py macro 手机号登录 \
  --tunnel-account familyLeader \
  --tunnel-keyword login
```

| 参数 | 说明 |
|------|------|
| `--tunnel-account` | `索引.json` → `testAccounts`（`guildLeader` / `familyLeader`） |
| `--tunnel-momoid` | 直接指定 userId |
| `--tunnel-keyword` | URL 子串过滤（如 `sendGift`、`heartbeat`） |
| `--tunnel-wait` | 最长等待秒数（默认 30） |
| `--tunnel-expect-ec` | 可选，校验 `response.ec` |

退出码：`0` = 业务成功（含 `response.ec` 符合 `--expect-ec`）；`3` = 未抓到请求或 **已抓到但 ec≠200**。

写操作（送礼、登录、发动态）须读响应体：**`response.em` 即失败原因**，不要只看请求是否发出。

| 情形 | 判定 |
|------|------|
| 未抓到 `gift/send` | Send 未生效或网络未发出 → 读图排查 |
| 抓到且 `ec=200` | 成功，不必读图 |
| 抓到且 `ec≠200` | 失败，读 `failureReason` / `responseEm` |

### Tunnel 等待 / 读取最近结果

```bash
python3 adb/adb_execute.py tunnel wait --account guildLeader --keyword gift/send --since 30 --wait 25 --expect-ec 200
python3 adb/adb_execute.py tunnel last --account guildLeader --keyword gift/send --since 120
```

### 弹窗：先抓包再决定是否关（login / home / me / room / mic）

```bash
python3 adb/adb_execute.py popup analyze --scene me --account familyLeader --since 120 --capture
python3 adb/adb_execute.py run --compose 家族长冷启动登录 \
  --tunnel-account familyLeader --popup-scene login --popup-auto-dismiss
```

抓包规则见 `录制脚本/弹窗抓包信号.json`；UI 说明见 `录制脚本/弹窗说明.md`。

### 礼物面板：Tunnel 解析 Tab / 礼物列表

打开橙色礼物盒后：

```bash
python3 adb/adb_execute.py gift panel analyze --account familyLeader --since 120
python3 adb/adb_execute.py gift panel find --account familyLeader --price 99 --tab Gift
```

数据源：`getGiftTabListV3`。Tab **左右滑**、礼物格 **上下滑**，见 `录制脚本/礼物面板抓包.md`。

Cookie 复用 `MOA/.env.local`。Agent Skill：`.cursor/skills/adb-tunnel-verify/SKILL.md`。

## 验证成功自动录制

Agent 在真机上探索 UI 操作时，**验收通过后才落库**；脚本内容写入 `录制脚本/`，本 README 只描述流程。

### 流程总览

```text
① 探索    无脚本：抓包+读图并用定坐标；有 gift panel find / popup analyze 可辅助
② 验收    有脚本/有接口：先 tunnel（--no-capture）→ 失败再读图；无脚本：抓包+读图并用
③ 落库    写片段 / 索引 / 组合（含 tunnelVerify）→ 更新 录制脚本/README.md、KB对照.md
④ 回放    compose/macro --no-capture，以 tunnel 验收；失败再读图
```

未通过验收时回到 ①。**勿因截图「看起来对了」就判成功**（尤其 Toast、表单提交成功提示）。

### ② 验收标准

| 情形 | 顺序 |
|------|------|
| **脚本已实现**（含 `tunnelVerify` 或已知 API） | ① 抓包通过 → 成功；② 抓包失败 → 读图排查 → 调步骤 |
| **脚本未实现**（探索新能力） | 抓包 + 读图**同时**用于定位与验收 |
| **提交表单**（Save/Post/Send/登录） | **先**等写接口（`updateUserBase`、`feed`、`gift/send` 等），**后**读图 |

共同要求：退出码 **0**；退出码 **3** 不算成功。组合落库时**应写 `tunnelVerify`**。

### ③ 落库清单（写入 `录制脚本/`，非本文件）

| 产物 | 路径 / 动作 |
|------|-------------|
| 片段 | `片段/<一级模块>/<中文名>.json`（`tap_pct`、`swipe`、`run_script`；`recordedOn` 对齐基准机） |
| 索引 | `索引.json` 登记 `kind`、`module`、`file`、可选 `params` |
| 组合 | 端到端流程写 `组合/<模块>/<中文名>.json`，可内嵌 `tunnelVerify` |
| 文档 | 更新 [`录制脚本/README.md`](录制脚本/README.md)、[`KB对照.md`](录制脚本/KB对照.md) |

细则见 [`录制脚本/README.md#成功即落库`](录制脚本/README.md#成功即落库agent-必做)。

### ④ 回放验证

落库后用 `macro` / `compose --no-capture` 无人工干预再执行一次；以 **tunnel 验收** 为准，才算录制完成。

## 说明

- 仅支持 **Android + adb**。
- 可选 `--skip`：`dismiss_splash_ad`、`login_lang`、`dismiss_popup_taps` 等（见各片段 `skip_key`）。
- **偶发弹窗**：登录、发动态、进 Me 等流程会执行 **关闭常见弹窗**（先 BACK，再点常见 Cancel）。稳定页且确认无弹窗时可 `--skip dismiss_popup_taps` 只保留 BACK 关层。
