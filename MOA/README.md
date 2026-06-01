# MOA 调用脚本（Cursor 可运行）

这个目录用于在本地（Cursor 终端）复现 MOA 的 `execute` 调用：把 MOA 页面里的一段请求 JSON 作为 body，POST 到 httpproxy 接口，由后端执行目标 service 的 `execute`。

> 首次使用或换电脑：请先阅读 [docs/新手上手.md](../docs/新手上手.md) 配置 `MOA/.env.local`。

## 1) 准备环境变量（必需）

- `MOA_ENTRY_URL`: httpproxy 入口完整 URL  
  例（你抓包里真实请求）：`https://mse.wemomo.com/apirest/httpproxy/moa/test`
- `MOA_COOKIE`: 从浏览器/MOA 页面复制的整段 Cookie（敏感信息，不要提交到仓库）

推荐做法：把这些变量写入 `MOA/.env.local`（已加入 `.gitignore`，不会被提交），脚本会自动加载。

你可以先复制模板：

```bash
cp MOA/.env.example MOA/.env.local
```

然后把 `MOA/.env.local` 里的 `MOA_COOKIE=...` 替换成你自己的 Cookie。

示例：

```bash
export MOA_ENTRY_URL='https://mse.wemomo.com/apirest/httpproxy/moa/test'
export MOA_COOKIE='JSESSIONID=...; tunnel_login_session=...; auth_cookie=...'
```

可选但建议（与你抓到的请求头对齐，部分环境会校验这些字段）：

- `MOA_ORIGIN`: `https://mse.wemomo.com`
- `MOA_REFERER`: `https://mse.wemomo.com/`
- `MOA_USER_AGENT`: 浏览器 UA（可简化成 `Mozilla/5.0`）
- `MOA_REQUEST_SOURCE`: `moaProxy`

```bash
export MOA_ORIGIN='https://mse.wemomo.com'
export MOA_REFERER='https://mse.wemomo.com/'
export MOA_USER_AGENT='Mozilla/5.0'
export MOA_REQUEST_SOURCE='moaProxy'
```

## 2) 直接执行（传入完整 JSON）

把你在 MOA 里看到/导出的请求 JSON 保存成文件（比如 `payload.json`），然后运行：

```bash
python3 MOA/moa_execute.py --payload-file payload.json
```

或者直接把 JSON 作为参数（适合短 payload）：

```bash
python3 MOA/moa_execute.py --payload '{"type":"moa","url":"/service/xxx","method":"execute","params":[...]}'
```

## 2.1) 一条命令复现「你抓包里的 MOA」

你抓到的请求入口与 body（不含 Cookie）是：

- 入口：`https://mse.wemomo.com/apirest/httpproxy/moa/test`
- body 里核心字段：`url=/service/voga-mts-room-backdoor`、`method=execute`

所以最短运行方式是（roomId/exp 可替换）：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id 31668628 \
  --exp 11
```

## 3) 便捷模式：只改表达式（可选）

如果你只想快速替换 `params[0].value`，可以用：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --expr 'context.getBean("roomProfileDao").addRoomActiveValue("31668628",10000000D)'
```

或者用便捷参数生成「给房间增加经验值」的表达式（会覆盖 `params[0].value/txt`）：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --room-id 31668628 \
  --exp 10000000
```

## 房间等级经验值阈值（配置文件）

阈值已迁移到 `MOA/config.json` 的 `room_level_exp_thresholds` 字段；后续类似“规则/映射表”都统一沉淀到该配置文件。

### 只说等级的用法（脚本按阈值算增量）

注意：MOA 方法是 `addRoomActiveValue`（增量增加），所以需要“当前经验值”来计算要加多少。

现在脚本在 `--level` 模式下会**自动先查询当前经验值（0D）**，再补差值；通常不需要你再传 `--current-exp`。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id 31668628 \
  --level 3
```

如果你明确知道当前经验值，也可以传 `--current-exp` 跳过查询（适用于批量操作/减少一次请求）。

## 查询房间当前经验值与等级

可以通过“增加 0 经验值”的方式拿到当前经验值（你提到的做法），然后脚本会按阈值计算等级：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id 89333567 \
  --query-current
```

如果 MOA 页面里选择了具体实例（例如右上角显示 `10.247.244.119:29584`），通常需要把它写进 `settings.host`，可以用：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --host 10.247.244.119:29584 \
  --room-id 31668628 \
  --exp 10000000
```

## VIP：增加 VIP 经验值 / 按 VIP 等级补差

