# Stage 送礼 Reference

## 固定常量

| 项 | 值 |
|----|-----|
| appId | `2005` |
| CMDB appkey | `momo.ibt.yaahlan.service.yaahlan-web` |
| CMDB corp/env | `alpha` / `stage` |
| CMDB Token | 环境变量 `CMDB_TOKEN`，fallback `61430279892c78e0587d58b338288ac06e7641fb`（`Gift/.env.local` 可覆盖） |
| 默认 package-id | `12321312` |
| MOA lookup | `moa_lookup_alpha.momo.com:10010` |
| 礼物 MOA | `/service/mdp-gift/gift-query-service` |
| 用户 MOA | `/service/voga-mts-user-profile-stage` |
| HTTP 路径 | `http://{instance_ip}:8080/v2/gift/send` |

## Probe 记录（真实响应结构）

### CMDB

请求返回 **JSON 数组**，取 `[0].instance_ip`：

```json
[
  {
    "instance_id": "yaahlan-web-alpha-stage-54c7b654f-jdlhv",
    "instance_ip": "10.247.254.135",
    "env_labels": {"corp": "alpha", "env": "stage"}
  }
]
```

### MOA 礼物 `batchQueryCategoryPropAndGifts`

外层 Redis 响应 `{ec:0, result:{...}}`，`result` 为业务体：

```json
{
  "ec": 200,
  "em": "success",
  "data": [{
    "productId": 2005004730,
    "giftType": 0,
    "giftSubType": 0,
    "category": 2005000189,
    "productName": "Golden Lion King(复制)"
  }]
}
```

取 `result.data[0]`。无数据时 fallback `batchQueryCategoryProps`，同样 `result.data[0]`。

### MOA 用户 `getUserVersionInfo`

外层 `{ec:0, result:{...}}`，`result` **直接** 为 UserVersion（无 ec/data 包装）：

```json
{
  "userId": "8250",
  "lang": "en",
  "appVersion": "2.4.8_dev",
  "osType": "android",
  "ip": "172.18.125.76",
  "deviceId": "29eda15eeb2a8525",
  "ua": "Yaahlan2.4.8_dev Android/368 (...)"
}
```

缺字段时 fallback `getUserInfoByFields`，args：`["<userId>", [], "en"]`。

## giftType / isPackage 映射

依据 `ProductTypeEnum.getByGiftTypeAndSubType(giftDTO.giftType, giftDTO.giftSubType)`：

| giftDTO (type, subType) | 请求 giftType | 请求 isPackage |
|-------------------------|---------------|----------------|
| (2, 0) PROP_DEFAULT | 2 | 0 |
| (1, 0) PACK_DEFAULT | 0 | 1 |
| 其他 | 0 | 0 |

## 场景 ext 模板

所有场景 `fromCursor: 1`。

### chatroom

```json
{
  "timeZone": "Asia/Shanghai",
  "source": "chatroom",
  "localTime": "<毫秒时间戳>",
  "room_id": "<roomId>",
  "receiverIds": "uid1,uid2",
  "giftNum": 1,
  "fromCursor": 1
}
```

`sceneId` = roomId。

### group

```json
{
  "timeZone": "Asia/Shanghai",
  "source": "group",
  "localTime": "<毫秒时间戳>",
  "receiverIds": "uid1,uid2",
  "giftNum": 1,
  "fromCursor": 1
}
```

`sceneId` = groupId。

### private (im)

```json
{
  "timeZone": "Asia/Shanghai",
  "source": "im",
  "localTime": "<毫秒时间戳>",
  "receiverIds": "uid1",
  "giftNum": 1,
  "fromCursor": 1
}
```

不传 `sceneId`。

## 全房间送礼

`--send-room-all` 仅 chatroom：

1. POST `/v2/gift/getSendRoomAllSnap`（body: sceneId, giftId, num）
2. 取 `data.snapId` 写入 `sendRoomAllSnapId`
3. POST `/v2/gift/send`（无需 receivers / remoteIdList）

## CLI 完整示例

```bash
# 探测（不 POST）
python3 Gift/gift_execute.py \
  --probe --scene chatroom --sender 8250 --receivers 100465989 \
  --gift-id 2005004730 --scene-id 38826842

# 只看 payload
python3 Gift/gift_execute.py \
  --dry-run --scene private --sender 8250 --receivers 100465989 \
  --gift-id 2005004730

# 直接送礼
python3 Gift/gift_execute.py \
  --scene group --sender 8250 --receivers 100465989 \
  --gift-id 2005004730 --scene-id 55519679 --num 1

# 全房送礼
python3 Gift/gift_execute.py \
  --scene chatroom --sender 8250 --gift-id 2005004730 \
  --scene-id 38826842 --send-room-all
```

## HTTP 响应

成功时 `response.ec == 0`，`data` 含余额等信息。失败时读 `response.em`。

## MOA Redis 协议（脚本内置）

与 `yaahlan-mcp` 的 `queryMoaService_Stage` 同源：

1. **Lookup**：对 `moa_lookup_alpha.momo.com:10010` 执行 Redis GET，key 为  
   `{"action":"/service/lookup","params":{"m":"getService","args":["<serviceUri>","redis"]}}`
2. 从 `result.hosts[0]` 解析 `10.x.x.x:port`
3. **调用**：对 provider Redis GET，key 为  
   `{"action":"<serviceUri>","params":{"m":"<method>","args":[...]}}`

## 不支持

- 生产 / 线上环境（仅用 Stage alpha/stage）
