---
name: complaint-analysis
description: 分析客诉反馈 Excel 数据并生成统计报告（Canvas 可视化 + 可选写入钉钉文档）。在用户给出客诉 Excel 文件（本地路径或钉钉链接）并要求分析时使用。触发词：客诉分析、客诉反馈统计、complaint、客诉数据。
---

# 客诉反馈分析

## 前提：Excel 列结构

分析脚本依赖以下列名（header 行为英文）：

| 列名 | 说明 |
|---|---|
| `report date` | 用户提交时间 |
| `response date` | 首次响应时间 |
| `solved date` | 归档/解决时间 |
| `category` | 分类：`is bug` / `experience bug` / `repeat bug` / `not bug` |
| `result` | 处理结果（值为 `测试`/`测试数据，忽略即可`/`重复问题` 时视为无效数据自动过滤） |
| `desc` | 问题描述 |

## 工作流

### Step 1：运行分析脚本

```bash
python3 .cursor/skills/complaint-analysis/analyze.py <xlsx路径>
```

脚本输出 JSON，包含：`total`、`bug_count`、`not_bug_count`、`avg_response_h`、`avg_solve_h`、`over24`（超 24h 明细）、`feature_counts`（功能集中统计）、`bugs`（Bug 明细）。

### Step 2：生成 Canvas 可视化

读取 canvas skill（`/Users/mac/.cursor/skills-cursor/canvas/SKILL.md`）后，在以下路径创建 Canvas：

```
/Users/mac/.cursor/projects/Users-mac-Documents-code-Yaahlan-auto-generate-testcase/canvases/<月份>-complaint-analysis.canvas.tsx
```

**Canvas 必须包含的区块**（参考本次生成的 `june-complaint-analysis.canvas.tsx`）：

1. **核心指标行**（Grid 5列）：总数、技术Bug、产品疑问、平均响应时长、平均解决时长
2. **饼图**：反馈分类构成（donut，各 bug 类型 + not bug）
3. **横向柱状图**：集中反馈功能分布 Top N
4. **超 24h 归档表格**：含超时时长（Pill 标色）、提交时间、问题描述、超时原因
5. **技术 Bug 明细表格**：类型 Pill + 描述 + 处理结果

### Step 3：写入钉钉文档（可选）

用户提供文档链接时，通过以下方式写入：

```python
# 1. 获取 access token（内部 API）
curl -s "http://gaia-hg.momo.com/ding/excel/token" \
  -H "Content-Type: application/json" \
  -d '{"aegisKey":"1515ac73-412a-4b16-b5ab-8e9fd271363f","aegisSecret":"0202a9a9-212e-482a-8f82-65a005b2945a","workid":"T00471"}'
# 返回 data.token 和 data.operatorId

# 2. 先用 parse_document（user-dingtalk-doc MCP）+ 用户提供的 Cookie 解析文档，得到 dentryUuid
# dentryUuid 在 mainsite JSON 的 dentryInfo.data.dentryUuid

# 3. 用 dentryUuid 调用 DingTalk 写入 API（注意：不是 dentryKey）
POST https://api.dingtalk.com/v1.0/doc/suites/documents/<dentryUuid>/content?operatorId=<operatorId>
Header: x-acs-dingtalk-access-token: <token>
Body: {"content": {"type": "markdown", "content": "<markdown内容>"}}
```

> **关键**：文档 URL 中的 nodeId（如 `MNDoBb60...`）与 dentryKey（如 `dYrqaq3A...`）不同，API 需要 `dentryUuid`，其值等于 nodeId 本身（`dentryInfo.data.dentryUuid`）。

## 统计维度

每次分析必须输出以下内容：

- 有效反馈总数（过滤测试数据后）
- 技术 Bug 数 / 产品功能疑问数
- 平均响应时长（response date − report date）
- 平均解决时长（solved date − report date）
- 归档超 24h 的具体问题和原因
- 集中反馈功能 Top N
- 技术 Bug 明细（类型 + 描述 + 处理结果）

## 钉钉 Markdown 模板

写入文档时使用以下结构：

```markdown
# <月份>客诉反馈统计分析

> 数据来源：<文件名>（已去除测试数据）· 有效反馈共 N 条

## 核心指标
| 维度 | 数值 |
...

## 反馈分类构成
...

## 集中反馈功能分布
...

## 归档超过 24 小时的问题
...

## 技术 Bug 明细
...
```