你抓包的 VIP MOA：

- `url`: `/service/voga-mts-user-vip-stage`
- `method`: `addVipValue`
- `params[0]`: 用户ID（string）
- `params[1]`: 增加的 VIP 经验值（int）

### 给用户增加指定 VIP 经验值

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-exp 10
```

### 只说目标 VIP 等级（自动先查当前 VIP 经验，再补差）

VIP 等级阈值已迁移到 `MOA/config.json` 的 `vip_level_exp_thresholds`。

默认 `--level-exp-mode min`：补到该等级**最低**阈值（刚达标）。  
若需补到该等级**最高**经验（下一级阈值 - 1），加 `--level-exp-mode max`。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-level 4
```

```bash
# 升到 VIP4 的最高经验（VIP5 阈值 - 1）
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-level 4 \
  --level-exp-mode max
```

> `--level-exp-mode` 同样适用于房间、家族、贵族、房间成员等等级升级场景。

### 查询当前 VIP 经验值与等级

通过 `getVipInfo` 查询，返回 `value` 作为 VIP 经验值、`level`/`trueLevel` 作为当前等级。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-query-current
```

输出示例：

```json
{
  "userId": "100465989",
  "currentVipExp": 1809999,
  "vipLevel": 4,
  "trueLevel": 4,
  "tryLevel": 0,
  "nextVipLevelThreshold": 1810000,
  "remainingToNextVipLevel": 1
}
```

> 说明：`addVipValue(userId, 0)` 仅返回 `true`，不能用于查询经验值；升级补差也已改为先调 `getVipInfo` 读取 `value`。

### 清除用户 VIP 等级信息

你抓包的 VIP 清除 MOA：

- `url`: `/service/voga-mts-user-vip-stage`
- `method`: `delVipInfo`
- `params[0]`: 用户ID（string）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_del_payload.example.json \
  --vip-del-user-id 2176
```

如果返回 `ec=300` 但 MOA 页面同操作能成功，优先怀疑这几个字段与你页面不一致（常见：`yoga`/`voga` 拼写、超时太短）：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --host 10.247.244.119:29584 \
  --service-url /service/yoga-mts-room-backdoor \
  --moa-time 5000 \
  --room-id 34760986 \
  --exp 10000000
```

## 实名认证：查询用户认证记录

你抓包的实名认证查询 MOA：

- `url`: `/service/internal/user/id-auth-api`
- `method`: `queryRealPersonRecord`
- `params[0]`: `{"userId":"..."}`（json）

### 查询指定用户的认证记录

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_payload.example.json \
  --id-auth-user-id 100486375
```

默认输出为“最近一条记录的 reason”（便于你快速查看审核原因等）。如果需要完整 JSON：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_payload.example.json \
  --id-auth-user-id 100486375 \
  --id-auth-output json
```

## 实名认证：设置用户认证过期时间

你抓包的 MOA：

- `url`: `/service/internal/user/id-auth-api`
- `method`: `resetRelationPersonExpireTime`
- `params[0]`: `userId`（string）
- `params[1]`: `expireTime`（long，毫秒时间戳）

脚本接收毫秒时间戳，或通过 `--id-auth-expire-at` 传入自然语言/日期（如 `tomorrow`、`明天`、`+1d`、`2026-05-30 23:59:59`）。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_reset_expire_payload.example.json \
  --id-auth-reset-expire-user-id 100006869 \
  --id-auth-expire-at tomorrow
```

也可直接传毫秒时间戳：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_reset_expire_payload.example.json \
  --id-auth-reset-expire-user-id 100006869 \
  --id-auth-expire-ms 1747034397000
```

## 实名认证：清除用户认证信息

你抓包的 MOA：

- `url`: `/service/internal/user/id-auth-api`
- `method`: `internalAuthDeletePerson`
- `params[0]`: `userId`（string）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_delete_person_payload.example.json \
  --id-auth-delete-user-id 107427060
```

## 实名认证：解决“认证失败”关联账号（自动清除 reason 中账号）

当你说“解决某个用户认证失败”，脚本会：

1. 查询该用户的认证记录（`queryRealPersonRecord`）
2. 取最近一条记录的 `reason`（通常是一个账号列表）
3. 逐个调用 `internalAuthDeletePerson` 清除这些账号的认证记录

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/id_auth_payload.example.json \
  --id-auth-fix-failure-user-id 100079102
