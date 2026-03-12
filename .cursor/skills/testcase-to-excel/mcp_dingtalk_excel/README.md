# 钉钉Excel操作 MCP 服务器

一个用于读取和写入钉钉Excel表格数据的MCP服务器。

## ✨ 功能特性

### 读取功能
- 📊 **完整数据获取**: 自动获取钉钉Excel表格中指定Sheet的所有数据
- 🚫 **智能过滤**: 自动过滤空行，只返回有效数据
- 🔄 **动态范围**: 根据Sheet维度信息自动确定数据范围

### 写入功能
- ✏️ **数据写入**: 向指定Sheet的指定位置写入数据
- ➕ **添加行**: 在表格末尾添加新行
- 🗑️ **删除行**: 根据序号删除指定行，并自动重新调整序号

### 通用功能
- 💾 **Token缓存**: 本地缓存访问令牌，避免重复请求
- ⚙️ **灵活配置**: 支持环境变量或参数传递应用凭证

## 📦 安装

### 方式一: 从源码安装

```bash
cd mcp_dingtalk_excel
pip install -e .
```

### 方式二: 使用 uv

```bash
uv pip install -e mcp_dingtalk_excel
```

## ⚙️ 配置

### 环境变量

本服务通过内部API获取访问令牌和操作者ID，需要在MCP配置中设置以下环境变量：

- `DINGTALK_AEGIS_KEY`: Aegis密钥
- `DINGTALK_AEGIS_SECRET`: Aegis密钥Secret  
- `DINGTALK_WORKID`: 工作ID
- `DINGTALK_EXCEL_OUTPUT_DIR`: 输出目录（可选，默认值为 `~/Documents/cursor-mcp/dingExcel`，目前暂未使用，为将来扩展预留）

这些环境变量可以在MCP配置文件中设置，也可以在调用工具时通过参数传递（参数优先）。

Aegis密钥和Aegis密钥Secret获取地址：[https://aegis.immomo.com/v3/app/my](https://aegis.immomo.com/v3/app/my)，点击右边的"➕"

内部API会返回：
- `token`: 钉钉访问令牌
- `operatorId`: 钉钉的unionid（作为操作者ID）

### 测试运行

**测试读取服务器：**
```bash
cd ~/codes/AIGC/mcp_dingtalk_excel
python3 server_read.py
```

**测试写入服务器：**
```bash
cd ~/codes/AIGC/mcp_dingtalk_excel
python3 server_write.py
```

看到服务启动（没有错误）就OK！按 `Ctrl+C` 停止。

### MCP 配置

在 Cursor 或其他支持MCP的客户端中配置。本项目提供两个独立的MCP服务器：

**1. 读取服务器（server_read.py）**
```json
{
  "mcpServers": {
    "dingtalk-excel-read": {
      "command": "python3",
      "args": [
        "~/codes/AIGC/mcp_dingtalk_excel/server_read.py"
      ],
      "env": {
        "DINGTALK_AEGIS_KEY": "你的aegis里的Key",
        "DINGTALK_AEGIS_SECRET": "你的aegis里的Secret",
        "DINGTALK_WORKID": "你的工号",
        "DINGTALK_EXCEL_OUTPUT_DIR": "~/Documents/cursor-mcp/dingExcel"
      }
    }
  }
}
```

**2. 写入服务器（server_write.py）**
```json
{
  "mcpServers": {
    "dingtalk-excel-write": {
      "command": "python3",
      "args": [
        "~/codes/AIGC/mcp_dingtalk_excel/server_write.py"
      ],
      "env": {
        "DINGTALK_AEGIS_KEY": "你的aegis里的Key",
        "DINGTALK_AEGIS_SECRET": "你的aegis里的Secret",
        "DINGTALK_WORKID": "你的工号"
      }
    }
  }
}
```

**同时配置两个服务器：**
```json
{
  "mcpServers": {
    "dingtalk-excel-read": {
      "command": "python3",
      "args": [
        "~/codes/AIGC/mcp_dingtalk_excel/server_read.py"
      ],
      "env": {
        "DINGTALK_AEGIS_KEY": "你的aegis里的Key",
        "DINGTALK_AEGIS_SECRET": "你的aegis里的Secret",
        "DINGTALK_WORKID": "你的工号"
      }
    },
    "dingtalk-excel-write": {
      "command": "python3",
      "args": [
        "~/codes/AIGC/mcp_dingtalk_excel/server_write.py"
      ],
      "env": {
        "DINGTALK_AEGIS_KEY": "你的aegis里的Key",
        "DINGTALK_AEGIS_SECRET": "你的aegis里的Secret",
        "DINGTALK_WORKID": "你的工号"
      }
    }
  }
}
```

**注意：** 这些环境变量可以在调用工具时通过参数覆盖，如果未提供参数则使用环境变量中的值。

**注意：**
- `command`: 如果你有很多python版本，可以写python的绝对路径，例如：`"~/anaconda3/envs/coderunner/bin/python"`
- `args`: 改成你自己文件夹的地址

## 🚀 使用方法

重启Cursor，然后在聊天框输入：

### 读取数据示例

```
请帮我获取这个钉钉Excel表格的数据：
URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
Sheet名称: 班次管理
```

AI会自动调用 `get_sheet_info` 工具！

### 写入数据示例

```
请帮我在这个钉钉Excel表格的第5行写入数据：
URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
数据: [["王五", "早班", "2025-01-15"]]
```

### 删除行示例

```
请帮我删除这个钉钉Excel表格中序号为8的行：
URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
```

### 添加行示例

```
请帮我在这个钉钉Excel表格末尾添加一行：
URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
行数据: [12, "新问题", "新答案"]
```

**注意：** 如果已在MCP配置中设置了环境变量，则无需在调用时传递 `aegisKey`、`aegisSecret` 和 `workid` 参数。

### Tool: get_sheet_info

**功能：** 获取钉钉Excel表格中指定Sheet的所有数据（自动过滤空行）

**示例1：指定Sheet名称（使用环境变量中的配置）**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "sheetname": "班次管理"
}
```

**示例2：使用默认第一个Sheet（使用环境变量中的配置）**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r"
}
```

