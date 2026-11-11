---
name: code-testcase-review
description: 从钉钉 AliDocs 读取测试用例表格、按 E 列仓库拉取 voga-repos（服务端 Java / Android / iOS / yaahlan-fe H5）并交叉分析代码与用例，E 列标 fail、未覆盖场景末尾补用例。用于「用例覆盖率分析」「代码用例交叉验证」「补充测试用例」「标注fail」「服务端/客户端代码用例比对」。
---

# 代码 × 用例交叉审查工作流

## 完整工作流（五阶段）

| 阶段 | 做什么 | 入口与约束 |
|------|--------|------------|
| **1 读用例** | 钉钉 AliDocs：`workbookId` + Sheet 名；读 **A–E**；备注解析仓库/分支；**B7=覆盖率任务代码质量平台** 时读 **C7/D7** 需求分支（无则忽略） | MCP / `scripts/dingtalk_sheet.py`；E 列为仓库/覆盖率备注 |
| **2 拉代码** | 本地更新或 clone 至 `voga-repos/` | `python3 DevCode/voga_pull_execute.py`（或 `--repo`）；按 E 列切分支 |
| **3 比对比** | 按仓扫描（Java；Android strings/VM；iOS Localizable/VC；yaahlan-fe i18n/页面）→ **代码行为清单** ↔ 用例 | 只读代码，**禁止** commit/push |
| **4 标注** | 与预期不符 → **E 列** `fail`；**F 列**可选原因 | **禁止**改 A–D（编号/模块/步骤/预期） |
| **5 补用例** | 未覆盖场景 → Sheet **末尾**追加 A–D，编号续接 | 写入前定位首空行；写入后 GET 复核 |

**形式**：非工具台一键脚本；由 Cursor Agent 按本 Skill 串行执行。前置拉仓能力见 DevCode `pull_voga_repos` / `pull_voga_repo_one`；工具台 **开发代码 → 用例审查** 对应 `code_testcase_review`。

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
  - 仓库地址规则：默认 `https://git.wemomo.com/voga/{repo-name}`；**H5** `yaahlan-fe` 为 `https://git.wemomo.com/yaahlan-fe`（见 `DevCode/config/repos.json` → `clone_urls`）
- **第 7 行（B7）**：若 B7 单元格为 **`覆盖率任务代码质量平台`**，则 **C7、D7** 为需求所属 **分支名**（可含 `分支：` 前缀）；C/D 为空或非该 B7 文案时 **不读取**。脚本：`extract_b7_requirement_branches` / `extract_sheet_git_context`，并与 E 列仓库备注合并缺省分支（`extract_repo_info`）

---

## 第二阶段：拉取开发代码

仓库清单与本地目录见 `DevCode/config/repos.json`（9 仓：5 服务端 + `voga_android` + `voga_ios` + `voga_ios_modules` + `yaahlan-fe` H5）。

### 2.1 默认路径（本仓库）

```bash
# 工作区根目录下
ls voga-repos/{repo-name}
python3 DevCode/voga_pull_execute.py
# 或单仓：python3 DevCode/voga_pull_execute.py --repo {repo-name}
```

### 2.2 按 E 列仓库名切换分支（若备注含分支）

```bash
cd voga-repos/{repo-name}
git fetch origin
git checkout {branch-name}
git pull origin {branch-name} --ff-only
```

### 2.3 未 clone 的仓

```bash
# clone URL 以 DevCode/devcode/repos.py → clone_url(name) 为准；voga 仓与 yaahlan-fe 不同前缀
git clone <clone-url> voga-repos/{repo-name}
cd voga-repos/{repo-name}
git checkout {branch-name}
```

### 2.4 前端独立 H5 仓（汇总表，与九仓清单分离）

