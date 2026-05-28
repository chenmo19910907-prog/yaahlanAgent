## 已录入 MOA 清单（自动生成）

> 本文件由 `MOA/generate_moa_index.py` 根据 `MOA/moa_registry.json` 自动生成，请勿手动编辑。

### 目录

- [1) VIP 经验值（voga-mts-user-vip-stage）](#moa-cat-1)
  - [VIP等级-升级到目标等级](#vip_level_upgrade)
  - [VIP等级-清除VIP信息](#vip_delete_info)
  - [VIP经验值-增加](#vip_exp_add)
  - [VIP经验值-查询当前等级经验](#vip_query_current)
- [2) 实名认证（internal/user/id-auth-api）](#moa-cat-2)
  - [实名认证-查询认证记录](#id_auth_query_real_person_record)
  - [实名认证-清除认证信息](#id_auth_delete_person)
  - [实名认证-解决认证失败（清 reason 关联账号）](#id_auth_fix_failure_by_reason)
  - [实名认证-设置认证过期时间](#id_auth_reset_relation_expire_time)
- [3) 房间经验值（voga-mts-room-backdoor）](#moa-cat-3)
  - [房间等级-升级到目标等级](#room_level_upgrade)
  - [房间经验值-增加](#room_exp_add)
  - [房间经验值-查询当前等级经验](#room_query_current)
- [4) 背包礼物（voga-base-service-middle-gift-stage）](#moa-cat-4)
  - [背包礼物-下发](#package_gift_add)
- [5) 钻石（voga-base-service-middle-pay-stage）](#moa-cat-5)
  - [钻石-发放](#diamond_provide)

### 使用说明

- **提示词**：你对我说的自然语言口令
- **命令**：对应可执行脚本命令（默认已配置 `MOA/.env.local`）

<a id="moa-cat-1"></a>

## 1) VIP 经验值（voga-mts-user-vip-stage）

<a id="vip_level_upgrade"></a>

### VIP等级-升级到目标等级

- **功能**：把用户升级到目标 VIP 等级（按阈值自动先查当前 VIP 经验后补差）
- **提示词**：
  - `用户 <userId> 升级到 VIP<level>`
  - `把用户 <userId> 升级到 VIP<level>`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id <userId> \
  --vip-level <level>
```

<a id="vip_delete_info"></a>

### VIP等级-清除VIP信息

- **功能**：清除用户VIP等级信息（delVipInfo）
- **提示词**：
  - `清除用户 <userId> 的VIP等级`
  - `清除 <userId> 的VIP等级`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_del_payload.example.json \
  --vip-del-user-id <userId>
```

<a id="vip_exp_add"></a>

### VIP经验值-增加

- **功能**：给指定用户增加 VIP 经验值（增量）
- **提示词**：
  - `给用户 <userId> 增加 <vipExp> VIP经验值`
  - `给用户 <userId> 增加 <vipExp> VIP 经验值`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id <userId> \
  --vip-exp <vipExp>
```

<a id="vip_query_current"></a>

### VIP经验值-查询当前等级经验

- **功能**：查询用户当前 VIP 经验值与等级（通过 addVipValue(userId,0)）
- **提示词**：
  - `查询用户 <userId> 当前VIP等级经验值`
  - `帮我查询用户 <userId> 当前VIP等级经验值`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id <userId> \
  --vip-query-current
```

<a id="moa-cat-2"></a>

## 2) 实名认证（internal/user/id-auth-api）

<a id="id_auth_query_real_person_record"></a>

### 实名认证-查询认证记录

- **功能**：查询用户实名认证记录（queryRealPersonRecord）
- **提示词**：
  - `查询用户 <userId> 的认证结果`
  - `查询用户 <userId> 实名认证结果`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_payload.example.json \
  --id-auth-user-id <userId>
```

<a id="id_auth_delete_person"></a>

### 实名认证-清除认证信息

- **功能**：清除用户认证信息（internalAuthDeletePerson）
- **提示词**：
  - `清除用户 <userId> 的认证信息`
  - `删除用户 <userId> 的认证信息`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_delete_person_payload.example.json \
  --id-auth-delete-user-id <userId>
```

<a id="id_auth_fix_failure_by_reason"></a>

### 实名认证-解决认证失败（清 reason 关联账号）

- **功能**：查询用户认证记录并清除最近一条 reason 中的账号认证记录（queryRealPersonRecord -> internalAuthDeletePerson）
- **提示词**：
  - `解决用户 <userId> 认证失败`
  - `解决 <userId> 认证失败`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_payload.example.json \
  --id-auth-fix-failure-user-id <userId>
```

<a id="id_auth_reset_relation_expire_time"></a>

### 实名认证-设置认证过期时间

- **功能**：设置用户认证过期时间（resetRelationPersonExpireTime，支持输入日期时间自动转毫秒时间戳）
- **提示词**：
  - `把用户 <userId> 的认证过期时间设置为 <time>`
  - `设置用户 <userId> 认证过期时间为 <time>`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_reset_expire_payload.example.json \
  --id-auth-reset-expire-user-id <userId> \
  --id-auth-expire-ms <expireMs>
```

<a id="moa-cat-3"></a>

## 3) 房间经验值（voga-mts-room-backdoor）

<a id="room_level_upgrade"></a>

### 房间等级-升级到目标等级

- **功能**：把房间升级到目标等级（按阈值自动先查当前经验后补差）
- **提示词**：
  - `把房间 <roomId> 升级到 <level> 级`
  - `把房间 <roomId> 升级到 <level>级`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id <roomId> \
  --level <level>
```

<a id="room_exp_add"></a>

### 房间经验值-增加

- **功能**：给指定房间增加经验值（增量）
- **提示词**：
  - `给房间 <roomId> 增加 <exp> 经验值`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id <roomId> \
  --exp <exp>
```

<a id="room_query_current"></a>

### 房间经验值-查询当前等级经验

- **功能**：查询房间当前经验值与等级（通过 addRoomActiveValue(roomId,0D)）
- **提示词**：
  - `查询房间 <roomId> 当前等级经验值`
  - `帮我查询房间 <roomId> 当前等级经验值`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id <roomId> \
  --query-current
```

<a id="moa-cat-4"></a>

## 4) 背包礼物（voga-base-service-middle-gift-stage）

<a id="package_gift_add"></a>

### 背包礼物-下发

- **功能**：给用户下发背包礼物（addPackageGift，默认两种各100个）；outOrderId 末尾每次随机13位数
- **提示词**：
  - `给用户 <userId> 下发背包礼物`
  - `给用户 <userId> 下发100个两种背包礼物`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/package_gift_payload.example.json \
  --package-gift-user-id <userId>
```

<a id="moa-cat-5"></a>

## 5) 钻石（voga-base-service-middle-pay-stage）

<a id="diamond_provide"></a>

### 钻石-发放

- **功能**：给用户发放钻石（provideDiamond）；outOrderId 每次自动生成 system-随机5位数
- **提示词**：
  - `给用户 <userId> 增加 <num> 钻石`
  - `给用户 <userId> 发放 <num> 钻石`
- **命令**：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/diamond_payload.example.json \
  --diamond-user-id <userId> \
  --diamond-num <num>
```
