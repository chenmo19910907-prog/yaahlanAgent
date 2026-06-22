# Skill: Yaahlan用例自动生成

## 概览

本 Skill 根据需求文档和营收活动设计思路自动生成高质量测试用例，始终以 **测试工程师视角** 思考，确保用例可执行、可复现、可验证。

该 Skill 采用 [Agent Skills 开放规范](https://agentskills.io/home)，可被支持 Skills 的任意代理加载使用。

## 输入要求

- 输入的需求文档是钉钉文档的格式
- 需求文档的权限已经开启


### 1. 读取并理解需求文档

在生成用例前，**必须先完成需求理解**，不得盲目生成。

1. **参数说明：**
   - `requirements_file_path`：需求文档地址（钉钉文档 URL）

2. **读取文档**：
   - 使用 `dingtalk-doc-read` 技能 / MCP `parse_document` 读取需求文档。若返回「权限已过期」，调用 `refresh_cookie` 传入新 Cookie 后重试

3. **结构化理解（参考 `prd-review` Skill）**：
   - **Step 1 判断功能类型**：房间内玩法 / 活动运营 / 支付经济 / 用户功能 / 后台工具，功能类型决定用例覆盖侧重点
   - **Step 2 按维度逐项审查**：从 PRD 中提炼核心场景、入口、业务规则、边界与异常，并记录模糊/缺失项
     - 用户场景：核心流程、入口、多角色差异（如 VIP vs 非VIP、房主 vs 普通用户）
     - 业务规则：资格条件、数量限制、奖励/扣款规则、关联功能影响
     - 边界与异常：网络中断、重复操作、并发冲突、时间边界、封禁用户
     - 活动专项（限时活动必审）：时间线、时区、地区差异
     - 支付专项（涉及资金必审）：币种、扣款确认、余额不足引导
   - **Step 3 输出需求摘要**：列出功能类型、核心场景、业务规则、边界与异常、待确认点，供后续用例生成使用；若有模糊项先向用户确认，再生成用例

### 2. 设计覆盖策略

在生成用例前，先在思考中明确覆盖维度（可在回复中简要列出）：

- 功能覆盖：覆盖需求里列出的**所有板块**、**需求内容**。
- 正反用例：对每个关键流程，既有成功路径，也有失败/异常路径。
- 边界用例：极端输入、并发登录、被其他应用打断、退到后台等。
- 专项用例：性能测试、幂等性测试、兼容性测试、安全性测试等

### 3. 生成用例的操作步骤

> **判断需求类型（必须）**：
> - **版本需求**（发版/版本迭代/回归）→ 以 `rules/version_testcase_generation_rules.md` 为主规则生成，**必须先读 `documents/` 对应模块文档**做业务上下文对齐，再结合 PRD 变更点生成用例
> - **活动/其他需求** → 以 `rules/testcase_generation_rules.md` 通用规则生成

当需求理解完成后，遵循以下流程：

1. **处理流程**：

   **若为版本需求**，额外执行：
   - **【documents 对齐】** 根据需求模块名在 `documents/` 目录（含子目录如 `documents/moments/`）查找对应 `.md` 文档，完整阅读其模块范围、主链路、必查场景、异常与边界说明；若不存在，在用例中标注「未找到 documents 对照，建议补充模块文档」，并**主动询问用户是否需要将本次需求整理为知识库文档保存至 `documents/` 目录**
   - **【变更点聚焦】** 结合 PRD 中的本次变更点，在 documents 业务上下文基础上，重点生成变更影响的新增用例、回归用例
   - **【覆盖目标】** 按 `version_testcase_generation_rules.md` 要求覆盖：功能验收、边界值、多角色、屏幕适配（有前端变更时）、多语言（英/阿/土/俄，所有需求均需覆盖）

   **【知识库参考（所有需求，推荐）】**：
   - 生成前运行 `python3 scripts/suggest_kb_for_module.py <模块关键词>`（或 `--file modules.txt`）获取应读的 `documents/`、`testcase-kb/`、`bug-kb/`、`templates/` 路径
   - **活动/营收需求**：使用活动模式列出全部历史模板并做相似度排序：
     ```bash
     python3 scripts/suggest_kb_for_module.py --activity 世界杯 榜单 抽奖
     # 或仅要全量模板索引
     python3 scripts/suggest_kb_for_module.py --all-templates
     ```
     - 脚本会递归收录 `templates/**/*.md`（含 `templates/2026活动/`、`templates/2026之前活动相关/` 等子目录）
     - **阅读策略**：不必全文读入所有模板；优先读输出中标注「推荐」的相似活动 + 根目录通用模块模板（如 `抽奖.md`、`yaahlan榜单.md`），其余按 PRD 模块结构对齐参考
   - **活动/营收需求**：在 `bug-kb/` 查阅同模块历史缺陷，优先补充严重/阻碍与现网翻车场景（不必等版本需求才读）
   - **版本需求**：另读 `rules/version_testcase_generation_rules.md` §1

   **通用步骤（所有需求）**：
   - **【模块提取】从需求文档开发需求表格中提取所有模块**：逐行遍历表格，不遗漏任何一行（头图、规则、奖励、一级tab、各业务模块、预热模块、活动条等）。用户若只列举部分模块，仍需覆盖文档中的全部模块。
   - **【层级拆解】对每个模块拆解子功能点**：如「开斋旅行」下含中奖滚动条、地图、宝箱、骰子、终点瓜分、瓜分逻辑、榜单icon、榜单弹窗、兑换商店等；「终点瓜分」下含瓜分逻辑。确保每个有独立说明的子功能都有对应用例。
   - **【相似模块对齐】存在相似模块时参考模板**：如房间榜与礼物榜结构相似，需参考`templates/榜单.md`，按数据格式、显示规则、交互、分页、计值、吸底、定榜等维度对齐生成用例。
   - 为需求文档里的所有模块自主生成详细的测试用例，包括正向、反向、异常情况、边界情况、如果有数据的输入和输出，要细化数据的前置条件和预期结果
   - 生成每个模块的用例时，除了根据产品原型生成全部的测试用例，还需要参考对应规则文件（版本需求用 `version_testcase_generation_rules.md`，活动需求用 `testcase_generation_rules.md`）里的通用规则进行用例补充
   - 用例格式根据使用场景分两种：
     - **写入钉钉 Excel**：使用 3 列格式，**不需要用例ID**

       | 功能模块 | 测试步骤 | 预期结果 |
       |----------|----------|----------|

     - **知识库/文档**：使用 5 列格式（含用例ID）

       | 用例ID | 功能模块 | 用例标题 | 测试步骤 | 期望结果 |
       |--------|----------|----------|----------|----------|

   - **功能模块列写法**：只写模块名，不写「-」后的说明，细节移入测试步骤。示例：`【后台侧】新用户建联列表`，不写 `【后台侧】新用户建联列表 - 触发条件验证`
   - **同模块连续多条用例**：功能模块列留空，不重复填写
   - **一条用例多个预期**：拆成多行，测试步骤列留空，每行一个预期
   - 生成的测试用例临时放到 `temporary_testcase` 文件夹

2. **【生成前校验】输出前自检清单**（可口头确认）：
   - 需求文档表格中每一行模块是否都有对应用例？
   - 每个模块下的子功能点（加粗标题、独立段落）是否都有覆盖？
   - 相似模块（如礼物榜/房间榜）是否已参考模板做结构对齐？
   - 边界值三档是否覆盖：恰好等于临界值 / 略大于 / 略小于（如充值门槛 2 美金，需分别写 2.00、3.00、1.99 三条）
   - 「状态 × 行为」矩阵是否完整：如「7日内 vs 第8日」×「直连入口 vs 其他入口」，每个组合单独一条
   - 字段级校验是否独立列出：列表表头字段、详情弹窗字段需逐项验证，不合并描述
   - 基础流程是否覆盖：「返回按钮」「重置按钮」「筛选后再重置」等基础操作不要省略

4. **需求来源为对话而非文档时的处理规范**：
   - 生成前做一次结构化确认：把理解到的核心规则、边界条件、待定项列出来，让用户确认后再生成
   - 待定项显式保留：需求中明确说「待定」的逻辑，预期结果写「以产品最终结论为准，确认后更新」，不要猜测
   - 不要自行补充复杂派单/路由/多角色逻辑：涉及多角色、多入口、多状态的交叉场景，若没有逐条确认，极易写出与需求不符的用例，需主动询问

5. **输出整理**：
   - **落盘前校验**：`python3 scripts/check_testcase_md.py`（格式、续行预期、重复编号等）；可选 `python3 scripts/module_coverage.py --modules-file <PRD模块清单.txt> --testcase temporary_testcase/<文件>.md` 做覆盖 diff
   - 使用 `testcase-to-excel` 技能：读取 `temporary_testcase` 文件夹下的用例，通过 MCP `dingtalk-excel-write` 写入 `testcase_file_path`（钉钉 Excel URL）
   - 分批写入或一次性写入，确保 `testcase_file_path` 包含完整的全部测试用例
   - 写入前确认用户没有手动改动 Excel，若有需提前告知否则会被覆盖
   - ⚠️ **严禁**跳过本地文件步骤、直接在 MCP 工具调用参数里手写中文或 Unicode 转义码（`\uXXXX`）。手写 Unicode 转义码极易产生错别字（如 `\u5237` 刷 vs `\u5353` 卓），且难以肉眼发现。**必须先将用例写入本地 `.md` 文件，再通过 `testcase-to-excel` 技能读取写入 Excel。**

### 常用命令

```bash
# 环境自检（MOA / MCP / 用例目录）
python3 scripts/doctor.py
python3 scripts/doctor.py --run-moa-probe --check-testcases

# 生成前：推荐读哪些知识库
python3 scripts/suggest_kb_for_module.py 礼物 榜单
# 活动用例：全量 templates 索引 + 相似活动推荐
python3 scripts/suggest_kb_for_module.py --activity 世界杯 榜单

# 生成后：校验用例 Markdown
python3 scripts/check_testcase_md.py
python3 scripts/check_testcase_md.py temporary_testcase/某活动测试用例.md --strict

# 导出到桌面（评审/分享）
python3 scripts/export_testcases_to_desktop.py
python3 scripts/export_testcases_to_desktop.py --out-dir ./exports

# 维护者：同步四库（xlsx 路径可用环境变量 YAAHLAN_REGRESSION_XLSX / YAAHLAN_TASKS_XLSX）
python3 scripts/sync_all_kb.py
python3 scripts/sync_all_kb.py --dry-run
```