钉钉 [前端项目汇总表](https://alidocs.dingtalk.com/i/nodes/kDnRL6jAJM3jk7A7hDK5ve77WyMoPYe1) Sheet **版本**：**H** 项目名、**O** git 仓名、**P** 功能描述。按功能只拉一个仓：

```bash
python3 DevCode/fe_pull_execute.py --feature VIP
python3 DevCode/fe_pull_execute.py --resolve-only --feature VIP   # 仅解析
python3 DevCode/fe_pull_execute.py --repo yaahlan-h5-vip          # 直拉仓名
```

配置：`DevCode/config/fe_projects_sheet.json`；默认 **SSH** clone（`repos.json` → `fe_clone_base_ssh`），避免无交互 HTTPS 失败。九仓 `voga_pull_execute.py` **不包含**表内各独立 H5 仓。

---

## 第三阶段：代码 × 用例交叉分析

### 3.0 按仓库类型分流（E 列 / 备注「仓库：」）

| 类型 | 仓库名（示例） | 扫描侧重 |
|------|----------------|----------|
| 服务端 | `voga-mts-*`、`voga-common` | Java Biz/Service/Controller、多语言 properties |
| Android | `voga_android` | Kotlin/Java 业务层、UI 入口、strings |
| iOS | `voga_ios`、`voga_ios_modules` | VC/业务模块、路由、Localizable |
| Web H5 | 汇总表 **O 列** 仓名（如 `yaahlan-h5-vip`）或单体 `yaahlan-fe` | 独立 H5 用 `fe_pull_execute`；`locales`/`i18n`/`lang` 与页面逻辑 |

同一用例表可含多仓备注：**按行或按模块对应的仓库名**，分别进入对应扫描规则后再汇总 fail / 补用例。

### 3.1 定位核心代码（服务端 Java）

优先顺序：
1. `*BizService.java` — 核心业务逻辑
2. `*ServiceImpl.java` / `*FacadeImpl.java` — 接口实现
3. `*Controller.java` — HTTP 入口
4. `resources/multiLang/*.properties` — 错误提示文案

### 3.1a 定位核心代码（Android · `voga_android`）

优先顺序（用功能关键词 / 模块名 grep）：
1. `**/src/main/java/**/*ViewModel.{kt,java}`、`***Presenter*`、`***Interactor*` — 业务与状态
2. `***Activity.{kt,java}`、`**/*Fragment.{kt,java}` — 页面入口、跳转与可见性
3. `***Repository*`、`*Api*` / Retrofit 接口 — 请求参数与错误分支
4. `**/res/values*/strings.xml`、`values-*` — Toast/弹窗/按钮文案
5. 与用例相关的 `Router` / `DeepLink` / `scheme` 处理类

### 3.1b 定位核心代码（iOS · `voga_ios` + `voga_ios_modules`）

- 主工程：`voga_ios/Voga/Yaahlan/`；子模块：`voga_ios_modules/` 下对应 Pod/子仓
- 优先顺序：
  1. `*ViewController.{m,mm,swift}`、`*View.{swift}` — 交互与展示条件
  2. `*Manager*`、`*Service*`、`*Handler*` — 业务规则与权限
  3. `*Router*` / `*Coordinator*` / URL Scheme — 跳转与拦截
  4. `**/*.lproj/Localizable.strings`、`*.strings` — 文案与多语言
  5. 网络层 `*API*`、Model 解析中的枚举/默认值（与用例边界对齐）

### 3.1c 定位核心代码（Web H5 · `yaahlan-fe`）

- 路径：`voga-repos/yaahlan-fe/`（各业务多为独立子目录，如活动页、运营后台前端）
- 优先顺序：
  1. 页面入口 `index.html`、路由/`router`、`pages`/`views`
  2. `locales`、`i18n`、`lang`、`*.json` 多语言包与 key
  3. 接口请求与错误/空态展示（axios/fetch 封装）
  4. 条件渲染、版本开关、白名单与 URL 参数（`_bid`、`_ui` 等）

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

**常见 fail 场景（服务端）：**
- 枚举入参校验被静默 fallback（应报错却改用默认值）
- 错误文案与代码实际文案不一致
- 权限校验逻辑（只有 A 可以操作，用例写 B 也可以）
- 时限/阈值与代码常量不符（如用例写7天，代码是180天）

**常见 fail 场景（Android / iOS）：**
- 按钮/入口 `visibility`、版本开关、AB 或 `BuildConfig`/`#if` 与用例假设不一致
- Toast / Alert / Dialog 文案与 `strings.xml` / `Localizable.strings` 不一致
- 客户端前置校验（登录态、角色、房间状态）与服务端用例描述混用导致预期偏差——以**当前扫描仓**代码为准标 fail 或注明「需服务端用例」
- 跳转被拦截（未处理 DeepLink、返回上一级）与用例步骤不符
- 列表分页、空态、loading 与代码分支未覆盖

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
LOCAL_REPO_BASE = "<工作区根>/voga-repos"  # 与 DevCode/config/repos.json 一致
REPOS_MANIFEST  = "DevCode/config/repos.json"
GIT_BASE_URL    = "https://git.wemomo.com/voga"  # yaahlan-fe 等见 repos.json clone_urls
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
按仓扫描：Java Biz/Service | Android VM/Activity/strings | iOS VC/Localizable | yaahlan-fe i18n/页面
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
- 仓库 clone 地址以 `DevCode/config/repos.json` 为准（voga 组与 `yaahlan-fe` 分组不同）
- fail 原因尽量精确（引用代码行号或方法名），便于开发定位
