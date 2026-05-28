## MOA 方法录入规范（你说我记）

本文件用于约定：你提供一段 MOA 抓包/请求信息后，我如何把它落到 `MOA/` 里，做到“后续一句话即可调用”。

### 0. 录入目标

- **可运行**：在本仓库用 `python3 MOA/moa_execute.py ...` 可以直接执行
- **可复用**：参数化（用户只给核心参数，如 roomId/level/userId 等）
- **可追溯**：README 里能看懂“这个方法干什么/怎么用/成功怎么判定”
- **安全**：Cookie/Token 只放本地（`MOA/.env.local`），绝不入库

---

## 1. 你需要提供的最小信息

把下面 3 块信息粘贴给我即可（越完整越好）。

### 1.1 入口请求（httpproxy）

从浏览器 Network 抓包复制这几项：

- **URL**：例如 `https://mse.wemomo.com/apirest/httpproxy/moa/test`
- **请求行**：例如 `POST /apirest/httpproxy/moa/test HTTP/1.1`
- **关键请求头**（能复制就复制，至少要有这些）：
  - `Content-Type: application/json`
  - `Origin`
  - `Referer`
  - `request-source: moaProxy`（如果有）
  - `User-Agent`
  - `Cookie`（敏感，可单独发我，我会只写进 `MOA/.env.local` 并加忽略）

### 1.2 请求 body（payload JSON）

把 Network 里 “请求数据 / Request Payload” 的 JSON 原样贴出来，例如：

```json
{
  "type": "moa",
  "url": "/service/xxx",
  "method": "execute",
  "params": [ ... ],
  "settings": { "time": "2000", "group": "default", "host": "", "headerType": "TXT" },
  "region": "alpha",
  "env": "alpha",
  "cluster": "stage",
  "server": "config"
}
```

### 1.3 参数说明（你口述我记录）

请告诉我：

- **这个 MOA 做什么**（一句话）
- **params 每个参数的含义与类型**（string/int/long…）
- **调取方式**（你希望以后怎么说）
  - 例：`给房间 <roomId> 升级到 <level>`
  - 例：`用户 <userId> 升到 VIP<level>`
- **成功判定**：返回体里哪个字段为成功（常见：外层 `ec=200`，内层 `result.ec=0`）
- **是否需要“先查再补差”**：比如升级等级需要先查当前经验值（可通过“加 0”查询）

---

## 2. 我会如何落库（我来做）

### 2.1 写入本地敏感配置（不入库）

我会把敏感信息放到 `MOA/.env.local`（已在 `.gitignore` 忽略），常见键包括：

- `MOA_ENTRY_URL`
- `MOA_COOKIE`
- `MOA_ORIGIN`
- `MOA_REFERER`
- `MOA_USER_AGENT`
- `MOA_REQUEST_SOURCE`

### 2.2 生成 payload 示例文件

我会在 `MOA/` 下新增一个 `*_payload.example.json`，内容来自你给的 body（用于后续复用与对齐）。

### 2.3 在脚本里加“可调用入口”

我会在 `MOA/moa_execute.py` 里新增一组参数（或子模式）来驱动这个方法，例如：

- `--room-id/--level`（升级房间等级，自动先查再补差）
- `--vip-user-id/--vip-level`（升级 VIP，自动先查再补差）
- 或通用 `--expr`（直接执行表达式，适合调试）

### 2.4 把规则/映射沉淀到配置文件

所有类似“等级阈值/映射表/常量规则”会写入：

- `MOA/config.json`

脚本会自动读取它。

### 2.5 README 记录

我会在 `MOA/README.md` 增加该方法的文档段落，至少包括：

- 方法用途
- 参数说明
- 最短可执行命令
- 成功判定与常见错误排查

---

## 3. 你给我的推荐模板（复制填空即可）

```text
【方法名称】：
【用途一句话】：

【入口 URL】：
【请求头（除 Cookie 外）】：
【Cookie】：（单独贴也行）

【payload JSON】：
（粘贴完整 JSON）

【params 说明】：
1) ...
2) ...

【我希望以后怎么说】：
（例如：把房间 89333567 升级到 5 级）

【成功判定】：
（例如：外层 ec=200 且 result.ec=0）

【是否需要先查再补差】：
（是/否；若是，如何查询当前值）
```