```

## 贵族：增加月消费值 / 升级等级

服务：`/service/voga-mts-user-wealth-charm-level-stage`

贵族等级与月消费值阈值见 `MOA/config.json` 的 `noble_level_exp_thresholds`（lv1=25000 … lv6=21000000）。

### 增加贵族月消费值（增量）

- `method`: `incrNobelLevel`
- `params[0]`: 用户 ID（string）
- `params[1]`: 增加的月消费值（long）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/noble_payload.example.json \
  --noble-user-id 100079102 \
  --noble-exp 400000
```

### 升级到目标贵族等级（需已知当前月消费值）

已知当前月消费值时，脚本按 `noble_level_exp_thresholds` 计算需增加的数值；未传 `--noble-current-exp` 时默认按 0 计算。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/noble_payload.example.json \
  --noble-user-id 100079102 \
  --noble-level 2 \
  --noble-current-exp 25000
```

## 家族：增加声望值 / 升级等级

服务：`/service/internal/user/family-moa`

家族等级与声望值阈值见 `MOA/config.json` 的 `family_level_exp_thresholds`（lv1=0 … lv10=8724000）。

### 增加家族声望值（增量）

- `method`: `addFamilyActiveValueBySystem`
- `params[0]`: 家族 ID（string）
- `params[1]`: 增加的声望值（long）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_exp_payload.example.json \
  --family-id 101435 \
  --family-exp 10
```

### 衰减家族声望值

- `method`: `decreaseFamilyActiveValue`
- `params[0]`: 家族 ID（string）
- `params[1]`: 衰减量（long，**负值**，如 `-10`）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_decrease_exp_payload.example.json \
  --family-id 101435 \
  --family-decrease-exp 10
```

执行后会输出衰减后的当前声望值与等级摘要（若接口返回数值）。

### 家族基金 ABC 档位小档位阈值

配置见 `MOA/config.json` 的 `family_fund_tier_sub_rewards`（仅小档位、家族整体贡献值、返奖钻石）。

**A 档（≥ 1,000,000）**

| 小档位 | 家族整体贡献值 | 返奖钻石 |
|--------|----------------|----------|
| 初始值 | 0 | 0 |
| 档位 1 | 1,000,000 | 80,000 |
| 档位 2 | 3,000,000 | 240,000 |
| 档位 3 | 4,500,000 | 360,000 |
| 档位 4 | 6,000,000 | 600,000 |

**B 档（< 1,000,000）**

| 小档位 | 家族整体贡献值 | 返奖钻石 |
|--------|----------------|----------|
| 初始值 | 0 | 0 |
| 档位 1 | 100,000 | 6,000 |
| 档位 2 | 350,000 | 21,000 |
| 档位 3 | 450,000 | 27,000 |
| 档位 4 | 600,000 | 48,000 |

**C 档（< 100,000）**

| 小档位 | 家族整体贡献值 | 返奖钻石 |
|--------|----------------|----------|
| 初始值 | 0 | 0 |
| 档位 1 | 10,000 | 400 |
| 档位 2 | 25,000 | 1,000 |
| 档位 3 | 45,000 | 1,800 |
| 档位 4 | 70,000 | 4,200 |

### 设置家族基金档位

- 服务：`/service/voga-mts-user-backdoor` / `execute`
- 表达式：`context.getBean("familyFundService").batchSetFamilyFundTierForTest(...)`
- **返回 `result` 为成功更新的家族数量**；`0` 表示未更新（设置失败）
- 家族 ID 必须为 **字符串**（json 数组 `["101435"]`），数字数组会报错

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_tier_payload.example.json \
  --family-id 101435 \
  --family-fund-tier B
```

### 一键设置家族基金返奖钻石

自动：清除本周贡献 → 设置档位 → 设置贡献值 → 查询摘要。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_tier_payload.example.json \
  --family-id 101435 \
  --family-fund-reward-diamonds 27000
```

批量设置多个家族档位：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_tier_payload.example.json \
  --family-fund-ids 101435,101436 \
  --family-fund-tier B
```

### 增加家族基金贡献值

- 服务：`/service/voga-mts-user-backdoor` / `execute`
- 表达式：`context.getBean("familyFundDao").incrFundFamilyTotal("<familyId>",<contrib>L,"<YYYYMMDD>-week")`
- 周期键为该周**周一**日期 + `-week`（如 `20260525-week`）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_contrib_payload.example.json \
  --family-id 101435 \
  --family-fund-contrib 1 \
  --family-fund-week 20260525
