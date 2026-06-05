---
name: testpoints-to-testcases
description: 工作流见项目根 SKILL.md（含分场景简/中/详扩写密度）；扩写细则按需读 rules（勿预读全量）；「生成提速」见根 SKILL 同节。
---

# 技能入口：仓库根目录

**主流程**：项目根目录 **`SKILL.md`**（精简版；Agent **默认先读本文件**即可跑通）。

**扩展规则**：`rules/testcase_generation_rules.md`、`rules/version_testcase_generation_rules.md`（按需求类型择一为主），其余细则按根 `SKILL.md` 引用再读。

使用本技能时，请 **Read** 项目根 `SKILL.md` 并严格遵循其流程与路由。

**落盘/导出前**：先跑 `python3 scripts/check_testcase_md.py`，再 `python3 scripts/export_testcases_to_desktop.py`（**默认输出 ~/Desktop**；无桌面写权限时再加 `--out-dir ./exports`），见根 `SKILL.md`「常用命令」。
