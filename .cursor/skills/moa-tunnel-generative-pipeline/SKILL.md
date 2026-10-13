---
name: moa-tunnel-generative-pipeline
description: Tunnel 抓包 → 解析 body/调用链 → 生成式 MOA 试跑 →（可选）MOA/templates 固定模板入库。交给外部 Agent 时须同时提供本仓库、MOA/Tunnel 凭证、终端执行权限。触发词：Tunnel抓包、生成式MOA、抓包转MOA、MOA入库、sync_registry、moa-generative-run。
---

# Tunnel · 生成式 MOA · MOA 入库（一体化 Skill）

本文档把 **Tunnel 只读抓包**、**生成式 MOA 套壳执行**、**固定 MOA 模板入库** 串成一条 Agent 可照做的流水线。适用于 Yaahlan 测试环境（alpha / stage httpproxy）；**线上**须用户提示词含「线上环境」并走 `online/online_execute.py`。

## 0. 外部 Agent 前置条件（必读）

| 条件 | 说明 |
|------|------|
| 代码仓库 | 克隆本 monorepo；命令均从仓库根目录执行 |
| MOA 凭证 | `MOA/.env.local`（MSE / 质量平台 httpproxy 可用） |
| Tunnel 凭证 | 复用 `MOA/.env.local` 内 `tunnel_login_session`，或 `Tunnel/.env.local` 的 `TUNNEL_COOKIE` |
| 执行能力 | Agent 须能跑 `python3 MOA/moa_execute.py`、`Tunnel/tunnel_execute.py` 等 |
| 不能仅靠本文 | 无仓库/无凭证/无终端 → 只能「纸上流程」，无法验收 |

挂到 Cursor 时：将本文件放在 `.cursor/skills/moa-tunnel-generative-pipeline/SKILL.md`，并在 Rules 中强调「试跑成功再入库」「禁止探活代替业务试跑」。

---

## 1. 概念与模块分工

| 模块 | 路径 | 职责 |
|------|------|------|
| Tunnel | `Tunnel/` | 按 userId 查 HTTP 抓包列表与 request/response |
| MOA-generative | `MOA-generative/` | 抓包 body + **调用链 ServiceUrl/Method** → 可执行 payload |
| MOA 固定模板 | `MOA/templates/` + `MOA/config/registry.json` | 参数化、可重复调用的后门/测试 MOA |
| 工作流 | `workflow/workflows/moa-generative-run.json` | 一键：生成 payload + `moa_execute` |
| 工具台 | `platform/catalog.html` | registry 变更后由 `after_registry_update.py` 刷新 |

**两种 MOA 形态**

1. **生成式（临时）**：payload 多在 `.tmp/` 或 `MOA-generative/templates/example-*.body.json`；适合「端上 HTTP 已存在、无现成 MOA 模板」。
2. **固定模板（持久）**：写入 `MOA/templates/<名>.json`，试跑成功后 **sync_registry**，供自然语言 / 工具台反复调用。

---

## 2. Tunnel 抓包（实现与 Agent 步骤）

### 2.1 平台与 API

