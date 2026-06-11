# 测试报告生成（Report）

从**版本用例 xlsx** 读取各 sheet 的 D2 需求摘要与 Sheet1 I2 链接/缺陷统计，生成：

- `{xlsx文件名}_内网测试总结.html`
- `{xlsx文件名}_外网测试总结.html`

HTML 与 xlsx **同目录**输出；默认用系统浏览器打开（可通过环境变量 `COUNT_NO_BROWSER=1` 关闭）。

## 1) 准备环境

```bash
python3 -m venv Report/.venv
source Report/.venv/bin/activate
python -m pip install -r Report/requirements.txt
```

若未建 venv，脚本会尝试使用项目根目录的 `.venv-xlsx` 或 `.venv`（需已安装 openpyxl）。

## 2) 从钉钉 Excel URL 直接生成（推荐）

```bash
python3 Report/dingtalk_report_execute.py "https://alidocs.dingtalk.com/i/nodes/XXXX"
```

流程：拉取钉钉表格全部 sheet → 保存为桌面 `{版本}版本用例_钉钉.xlsx` → 生成内网/外网 HTML（与本地 xlsx 规则相同，D2 由脚本按 D/E 列回退统计）。

仅下载 xlsx、不生成报告：

```bash
python3 Report/dingtalk_report_execute.py --xlsx-only "https://alidocs.dingtalk.com/i/nodes/XXXX"
```

指定输出路径：

```bash
python3 Report/dingtalk_report_execute.py -o ~/Desktop/2.5.2版本用例.xlsx "https://alidocs.dingtalk.com/i/nodes/XXXX"
```

需配置环境变量 `DINGTALK_AEGIS_KEY`、`DINGTALK_AEGIS_SECRET`、`DINGTALK_WORKID`（与 `dingtalk-excel-read` MCP 相同；未设置时自动读 `~/.cursor/mcp.json`）。

钉钉报告链接规则（`dingtalk_report_execute.py` 自动应用）：

| 链接 | 来源 |
|------|------|
| 缺陷链接 | 写死 TB 地址 |
| 回归用例链接 | 写死钉钉回归表地址 |
| 版本用例链接 | 命令行传入的钉钉表格 URL |

缺陷各级数量仍从表格 I2 读取。

生成成功后会**自动用浏览器打开**内网、外网两份 HTML，**默认等待 5 秒**（可用环境变量 `REPORT_DELETE_DELAY_SEC` 调整）后**删除本地三个文件**（xlsx + 两份 HTML），避免浏览器尚未加载完就被删掉。

## 3) 指定本地 xlsx 生成报告

```bash
python3 Report/report_execute.py /path/to/v2.4.4版本用例（xxx）.xlsx
```

相对路径相对于**当前工作目录**：

```bash
cd ~/Downloads
python3 ~/CursorProjects/auto-generate-testcase/Report/report_execute.py v2.4.4版本用例.xlsx
```

## 4) 仅打印 I2 格式化文本

用于核对 Sheet1 I2 中的缺陷链接、用例链接与未完成/已完成缺陷统计：

```bash
python3 Report/report_execute.py --print-i2 /path/to/版本用例.xlsx
```

## 5) xlsx 数据约定

| 位置 | 含义 |
|------|------|
| 各 **visible** sheet 的 **D2** | 需求摘要。普通需求 sheet 用「用例条数」公式；**优化需求 / 技术优化** 等 sheet 用「技术优化需求」公式 |
| **Sheet1**（或首个 I2 非空的 visible sheet）的 **I2** | 缺陷链接、版本用例链接、回归用例链接；未完成/已完成缺陷各级数量 |

### D2 自动统计公式（普通需求 sheet）

在 **D2** 填入（按 sheet 名 + D7:D10000 预期结果条数 + E7:E10000 已执行条数统计）：

```excel
=IF(COUNTA(D7:D10000)=0,IF(ISERROR(FIND("（",SHEETSNAME(A1)&"（")),SHEETSNAME(A1),LEFT(SHEETSNAME(A1),FIND("（",SHEETSNAME(A1)&"（")-1))&"：用例条数0条，实际执行"&COUNTA(E7:E10000)&"条，执行率0.00%",IF(COUNTA(E7:E10000)>COUNTA(D7:D10000),IF(ISERROR(FIND("（",SHEETSNAME(A1)&"（")),SHEETSNAME(A1),LEFT(SHEETSNAME(A1),FIND("（",SHEETSNAME(A1)&"（")-1))&"：用例条数"&COUNTA(E7:E10000)&"条，实际执行"&COUNTA(E7:E10000)&"条，执行率100.00%",IF(ISERROR(FIND("（",SHEETSNAME(A1)&"（")),SHEETSNAME(A1),LEFT(SHEETSNAME(A1),FIND("（",SHEETSNAME(A1)&"（")-1))&"：用例条数"&COUNTA(D7:D10000)&"条，实际执行"&COUNTA(E7:E10000)&"条，执行率"&TEXT(COUNTA(E7:E10000)/COUNTA(D7:D10000),"0.00%")))
```

说明：

- **D 列**（第 7 行起）：有「预期结果」的行计为用例条数
- **E 列**（第 7 行起）：有「测试组结果-android」的行计为实际执行条数
- sheet 名含 `（` 时，摘要标题取括号前一段（与 `SHEETSNAME` 规则一致）
- 实际执行条数 **大于** 用例条数时，两项均取实际执行数，执行率固定 **100.00%**
- 报告脚本在 D2 为空或仅为未缓存公式时，会按相同规则从 D/E 列回退计算，无需先手工刷新 Excel

### D2 自动统计公式（技术优化 sheet）

在 **优化需求**、**技术优化**（或名称含「技术优化」）sheet 的 **D2** 填入（从 B 列「仅 B 有值、C/D 为空」的分组标题行生成子项列表）：

```excel
="技术优化需求："&CHAR(10)&TEXTJOIN(CHAR(10),TRUE,SEQUENCE(ROWS(FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))))&") "&IF(IFERROR(FIND("【",FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))),9999)<IFERROR(FIND("（",FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))),9999),IF(IFERROR(FIND("【",FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))),9999)>=9999,FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990="")),LEFT(FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990="")),IFERROR(FIND("【",FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))),9999)-1)),IF(IFERROR(FIND("（",FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))),9999)>=9999,FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990="")),LEFT(FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990="")),IFERROR(FIND("（",FILTER(B7:B990,(B7:B990<>"")*(C7:C990="")*(D7:D990=""))),9999)-1))))
```

说明：

- 分组标题行：**B 非空** 且 **C、D 均为空**
- 子项标题在 `【` 或 `（` 处截断（`【` 优先于 `（`）
- 报告脚本在公式未缓存时，会按相同规则从 B/C/D 列回退生成

## 6) 环境变量

| 变量 | 说明 |
|------|------|
| `COUNT_NO_BROWSER=1` | 本地 `report_execute.py` 生成后不自动打开浏览器 |
| `REPORT_DELETE_DELAY_SEC` | 钉钉流程：打开报告后、删除本地文件前的等待秒数（默认 `5`） |
