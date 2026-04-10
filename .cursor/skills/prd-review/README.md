# PRD Review — 需求理解与审查

**本目录职责**：PRD 审查维度与用法；需求理解入口与索引已合并进 **SKILL.md** 文首。流程与知识库见 **.cursor/skills/qa-testcase-agent-system/testcase_agent_system_prompt.md**。

从产品文档中**理解需求**并检查是否完整、清晰，用于生成测试用例前的结构化理解。

## 在本项目中的位置

- **路径**：`overseas-social-app-qa/.cursor/skills/prd-review/`
- **与用例生成的关系**：生成用例前须先按 **SKILL.md** 理解需求，再结合项目规则与用例生成 Skills；流程与知识库见 **.cursor/skills/qa-testcase-agent-system/testcase_agent_system_prompt.md**。

## 使用方式

- **理解需求并生成用例**：先引用本 Skill 或 `@.cursor/skills/prd-review/SKILL.md`，对需求文档做功能类型判断与维度审查，输出理解摘要；再基于摘要与 knowledge-base 生成用例。
- **仅审查 PRD**：将 PRD 内容粘贴或引用后，要求按本 Skill 输出审查报告（必须补充/建议补充/待确认问题）。

## 审查维度摘要

功能目标、用户场景、交互与文案、业务规则、边界与异常、活动运营专项、支付经济专项、通知与触达。详见 `SKILL.md`。