**示例3：覆盖环境变量配置**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "sheetname": "班次管理",
  "aegisKey": "your_custom_aegis_key",
  "aegisSecret": "your_custom_aegis_secret",
  "workid": "your_custom_workid"
}
```

**输出：**
```
✅ 成功获取Excel表格数据

📊 Sheet名称: 班次管理
🔗 Excel URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
📏 数据行数: 15

📄 数据预览（前3行）:
  行1: ['姓名', '班次', '日期', ...]
  行2: ['张三', '早班', '2025-01-01', ...]
  行3: ['李四', '晚班', '2025-01-01', ...]
  ... 还有 12 行数据

📦 完整数据（JSON格式）:
[
  ["姓名", "班次", "日期", ...],
  ["张三", "早班", "2025-01-01", ...],
  ...
]
```

### Tool: write_sheet_data

**功能：** 向钉钉Excel表格中指定Sheet写入数据

**示例1：写入数据到指定位置（使用环境变量中的配置）**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "data": [
    ["姓名", "年龄", "城市"],
    ["张三", 25, "北京"],
    ["李四", 30, "上海"]
  ],
  "startRow": 1,
  "startColumn": 1
}
```

**示例2：写入到指定Sheet的指定位置**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "sheetname": "班次管理",
  "data": [
    ["王五", "早班", "2025-01-15"]
  ],
  "startRow": 5,
  "startColumn": 1
}
```

**参数说明：**
- `url`: 钉钉Excel的完整URL（必需）
- `data`: 要写入的数据，二维数组格式（必需）
- `sheetname`: Sheet名称（可选，未提供则使用第一个Sheet）
- `startRow`: 起始行号，从1开始（可选，默认为1）
- `startColumn`: 起始列号，从1开始（可选，默认为1）
- `aegisKey`, `aegisSecret`, `workid`: 可选，未提供则使用环境变量

**输出：**
```
✅ 成功写入Excel表格数据

📊 Sheet名称: 班次管理
   (使用默认的第一个Sheet)
🔗 Excel URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
📍 写入位置: 行1列1 到 行3列3
📏 写入数据: 3行 × 3列
```

### Tool: delete_row_by_seq

**功能：** 删除钉钉Excel表格中指定序号的行，并自动重新调整序号

**示例1：删除序号为5的行（使用环境变量中的配置）**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "seqNumber": 5
}
```

**示例2：删除指定Sheet中序号为8的行**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "sheetname": "班次管理",
  "seqNumber": 8
}
```

**参数说明：**
- `url`: 钉钉Excel的完整URL（必需）
- `seqNumber`: 要删除的序号（第一列的序号值）（必需）
- `sheetname`: Sheet名称（可选，未提供则使用第一个Sheet）
- `aegisKey`, `aegisSecret`, `workid`: 可选，未提供则使用环境变量

**输出：**
```
✅ 成功删除序号为 8 的行

