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

## 2) 指定 xlsx 生成报告（推荐）

```bash
python3 Report/report_execute.py /path/to/v2.4.4版本用例（xxx）.xlsx
```

相对路径相对于**当前工作目录**：

```bash
cd ~/Downloads
python3 ~/CursorProjects/auto-generate-testcase/Report/report_execute.py v2.4.4版本用例.xlsx
```

## 3) 仅打印 I2 格式化文本

用于核对 Sheet1 I2 中的缺陷链接、用例链接与未完成/已完成缺陷统计：

```bash
python3 Report/report_execute.py --print-i2 /path/to/版本用例.xlsx
```

## 4) xlsx 数据约定

| 位置 | 含义 |
|------|------|
| 各 **visible** sheet 的 **D2** | 需求标题；首行为模块名，后续行为「技术优化需求」子项 |
| **Sheet1**（或首个 I2 非空的 visible sheet）的 **I2** | 缺陷链接、版本用例链接、回归用例链接；未完成/已完成缺陷各级数量 |

## 5) 环境变量

| 变量 | 说明 |
|------|------|
| `COUNT_NO_BROWSER=1` | 生成后不自动打开浏览器 |
