---
name: adb-page-learn
description: >-
  Yaahlan App 真机页面学习：capture 读图 → 每页 swipe 读全 → tap 单入口 → activity 验收 →
  对照 KB 落 ADB 片段并更新索引。用于「深入学习/遍历 App/沉淀录制脚本/探索五底栏与子页」；
  禁止 Python 批量盲扫代替读图。与 adb-tunnel-verify 配合：探索读图定坐标，有接口时验收抓包。
---

# ADB 页面学习（读图 → 操作 → 落片段）

## 何时使用

- 用户要求 **深入学习 / 遍历 App / 沉淀片段 / 页面地图 / 录制脚本**
- 需要覆盖 **五底栏**（Game / Room / Message / Moment / Me）及 **子 Tab、卡片、二级页**
- 验收通过后要 **落库** `adb/录制脚本/`

**不要**用本技能替代：`adb-tunnel-verify`（已实现脚本的抓包回放验收）、`testcase-generator`（从 PRD 写用例）。

## 铁律

| 必须 | 禁止 |
|------|------|
| 每页 **先 swipe 读全** 再点下一项 | Python/`learn scan` **批量乱点** 代替读图 |
| **一次只探一个入口**：tap → activity → capture | 未读图就写坐标 |
| 探完 **立刻落片段** + 更新索引，再下一项 | 攒一堆操作最后才落库 |
| 子页同样 swipe 读全；**BACK** 回上一层 | 学习期对 **首页-游戏帧 / 首页-房间帧 / 我的帧** 强跑 macro（除非 `--force-script` 调试） |
| Me/home 弹窗 **读图点 Cancel** | Me/home 上盲 **BACK**（会出退出确认） |
| 落点不对 **capture 纠偏**，勿 force-stop | 除非用户明确要求冷启，否则 **force-stop 杀 App** |

辅助：`learn scan --tab me` 仅作 **坐标参考**，tap 前仍须 **capture 读图确认**。

## 主循环（每个入口）

```text
① capture --max-edge 1170 读图 → 确认当前页与可点入口
② 【本页】上滑若干次（每次 swipe 后再 capture），直到内容穷尽；必要时滑回顶部
③ 选一个未落库入口
④ tap（读图算坐标；Tab 等可 uiautomator dump 精确定位）
⑤ activity 快验 + capture 验收落点（WebView / ProfileActivity / PayActivity 等）
⑥ 子页重复 ②；对照 testcase-kb / documents 写 kbRef、description
⑦ 落 片段/<模块>/*.json → 更新 索引.json、KB对照.md
⑧ key 4 或读图点返回，回到列表页
⑨ 下一入口
```

## 常用命令

```bash
# 读图（优先缩略，加快 Agent 读图）
python3 adb/adb_execute.py capture --max-edge 1170
python3 adb/adb_execute.py activity

# 滑动（1080×2340 基准）
python3 adb/adb_execute.py swipe 540 1700 540 800 --duration 350   # 上滑看下方
python3 adb/adb_execute.py swipe 540 800 540 1700 --duration 300   # 回顶

python3 adb/adb_execute.py tap X Y
python3 adb/adb_execute.py key 4    # 返回（Me/home 慎用）

# 底栏（读图确认选中态；LTR 英文环境下约）
# Game ~108,2237  Room ~324  Message ~540  Moment ~756  Me ~972

# VIP 门控（如 Viewed me 需 VIP1+）
python3 adb/adb_execute.py vip try --account familyLeader --level 5 --days 1 --clear-first

# 辅助列坐标（不可代替读图）
python3 adb/adb_execute.py learn scan --tab me
```

## 模块与目录

| 底栏 / 场景 | 片段目录 | 学习期操作方式 |
|-------------|----------|----------------|
| Game | `片段/首页-游戏帧/` | capture + tap（目录内 JSON 仅参考） |
| Room | `片段/首页-房间帧/` | 同上；退房见下节 |
| Message | `片段/消息帧/` | 可 macro + 读图补充 |
| Moment | `片段/动态帧/` | 可 macro + 读图补充 |
| Me / 资料 / 家族 | `片段/我的帧/` | capture + tap |
| 登录换号 | `片段/注册登录/` | `macro 手机号登录 --text <phone>` |

`ai prepare --goal enter_me|exit_room|logout|recover` 见 `adb/README.md`。

## 与 adb-tunnel-verify 的分工

| 阶段 | 做法 |
|------|------|
| **探索定坐标** | capture 读图 + tap（本技能） |
| **落库后回放** | macro + tunnel（`adb-tunnel-verify`）；多步逐段 macro |
| **提交类**（Save/Post/登录） | 落库时写 `tunnelVerify`；验收优先抓包 |

探索阶段 **不以 Toast 读图判成功**；有已知 API 时可并行 `tunnel wait` 辅助。

## 特殊场景（必读）

| 场景 | 处理 |
|------|------|
| **房内三方游戏全屏**（Ludo / 7up7down） | 先 `macro 房内三方游戏最小化`（顶部 **Minimize**，约 `0.500, 0.171`）；Game Rewards 弹窗用 `key 4`；再 `macro 退出房间 --force-script --no-popup-gate` |
| **退出房间后落 Search 页** | capture 读图 → AI 点返回或 `搜索页返回房间帧` |
| **Profile Tab 切换** | Honor/Relationship 用 dump 取 bounds，勿盲 y≈520 |
| **家族 Members More** | 点标题行 **More >**，勿点下方头像行（会进他人资料） |
| **解除客服身份** | Admin：`--save-cs-data --cs-user-id <id> --cs-enable 0 --cs-opt-type 2` |
| **换号登录** | `macro 退出登录` → `macro 手机号登录 --text <phone>` |
| **RTL 语言** | 原生页 x 可能镜像 `x'=1-x`；WebView 单独读图 |

详见 [reference.md](reference.md#特殊场景清单)。

## 落库清单（验收通过后必做）

1. **片段** `片段/<一级模块>/<中文名>.json`（含 `id`、`name`、`recordedOn`、`steps`、`kbRef`、`description`）
2. **索引** `索引.json` 登记 `kind: fragment`、`module`、`file`
3. **KB对照** `KB对照.md` 增一行映射
4. 端到端流程：拆成多个片段，逐段 macro + 片段间验收（可选 `tunnelVerify` 写在片段 JSON）

片段 JSON 模板与 `id` 命名见 [reference.md](reference.md#片段-json-模板)。

## traverse 顺序（默认）

```text
Me（一级 → 下滑 → 设置/钱包/资料子 Tab）
  → Game → Room → Message → Moment
每帧：首屏读全 → 逐入口 → 二级页 swipe 读全 → 落片段 → BACK
```

用户指定范围时以用户为准；未指定则从 **当前 Activity 所在帧** 继续，不重复已落库 id。

## 相关文档

- [adb/README.md](../../../adb/README.md) — 页面学习主流程、片段间验收
- [adb/录制脚本/README.md](../../../adb/录制脚本/README.md) — 成功即落库
- [adb/录制脚本/KB对照.md](../../../adb/录制脚本/KB对照.md)
- [adb/录制脚本/弹窗说明.md](../../../adb/录制脚本/弹窗说明.md)
- [.cursor/skills/adb-tunnel-verify/SKILL.md](../adb-tunnel-verify/SKILL.md)