- Web：[tunnel.wemomo.com](https://tunnel.wemomo.com)
- CLI：`GET {TUNNEL_BASE_URL}/api/requests`（默认 `https://tunnel.wemomo.com`）
- 实现：`Tunnel/tunnel_execute.py` → `Tunnel/tunnel/client.py`

### 2.2 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `TUNNEL_BASE_URL` | `https://tunnel.wemomo.com` | |
| `TUNNEL_COOKIE` | — | 须含 `tunnel_login_session` |
| `TUNNEL_G_APPID` | `All` | 可 `yaahlan` |
| `TUNNEL_G_ENV` | `alpha` | 测试；线上用 `online` 模块 → `overseas` |

Cookie 过期时从浏览器 Tunnel 页或 MSE 重新复制；**勿提交 Git**。

### 2.3 命令（测试环境）

```bash
# 最近 1 小时列表（表格摘要）
python3 Tunnel/tunnel_execute.py --momoid <userId> --since 3600

# URL 关键字（gift、login、likeContent 等）
python3 Tunnel/tunnel_execute.py --momoid <userId> --keyword <kw> --since 7200

# 完整 JSON（解析 request/response）
python3 Tunnel/tunnel_execute.py --momoid <userId> --since 3600 --output json

# 单条展开（_id 来自列表 key）
python3 Tunnel/tunnel_execute.py --momoid <userId> --request-id <_id> --since 7200
```

**线上环境**（用户话术含「线上环境」）：

```bash
python3 online/online_execute.py tunnel --momoid <userId> --since 3600
python3 online/online_execute.py tunnel --momoid <userId> --keyword gift --since 7200 --output json
```

### 2.4 响应结构

- 顶层 `ec=200` 表示查询成功
- `data.list`：dict，key 为 `_id`；每条含 `url`、`method`、`time`、`status`、`request`、`response` 等
- **列表项已含 request/response**，一般不必再调浏览器详情 API
- 浏览器单条链接（写 bug / 人工核对）：
  `https://tunnel.wemomo.com/request/<_id>?req_time=<unix>&g_appid=All&g_env=alpha`

### 2.5 Agent 从抓包提取什么

| 字段 | 用途 |
|------|------|
| `url` | HTTP 路径；**末段常 ≈ method 名**（仅参考，不能代替调用链） |
| `request` / `request.body` | 生成式 MOA 的 **body**（须为 JSON object） |
| `momoid` | 与操作账号 userId 一致 |
| `_id` + `time` | 附 tunnel 链接、对照 MOA-generative/mappings.md |

**典型流程**：真机/App 完成操作 → `--since 600~3600` 拉包 → `--keyword` 缩小 → `--output json` 或 `--request-id` 取 body → 落盘如 `.tmp/capture_<接口>.body.json`（UTF-8，pretty 或 compact 均可）。

### 2.6 与 adb 联动（可选）

```bash
python3 adb/adb_execute.py run --macro <片段> --tunnel-account <账号> --tunnel-keyword <kw>
```

详见 `.cursor/skills/adb-tunnel-verify/SKILL.md`、`Tunnel/README.md`。

---

## 3. 生成式 MOA（Tunnel → payload → 执行）

### 3.1 核心规律（套壳铁律）

端上请求经 MSE **httpproxy** 转发到后端 MOA 服务，质量平台 payload 必须：

1. **`url`**：调用链里的 **ServiceUrl**（形如 `/service/...`），**禁止**仅凭 HTTP 路径猜测
2. **`method`**：调用链 Method（注意大小写，`signin` ≠ `signIn`）
3. **body 双写**：
   - `header` = body 的 JSON **字符串**（`separators=(",", ":")` 紧凑序列化）
   - `params[0].type` = `"json"`
   - `params[0].value` = body **对象**
   - `params[0].json` = 与 `header` **相同字符串**

违反双写常见报错：`ClassCastException`、`System error`。

默认 meta（`build_payload.py`）：`type=moa`、`key=momo.pt.toB.cosmos-server.quality-platform.codequality`、`region/env=alpha`、`cluster=stage`、`settings.time` 为超时毫秒。

### 3.2 如何得到 ServiceUrl / Method

1. Tunnel 打开对应 HTTP 请求
2. 查看 **调用链**（MSE / Tunnel UI）：取落地 **ServiceUrl** 与 **Method**
3. 对照已验证表：`MOA-generative/mappings.md`（新映射验证通过后追加一行）
4. HTTP 末段仅作线索，例如：
   - `/yaahlan/sign/signIn` → `/service/yaahlan-trick/external/app-task` + `signIn`
   - `/yaahlan/feed-interact/likeContent` → `/service/feed/external/feed-interact-stage` + `likeContent`

### 3.3 推荐入口：工作流 `moa-generative-run`

定义：`workflow/workflows/moa-generative-run.json`

```bash
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/feed/external/feed-interact-stage \
  --method likeContent \
  --body-file .tmp/like_body.json \
  --timeout-ms 20000 \
  --strict 0
```

| 参数 | 含义 |
|------|------|
| `--service-url` | 调用链 ServiceUrl |
| `--method` | MOA method |
| `--body-file` | Tunnel 导出的 request body JSON 文件 |
| `--timeout-ms` | 写入 `settings.time` 并传给 `moa_execute` |
| `--strict 0` | **默认**：代理可达即成功（已签到/已点赞等业务拒绝也算过） |
| `--strict 1` | 要求业务 `success=true` 或 `ec/code` 为 0/200 |

报告目录：`.tmp/workflow_runs/`。

### 3.4 等价脚本

**一键生成 + 执行**（与工作流同逻辑）：

```bash
python3 MOA-generative/scripts/run_generative_moa.py \
  --url /service/yaahlan-trick/external/app-task \
  --method signIn \
  --body-file MOA-generative/templates/example-signIn.body.json \
  --out .tmp/generative_moa_payload.json \
  --timeout-ms 20000 \
  --strict 0
```

stdout 为 JSON 摘要：`ok`、`proxyOk`、`proxyReason`、`business`、`payloadPath`、`raw`。

**仅生成 payload**：

```bash
python3 MOA-generative/scripts/build_payload.py \
  --url <ServiceUrl> \
  --method <Method> \
  --body-file <body.json> \
  --out .tmp/generative_moa_payload.json \
  --timeout-ms 20000

python3 MOA/moa_execute.py \
  --payload-file .tmp/generative_moa_payload.json \
  --timeout-ms 20000
```

也可 `--body-json '{...}'` 代替 `--body-file`。

### 3.5 成功 / 失败判定（`run_generative_moa.py`）

**代理层失败（须改 url/method 或套壳）**

| 现象 | 处理 |
|------|------|
| `No address found` | ServiceUrl 错误或未注册路由 |
| `Method not found` | method 拼写/大小写错误 |
| `ClassCastException` | body 未按 json 双写 |
| proxy outer `ec` 非 0/200 | 查 stderr / 原始响应 |

**业务层（`--strict 1` 时才强制）**

- 内层 `success=true` 或 `ec/code` ∈ {0, 200} → 业务成功
- `ec=40002` 等「已点赞/已签到」在 `--strict 0` 下仍算 **流水线成功**（代理已通）

### 3.6 生成式能力登记（MOA-generative registry）

重复使用的接口可登记 `MOA-generative/config/registry.json`（示例能力、form 脚本），刷新：

```bash
python3 MOA-generative/scripts/generate_index.py
```

**不等于** `MOA/templates` 入库；后者见第 4 节。

### 3.7 闭环示例（点赞）

```bash
# 1) 用户 App 点赞后抓包
python3 Tunnel/tunnel_execute.py --momoid 100334384 --keyword likeContent --since 1800 --output json
# 2) 从匹配项取出 request body 写入文件
# 3) 调用链确认 url/method（或查 mappings.md）
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/feed/external/feed-interact-stage \
  --method likeContent \
  --body-file .tmp/like_capture.json \
  --strict 0
```

仓库内固定模板等价物：`MOA/templates/动态-帖子点赞.json`（已入库，可改 `contentId` 后直接 `--payload-file`）。

---

## 4. MOA 固定模板入库（registry）

### 4.1 何时入库

- 同一接口需 **反复调用**、工具台 / 自然语言可发现
- 生成式试跑稳定后，将 payload **参数化** 固化为 `MOA/templates/*.json`
- **禁止**：未试跑成功就 `sync_registry`；试跑失败不得入库
- **禁止**（探活代替入库）：`MOA检查`、`doctor`、`credential_probe`、`moa_execute --vip-query-current` 等仅验证凭证的命令不能代替目标接口试跑

### 4.2 模板文件结构

路径：`MOA/templates/<能力名>.json`

必填字段示例见 `MOA/templates/动态-帖子点赞.json`：

- `type`, `key`, `url`, `method`, `header`, `params`, `settings`, `region`, `env`, `cluster`, `server`, `momoId`, `momoName`
- 可选 **`_registry`**（推荐，供 sync 生成 catalog 元数据）：
  - `id`：registry 唯一 id（冲突时 sync 自动加后缀）
  - `name`：展示名
  - `category`：分类
  - `description`：功能说明（含 HTTP 对照、参数含义、常见 ec）
  - `prompts`：自然语言触发句数组
  - `cli` / `commandSuffix`：追加到 `moa_execute` 的 CLI（如 `--diamond-user-id {{userId}}`）

**执行时**：`MOA/moa/payload.py` 会 **`pop("_registry")`**，不会发给 MOA 网关。

### 4.3 标准 Agent 流程

```
依据 PRD/抓包/附图
  → 编写 MOA/templates/<名>.json（含 _registry）
  → python3 MOA/moa_execute.py --payload-file MOA/templates/<名>.json [业务 CLI 参数]
  → 退出码 0 且响应符合预期
  → （默认）auto_sync_registry
  → 确认 MOA/config/registry.json 出现 id
  → 确认 MOA/使用方法.md / platform/catalog.html 已更新
```

**试跑命令示例**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/templates/动态-帖子点赞.json \
  --timeout-ms 20000
```

跳过自动入库：

```bash
python3 MOA/moa_execute.py --payload-file MOA/templates/新模板.json --no-auto-sync-registry
```

### 4.4 自动入库机制

- 入口：`MOA/moa/cli.py` → `_exit_with_auto_sync` → `MOA/moa/registry_sync.py`
- 条件：`--payload-file` 指向 `MOA/templates/` 下 `.json`；该文件名尚未出现在 registry 各条 `command` 中；试跑 **returncode=0**
- 动作：运行 `MOA/scripts/sync_registry.py` → `MOA/scripts/generate_index.py` → `platform/scripts/after_registry_update.py`

**手动入库**：

```bash
python3 MOA/scripts/sync_registry.py --dry-run   # 预览
python3 MOA/scripts/sync_registry.py             # 写入 registry + 刷新文档
```

`sync_registry` 扫描 `MOA/templates/*.json`，凡 **command 未引用** 的文件各增一条 registry item；`_registry` 缺省时从文件名/url 推断 category/description。

### 4.5 入库验收清单

回复用户或 PR 时建议包含：

| 项 | 示例 |
|----|------|
| 能力名 | 动态-帖子点赞 |
| 模板路径 | `MOA/templates/动态-帖子点赞.json` |
| registry id | `feed_like_feed` |
| 命令 | `python3 MOA/moa_execute.py --payload-file MOA/templates/动态-帖子点赞.json` |

### 4.6 从生成式到固定模板

1. Tunnel 抓包 + 生成式试跑确认 url/method/body 结构
2. 将 body 中易变字段（userId、roomId、contentId 等）保留为可改字段
3. 复制 `.tmp/generative_moa_payload.json` 到 `MOA/templates/<语义名>.json`
4. 补全 `_registry`（id、prompts、description）
5. 再跑 `moa_execute --payload-file` 验收 → 自动或手动 sync
6. 在 `MOA-generative/mappings.md` 追加 HTTP↔MOA 一行（若为新映射）

---

## 5. 端到端 Still 流程（Agent 逐步验收）

下列为 **一段一验** 推荐顺序（禁止跳过试跑直接入库）：

| 步 | 动作 | 验收 |
|----|------|------|
| 1 | 确认 userId；`Tunnel/tunnel_execute.py --momoid ... --since ...` | 能拉到列表 |
| 2 | 真机/App 触发目标行为 | — |
| 3 | `--keyword` / `--request-id` 取 **request body** | JSON object 落盘 |
| 4 | 调用链得到 **ServiceUrl + Method**（查 mappings 辅助） | 与 HTTP 末段一致或表中有记录 |
| 5 | `workflow run moa-generative-run` 或 `run_generative_moa.py` | stdout `ok=true` 或知悉 strict 下业务 ec |
| 6 | （可选）固化 `MOA/templates/` + `_registry` | — |
| 7 | `moa_execute --payload-file MOA/templates/...` | returncode 0 |
| 8 | 检查 `MOA/config/registry.json` | 含新 `id` |
| 9 | （可选）`MOA-generative/mappings.md` 追加 | 团队可复用 |

---

## 6. 铁律与常见错误

### 6.1 禁止

- 未试跑成功执行 `sync_registry` 并宣称已入库
- 用 MOA 探活/ doctor 代替 **目标模板** 试跑
- 无调用链仅凭 HTTP path 编造 ServiceUrl
- body 只填 `params` 不写 `header`（或把 body 当纯 TXT）
- 将 `.env.local`、Cookie 提交 Git
- 用户未说「线上环境」时调用 `online/` 或 overseas 抓包

### 6.2 错误速查

| 错误 | 原因 | 修复 |
|------|------|------|
| Tunnel ec≠200 / 空列表 | Cookie 过期、momoid 错、时间窗太短 | 更新 Cookie、加大 `--since` |
| No address found | ServiceUrl 错 | 调用链 / mappings |
| Method not found | method 大小写 | 改 method |
| ClassCastException | 未双写 json | `build_payload.py` 规则 |
| auto_sync 未触发 | payload 不在 `MOA/templates/` 或已登记 | 路径与 registry |
| 业务 ec 拒绝 | 状态不允许（已点赞等） | strict=0 视为代理成功；strict=1 须换数据 |

---

## 7. 代码索引（便于外部 AI 读源码）

| 能力 | 文件 |
|------|------|
| Tunnel CLI | `Tunnel/tunnel_execute.py`, `Tunnel/tunnel/cli.py`, `Tunnel/tunnel/client.py` |
| 生成 payload | `MOA-generative/scripts/build_payload.py` |
| 生成+执行 | `MOA-generative/scripts/run_generative_moa.py` |
| 工作流定义 | `workflow/workflows/moa-generative-run.json` |
| MOA 执行 | `MOA/moa_execute.py`, `MOA/moa/cli.py` |
| 剥离 _registry | `MOA/moa/payload.py` |
| 自动入库 | `MOA/moa/registry_sync.py`, `MOA/scripts/sync_registry.py` |
| HTTP↔MOA 表 | `MOA-generative/mappings.md` |
| Tunnel Skill 摘要 | `.cursor/skills/tunnel-read/SKILL.md` |
| adb+Tunnel | `.cursor/skills/adb-tunnel-verify/SKILL.md` |

---

## 8. 文档与工具台

| 文档 | 生成方式 |
|------|----------|
| `MOA/使用方法.md` | `python3 MOA/scripts/generate_index.py` |
| `MOA-generative/使用方法.md` | `python3 MOA-generative/scripts/generate_index.py` |
| `Tunnel/使用方法.md` | `python3 Tunnel/scripts/generate_index.py` |
| `platform/catalog.html` | registry 更新后 `platform/scripts/after_registry_update.py` 或 `python3 platform/open_catalog.py` |

修改 `*/config/registry.json` 或新增模板入库后，**必须**跑对应 `generate_index`（sync_registry 已会自动触发 MOA 侧）。

---

## 9. 最小可复制示例（给外部 AI  smoke）

在仓库根、凭证已配置的前提下：

```bash
# A. Tunnel 可读
python3 Tunnel/tunnel_execute.py --momoid <userId> --since 3600

# B. 生成式 MOA（无需真抓包，用仓库示例 body）
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/yaahlan-trick/external/app-task \
  --method signIn \
  --body-file MOA-generative/templates/example-signIn.body.json \
  --strict 0

# C. 固定模板（已入库示例）
python3 MOA/moa_execute.py --payload-file MOA/templates/动态-帖子点赞.json --no-auto-sync-registry
```

A/B/C 均成功 → 外部 Agent 已具备复现本 Skill 全流程的环境。
