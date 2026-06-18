# Tunnel 抓包平台本地调用

通过 [tunnel.wemomo.com](https://tunnel.wemomo.com) 查询测试 App 的 HTTP 抓包记录，用于验证接口是否发出、核对 request/response、排查送礼/登录等业务问题。

> 能力口令与可复制命令见 **[使用方法.md](使用方法.md)**（由 `Tunnel/config/registry.json` 自动生成）。

## 是什么

Tunnel 是内部抓包平台：真机或模拟器走测试/线上环境时，会把该 **userId（momoid）** 的网关请求记录下来。Web 端可浏览单条详情；本项目通过 **`GET /api/requests`** 在终端批量查询。

> **线上环境**：见 [`online/`](../online/README.md) 模块；口令与命令见 [online/使用方法.md](../online/使用方法.md)（`python3 online/online_execute.py tunnel ...`）。

与 bug-kb 里常见的 `https://tunnel.wemomo.com/request/...` 链接同源——那些是浏览器打开的**单条详情页**；CLI 拉列表后，每条记录的 `request` / `response` 字段已包含解析后的 JSON。

## 目录结构

```
Tunnel/
├── README.md                 # 本文件
├── tunnel_execute.py         # CLI 入口
├── .env.example / .env.local # 可选；Cookie 可复用 MOA
├── config/
│   └── registry.json         # 能力登记
├── 使用方法.md                # 能力清单（自动生成）
├── scripts/
│   └── generate_index.py
└── tunnel/                   # Python 实现
    ├── cli.py
    ├── client.py
    ├── env.py
    └── summary.py
```

## 环境配置

**方式 A（推荐）**：已配置 `MOA/.env.local` 时，**无需再建** `Tunnel/.env.local`。MOA Cookie 中含 `tunnel_login_session`，会自动复用。

**方式 B**：单独配置 Tunnel

```bash
cp Tunnel/.env.example Tunnel/.env.local
# 浏览器打开 https://tunnel.wemomo.com 并登录
# F12 → 网络 → 任选 /api/requests → 复制完整 Cookie 到 TUNNEL_COOKIE
```

| 变量 | 说明 |
|------|------|
| `TUNNEL_BASE_URL` | 默认 `https://tunnel.wemomo.com` |
| `TUNNEL_COOKIE` | 含 `tunnel_login_session` 的完整 Cookie |
| `TUNNEL_G_APPID` | 默认 `All`；可 `yaahlan`、`sc_dev_all` |
| `TUNNEL_G_ENV` | 默认 `alpha`；可 `overseas` |
| `TUNNEL_REFERER` | 默认 `https://tunnel.wemomo.com/` |

> Cookie 会过期；失效时从 tunnel 页面或 MSE 重新抓包更新。**勿将 Cookie 提交到 Git。**

## API 说明

### 列表查询

```
GET /api/requests
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `momoid` | 用户 userId | `100486375` |
| `start_time` | 起始 Unix 时间戳（秒） | `1780626889` |
| `mode` | 固定 `tunnel` | `tunnel` |
| `keyword` | URL 关键字，可空 | `gift`、`sendGift` |
| `g_appid` | 应用 | `All`、`yaahlan` |
| `g_env` | 环境 | `alpha`、`overseas` |

响应结构：

```json
{
  "ec": 200,
  "em": "success",
  "data": {
    "first_time": "...",
    "last_time": "...",
    "list": {
      "<_id>": {
        "_id", "time", "method", "url", "status", "time_cost",
        "momoid", "appId", "env", "request", "response", ...
      }
    }
  }
}
```

### 单条详情（浏览器）

```
https://tunnel.wemomo.com/request/<_id>?req_time=<unix>&g_appid=All&g_env=alpha
```

CLI 无需再调详情接口——列表项内已有 `request` / `response`；用 `--request-id` 展开即可。

## 快速开始

```bash
# 查家族长 100486375 最近 1 小时请求
python3 Tunnel/tunnel_execute.py --momoid 100486375 --since 3600

# 按关键字过滤送礼相关
python3 Tunnel/tunnel_execute.py --momoid 100486375 --keyword gift --since 7200

# 指定起始时间戳（与浏览器抓包一致）
python3 Tunnel/tunnel_execute.py --momoid 100486375 --start-time 1780626889

# 完整 JSON
python3 Tunnel/tunnel_execute.py --momoid 100486375 --since 3600 --output json

# 单条详情（_id 来自列表）
python3 Tunnel/tunnel_execute.py --momoid 100486375 --request-id t5OnlZ4B_1006Fv6E696 --since 7200
```

## 典型场景

| 场景 | 命令要点 |
|------|----------|
| 验证是否调了送礼接口 | `--keyword sendGift` 或 `--keyword gift` |
| 查登录/心跳 | `--keyword login` / `--keyword heartbeat` |
| 对照公屏与接口 | 先 adb 操作，再 `--since 600` 拉最近 10 分钟 |
| 写 bug 附 tunnel 链接 | 从列表取 `_id` + `time` 拼 `/request/<id>?req_time=...` |

## 维护

| 操作 | 命令 |
|------|------|
| 刷新能力清单 | `python3 Tunnel/scripts/generate_index.py` |

## 与其他模块的关系

| 能力 | 模块 | 说明 |
|------|------|------|
| userId → 昵称/手机 | `Admin/` | 查账号归属 |
| 手机号 → userId | `MOA/` | `queryLoginStatusV2` |
| 真机 UI 操作 | `adb/` | 截屏点击 |
| 接口是否发出/返回 | `Tunnel/` | 本模块 |
| **操作 + 截图 + 抓包** | `adb run` | `python3 adb/adb_execute.py run --macro ... --tunnel-account familyLeader --tunnel-keyword gift` |

一体化流程见 [adb/README.md](../adb/README.md#adb--tunnel-抓包校验推荐) 与 Skill `.cursor/skills/adb-tunnel-verify/SKILL.md`。
