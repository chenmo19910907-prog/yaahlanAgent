# Yaahlan Admin 本地调用

调用 Yaahlan 测试后台 HTTP 接口。

> 能力口令与可复制命令见 **[使用方法.md](使用方法.md)**（由 `Admin/config/registry.json` 自动生成）。

> **线上环境**：见 [`online/`](../online/README.md) 模块；口令与命令见 [online/使用方法.md](../online/使用方法.md)（`python3 online/online_execute.py admin ...`）。

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

## 重置定制礼物上传时间

接口：`POST /mts/components/resetExpireTime`（yaahlan-admin）

```bash
python3 Admin/admin_execute.py \
  --reset-custom-gift-upload \
  --custom-gift-reset-user-id 100465989
```

## 重置定制座驾上传冷却

接口：`POST /backend/custom/resetCoolDown`（yaahlan-admin）

```bash
python3 Admin/admin_execute.py \
  --reset-custom-vehicle-cooldown \
  --custom-vehicle-remote-id 100465989
```

## 重置定制头像框上传冷却

接口：`POST /backend/custom/resetCoolDownProp`（yaahlan-admin）

```bash
python3 Admin/admin_execute.py \
  --reset-custom-prop-cooldown \
  --custom-prop-remote-id 100465989 \
  --custom-prop-type HEADER_FRAME
```

## 定制装扮开通流程

| 需求 | 所需 VIP | 步骤 |
|------|---------|------|
| 定制头像框 | VIP6 | ① MOA 升到 VIP6 → ② Admin 重置 HEADER_FRAME 冷却 |
| 定制座驾 | VIP8 | ① MOA 升到 VIP8 → ② Admin 重置座驾冷却 |

示例（用户 `100465989` 需要定制头像框）：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/templates/VIP-增加经验值.json \
  --vip-user-id 100465989 \
  --vip-level 6

python3 Admin/admin_execute.py \
  --reset-custom-prop-cooldown \
  --custom-prop-remote-id 100465989 \
  --custom-prop-type HEADER_FRAME
```

完整口令见 [使用方法.md](使用方法.md) 中「定制装扮工作流」章节。

## 增加家族成员

接口：`POST /yaahlan/backend/family/addFamilyMember`（melon-gateway）

```bash
python3 Admin/admin_execute.py \
  --add-family-member \
  --family-id 42230 \
  --family-user-id 100461563
```

## 查询家族信息

接口：`POST /yaahlan/backend/family/queryFamilyByIdAndName`（melon-gateway）

按家族 ID：

```bash
python3 Admin/admin_execute.py --query-family --family-id 42230
```

按家族名称：

```bash
python3 Admin/admin_execute.py --query-family --family-name 家人们t1
```

返回字段含：家族头像、名称、等级、ID、家族长 ID、成立日期、当前人数、活跃人数、加入总数、退出总数。

## 用户加入公会

接口：`POST /yaahlan/cms/anchor/addAnchor/addAnchor`（melon-gateway）

按公会 ID：

```bash
python3 Admin/admin_execute.py \
  --add-guild-member \
  --trade-id 4295972845 \
  --guild-user-id 100461563
```

按公会名称：

```bash
python3 Admin/admin_execute.py \
  --add-guild-member \
  --trade-union <公会名> \
  --guild-user-id 100461563
```

## 用户移除公会

接口：`POST /yaahlan/cms/anchor-opt/batchDeleteAnchor`（melon-gateway）

```bash
python3 Admin/admin_execute.py \
  --remove-guild-member \
  --guild-user-id 100461563
```

多个用户（逗号分隔）：

```bash
python3 Admin/admin_execute.py \
  --remove-guild-member \
  --guild-user-id 100461563,100465989
```

## 用户转移公会

接口：`POST /yaahlan/cms/anchor-opt/batchAnchorChangeTradeUnion`（melon-gateway）

```bash
python3 Admin/admin_execute.py \
  --change-guild-member \
  --trade-union cm3 \
  --guild-user-id 100461563
```

## 查询公会信息

接口：`POST /yaahlan/cms/anchor/tradeUnionList/tradeUnionPageList`（melon-gateway）

按公会长 userId：

```bash
python3 Admin/admin_execute.py --query-guild --guild-leader-id 100465989
```

按公会 ID 或名称：

```bash
python3 Admin/admin_execute.py --query-guild --trade-id 1007302526
python3 Admin/admin_execute.py --query-guild --trade-union cm3
```

## 维护

| 操作 | 命令 |
|------|------|
| 刷新能力清单 | `python3 Admin/scripts/generate_index.py` |

## 与 MOA 手机号查询的关系

| 能力 | 模块 | 输入 | 输出 |
|------|------|------|------|
| 手机号 → userId | `MOA/` `queryLoginStatusV2` | 手机号 | userId / 是否注册 |
| 用户列表（筛选/分页） | `Admin/` `queryUserProfileList` | userId/昵称/手机/mmuidv3 等 | userId、昵称、大区、注册时间等 |
| 用户列表 → 批量互关结好友 | `Admin/scripts/batch_mutual_friends_from_user_list.py` | 目标 userId + 数量 | 互关成功/失败明细 |
| userId → 全量资料 | `Admin/` `queryUserDetail` | userId | 昵称、手机、等级、资产、设备等 |