```

省略 `--family-fund-week` 时默认使用**本周周一**；也可传任意日期，脚本会自动归到该周周一。

### 查询家族基金贡献值

- 表达式：`incrFundFamilyTotal("<familyId>",0L,"<YYYYMMDD>-week")`（增量 0 仅查询）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_contrib_payload.example.json \
  --family-id 101435 \
  --family-fund-contrib 0
```

### 清除家族基金贡献值

- 表达式：`context.getBean("familyFundService").delFamilyFundRankTest("<familyId>",<weekOffset>)`
- `weekOffset`：`0`=本周，`-1`=上周

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_clear_payload.example.json \
  --family-id 101435 \
  --family-fund-clear
```

清除上周：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_fund_clear_payload.example.json \
  --family-id 101435 \
  --family-fund-clear \
  --family-fund-week-offset -1
```

### 给成员增加家族基金贡献值

- `method`: `batchIncrFundContribution`
- `params[0]`: 家族 ID（string）
- `params[1]`: 周期键（string，如 `20260525-week`）
- `params[2]`: 成员贡献 map（json，`userId -> API传值`）
- **注意**：API 传值为实际贡献值的 **2 倍**（如贡献 500，传 `1000`）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_member_fund_contrib_payload.example.json \
  --family-id 101435 \
  --family-member-fund-user-id 100465989 \
  --family-member-fund-contrib 500 \
  --family-fund-week 20260525
```

### 升级到目标家族等级（自动先查当前声望值再补差）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_exp_payload.example.json \
  --family-id 101435 \
  --family-level 3
```

### 查询当前家族声望值与等级

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/family_exp_payload.example.json \
  --family-id 101435 \
  --family-query-current
```

说明：`addFamilyActiveValueBySystem` 在增量为 **0** 时也会返回当前家族声望总值（与贵族/房间成员接口不同）。

## 钻石：查询余额 / 发放

服务：`/service/voga-base-service-middle-pay-stage`

### 查询用户当前钻石数

- `method`: `queryUserAccount`
- `params[0]`: `userId`（string）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/diamond_query_payload.example.json \
  --diamond-query-user-id 100465989
```

默认输出摘要 JSON（含 `diamonds`、`coinCount` 等）。完整响应：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/diamond_query_payload.example.json \
  --diamond-query-user-id 100465989 \
  --diamond-output json
```

### 给用户发放钻石

- `method`: `provideDiamond`

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/diamond_payload.example.json \
  --diamond-user-id 100465989 \
  --diamond-num 10000
```

## 房间：增加在线机器人

你抓包的 MOA：

- `url`: `/service/room/internal/room-test-stage`
- `method`: `addOnlineUsersToRoom`
- `params[0]`: 房间 ID（string）
- `params[1]`: 在线机器人总数（int）
- `params[2]`: 麦上机器人数量（int）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/room_bot_payload.example.json \
  --room-bot-room-id 38826842 \
  --room-bot-total 10 \
  --room-bot-on-mic 5
```

## 房间成员：增加陪伴值 / 升级等级

服务：`/service/room/internal/room-user-active-stage`

成员等级与陪伴值阈值见 `MOA/config.json` 的 `member_level_exp_thresholds`（lv1=0 … lv20=55000000）。

### 增加陪伴值（增量）

- `method`: `doorIncrMemberLv`
- `params[0]`: 房间 ID（string）
- `params[1]`: 用户 ID（string）
- `params[2]`: 增加的陪伴值（int）

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/room_member_lv_payload.example.json \
  --member-lv-room-id 44283732 \
  --member-lv-user-id 8250 \
  --member-lv-exp 1
```

### 升级到目标成员等级（需已知当前陪伴值）

已知当前陪伴值时，脚本按 `member_level_exp_thresholds` 计算需增加的陪伴值；未传 `--member-lv-current-exp` 时默认按 0 计算。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/room_member_lv_payload.example.json \
  --member-lv-room-id 44283732 \
  --member-lv-user-id 8250 \
  --member-lv-level 5 \
  --member-lv-current-exp 3000
