---
name: tunnel-mock
description: Tunnel 抓包平台 Mock：param_mock 字段覆盖与 mock_cases 整包响应。在用户要 mock 接口返回、改 CP 爱意宝箱倒计时 countdownSec、模拟 ec/分页/字段值，或问 tunnel mock 怎么用 时使用。
---

# Tunnel Mock

## 何时使用

- 改 **单个 response 字段**（推荐）：`param_mock`，如 CP 爱意宝箱 `data.countdownSec`
- 改 **整段 response JSON**：`mock_cases`
- 测异常码、边界值、倒计时归零，而不改后端/MOA

## 前置条件

- `MOA/.env.local` 含 `tunnel_login_session`（或 `Tunnel/.env.local` 的 `TUNNEL_COOKIE`）
- 目标 **userId（momoid）**；手机号先 `MOA/moa_execute.py --query-user-by-phone`
- App **先触发一次真实请求**（如打开 CP 爱意宝箱页），以便 Tunnel 有 URI 与 baseline response

## 两种 Mock

| 类型 | API | CLI | 适用 |
|------|-----|-----|------|
| **整包 Mock** | `POST /api/mock_cases?g_appid=All&g_env=alpha` | `case-create` | 在 Tunnel 详情页编辑整段 response（如改 `data.countdownSec`） |
| **字段 Mock** | `POST /api/param_mock` | `param-set` / `field` | 只改单个字段，payload 更小 |

抓包列表里 `param_mock=1` / `is_mock=1` 表示该请求已被 Mock 命中。

## 整包 Mock（你刚用的方法）

Tunnel 详情页 → Mock → 编辑 response JSON → 提交，对应：

```http
POST /api/mock_cases?g_appid=All&g_env=alpha
Content-Type: application/json

{
  "uri": "http://gw-api-alpha.yaahlan.fun/yaahlan/trick/cpLoveChest/getCpLoveChestHomepage",
  "json": "{...整段 response 字符串，内含 data.countdownSec...}",
  "index": 0,
  "name": "",
  "momoid": "100414599",
  "appId": "All",
  "enable": 1
}
```

要点：

- **`json` 是字符串**，不是嵌套 object（与浏览器 Network 面板一致）
- **`enable: 1`** 表示创建后立即生效
- 改倒计时：在 `json` 内把 **`data.countdownSec`** 设为秒数（你示例为 `60`）
- **`uri`** 必须是完整网关 URL
- 测试环境 query：`g_appid=All`、`g_env=alpha`

CLI 等价（基于最近抓包 response，改完再提交可先 `--response-file`）：

```bash
python3 Tunnel/tunnel_mock_execute.py case-create \
  --momoid 100414599 \
  --keyword getCpLoveChestHomepage \
  --response-file /path/to/edited-response.json \
  --enable \
  --g-appid All --g-env alpha \
  --since 3600
```

## 执行步骤（字段 Mock，轻量替代）

1. 查 userId（若只有手机号）：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/templates/用户-按手机号查userId.json \
  --query-user-by-phone <phone>
```

2. 用户在 App 打开目标页（产生抓包）。

3. 设置字段 Mock：

```bash
python3 Tunnel/tunnel_mock_execute.py field \
  --momoid <userId> \
  --keyword getCpLoveChestHomepage \
  --key data.countdownSec \
  --value 581580 \
  --since 3600
```

4. App **重进页面**（或杀进程重开）触发新请求。

5. 验收：Tunnel 查该请求 `response.data.countdownSec` 是否为 mock 值。

## 常用命令

```bash
# 列出字段 mock
python3 Tunnel/tunnel_mock_execute.py param-list \
  --momoid <userId> --keyword <keyword> --since 3600

# 列出整包 mock
python3 Tunnel/tunnel_mock_execute.py list \
  --momoid <userId> --keyword <keyword> --since 3600

# 整包 mock（用最近抓包 response，并启用）
python3 Tunnel/tunnel_mock_execute.py case-create \
  --momoid <userId> --keyword <keyword> --since 3600 --enable

# 停用整包 mock
python3 Tunnel/tunnel_mock_execute.py case-stop \
  --momoid <userId> --uri <fullUrlOrPath>

# 删除字段 mock
python3 Tunnel/tunnel_mock_execute.py param-delete \
  --momoid <userId> --uri <fullUrlOrPath> --key data.countdownSec
```

`--uri` 与 `--keyword` 二选一；`--keyword` 会从最近抓包取完整 URL。

## CP 爱意宝箱倒计时

| 项 | 值 |
|----|-----|
| 接口 | `/yaahlan/trick/cpLoveChest/getCpLoveChestHomepage` |
| Mock 字段 | **`data.countdownSec`**（秒） |
| 展示 | `dd:hh:mm:ss`（15 天周期剩余） |
| 勿改 | 外层 `timestamp` / `millisecond`（服务端时间，非倒计时） |

换算：`countdownSec = 天×86400 + 时×3600 + 分×60 + 秒`

示例：

| 目标展示 | countdownSec |
|----------|--------------|
| 6天17时33分 | 581580 |
| 1 分钟 | 60 |
| 周期结束 | 0 |

## 整包 Mock 注意

- 与你在 Tunnel 网页操作完全同源：`POST /api/mock_cases` + query `g_appid` / `g_env`
- `case-create` 可 `--response-file` 指定 JSON，或自动用最近抓包的 `response`
- 创建后 `--enable`（即 `enable: 1`）；已有规则用 `case-start` / `case-stop`
- 只改倒计时时，整包 mock 与 `param-set --key data.countdownSec` 均可；**只改一个字段优先 param_mock**

## 与 tunnel-read 配合

```bash
# mock 前/后对比
python3 Tunnel/tunnel_execute.py \
  --momoid <userId> --keyword <keyword> --since 600 --output json
```

## 相关

- 技能 `tunnel-read`（只读抓包）
- [Tunnel/README.md](../../../Tunnel/README.md)
- [Tunnel/使用方法.md](../../../Tunnel/使用方法.md)
