---
name: code-testcase-review
description: 从钉钉 AliDocs 读取测试用例表格、提取服务端仓库信息并拉取代码、交叉分析代码逻辑与现有用例，自动标注不符合预期的用例行（E列写fail），并将代码中未覆盖的场景补充为新用例追加到 Sheet 末尾。用于「用例覆盖率分析」「代码用例交叉验证」「补充测试用例」「标注fail」「服务端代码用例比对」。
---

# 代码 × 用例交叉审查工作流

## 触发时机

用户说以下任意一种时启动本流程：
- "读取用例，结合代码补充/验证"
- "用例覆盖率分析"
- "代码不符合用例的标注 fail"
- "拉取代码和用例做比对"
- "补充代码中没有覆盖到的用例"

---

## 第一阶段：读取用例文档

### 1.1 获取文档信息

向用户确认钉钉文档链接（AliDocs URL），或从上下文中提取 `workbookId`。

URL 格式示例：
```
https://alidocs.dingtalk.com/i/nodes/{workbookId}
```

### 1.2 获取 Access Token

```python
import httpx, asyncio

TOKEN_URL = "http://gaia-hg.momo.com/ding/excel/token"
AEGIS_KEY   = "6e187070-8dfc-4260-94b2-3a87d2408479"
AEGIS_SECRET = "b64afa70-52ce-4c3f-9221-d4bf83ddf265"
WORKID = "110762"
API_BASE = "https://api.dingtalk.com/v1.0/doc"

async def get_token():
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{TOKEN_URL}?aegisKey={AEGIS_KEY}&aegisSecret={AEGIS_SECRET}&workid={WORKID}",
                        headers={"User-Agent": "Mozilla/5.0"})
        d = r.json()
        return d["data"]["token"], d["data"]["operatorId"]
```

### 1.3 列举 Sheet 列表，定位目标 Sheet

```python
sheets_url = f"{API_BASE}/workbooks/{WORKBOOK_ID}/sheets?operatorId={op}"
# 响应中找 name 匹配目标 tab 的 sheetId
```

### 1.4 读取用例数据

```python
# 通常读 A:E 列；E 列为「覆盖率备注/仓库信息」
range_str = "A1:E500"
read_url = f"{API_BASE}/workbooks/{WORKBOOK_ID}/sheets/{SHEET_ID}/ranges/{range_str}?operatorId={op}"
```

**从读取结果中提取：**
- 现有用例列表（编号、功能模块、步骤、预期结果）
- 覆盖率备注列中的仓库名称和分支（搜索包含「仓库：」「分支：」的行）
  - 仓库地址规则：`https://git.wemomo.com/voga/{repo-name}`

---

## 第二阶段：拉取服务端代码

### 2.1 检查本地是否已有仓库

```bash
ls /Users/dingliang/Projects/{repo-name}
```

### 2.2 已有仓库 → 切换分支并更新

```bash
cd /Users/dingliang/Projects/{repo-name}
git fetch origin
git checkout {branch-name}
git pull origin {branch-name}
```

### 2.3 没有仓库 → Clone

```bash
git clone https://git.wemomo.com/voga/{repo-name}.git /Users/dingliang/Projects/{repo-name}
cd /Users/dingliang/Projects/{repo-name}
git checkout {branch-name}
```

---

## 第三阶段：代码 × 用例交叉分析

### 3.1 定位核心业务类

优先顺序：
1. `*BizService.java` — 核心业务逻辑
2. `*ServiceImpl.java` / `*FacadeImpl.java` — 接口实现
3. `*Controller.java` — HTTP 入口
4. `resources/multiLang/*.properties` — 错误提示文案

### 3.2 整理「代码实际行为清单」

对每个核心方法，整理：
- 入参校验点（null 检查、枚举校验、权限校验）
- 业务规则（阈值数字、时间限制、次数限制）
- 每个分支的错误码 / 异常类型
- 正常路径的返回结构

### 3.3 逐条比对现有用例

对每条用例判断：

| 情况 | 标记 | 处理 |
|---|---|---|
| 代码行为与预期结果一致 | ✅ 通过 | 不处理 |
| 代码行为 ≠ 用例预期（错误码/逻辑不符） | ❌ 不符 | E 列写 `fail`，F 列可选填原因 |
| 代码中有但用例未覆盖的场景 | ➕ 缺失 | 整理为新用例追加到 Sheet 末尾 |

