# 钉钉营收活动测试用例自动生成

基于 Cursor Agent Skills 与钉钉 MCP 的营收活动测试用例自动生成工程。根据钉钉需求文档和通用测试规则，自动生成结构化测试用例并写入钉钉 Excel。

## 功能特性

- **需求解析**：从钉钉文档（普通文档/Excel）读取产品需求
- **规则驱动**：参考 `rules/testcase_generation_rules.md` 中的榜单、抽奖、兑换、礼包等通用规则补充用例
- **模板对齐**：相似模块（如房间榜/礼物榜）参考 `templates/` 下模板做结构对齐
- **用例输出**：生成 Markdown/JSON 用例，支持写入钉钉 Excel

## 项目结构

```
dingtalk-uc-auth-testcase-skill/
├── README.md                 # 本文件
├── SKILL.md                  # 主 Skill 定义（soulchill营收活动用例自动生成）
├── rules/
│   └── testcase_generation_rules.md   # 测试用例生成规则（榜单/抽奖/兑换/礼包）
├── templates/                # 模块用例模板
│   ├── 榜单.md
│   ├── 抽奖.md
│   └── 奖励领取.md
├── temporary_testcase/       # 生成的用例临时存放目录
├── .cursor/
│   ├── mcp.json              # MCP 服务器配置
│   └── skills/
│       ├── dingtalk-doc-read/       # 钉钉文档解析
│       ├── testcase-generator/      # 用例生成逻辑
│       └── testcase-to-excel/      # 用例写入钉钉 Excel
```

## 环境要求

- **Cursor**：支持 Agent Skills 和 MCP 的版本
- **钉钉文档权限**：需求文档需开启访问权限
- **MCP 配置**：需配置钉钉文档、钉钉 Excel 读写相关环境变量

## MCP 配置

在 `.cursor/mcp.json` 中配置以下 MCP 服务器：

| 服务器 | 用途 | 环境变量 |
|--------|------|----------|
| `dingtalk-doc` | 解析钉钉文档 | `DINGTALK_COOKIE` |
| `dingtalk-excel-read` | 读取钉钉 Excel | `DINGTALK_AEGIS_KEY`、`DINGTALK_AEGIS_SECRET`、`DINGTALK_WORKID` |
| `dingtalk-excel-write` | 写入钉钉 Excel | 同上 |

> 敏感信息请勿提交到版本库，建议使用环境变量或本地配置覆盖。

## 使用流程

### 1. 生成测试用例

提供钉钉需求文档 URL，由 Agent 执行：

1. 使用 `dingtalk-doc-read` 解析需求文档
2. 从需求表格提取所有模块（头图、规则、奖励、tab、业务模块等）
3. 按 `testcase_generation_rules.md` 和 `templates/` 补充通用用例
4. 生成用例并保存到 `temporary_testcase/`

### 2. 写入钉钉 Excel

提供钉钉 Excel URL，由 Agent 执行：

1. 从 `temporary_testcase/` 读取用例（支持 `.md`、`.json`）
2. 解析为 `编号 | 功能模块 | 测试步骤 | 预期结果` 格式
3. 通过 `dingtalk-excel-write` 写入钉钉 Excel（大批量自动分批）

### 3. 用例格式

| 字段 | 说明 |
|------|------|
| 用例ID | 唯一标识，如 `001` |
| 功能模块 | 按需求文档覆盖 |
| 测试步骤 | 1. 2. 3. 分行可执行步骤 |
| 期望结果 | 界面反馈、状态变化、系统响应 |

## 规则与模板

### 规则文档 (`rules/testcase_generation_rules.md`)

- **榜单**：数据格式、显示规则、交互、分页、计值、房间榜
- **抽奖**：积分获取、抽奖过程、奖励下发
- **兑换**：积分获取、兑换失败/成功
- **购买礼包**：礼包展示、购买/转赠成功/失败、状态更新

### 模板 (`templates/`)

- `榜单.md`：榜单类模块完整用例维度
- `抽奖.md`：抽奖活动用例模板
- `奖励领取.md`：任务型奖励领取用例模板

模板可从钉钉 Excel 的对应 sheet 同步更新。

## Skills 说明

| Skill | 说明 |
|-------|------|
| `dingtalk-doc-read` | 读取钉钉文档，支持 Cookie 过期时刷新 |
| `testcase-generator` | 从需求文档生成测试用例 |
| `testcase-to-excel` | 将用例写入钉钉 Excel |

## 扩展模板

从钉钉 Excel 同步模板到 `templates/`：

```
读取 https://alidocs.dingtalk.com/i/nodes/XXX 的 [sheet名] sheet
生成 [模块名].md 放到 templates 目录下
```

## 许可证

内部项目，未指定开源许可证。
