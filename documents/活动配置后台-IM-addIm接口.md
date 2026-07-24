# 活动配置后台 · IM 任务新建/保存（addIm）

> 来源：测试环境浏览器抓包（2026-07-23）  
> 业务：运营后台 → 活动配置 → IM 消息配置 → 新建/保存定时 IM 下发任务  
> 关联用例：`templates/2026之前活动相关/活动配置后台-IM配置.md`、`prd-kb/榜单.md`（活动配置后台-IM配置）

## 基本信息

| 项 | 值 |
|----|-----|
| **方法** | `POST` |
| **Path** | `/yaahlan/cms/activity/addIm` |
| **完整 URL（Stage）** | `https://melon-gateway-alpha-stage.immomo.com/yaahlan/cms/activity/addIm` |
| **Content-Type** | `application/json` |
| **鉴权** | Header：`sso-token`、`yaahlan-jwt`；可选 `yaahlan-lang`（默认 `zh`） |
| **Origin / Referer** | `https://test-s.immomo.com` |
| **分区** | Body 字段 `area`（示例：`MENA` 中东区） |

## 请求头（必需）

```http
POST /yaahlan/cms/activity/addIm HTTP/1.1
Content-Type: application/json
sso-token: <从 test-s.immomo.com 后台抓包>
yaahlan-jwt: <从 test-s.immomo.com 后台抓包>
yaahlan-lang: zh
Origin: https://test-s.immomo.com
Referer: https://test-s.immomo.com/
```

> Token 会过期，写入 `Admin/.env.local` 的 `ADMIN_SSO_TOKEN` / `ADMIN_YAAHLAN_JWT`（Gateway 类接口同时需 `ADMIN_GATEWAY_BASE_URL`）。

## 请求体字段

| 字段 | 类型 | 示例 | 说明 |
|------|------|------|------|
| `id` | string | `""` | 新建为空；编辑时填已有任务 ID |
| `name` | string | `"123"` | 任务名称 |
| `msgContent` | object | `{"en":"英文","ar":""}` | IM 文案，多语言：`en` 英语、`ar` 阿语（土/俄等分区可能还有对应 key，待补） |
| `image` | object | `{"en":"https://...jpg","ar":""}` | IM 配图 URL，按语言区分；无图时对应语言可为空字符串 |
| `userFilterType` | number | `0` | 用户筛选类型（枚举待补） |
| **`type`** | number | **`2`** | **下发类型**：`2`=定时任务下发 |
| `userType` | number | `2` | **下发用户**：`1`=近7天活跃；`2`=近30天活跃；`3`=白名单 |
| `whiteList` | string | `""` | 白名单 userId，英文逗号分隔；非白名单模式可为空 |
| `filePath` | string | `""` | 批量用户文件路径（白名单 Excel 等场景，可为空） |
| `fileName` | string | `""` | 上传文件名（可为空） |
| `userCount` | string | `""` | 发送用户数（新建时可为空，列表展示用） |
| `gotoUrl` | string | `""` | 点击 IM 跳转 URL；空表示纯消息无跳转 |
| `sendTime` | number | `1784791200000` | 定时下发时间，**毫秒时间戳** |
| **`sendType`** | number | `0`–`5` | **消息类型**（见下表） |

### 消息类型 `sendType` 枚举

| sendType | 后台文案 |
|----------|----------|
| 0 | 活动通知下发 |
| 1 | 活动奖励下发 |
| 2 | 游戏官方消息 |
| 3 | 主播官方消息 |
| 4 | Yaahlan助手消息 |
| 5 | 客服消息 |

> **勿混字段**：`type`=下发类型（定时固定 **2**）；`sendType`=消息类型（**0~5**）。

### 批量测试六种类型（Admin）

```bash
# 从 1 分钟后起，每分钟创建一种消息类型的「定时任务 + 近30天活跃」任务
python3 Admin/admin_execute.py --schedule-im-message-types --im-area MENA

# 仅预览 payload，不提交
python3 Admin/admin_execute.py --schedule-im-message-types --im-dry-run
```

### 示例 Body（抓包样例）

```json
{
  "id": "",
  "name": "123",
  "msgContent": {
    "en": "英文",
    "ar": ""
  },
  "userFilterType": 0,
  "type": 2,
  "userType": 1,
  "whiteList": "",
  "filePath": "",
  "fileName": "",
  "userCount": "",
  "image": {
    "ar": "",
    "en": "https://yaahlan.momocdn.com/picture/F9/07/F907504B-BB35-4D5A-BA47-7931D27F475C20260723_L.jpg"
  },
  "gotoUrl": "",
  "sendTime": 1784791200000,
  "sendType": 2,
  "bgColor": "",
  "area": "MENA"
}
```

## 响应

| 项 | 值 |
|----|-----|
| **HTTP 状态** | `200 OK` |
| **Content-Type** | `application/json` |
| **Body 长度** | 约 106 字节（样例） |

响应体 JSON 结构待补（通常为 `ec` / `em` / `data`，`data` 含新建任务 `id`）。保存成功后列表应出现新任务，状态为「等待中」，到 `sendTime` 后变为「已下发」。

## 测试验收要点

1. **抓包**：保存任务时必调 `POST .../addIm`，Body 与表单一致（文案、图片、分区、下发时间）。
2. **新建 vs 编辑**：`id` 为空为新建；编辑未发送任务应带原 `id`（编辑接口可能是同一 path 或 `updateIm`，待补）。
3. **定时下发**：`type=2` + 配置 `sendTime`；到点后客户端收到 IM，发送方/文案/图片与配置一致。
4. **分区隔离**：`area=MENA` 仅影响中东区任务，与其他区列表隔离（见 `testcase-kb/消息.md` · 运营PUSH-IM配置后台）。
5. **白名单**：`userType` 为白名单时 `whiteList` 必填；非白名单用户不应收到。
6. **活动关联**：「活动下发」类型任务 ID 需复制到活动配置「IM消息ID」/「活动宣发IM消息ID」（见 PRD，不一定走同一 `sendTime` 逻辑）。

## 相关接口

| 能力 | Path | 文档 |
|------|------|------|
| IM 任务列表 | `getImList` | `documents/活动配置后台-IM-getImList接口.md` |
| 删除 IM 任务 | `deleteIm` | `documents/活动配置后台-IM-deleteIm接口.md` |
| 新建/保存 IM 任务 | `addIm` | 本文档 |
| 编辑 IM 任务 | `updateIm` / 同 `addIm` 带 id | 待补 |
| 复制 | 待抓包 | 待补 |

## curl 模板（需替换 Token）

```bash
curl -sS -X POST \
  'https://melon-gateway-alpha-stage.immomo.com/yaahlan/cms/activity/addIm' \
  -H 'Content-Type: application/json' \
  -H 'sso-token: <ADMIN_SSO_TOKEN>' \
  -H 'yaahlan-jwt: <ADMIN_YAAHLAN_JWT>' \
  -H 'yaahlan-lang: zh' \
  -H 'Origin: https://test-s.immomo.com' \
  -H 'Referer: https://test-s.immomo.com/' \
  -d @Admin/templates/cms-activity-addIm.payload.example.json
```
