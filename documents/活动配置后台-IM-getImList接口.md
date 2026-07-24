# 活动配置后台 · IM 任务列表（getImList）

> 来源：测试环境浏览器抓包（2026-07-23）  
> 业务：运营后台 → 活动配置 → IM 消息配置 → 任务列表  
> 关联：`documents/活动配置后台-IM-addIm接口.md`

## 基本信息

| 项 | 值 |
|----|-----|
| **方法** | `POST` |
| **Path** | `/yaahlan/cms/activity/getImList` |
| **完整 URL（Stage）** | `https://melon-gateway-alpha-stage.immomo.com/yaahlan/cms/activity/getImList` |
| **Content-Type** | `application/json` |
| **鉴权** | Header：`sso-token`、`yaahlan-jwt`；可选 `yaahlan-lang`（默认 `zh`） |
| **Origin / Referer** | `https://test-s.immomo.com` |

## 请求头（必需）

```http
POST /yaahlan/cms/activity/getImList HTTP/1.1
Content-Type: application/json
sso-token: <从 test-s.immomo.com 后台抓包>
yaahlan-jwt: <从 test-s.immomo.com 后台抓包>
yaahlan-lang: zh
Origin: https://test-s.immomo.com
Referer: https://test-s.immomo.com/
```

## 请求体

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `area` | string | `"MENA"` | 运营分区（中东 / 土区 / 俄区 / 南洋 / 南亚等） |

### 示例 Body

```json
{
  "area": "MENA"
}
```

## 响应

| 项 | 值 |
|----|-----|
| **HTTP 状态** | `200 OK` |
| **Content-Type** | `application/json` |
| **结构** | `{ "ec": 200, "em": "success", "data": [ ... ] }` |

### `data[]` 主要字段

| 字段 | 说明 |
|------|------|
| `id` | 任务 ID |
| `name` | 任务名称 |
| **`type`** | **下发类型**（`2`=定时任务下发） |
| **`sendType`** | **消息类型**（`0`~`5`） |
| `userType` | 下发用户（`1`=近7天活跃；`2`=近30天活跃；`3`=白名单） |
| `sendStatus` | 状态（`0`=等待中；`1`=已下发） |
| `sendTime` | 定时下发时间，毫秒时间戳 |
| `sendNum` | 发送用户数 |
| `msgContent` | 多语言文案 `{en, ar, ...}` |
| `image` | 多语言配图 |
| `gotoUrl` | 跳转 URL |
| `bgColor` | 背景色 |
| `whiteList` | 白名单 UID |
| `area` | 分区 |
| `senderCsId` | 客服 ID（部分消息类型） |

### 示例条目

```json
{
  "id": 262,
  "name": "im-type-smoke-0723-1537-t1-活动通知下发",
  "type": 2,
  "sendType": 1,
  "userType": 2,
  "sendStatus": 0,
  "sendTime": 1784795935000,
  "sendNum": 0,
  "area": "MENA",
  "msgContent": {
    "en": "[IM smoke] Activity notification / 30-day active / MENA",
    "ar": "[اختبار IM] إشعار النشاط / نشط 30 يوم / MENA"
  }
}
```

## Admin 命令

```bash
# 查询中东区全部 IM 任务（摘要，按 id 倒序）
python3 Admin/admin_execute.py --query-im-list --im-area MENA

# 按名称模糊筛选 smoke 任务
python3 Admin/admin_execute.py --query-im-list --im-area MENA --im-name-contains im-type-smoke

# 按任务 ID 精确查
python3 Admin/admin_execute.py --query-im-list --im-area MENA --im-task-id 262
```

## curl 模板

```bash
curl -sS -X POST \
  'https://melon-gateway-alpha-stage.immomo.com/yaahlan/cms/activity/getImList' \
  -H 'Content-Type: application/json' \
  -H 'sso-token: <ADMIN_SSO_TOKEN>' \
  -H 'yaahlan-jwt: <ADMIN_YAAHLAN_JWT>' \
  -H 'yaahlan-lang: zh' \
  -H 'Origin: https://test-s.immomo.com' \
  -H 'Referer: https://test-s.immomo.com/' \
  -d '{"area":"MENA"}'
```
