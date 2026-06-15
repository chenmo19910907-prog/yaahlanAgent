---
name: autotest-p0
description: 从 PRD + 功能测试用例生成 P0 级可执行自动化用例（JSON），用 adb autotest 真机执行并输出 JSON/HTML 测试报告。用于「P0 自动化」「可执行用例」「自动回归」「测试报告」。
---

# 自动化测试用例（PRD → 分级整理 → 执行 → 报告）

## 何时使用

- 用户给出 **PRD + 功能测试用例**，要求把 **整个需求** 整理成自动化用例（**可自行指定 P0/P1/… 等级**）
- 发版前对已有 `macro` 片段覆盖的模块做 **分级自动回归**

## 流程

### 1. 理解需求与分级

1. 用 `prd-review` / `dingtalk-doc-read` 读 PRD；用 `dingtalk-excel-read` 读手工表
2. 生成 **`adb/自动化用例/registry/<需求>.json`**：全量测试点 + `priority` + `automationStatus`（用户可要求只整理 P0，或 P0+P1 等）
3. 等级建议：**P0** 主链路写操作 · **P1** 核心入口 · **P2** 浏览/预览 · **P3** 权限/边缘 · **P4** 需后台/特殊素材
4. **只把可执行项写入 cases/**：
   - **`action: steps`** 内联 `tap_pct` / `swipe` 等（**不必有命名片段**）
   - 或已有 `macro` 片段（见 `KB对照.md`）
   - 验收可依赖 **Tunnel** / **Activity** / 截图
5. 标出 **manual/blocked** 项 → 只留在 registry，不强行生成 JSON  
6. **场景可拓展**：不必与手工 1:1；用已有 `macro` 串「发布 / 多入口 / 列表详情 / 点赞 / 话题」等 smoke，在 `source.scenarioRef` 写意图

### 2. 生成自动化用例 JSON

目录：`adb/自动化用例/<需求名>/cases/<id>.json`（`id` 建议带等级前缀）

**方式 A — CLI 模板（推荐起步）**

```bash
python3 adb/adb_execute.py autotest generate \
  --id P0-<模块>-<场景> \
  --name "<用例标题>" \
  --module <testcase-kb模块名> \
  --account familyLeader \
  --macros "启动Yaahlan,手机号登录" \
  --tunnel-keyword login \
  --activity-hint home \
  --manual-ref "<手工用例编号或标题>" \
  --prd-ref "<钉钉URL或 documents/...>"
```

生成后 **必须人工/Agent 审阅** `operations` / `verifyPoints`，补全：
- `operationFlowDoc`：人类可读步骤
- `account.precondition`
- 每步 `tunnel` / `popupScene` / `text` 参数

**方式 B — 直接编写 JSON**（格式见 `adb/自动化用例/README.md`）

### 3. 登记 catalog

每个需求独立文件夹 `adb/自动化用例/<需求名>/`（含 `catalog.json`、`cases/`、可选 `registry.json`）。根 `catalog.json` 登记 `requirements[].id` + `folder`；用例 JSON 写入对应 `cases/`。

### 4. 执行前检查

```bash
python3 adb/adb_execute.py devices
python3 adb/adb_execute.py accounts check --account familyLeader
```

### 5. 执行并出报告

```bash
# 查看全量映射
python3 adb/adb_execute.py autotest map --requirement req-动态支持视频发布 --priority P0,P1

# 单条 / 套件 / 整需求（可限等级）
python3 adb/adb_execute.py autotest run --case P0-动态-发布视频动态
python3 adb/adb_execute.py autotest run --requirement req-动态支持视频发布 --priority P0
python3 adb/adb_execute.py autotest run --suite req-动态支持视频发布-p1
```

- 退出码：`0` = 全部通过，`3` = 有用例失败
- 报告：固定单文件 `adb/自动化用例/reports/report.html` + `report.json`（每次 run 覆盖）
- 向用户汇报：**通过数/总数**、失败用例、抓包 `failureReason`、截图路径

```bash
python3 adb/adb_execute.py autotest report --latest
```

## 用例 JSON 必填信息（对用户可见）

| 区块 | 内容 |
|------|------|
| `operationFlowDoc` | 详细操作流程（自然语言） |
| `account` | 别名、userId、前置条件 |
| `operations` | 可执行步骤（macro / account_check） |
| `verifyPoints` | 测试点 + 验收方式（tunnel / activity / screenshot） |
| `source` | 关联手工用例与 PRD |

## 验收方式选择

| 场景 | 优先 |
|------|------|
| 登录、发帖、送礼 | `tunnel` + `expectEc: 200` |
| 页面落点 | `activity` + `expectHint` |
| 留存证据 | `screenshot` |
| Toast / 动效 | **不用读图判定**；以 Tunnel 为准 |

## 禁止

- 禁止用批量 Python **盲扫页面** 代替已定义的 `autotest run`（探索仍用 `adb-page-learn` 单步）
- 禁止对 `aiOperateModules` 模块默认 `macro`（首页/Me/房间/礼物等）；无片段时标「需 AI 读图，暂不纳入 P0 自动」
- 禁止跳过 `accounts check` 直接登录

## 与现有技能关系

| 技能 | 分工 |
|------|------|
| `testcase-generator` | 生成 **手工** 功能用例 |
| `autotest-p0`（本技能） | 从 P0 手工用例 → **可执行 JSON** + 跑报告 |
| `adb-tunnel-verify` | 单条 macro + 抓包验收细节 |
| `adb-page-learn` | 无片段时探索并 **落库新片段**，再纳入 P0 |

## 内置示例

| id | 模块 |
|----|------|
| `P0-注册登录-手机号登录` | 注册登录 |
| `P0-动态-发布纯文本动态` | 动态 |