**常见 fail 场景：**
- 枚举入参校验被静默 fallback（应报错却改用默认值）
- 错误文案与代码实际文案不一致
- 权限校验逻辑（只有 A 可以操作，用例写 B 也可以）
- 时限/阈值与代码常量不符（如用例写7天，代码是180天）

---

## 第四阶段：标注 fail

### 4.1 批量写入 fail 标记

```python
async def mark_fail(token, op, workbook_id, sheet_id, row_nums: list[int], reason: str = ""):
    auth_h = {"x-acs-dingtalk-access-token": token,
               "content-type": "application/json",
               "User-Agent": "Mozilla/5.0"}
    async with httpx.AsyncClient(timeout=20) as c:
        for row in row_nums:
            # E 列写 fail
            rng = f"E{row}"
            val = [["fail"]] if not reason else [["fail", reason]]
            # F 列有备注时用 E{row}:F{row}
            if reason:
                rng = f"E{row}:F{row}"
            url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{rng}?operatorId={op}"
            await c.put(url, headers=auth_h, json={"values": val})
            print(f"  行{row} → fail")
```

---

## 第五阶段：追加补充用例

### 5.1 整理新用例格式（4列）

```
[用例编号, 功能模块, case步骤描述, 预期结果]
```

- 编号从现有最大编号 + 1 开始（如 REL_060）
- 按功能模块分组

### 5.2 确认追加起始行

```python
# 读 A列最后有数据的行，+1 即为追加行
last_row = max(i+1 for i, row in enumerate(values) if row and any(c for c in row))
start_row = last_row + 1
```

### 5.3 批量写入

```python
async def append_cases(token, op, workbook_id, sheet_id, cases: list[list], start_row: int):
    auth_h = {"x-acs-dingtalk-access-token": token,
               "content-type": "application/json",
               "User-Agent": "Mozilla/5.0"}
    end_row = start_row + len(cases) - 1
    rng = f"A{start_row}:D{end_row}"
    url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{rng}?operatorId={op}"
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(url, headers=auth_h, json={"values": cases})
        print(f"写入 {len(cases)} 条用例到 {rng}，状态：{r.status_code}")
```

---

## 核心常量（项目固定）

```python
TOKEN_URL    = "http://gaia-hg.momo.com/ding/excel/token"
AEGIS_KEY    = "6e187070-8dfc-4260-94b2-3a87d2408479"
AEGIS_SECRET = "b64afa70-52ce-4c3f-9221-d4bf83ddf265"
WORKID       = "110762"
API_BASE     = "https://api.dingtalk.com/v1.0/doc"
LOCAL_REPO_BASE = "/Users/dingliang/Projects"
GIT_BASE_URL    = "https://git.wemomo.com/voga"
```

完整可复用脚本见 [scripts/dingtalk_sheet.py](scripts/dingtalk_sheet.py)

---

## 流程快速参考

```
读取钉钉文档（Sheet A:E列）
    ↓
提取仓库名+分支（覆盖率备注列）
    ↓
本地 git fetch/checkout/pull 或 clone
    ↓
扫描 *BizService / *ServiceImpl / properties 文件
    ↓
整理「代码实际行为清单」
    ↓
逐条比对用例
    ├── 不符合 → E列写 fail（可选F列写原因）
    └── 未覆盖 → 整理新用例（编号续接）
    ↓
批量写入 fail 标记
    ↓
追加补充用例到 Sheet 末尾
```

---

## 注意事项

- **🚫 严禁修改原始测试用例**：已有用例的 A/B/C/D 列（编号、功能模块、步骤、预期结果）**只读，任何情况下不得修改、覆盖或删除**。唯一允许写入的列是 E 列（`fail` 标记）和 F 列（原因备注）
- **禁止** `git add`、`git commit`、`git push`，只读代码，不提交
- 写入钉钉前先读当前末尾行号，防止覆盖已有数据
- 每次写入后用 GET 读取验证数据正确
- 仓库名称前缀固定：`https://git.wemomo.com/voga/`
- fail 原因尽量精确（引用代码行号或方法名），便于开发定位
