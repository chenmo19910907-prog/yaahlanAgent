---
name: testcase-to-excel
description: 从 temporary_testcase 文件夹读取测试用例，使用 MCP dingtalk-excel-write 写入钉钉 Excel。在测试用例生成完成后、需要将用例同步到钉钉 Excel 时使用。
---

# 测试用例写入钉钉 Excel

## 何时使用

- 测试用例已生成并保存在 `temporary_testcase` 文件夹后
- 需要将用例同步到钉钉 Excel 表格时
- 用户提供 `testcase_file_path`（钉钉 Excel URL）时

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `testcase_file_path` | 钉钉 Excel 完整 URL | `https://alidocs.dingtalk.com/i/nodes/XXX` |
| `temporary_testcase` | 用例源文件夹（默认项目根目录下） | `temporary_testcase/` |

## 执行流程

### 1. 读取用例文件

从 `temporary_testcase` 文件夹读取所有用例文件：

- 支持格式：`.md`（Markdown 表格）、`.csv`
- 按文件名排序，合并所有用例

### 2. 解析用例格式

目标 Excel 列格式：`编号` | `功能模块` | `测试步骤` | `预期结果`

**Markdown 表格解析**：
- 识别表头行（含 编号/用例ID、功能模块、测试步骤、预期结果/期望结果）
- 提取数据行，映射到对应列
- 用例ID/编号 → 编号；功能模块/用例标题 → 功能模块；测试步骤 → 测试步骤；期望结果/预期结果 → 预期结果

**CSV 解析**：
- 按逗号分隔，首行为表头
- 列名映射同上

### 3. 写入钉钉 Excel

使用 MCP `user-dingtalk-excel-write` 的 `write_sheet_data` 工具：

```
参数：
- url: testcase_file_path（钉钉 Excel URL）
- data: 二维数组，首行为表头 [['编号','功能模块','测试步骤','预期结果']]，后续为用例行
- startRow: 1（覆盖写入）或 N（追加到第 N 行）
- startColumn: 1
```

**写入策略**：
- 用例数 ≤ 50：一次性 `write_sheet_data` 写入
- 用例数 > 50：分批写入，每批约 50 行，`startRow` 递增

### 4. 校验

- 写入成功后，确认行数与用例数一致
- 若写入失败（如 InvalidAuthentication），按主 SKILL 中的钉钉认证修复流程处理

## 用例格式示例

**输入（temporary_testcase/xxx.md）**：
```markdown
| 编号 | 功能模块 | 测试步骤 | 预期结果 |
|------|----------|----------|----------|
| FS_001 | 头图 | 1.打开页面 | 头图正常展示 |
| FS_002 | 规则 | 1.点击规则 | 弹窗打开 |
```

**输出（钉钉 Excel）**：
- 第 1 行：编号, 功能模块, 测试步骤, 预期结果
- 第 2 行：FS_001, 头图, 1.打开页面, 头图正常展示
- 第 3 行：FS_002, 规则, 1.点击规则, 弹窗打开

## 执行步骤（Agent 操作清单）

1. **列出文件**：`Glob` 或 `Grep` 查找 `temporary_testcase/**/*.{md,csv}`
2. **解析内容**：逐文件读取，提取表格行，映射为 `[编号, 功能模块, 测试步骤, 预期结果]`
3. **合并数据**：表头 + 所有用例行，组成 `data` 二维数组
4. **调用 MCP**：`call_mcp_tool` server=`user-dingtalk-excel-write` toolName=`write_sheet_data`，传入 `url=testcase_file_path`、`data`、`startRow=1`
5. **分批处理**：若 `data` 行数 > 50，分多批 `write_sheet_data`，每批 `startRow` 递增

## 与主流程的配合

在 `soulchill营收活动用例自动生成` 流程中：

1. 用例生成后保存到 `temporary_testcase/`
2. 用户提供 `testcase_file_path`（钉钉 Excel URL）
3. 调用本技能，将 `temporary_testcase` 下用例写入钉钉 Excel
4. 确保 `testcase_file_path` 包含完整的全部测试用例
