---
name: code-multilang-review
description: 读钉钉翻译/多语言词条表，拉 voga-repos（含 H5），四端扫描与词条对齐，在词条表 I/J/K/L 写服务端/Android/iOS/H5 校验结果。用于「写回翻译文档」「多语言校验」「L列写H5」「对照翻译文档」。
---

# 写回翻译文档（五阶段）

| 阶段 | 做什么 | 约束 |
|------|--------|------|
| **1 读表** | AliDocs 翻译文档 + **功能版本 Sheet**（如 `2.6.1`）；读至 **H**；确认 **I/J/K/L** 表头 | A–H 词条列只读 |
| **2 拉代码** | `python3 DevCode/voga_pull_execute.py`；H5 用 `fe_pull_execute.py --feature` | 只读 |
| **3 四端扫描** | multiLang / strings / Localizable / yaahlan-fe i18n | — |
| **4 写 I/J/K/L** | I=服务端 J=Android K=iOS **L=H5** | `缺失:` 附 zh/en/ar；禁止改 A–H |
| **5 复核** | GET `I:L` | — |

默认翻译文档：`https://alidocs.dingtalk.com/i/nodes/ZgpG2NdyVXrA0gOgCx07o2kO8MwvDqPk`

工具台：**开发代码 → 写回翻译文档**（`multilang_doc_writeback`）。

## 触发

- 写回翻译文档 / 多语言文档写回 / L列写H5 / 对照翻译文档与代码

## 读写 API

与 `code-testcase-review` 相同：`get_token` → `workbooks/{id}/sheets` → `ranges/{col}`；写回用 PUT/MCP `dingtalk-excel-write` 或 `.cursor/skills/code-testcase-review/scripts/dingtalk_sheet.py`。

## 与用例审查配合

可先跑 `code-testcase-review` 得 H5 仓与分支，再在本 Skill **④** 仅写 **L** 列（用户指定「L列写H5」时只写 L）。
