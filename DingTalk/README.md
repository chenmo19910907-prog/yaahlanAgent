# 钉钉目录列举与 testcase-kb 同步

列举 [钉钉 alidocs](https://alidocs.dingtalk.com) 目录下全部版本用例表格链接，并按版本升序同步到 `testcase-kb/`。

> 能力口令与可复制命令见 **[使用方法.md](使用方法.md)**（由 `DingTalk/config/registry.json` 自动生成）。

## 是什么

「版本迭代用例」等文件夹在页面上有上百张表格，但 MCP `list_folder_contents` 只能解析 mainsite 内嵌的**空间根**子项（约 29 个），拿不到文件夹内的 144 个表格。

本模块通过浏览器同款的 **Box API**（`/box/api/v2/dentry/list`）分页列举全部子项，再调用钉钉 Excel API 同步到知识库。

## 目录结构

```
DingTalk/
├── README.md                 # 本文件
├── 使用方法.md                # 能力清单（自动生成）
├── collect_execute.py        # 列举目录链接
├── kb_sync_execute.py        # 同步 testcase-kb
├── lookup_execute.py         # 按关键词查目录内文件链接
├── prd_sync_execute.py       # 同步 PRD → prd-kb
├── config/
│   ├── registry.json         # 能力登记
│   ├── folders.json          # 已登记钉钉目录（用例/活动/PRD）
│   ├── kb.json               # 用例同步选项
│   └── prd.json              # PRD 同步选项
└── scripts/
    └── generate_index.py     # 生成 使用方法.md

# 实现代码（共享）
scripts/dingtalk_collect_folder_links.py
scripts/dingtalk_kb_sync.py
scripts/dingtalk_kb_source.py
```

## 环境配置

| 用途 | 配置位置 |
|------|----------|
| 列举目录 | `dingtalk-doc` → `DINGTALK_COOKIE`（`.cursor/mcp.json` 或 `~/.dingtalk_doc_cookie`） |
| 读取表格 | `dingtalk-excel-read` → `DINGTALK_AEGIS_*` / `DINGTALK_WORKID` |
| 已登记目录 | `DingTalk/config/folders.json` → `yaahlan-testcases` 等 |
| 默认目录 | `DingTalk/config/kb.json` → `folderId` / `folderUrl` |

Cookie 过期时从浏览器 alidocs 复制完整 Cookie 更新上述位置。

## 快速开始

```bash
# 查看已登记目录
python3 DingTalk/lookup_execute.py --show-folders

# 按关键词查表格链接（如 2.5.4）
python3 DingTalk/lookup_execute.py 2.5.4

# 列举默认目录下全部用例表链接
python3 DingTalk/collect_execute.py --only-spreadsheet

# 导出 JSON
python3 DingTalk/collect_execute.py --only-spreadsheet \
  --output ~/Documents/cursor-mcp/dingExcel/folder-links.json

# 预览可同步的版本表
python3 DingTalk/kb_sync_execute.py --list-only

# 全量同步 → testcase-kb/
python3 DingTalk/kb_sync_execute.py

# 单表同步
python3 DingTalk/kb_sync_execute.py \
  --workbook-url "https://alidocs.dingtalk.com/i/nodes/XXXX"

# 同步产品需求 → prd-kb/（.raw 摘录后按模块整理）
python3 DingTalk/prd_sync_execute.py --folder-id yaahlan-prd
python3 scripts/prd_kb_build.py --input-dir prd-kb/.raw --output-dir prd-kb
```

## 维护

| 操作 | 命令 |
|------|------|
| 刷新能力清单 | `python3 DingTalk/scripts/generate_index.py` |
| 改默认目录 | 编辑 `DingTalk/config/kb.json` 的 `folderUrl` |

## 与其他模块的关系

| 能力 | 模块 | 说明 |
|------|------|------|
| 读单篇需求文档正文 | `dingtalk-doc-read` Skill / MCP | `parse_document` |
| **列举目录 + 批量同步用例** | `DingTalk/` | 本模块 |
| 用例知识库 | `testcase-kb/` | 用例同步输出 |
| 需求知识库 | `prd-kb/` | PRD 同步输出 |
| Agent 技能 | `.cursor/skills/dingtalk-folder-list/` | 编排说明 |