```

## 4) 输出与成功判定

脚本会把服务返回 JSON 原样打印，并尝试提取：

- `ec`: 0 代表成功（如果返回体包含该字段）
- `em`: 文本信息
- `result`: 业务返回值

当检测到 `ec != 0` 时脚本会以非 0 退出码退出，方便在流水线/批处理里判断失败。

## 5) （可选）用 curl 直接运行

适合验证“是不是脚本问题”，不适合长期复用（容易把 Cookie 留在历史记录里）。

```bash
curl -sS "$MOA_ENTRY_URL" \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/plain, */*' \
  -H "Cookie: $MOA_COOKIE" \
  -H "Origin: ${MOA_ORIGIN:-https://mse.wemomo.com}" \
  -H "Referer: ${MOA_REFERER:-https://mse.wemomo.com/}" \
  -H 'request-source: moaProxy' \
  --data-raw '{"type":"moa","url":"/service/voga-mts-room-backdoor","method":"execute","header":"","params":[{"title":"参数1","name":"1","txt":"context.getBean(\"roomProfileDao\").addRoomActiveValue(\"31668628\",11D)","json":"","type":"string","value":"context.getBean(\"roomProfileDao\").addRoomActiveValue(\"31668628\",11D)"}],"settings":{"time":"2000","group":"default","host":"","headerType":"TXT"},"region":"alpha","env":"alpha","cluster":"stage","server":"config","momoId":"df4c6f364f9fcae3","momoName":"e88aa376b29864ad"}'
```

---

## 6) MOA 方法录入规范（你说我记）

你后续提供新的 MOA 方法时，按以下规范提供信息；我会把它落到 `MOA/` 中，并自动加入 `MOA/MOA使用方法.md`（由 `MOA/generate_moa_index.py` 自动生成）。

### 6.1 录入目标

- **可运行**：在本仓库用 `python3 MOA/moa_execute.py ...` 可以直接执行
- **可复用**：参数化（用户只给核心参数，如 roomId/level/userId 等）
- **可追溯**：README 里能看懂“这个方法干什么/怎么用/成功怎么判定”
- **安全**：Cookie/Token 只放本地（`MOA/.env.local`），绝不入库

### 6.2 你需要提供的最小信息

把下面 3 块信息粘贴给我即可（越完整越好）。

#### 6.2.1 入口请求（httpproxy）

从浏览器 Network 抓包复制这几项：

- **URL**：例如 `https://mse.wemomo.com/apirest/httpproxy/moa/test`
- **请求行**：例如 `POST /apirest/httpproxy/moa/test HTTP/1.1`
- **关键请求头**（至少要有这些）：
  - `Content-Type: application/json`
  - `Origin`
  - `Referer`
  - `request-source: moaProxy`（如果有）
  - `User-Agent`
  - `Cookie`（敏感，可单独发我，我会只写进 `MOA/.env.local` 并加忽略）

#### 6.2.2 请求 body（payload JSON）

把 Network 里 “请求数据 / Request Payload” 的 JSON 原样贴出来，例如：

```json
{
  "type": "moa",
  "url": "/service/xxx",
  "method": "execute",
  "params": [ ... ],
  "settings": { "time": "2000", "group": "default", "host": "", "headerType": "TXT" },
  "region": "alpha",
  "env": "alpha",
  "cluster": "stage",
  "server": "config"
}
```

#### 6.2.3 参数说明（你口述我记录）

请告诉我：

- **这个 MOA 做什么**（一句话）
- **params 每个参数的含义与类型**（string/int/long…）
- **调取方式**（你希望以后怎么说）
  - 例：`给房间 <roomId> 升级到 <level>`
  - 例：`用户 <userId> 升到 VIP<level>`
- **成功判定**：返回体里哪个字段为成功（常见：外层 `ec=200`，内层 `result.ec=0`）
- **是否需要“先查再补差”**：比如升级等级需要先查当前经验值（可通过“加 0”查询）

### 6.3 我会如何落库（我来做）

- **敏感配置**：写入 `MOA/.env.local`（不入库）
- **payload 示例**：新增 `MOA/*_payload.example.json`
- **脚本入口**：在 `MOA/moa_execute.py` 增加可调用参数/模式
- **规则/映射表**：写入 `MOA/config.json`
- **清单登记**：写入 `MOA/moa_registry.json`，并运行 `MOA/generate_moa_index.py` 刷新 `MOA/MOA使用方法.md`

### 6.4 你给我的推荐模板（复制填空）

```text
【方法名称】：
【用途一句话】：

【入口 URL】：
【请求头（除 Cookie 外）】：
【Cookie】：（单独贴也行）

【payload JSON】：
（粘贴完整 JSON）

【params 说明】：
1) ...
2) ...

【我希望以后怎么说】：
（例如：把房间 89333567 升级到 5 级）

【成功判定】：
（例如：外层 ec=200 且 result.ec=0）

【是否需要先查再补差】：
（是/否；若是，如何查询当前值）
```

