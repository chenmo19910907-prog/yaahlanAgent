# MOA 方法录入规范（你说我来记）

目标：你把 MOA 请求信息（抓包/导出 JSON）和参数说明发我后，我会把它落到 `MOA/`，做到 **可执行脚本 + 可复用文档**，并把所有“规则/映射表/阈值”等沉淀到 `MOA/config.json`。

## 1) 你需要提供什么

### A. 请求入口（通常固定）

- `MOA_ENTRY_URL`：例如 `https://mse.wemomo.com/apirest/httpproxy/moa/test`
- 必要请求头（从抓包里抄）：
  - `Origin`
  - `Referer`
  - `User-Agent`
  - `request-source`（例如 `moaProxy`）
- Cookie：只用于本机执行，放到 `MOA/.env.local`（已忽略入库）

### B. body JSON（最关键）

把抓包里的 `请求数据` 原样贴出来（例如）：

```json
{
  "type": "moa",
  "url": "/service/xxx",
  "method": "yyy",
  "header": "",
  "params": [
    { "name": "1", "type": "string", "value": "..." },
    { "name": "2", "type": "int", "value": "..." }
  ],
  "settings": { "time": "2000", "group": "default", "host": "", "headerType": "TXT" },
  "region": "alpha",
  "env": "alpha",
  "cluster": "stage",
  "server": "config",
  "momoId": "...",
  "momoName": "..."
}
```

### C. 参数说明（你说清楚我就能做成 CLI）

按下面格式给我即可：

- **业务名**：例如「房间经验值」「VIP 经验值」
- **方法含义**：这个 MOA 做什么
- **参数列表**（按 `params` 顺序）：
  - 参数1：名字/类型/含义/示例/约束（范围、是否可为 0、是否必填）
  - 参数2：...
- **返回判定**：
  - 外层：`ec/em` 的成功条件（常见 `ec=0` 或 `ec=200`）
  - 内层：`result.ec/result.em/result.result` 的成功条件（常见 `result.ec=0`）
- **幂等/风险提示**：是否可以重复执行，是否可回滚

### D. （可选）“规则/映射表/阈值”

例如等级阈值、状态映射等，请直接给“键→值”列表。我会统一写进 `MOA/config.json`，并让脚本读取。

## 2) 我会怎么落地到仓库

- **新增/更新示例 payload**：`MOA/<业务>_payload.example.json`
- **脚本接入**：在 `MOA/moa_execute.py` 增加一组参数（例如 `--vip-*`），支持：
  - 指定增量执行
  - 只说目标等级/状态时，自动先查当前值再补差（如果该接口支持“0 查询”）
- **文档记录**：在 `MOA/README.md` 增加该方法的：
  - 目的、参数、示例命令、返回判定
- **配置沉淀**：所有规则统一进 `MOA/config.json`

## 3) 你给我信息的最简模板（复制后填空）

```text
【业务名】
【入口】MOA_ENTRY_URL=...
【MOA body JSON】(原样粘贴)
【参数说明】
1) ...
2) ...
【成功判定】外层ec=? 内层result.ec=?
【规则/阈值】(如果有)
```

