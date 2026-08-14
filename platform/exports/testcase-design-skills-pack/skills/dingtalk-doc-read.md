---
name: dingtalk-doc-read
description: 使用 MCP dingtalk-doc 读取钉钉需求文档（含目录列举 list_folder_contents、批量解析 parse_folder_documents），支持权限过期时自动刷新 Cookie。在需要解析钉钉文档、读取需求文档、或 parse_document 报错时使用。
---

# 钉钉文档读取技能

## 何时使用

- 需要从钉钉文档（alidocs.dingtalk.com）读取需求文档内容时
- 需要列出 **目录节点** 下有哪些子文档，或 **批量解析** 目录内多个文档时（`list_folder_contents` / `parse_folder_documents`）
- 测试用例生成流程中需要解析产品需求文档时
- parse_document 返回「权限过期」或 302 重定向错误时

## 使用方法

### 1. 读取文档

调用 MCP 工具 `parse_document`（server: `user-dingtalk-doc`）：

```
参数：
- url_or_node_id: 钉钉文档完整 URL 或 NODE_ID（必需）
- cookie: 可选，未提供时使用环境变量 DINGTALK_COOKIE
```

**示例**：`parse_document` 传入 `https://alidocs.dingtalk.com/i/nodes/XXX`

### 1.1 目录与子文档批量读取

- **`list_folder_contents`**：传入 **文件夹/目录** 节点的 `url_or_node_id`，返回 JSON 列表（每项含 `name`、`node_id`、`kind`：`folder` | `document`、`url`）。用于先看目录再决定解析哪些单篇。
- **`parse_folder_documents`**：在同一 MCP 上批量执行与 `parse_document` 相同的拉取与落盘；可调 `recursive`、`max_documents`、`max_folder_fetches`。子项解析依赖页面内嵌数据，若返回空列表，可对该目录节点执行一次 `parse_document`（保存 `*_mainsite.json`）对照结构是否变更。

**版本用例目录子项不全时**：MCP 只能解析 mainsite 内嵌的空间根子项（通常几十个），**拿不到**「版本迭代用例」这类文件夹内的全部表格（如 144 个）。改用 **`DingTalk/`** 模块或技能 **`dingtalk-folder-list`**：`DingTalk/collect_execute.py` / `DingTalk/kb_sync_execute.py`（Box API `/box/api/v2/dentry/list`）。

### 2. 权限过期时的处理

当返回以下任一情况时，视为权限/Cookie 过期：

- 错误信息包含「钉钉文档权限已过期」
- 错误信息包含「302」且重定向到 login
- 错误信息包含「未找到mainsite_server_content」（可能是登录页）

**处理步骤**：

1. 调用 `refresh_cookie` 工具，传入用户提供的新 Cookie
2. 或提示用户：在浏览器打开 https://alidocs.dingtalk.com 并登录，从开发者工具复制 Cookie，运行 `refresh_cookie` 并传入
3. 刷新成功后，重新调用 `parse_document`

### 3. 输出说明

解析成功后，输出目录默认为 `~/Documents/cursor-mcp/dingDoc/{文档标题}/`，包含：

- `*_mainsite.json`：页面元数据
- `*_document.json`：文档数据
- `*_content.json`：文档内容
- `*.html`：可读 HTML

## 与测试用例生成的配合

在 `soulchill营收活动用例自动生成` 流程中，本技能用于第一步：使用 `parse_document` 读取需求文档并分析，为后续用例生成提供输入。
