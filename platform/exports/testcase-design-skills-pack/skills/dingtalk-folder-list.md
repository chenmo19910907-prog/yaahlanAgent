---
name: dingtalk-folder-list
description: 列举钉钉 alidocs 目录下全部子文档/版本用例表格链接（Box API 分页，默认目录 144 项），导出 JSON/CSV，并驱动 testcase-kb 全量同步。在用户要遍历钉钉目录、批量获取表格 URL、列举版本用例、同步知识库、或 MCP list_folder_contents 子项不全时使用。
---

# 钉钉目录列举与用例同步

## 何时使用

- 需要**遍历钉钉目录**下每个文档/表格，拿到 `https://alidocs.dingtalk.com/i/nodes/XXX` 链接
- 要**批量同步**「版本迭代用例」等到 `testcase-kb/`
- MCP `list_folder_contents` / `parse_folder_documents` **子项很少或为空**（mainsite 只嵌空间根目录，不含文件夹内 144 个子项）
- 用户逐条粘贴表格链接前的**清单导出**

## 核心能力（优先脚本，直接执行）

| 入口（推荐） | 作用 |
|------|------|
| `DingTalk/lookup_execute.py` | 按关键词查目录内任意表格链接（默认 `yaahlan-testcases`） |
| `DingTalk/collect_execute.py` | 列举目录子项链接（Box API，无需开浏览器） |
| `DingTalk/kb_sync_execute.py` | 按版本升序同步全部用例表 → `testcase-kb/` |
| `DingTalk/config/folders.json` | **已登记目录**（Yaahlan 测试用例等） |
| `DingTalk/config/kb.json` | 默认 `folderId` / 同步选项 |

实现代码在 `scripts/dingtalk_*.py`；文档见 `DingTalk/README.md`、`DingTalk/使用方法.md`。

**不要**用 Python 循环盲扫页面；用已落库脚本 + Cookie 即可。

## 鉴权

与 `dingtalk-doc-read` 相同，按优先级：

1. 环境变量 `DINGTALK_COOKIE`
2. `.cursor/mcp.json` → `dingtalk-doc` / `user-dingtalk-doc`
3. `~/.dingtalk_doc_cookie`

过期症状：401/403、「权限已过期」→ 请用户从浏览器复制 Cookie 写入上述位置后重试。

读表格内容还需 `dingtalk-excel-read` 的 `DINGTALK_AEGIS_*` / `DINGTALK_WORKID`（同步脚本自动读取）。

## 0. 已登记目录（Yaahlan 测试用例）

默认目录 id：`yaahlan-testcases`  
URL：[版本迭代用例](https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7wodldCZEEZ3n1VGXn6lpz)  
登记文件：`DingTalk/config/folders.json`

```bash
# 查看全部已登记目录
python3 DingTalk/lookup_execute.py --show-folders

# 按关键词查表格（返回 文件名 + URL）
python3 DingTalk/lookup_execute.py 2.5.4
python3 DingTalk/lookup_execute.py 消息

# 列举目录内全部表格
python3 DingTalk/lookup_execute.py --list

# 拿到 URL 后：读表用 dingtalk-excel-read MCP；同步知识库用 kb_sync --workbook-url
```

## 1. 列举目录链接

```bash
# 默认目录（DingTalk/config/kb.json → 版本迭代用例）
python3 DingTalk/collect_execute.py --only-spreadsheet

# 指定目录
python3 DingTalk/collect_execute.py \
  --folder-url "https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7wodldCZEEZ3n1VGXn6lpz" \
  --only-spreadsheet

# 导出 JSON（含 name / node_id / url / kind / extension）
python3 DingTalk/collect_execute.py \
  --only-spreadsheet \
  --output ~/Documents/cursor-mcp/dingExcel/folder-links.json

# 按文件名过滤
python3 DingTalk/collect_execute.py --name-contains "2.5.4"
```

输出：每行 `文件名\tURL`；stderr 打印合计数量。

## 2. 同步到 testcase-kb

```bash
# 先预览将处理的版本表（不写库）
python3 DingTalk/kb_sync_execute.py --list-only

# 全量同步（版本升序，较新版本覆盖同名模块，结束后跑优化流水线）
python3 DingTalk/kb_sync_execute.py

# 单表同步（URL 须为表格 node）
python3 DingTalk/kb_sync_execute.py \
  --workbook-url "https://alidocs.dingtalk.com/i/nodes/AR4GpnMqJzMvolLlhAjwyy2OVKe0xjE3"

# 仅某一版本
python3 DingTalk/kb_sync_execute.py --only-version 2.5.4
```

**跳过规则**：文件名含「土语/俄语专项」整表跳过；Sheet 无标准用例表头则跳过该 Sheet（仍会从钉钉读取）。

## 3. Playwright 对照模式（可选）

仅当需验证浏览器侧行为时使用（较慢）：

```bash
# 需 scripts/.venv-playwright（见下方一次性安装）
python3 DingTalk/collect_execute.py --playwright --headed
```

一次性安装：

```bash
cd scripts && python3 -m venv .venv-playwright
.venv-playwright/bin/pip install playwright
.venv-playwright/bin/python -m playwright install chromium
```

## 技术说明（排障用）

- **正确 API**：`GET https://alidocs.dingtalk.com/box/api/v2/dentry/list`（`dentryUuid` + `listDentrySource=2` + 分页 `loadMoreId`）
- **错误路径**：解析 HTML `mainsite_server_content` 子节点 → 只能拿到空间根约 29 项，**拿不到**「版本迭代用例」内 144 个表格
- 实现位于 `scripts/dingtalk_kb_source.py`（`list_folder_children_via_box` / `discover_workbooks`）

## 推荐工作流

```
列举链接（collect） → 用户确认或全量 sync → 单表补漏用 --workbook-url
```

用户说「把用例整理到知识库」→ 直接 `python3 DingTalk/kb_sync_execute.py`，无需先手工逐条喂链接。

## 与 dingtalk-doc-read 的分工

| 场景 | 用哪个 |
|------|--------|
| 读**单篇**需求文档正文 | `dingtalk-doc-read` → MCP `parse_document` |
| **列举目录**下全部表格链接 | 本技能 → `DingTalk/collect_execute.py` |
| **批量同步**版本用例到知识库 | 本技能 → `DingTalk/kb_sync_execute.py` |
| 目录 MCP 返回空/很少 | 改用本技能 Box API，勿反复 `parse_folder_documents` |