📊 Sheet名称: Sheet1
   (使用默认的第一个Sheet)
🔗 Excel URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
🗑️ 删除行数: 1
📝 说明: 序号已自动重新调整
```

**注意：** 删除行后，后续行的序号会自动重新调整（例如：删除序号5后，原来的序号6变成5，序号7变成6，以此类推）。

### Tool: add_row

**功能：** 在钉钉Excel表格末尾添加新行

**示例1：在表格末尾添加新行（使用环境变量中的配置）**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "rowData": [12, "新问题", "新答案"]
}
```

**示例2：在指定Sheet末尾添加新行**
```json
{
  "url": "https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r",
  "sheetname": "班次管理",
  "rowData": ["赵六", "中班", "2025-01-16"]
}
```

**参数说明：**
- `url`: 钉钉Excel的完整URL（必需）
- `rowData`: 要添加的行数据，一维数组格式，例如：`['12', '问题', '答案']`。第一个元素通常是序号（必需）
- `sheetname`: Sheet名称（可选，未提供则使用第一个Sheet）
- `aegisKey`, `aegisSecret`, `workid`: 可选，未提供则使用环境变量

**输出：**
```
✅ 成功添加新行

📊 Sheet名称: Sheet1
   (使用默认的第一个Sheet)
🔗 Excel URL: https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMh2DNNdZrJkb4Mw9r
📍 添加位置: 第13行
📝 行数据: [12, '新问题', '新答案']
```

## 🔧 技术特性

### Token缓存机制

- 自动缓存访问令牌到本地文件（`.dingtalk_token_cache.json`）
- Token有效期为2小时（7200秒）
- 提前5分钟刷新，确保安全
- 减少不必要的API调用，提高效率

### 智能数据获取

- 自动获取Sheet维度信息（行数、列数）
- 根据实际维度动态确定数据范围
- 如果无法获取维度，使用默认范围（A1:ZZ10000）
- 确保获取所有有效数据

### 空行过滤

- 自动过滤所有单元格都为空的行
- 支持多种空值判断（None、空字符串、空白字符）
- 只返回包含有效数据的行

## 📖 支持的API

### 读取API
| API功能 | 说明 |
|---------|------|
| 获取Sheet列表 | 根据Sheet名称查找Sheet ID |
| 获取Sheet维度 | 获取Sheet的行数和列数 |
| 获取Sheet数据 | 获取指定范围的所有单元格数据 |

### 写入API
| API功能 | 说明 |
|---------|------|
| 写入Sheet数据 | 向指定范围写入数据（覆盖模式） |
| 删除行 | 删除指定序号的行并重新调整序号 |
| 添加行 | 在表格末尾添加新行 |

## 🔧 开发

### 项目结构

```
mcp_dingtalk_excel/
├── __init__.py           # 包初始化文件
├── server_read.py        # MCP服务器主文件（读取）
├── server_write.py       # MCP服务器主文件（写入）
├── dingExcel.py          # 原始脚本（保留）
├── pyproject.toml       # 项目配置
├── requirements.txt      # 依赖列表
├── README.md             # 说明文档
└── mcp_config_example.json  # MCP配置示例
```

## 🐛 已知限制

- ⚠️ 需要有效的钉钉应用凭证（AppKey和AppSecret）
- ⚠️ 需要工作簿的访问权限
- ⚠️ 操作者ID必须是有效的钉钉用户ID
- ⚠️ Sheet名称必须完全匹配（区分大小写）

## 📝 版本历史

### v1.1.0 (2025-01-XX)
- ✅ 新增写入功能
- ✅ 支持向指定位置写入数据（`write_sheet_data`）
- ✅ 支持删除指定序号的行（`delete_row_by_seq`）
- ✅ 支持在表格末尾添加新行（`add_row`）
- ✅ 删除行后自动重新调整序号

### v1.0.0 (2025-01-XX)
- ✅ 初始版本
- ✅ 支持Excel表格数据获取
- ✅ Token缓存机制
- ✅ 自动过滤空行
- ✅ 动态范围确定

## 📄 许可

本项目仅供学习和研究使用。

## 👨‍💻 作者

黄云堃 (Yunkun Huang)

---

**MCP版本**: 1.0.0  
**Python版本**: >=3.10  
**最后更新**: 2025-01-XX

