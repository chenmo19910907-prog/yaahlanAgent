# 活动配置后台 · IM 任务删除（deleteIm）

> 来源：测试环境浏览器抓包（2026-07-23）  
> 业务：运营后台 → 活动配置 → IM 消息配置 → 删除任务  
> 关联：`documents/活动配置后台-IM-getImList接口.md`

## 基本信息

| 项 | 值 |
|----|-----|
| **方法** | `POST` |
| **Path** | `/yaahlan/cms/activity/deleteIm` |
| **完整 URL（Stage）** | `https://melon-gateway-alpha-stage.immomo.com/yaahlan/cms/activity/deleteIm` |
| **Content-Type** | `application/json` |
| **鉴权** | Header：`sso-token`、`yaahlan-jwt` |

## 请求体

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `id` | number | `213` | 任务 ID |
| `area` | string | `"MENA"` | 运营分区 |

### 示例 Body

```json
{
  "id": 213,
  "area": "MENA"
}
```

## 响应

| 项 | 值 |
|----|-----|
| **HTTP 状态** | `200 OK` |
| **结构** | `{ "ec": 200, "em": "success", "data": true }`（样例） |

## Admin 命令

```bash
# 删除单条
python3 Admin/admin_execute.py --delete-im-task --im-task-id 213 --im-area MENA

# 批量删除 id > 200 的任务（先预览）
python3 Admin/admin_execute.py --delete-im-tasks-above-id 200 --im-area MENA --im-dry-run

# 批量删除 id > 200 的任务
python3 Admin/admin_execute.py --delete-im-tasks-above-id 200 --im-area MENA
```

## curl 模板

```bash
curl -sS -X POST \
  'https://melon-gateway-alpha-stage.immomo.com/yaahlan/cms/activity/deleteIm' \
  -H 'Content-Type: application/json' \
  -H 'sso-token: <ADMIN_SSO_TOKEN>' \
  -H 'yaahlan-jwt: <ADMIN_YAAHLAN_JWT>' \
  -H 'yaahlan-lang: zh' \
  -H 'Origin: https://test-s.immomo.com' \
  -H 'Referer: https://test-s.immomo.com/' \
  -d '{"id":213,"area":"MENA"}'
```
