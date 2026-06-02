# Yaahlan Admin 本地调用

调用 Yaahlan 测试后台 HTTP 接口，用于按 userId 查询用户全量详情。

## 环境配置

```bash
cp Admin/.env.example Admin/.env.local
# 编辑 Admin/.env.local，填入浏览器抓包中的 sso-token 与 yaahlan-jwt
```

| 变量 | 说明 |
|------|------|
| `ADMIN_BASE_URL` | 默认 `https://yaahlan-admin-alpha.wemomo.com` |
| `ADMIN_SSO_TOKEN` | 请求头 `sso-token` |
| `ADMIN_YAAHLAN_JWT` | 请求头 `yaahlan-jwt` |
| `ADMIN_LANG` | 默认 `zh` |
| `ADMIN_ORIGIN` / `ADMIN_REFERER` | 默认 `https://test-s.immomo.com` |
| `ADMIN_GATEWAY_BASE_URL` | 定制礼物列表 Gateway，默认 `https://melon-gateway-alpha-stage.immomo.com` |

> Token 会过期，失效时从后台页面重新抓包更新 `.env.local`。

## 查询用户详情

接口：`POST /admin/user/queryUserDetail`

```bash
python3 Admin/admin_execute.py --query-user-id 100465989
```

返回摘要包含：基础资料、等级、钻石/币商余额、房间、公会、登录/注册设备（mmuid/mmuidv3）、业务状态等。

完整 JSON：

```bash
python3 Admin/admin_execute.py --query-user-id 100465989 --output json
```

使用 payload 文件：

```bash
python3 Admin/admin_execute.py \
  --payload-file Admin/query_user_detail_payload.example.json
```

## 查询定制礼物列表（userId ↔ giftId）

接口：`GET /yaahlan/backend/vip5UserConfig/getListConfig`（melon-gateway）

```bash
python3 Admin/admin_execute.py --query-custom-gift-list
```

按 userId 查对应 giftId：

```bash
python3 Admin/admin_execute.py --query-custom-gift-list --custom-gift-user-id 100006869
```

完整 JSON：

```bash
python3 Admin/admin_execute.py --query-custom-gift-list --output json
```

## 与 MOA 手机号查询的关系

| 能力 | 模块 | 输入 | 输出 |
|------|------|------|------|
| 手机号 → userId | `MOA/` `queryLoginStatusV2` | 手机号 | userId / 是否注册 |
| userId → 全量资料 | `Admin/` `queryUserDetail` | userId | 昵称、手机、等级、资产、设备等 |
