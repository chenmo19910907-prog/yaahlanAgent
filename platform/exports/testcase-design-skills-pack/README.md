# Yaahlan 用例设计 Skill 压缩包

打包时间：2026-08-13

## 使用顺序

1. **SKILL.md** — 主流程入口（读 PRD → 判类型 → 读知识库 → 生成用例）
2. **skills/prd-review.md** — 生成前先理解需求
3. **skills/dingtalk-doc-read.md** — 读钉钉 PRD
4. **skills/testcase-generator.md** — 生成规范与实践经验
5. **rules/** — 活动规则 + 版本回归规则
6. **skills/testcase-to-excel.md** — 写入钉钉 Excel
7. **scripts/check_testcase_md.py** — 落盘前校验

## 文件清单

| 路径 | 说明 |
|------|------|
| SKILL.md | Yaahlan 用例自动生成（主 Skill） |
| skills/testpoints-to-testcases.md | 指向根 SKILL，扩写入口 |
| skills/testcase-generator.md | 钉钉文档 → 用例生成器 |
| skills/prd-review.md | PRD 理解与审查 |
| skills/testcase-to-excel.md | 写入钉钉 Excel |
| skills/testcase-handwritten-excel-style.md | 手写 Excel 合并风格 |
| skills/user-testcase-style-shortphrase.md | 短语两段式风格 |
| skills/dingtalk-doc-read.md | 钉钉文档读取 |
| skills/dingtalk-folder-list.md | 钉钉目录/版本用例同步 |
| rules/testcase_generation_rules.md | 活动/通用业务规则 |
| rules/version_testcase_generation_rules.md | 版本 Case 规则 |
| rules/dingtalk_historical_testcase_to_md.md | 历史用例转 MD |
| scripts/check_testcase_md.py | Markdown 用例校验 |
| scripts/export_testcases_to_desktop.py | 导出 xlsx 到桌面 |
| scripts/suggest_kb_for_module.py | 生成前推荐知识库 |

## 常用命令

```bash
python3 scripts/suggest_kb_for_module.py 礼物 CP
python3 scripts/check_testcase_md.py temporary_testcase/xxx.md
python3 scripts/export_testcases_to_desktop.py
```

## 在 Cursor 中使用

将 `skills/*.md` 放入 `.cursor/skills/<name>/SKILL.md`，或将根 `SKILL.md` 放在项目根目录。
