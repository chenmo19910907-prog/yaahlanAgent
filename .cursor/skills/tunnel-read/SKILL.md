---
name: tunnel-read
description: 使用 Tunnel 抓包平台查询用户 HTTP 请求列表与 request/response。在用户要验证接口是否调用、查送礼/登录抓包、tunnel 链接、或 adb 操作后核对接口时使用。
---

# Tunnel 抓包查询

## 何时使用

- 验证真机操作是否触发预期接口（送礼、进房、登录等）
- 按 URL 关键字过滤请求
- 展开单条 request/response JSON
- 为 bug 报告生成 `tunnel.wemomo.com/request/...` 链接

## 前置条件

- 已配置 `MOA/.env.local`（含 `tunnel_login_session`），或 `Tunnel/.env.local` 的 `TUNNEL_COOKIE`
- **线上环境**：须 `online/.env.local`，命令用 `online/online_execute.py tunnel ...`；用户提示词须含「线上环境」
- 知道目标 **userId（momoid）**

## 执行步骤

1. **列表查询**（默认最近 1 小时）：

```bash
python3 Tunnel/tunnel_execute.py --momoid <userId> --since 3600
```

2. **关键字过滤**（送礼、登录等）：

```bash
python3 Tunnel/tunnel_execute.py --momoid <userId> --keyword gift --since 7200
```

**线上环境**（须提示词含「线上环境」）：

```bash
python3 online/online_execute.py tunnel --momoid <userId> --since 3600
python3 online/online_execute.py tunnel --momoid <userId> --keyword gift --since 7200
```

3. **完整 JSON**（需解析 response.ec / data）：

```bash
python3 Tunnel/tunnel_execute.py --momoid <userId> --since 3600 --output json
```

4. **单条详情**（`_id` 来自列表）：

```bash
python3 Tunnel/tunnel_execute.py --momoid <userId> --request-id <_id> --since 7200
```

## 参数速查

| CLI 参数 | API 参数 | 默认 |
|----------|----------|------|
| `--momoid` | `momoid` | 必填 |
| `--start-time` | `start_time` | 与 `--since` 二选一 |
| `--since` | （换算为 start_time） | `3600` |
| `--keyword` | `keyword` | 空 |
| `--g-appid` | `g_appid` | `All` |
| `--g-env` | `g_env` | `alpha`（线上用 `online/online_execute.py tunnel` → overseas） |

## 输出解读

- `ec=200` 表示查询成功
- `data.list` 为 dict，key 为 `_id`
- 每条含 `url`、`method`、`status`、`time`、`request`、`response`
- 摘要模式只展示表格；分析接口体用 `--output json` 或 `--request-id`

## 浏览器单条链接格式

```
https://tunnel.wemomo.com/request/<_id>?req_time=<unix_seconds>&g_appid=All&g_env=alpha
```

## 更多说明

- [Tunnel/README.md](../../../Tunnel/README.md)
- [Tunnel/使用方法.md](../../../Tunnel/使用方法.md)
- Mock 字段/整包响应：技能 **`tunnel-mock`**，`python3 Tunnel/tunnel_mock_execute.py`
