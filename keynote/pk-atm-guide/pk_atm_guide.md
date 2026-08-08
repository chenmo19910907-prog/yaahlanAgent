# PK 提款机：从零到 MOA 造数与自动化（2.5.9）

| 形式 | 地址 |
|------|------|
| **内网网页** | http://172.18.125.90:18766/keynote/pk-atm-guide |
| **本机网页** | http://127.0.0.1:18766/keynote/pk-atm-guide |

> 网页版由 `platform/web_agent/keynote/sync_pk_atm_guide.py` 同步；改本文后重跑该脚本即可刷新。

**本文档讲什么**：记录一次真实协作——从 **读 PRD、澄清规则**，到 **抓包落 MOA、对话里跑通场景（C1～C9）**，再到 **Sheet2 全链路验收 + 工作流沉淀**。  
协作主路径：`读 PRD` → `抓包落 MOA` → `对话迭代 C1～C9` → `赛况 / 返钻弹窗 / 提款排名 / 吸底验收` → `pk_atm_dingtalk_sheet2_run.py`（或工作流 `pk-atm-test`）。

**最终一键命令**（Web Agent / 对话内重跑，**推荐**）：

```bash
python3 workflow/scripts/pk_atm_dingtalk_sheet2_run.py \
  --phone-a 13311111111 --phone-b 13311111115 \
  --target-combined-pk 200000 \
  --gift-min-diamonds 100 --gift-max-diamonds 1500 \
  --gift-count 50 --personal-pk-threshold 10000
```

产出：`.tmp/pk_atm_sheet2_<pkId>.json` + 钉钉 Sheet「测试结果-<pkId 后缀>」。

工作流入口（等价底层脚本 `pk_atm_test_run.py`）：

```bash
python3 workflow/workflow_execute.py run pk-atm-test
```

---

## 1. 核心思路：五层递进，不要一次写全

PK 提款机能力不是一句「帮我写自动化」出来的，而是按下面五层 **逐层提问、逐层验收**：

```mermaid
flowchart LR
  P1[① 知识层<br>PRD/用例/梯度] --> P2[② 接口层<br>Tunnel→MOA]
  P2 --> P3[③ 场景层<br>跨房PK造数]
  P3 --> P4[④ 验收层<br>PK报告+返钻]
  P4 --> P5[⑤ 资产层<br>工作流+文档]
```

| 阶段 | 你要 AI 做到什么 | 你怎么问 | 典型产出 |
|------|------------------|----------|----------|
| ① 知识层 | AI **懂业务**，能回答门槛/梯度/边界 | 读 PRD、补梯度、生成用例 | `prd-kb/`、`temporary_testcase/PK提款机_2.5.9_测试用例.md` |
| ② 接口层 | AI **能调接口**，不靠手点 App | 抓包 → 记录 MOA | `MOA/templates/跨房PK-*.json`、`MOA-generative/mappings.md` |
| ③ 场景层 | 对话里 **跑通一场 PK** | 双号 + 机器人 + 送礼（分步修正） | 临时命令、`.tmp` 中间结果 |
| ④ 验收层 | 能 **断言发奖与页面数据** | C6 钻石差值；C7 结束前赛况 MOA；C8 结束后提款排名 MOA | `workflow/scripts/pk_atm_test_run.py` |
| ⑤ 资产层 | **别人能复用** | 「结合到 PK 提款机测试」「整理学习文档」 | 工作流 `pk-atm-test`、本文档 |

**三条铁律**

1. **先对话跑通，再落库**——不要跳过 ③ 直接要脚本。  
2. **用修正句迭代**——C2「然后加机器人」比重写全文省力。  
3. **规则有「待确认」就显式列假设**——例如个人 PK 门槛，不要 silently 默认。

---

## 2. 阶段 ①：分析需求（不必写代码）

目标：让 AI 在造数之前，能回答「什么算提款机场次」「梯度怎么算」「哪些边界要测」。

### 2.1 实际提问顺序

| 顺序 | 你说了什么（要点） | 为什么要问 |
|------|-------------------|------------|
| A1 | 读取 2.5.9 PRD，生成知识库 | 统一术语与模块边界 |
| A2 | PK 提款机以前版本做过吗 | 定回归范围，避免重复造轮子 |
| A3 | （贴梯度表）不同阈值对应返奖比例 | 把表格变成可引用知识 |
| A4 | 个人获得奖励的门槛是多少 | 区分「场次门槛 vs 个人门槛」 |
| A5 | PK 提前结束怎么处理 | 准备阶段 / 认输 / 惩罚等边界 |
| A6 | 2.5.9 还有什么问题要处理 | 产出待确认清单 |
| A7 | 生成 2.5.9 PK 提款机全量用例 | 102 条用例 + 可导出钉钉 |

### 2.2 本阶段应搞清的业务要点（够用即可）

| 规则 | 要点 |
|------|------|
| 计入活动 | 仅 **跨房 PK · 随机匹配**；指定邀请 / 再来一局 **不计入** |
| 场次门槛 | PRD：**双方总 PK ≥ 50 万**；**alpha 实测 MSE** 见 §2.4（当前 **2 万**） |
| 梯度发奖 | 双方总 PK 命中梯度 → 按 **返钻比例 %** 计算本场总奖金（alpha 见 §2.4） |
| 个人瓜分 | 仅 **胜方**且 **个人 PK ≥ 个人门槛（当前 1 万）**；`floor(个人 PK / 胜方总 PK × 本场总奖金)`；**未达门槛应得 0、实发必须 0** |
| PK 换算 | 麦上送礼：**1 钻石 = 10 PK 值** |
| 返钻基数 | **送礼钻石（总 PK÷10）× 命中档位返钻 %**，向下取整得 **下发总钻石**；等价于 **总 PK × 0.3%/0.4%/…**（3% 档时） |
| 梯度命中 | **双方总 PK ≥ 左列阈值时取满足条件的最高档**（不是「≤ 上限档」） |
| 首胜翻倍 | alpha MSE 已开：`firstWinMultiplier = 2` |
| 胜负判定 | **主动结束 PK 的一方记败**；另一方为胜方 |

全量用例：`temporary_testcase/PK提款机_2.5.9_测试用例.md`（PK_001～PK_102）。用例按 PRD 梯度编写；**造数验收以 MSE 为准**（§2.4）。

### 2.3 本阶段提问模板

```text
读取{版本} PRD，生成知识库。
{粘贴梯度表} —— 请整理成表格并说明如何用于验收。
生成{功能}全量测试用例并导出钉钉表格。
{规则点} 在 PRD 里是否明确？不明确请列出待确认项和你的假设。
```

### 2.4 服务配置（MSE alpha · pkAtmConfig）

**来源**：MSE `voga-common` / `pkAtmConfig`，cluster/env/region 均为 **alpha**；appKey `momo.bpm.biz.gameplatform.overseas-voga-mts-room`。  
**最后更新**：2026-08-07（v-chen.mo）。  
**钉钉单表**：[PK提款机-pkAtmConfig-20260807](https://alidocs.dingtalk.com/i/nodes/oP0MALyR8k7Aow9wCY9wvqBd83bzYmDO)（Agent 导出目录，单 Sheet「活动配置」）。

拉取命令：

```bash
python3 MSE/mse_execute.py \
  --namespace voga-common --config-key pkAtmConfig \
  --cluster alpha --env alpha --region alpha --output json

# 写入 / 刷新钉钉表格（新建）
python3 platform/dingtalk_gateway/pk_atm_mse_to_workbook.py \
  --workbook-name "PK提款机-pkAtmConfig-YYYYMMDD"

# 覆盖已有表格（推荐更新时用）
python3 platform/dingtalk_gateway/pk_atm_mse_to_workbook.py \
  --workbook-url "https://alidocs.dingtalk.com/i/nodes/oP0MALyR8k7Aow9wCY9wvqBd83bzYmDO"
```

#### 基础参数（alpha 当前值）

| 键 | 值 | 说明 |
|----|-----|------|
| `enabled` | `true` | 活动总开关 |
| `longTermEnabled` | `true` | 长期活动 |
| `startTime` / `endTime` | 2026-01-01 ～ 2026-12-31 | 活动期 |
| `dailyStartHour` / `dailyEndHour` | 0 / 24 | 每日时段 |
| **`minTotalPkValue`** | **20,000** | 场次总 PK 门槛（PRD 50 万，测试环境已下调） |
| **`minMemberRewardPk`** | **10,000** | **个人瓜分 PK 门槛**（以服务端当前配置为准） |
| `broadcastMinDiamond` | 1,000 | 广播最低钻石 |
| `firstWinEnabled` | `true` | 首胜翻倍开关 |
| **`firstWinMultiplier`** | **2** | 首胜倍数 |

#### 梯度表 `matchPoolGradients`（双方总 PK **≥** 左列 → 返钻比例）

| minTotalPkValue | returnRatioPercent | 下发总钻示例（总 PK=223,430） |
|-----------------|-------------------|-------------------------------|
| 20,000 | 3% | floor(22343×3%) = **670** |
| 100,000 | 3% | 同上档（取 **≥10 万** 最高档） |
| 400,000 | 4% | floor(22343×4%) = 893（仅当总 PK≥40 万） |
| 1,000,000 | 5% | |
| 2,000,000 | 5% | |
| 5,000,000 | 6% | |

> **注意**：返钻 **3%** 指占 **送礼钻石** 的比例，即总 PK 的 **0.3%**（因 1 钻=10 PK）。

#### 发钻配置 `diamondDispatchConfig`

| 键 | 值 |
|----|-----|
| `activityId` | `2005005017` |
| `activityTaskId` | `2005005019` |
| `activitySign` | `7e5721b379b14962a38f9d2e81376605` |

**与工作流关系**：`pk_atm_test_run.py` / `pk_atm_dingtalk_sheet2_run.py` 优先 MOA 拉运行时配置；拉不到或报告快照滞后时，以 `workflow/config/pk_atm_default_config.json` 为准（**个人门槛 10000**）。验收对齐：

```bash
--min-combined-pk 20000 --personal-pk-threshold 10000
```

---

## 3. 阶段 ②：抓包 → 提供 MOA（一次一个接口）

目标：每个 HTTP 动作都有 **可重复执行的 MOA 模板**，后续造数不再依赖手点 App。

### 3.1 实际提问顺序

| 顺序 | 你说了什么（要点） | 产出 |
|------|-------------------|------|
| B0 | **13311111112 / 13311111113 同时发起随机匹配**跨房 PK | 双房 `applyAcrossRoomPk`（`acrossPkType=1`）+ 配对成功 |
| B1 | 抓包 13311111113 **发起随机匹配**的 tunnel | Tunnel `_id=VmdPzJ8BR2LVRzbvVZwa` + MOA 随机匹配模板 |
| B2 | 根据抓包生成 MOA | `applyAcrossRoomPk` 映射（随机匹配 + 指定邀请两条） |
| B3 | （探索）13311111113 邀请 80949067 跨房 PK | 指定邀请模板；**不计入提款机** |
| B4 | 13311111114 接受邀请 / 13311111113 结束 PK，抓包 | `acceptAcrossRoomPkInvite` / `closeAcrossRoomPk` |

### 3.2 提问格式（固定句式）

```text
抓包{手机号}{动作描述}的 tunnel，并记录到 MOA。
```

示例：

- `13311111112和13311111113同时发起跨房PK随机匹配`
- `抓包13311111113发起跨房PK随机匹配的tunnel，并记录到MOA`
- `抓包13311111113邀请80949067跨房PK的tunnel，并记录到MOA`（探索用，非提款机计入）
- `13311111113结束PK，抓包并记录MOA`

### 3.3 操作习惯

| 习惯 | 原因 |
|------|------|
| **一次只录一个接口** | 避免 AI 批量猜 method，难验收 |
| 账号用 **手机号**，房间可只给 **roomId** | AI 会反查 userId |
| 录完让 AI **当场 MOA 执行一次** | 确认模板可用，而不只是落文件 |
| 跨房 PK 造数 **默认随机匹配** | 指定邀请常限频 / pending，且 **不计入提款机**；两房先后 `applyAcrossRoomPk`（`acrossPkType=1`）即可配对 |

### 3.4 本阶段产出清单

| 资产 | 用途 |
|------|------|
| `MOA/templates/跨房PK-随机匹配.json` | **提款机造数**：双房随机匹配（`acrossPkType=1`，`acrossRoomId=""`） |
| `MOA-generative/templates/example-applyAcrossRoomPk-random-match.body.json` | 生成式 MOA 随机匹配 body 示例 |
| `MOA/templates/跨房PK-指定邀请.json` | 探索 / 指定邀请（**不计入提款机**） |
| `MOA/templates/跨房PK-接受邀请.json` | 接受指定邀请 |
| `MOA/templates/跨房PK-结束PK.json` | 结束 PK |
| `MOA/templates/房间-增加机器人.json` | 麦上有人可收礼 |
| `MOA-generative/mappings.md` | room-pk-api 路径 ↔ method 登记 |

### 3.5 随机匹配 MOA 要点（Tunnel 实测）

| 字段 | 随机匹配 | 指定邀请 |
|------|----------|----------|
| HTTP | `/yaahlan/room/acrossRoomPk/applyAcrossRoomPk` | 同左 |
| MOA | `/service/room/external/room-pk-api` + `applyAcrossRoomPk` | 同左 |
| `acrossPkType` | `"1"` | `"2"` |
| `acrossRoomId` | `""`（空） | 目标 roomId |
| `pkMinute` | `5` / `10` / `30` | 同左 |
| Tunnel 样例 | `100079102` `_id=VmdPzJ8BR2LVRzbvVZwa`（2026-08-04） | `_id=ZPxoxp8Bpk1mjMPPZg6N` |

单步 MOA（随机匹配）：

```bash
python3 MOA/moa_execute.py --payload-file MOA/templates/跨房PK-随机匹配.json

python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/room/external/room-pk-api \
  --method applyAcrossRoomPk \
  --body-file MOA-generative/templates/example-applyAcrossRoomPk-random-match.body.json \
  --strict 0
```

**配对习惯**：两房几乎同时进入匹配池（工作流内 A 房 apply → 等 1 秒 → B 房 apply）；实测 **13311111112**（room `31668628`）与 **13311111113**（room `50861924`）约 5～60 秒可配成一对。

---

## 4. 阶段 ③④：对话里跑场景 → 补验收（迭代修正）

目标：在 **同一条 Web Agent 对话** 里，用自然语言把一场 PK 从头到尾跑通，并逐轮补上遗漏的前置与断言。

### 4.1 实际对话轮次（原文要点 → 修正了什么）

| 轮次 | 你的消息 | 修正了什么 |
|------|----------|------------|
| C1 | **13311111112/13 随机匹配**跨房 PK，20 秒后 20 账号两房随机送礼，结束 PK | **最小闭环**（提款机计入路径） |
| C2 | **然后**两房间麦上各加 5 机器人 | 补前置：麦上有人 |
| C3 | 送礼给 **麦上随机用户**，随机 **1～1000 钻**；全部送完后 **等 20 秒** 再结束 | 修正对象、金额、时序 |
| C4 | 结束时记录各房 PK、胜负、每用户贡献及 **占房间 PK 占比** | 补 **可读报告** |
| C5 | **把以上能力结合到 PK 提款机测试中** | 临时步骤 → **产品化意图** |
| C6 | 先拉配置 → 造 PK → 送礼 → 记 PK/余额/应得钻 → **再结束** → 校验钻石差值 | 补 **业务验收顺序**（结束前先快照余额） |
| C7 | PK 结束前还要测 **PK 赛况页**：对战信息与 PK 值展示正确；用 **生成式 MOA** 模拟请求（赛况列表接口后续抓包补充） | 补 **结束前 UI 数据层验收**（不等结束 PK 才断言） |
| C8 | PK 结束后测 **提款排名**、**返钻弹窗**、活动页吸底「本周已提款」 | 补 **结束后排名/弹窗/汇总验收** |
| C9 | **再跑一轮** `{总PK}万`，每人随机送礼 `{min}~{max}` 钻 | Web Agent 对话内参数化重跑 + Sheet2 写表 |

### 4.2 场景层推荐首问（模板①）

```text
再跑一轮总PK值{目标总PK}的，要求每个用户随机送礼{最小}到{最大}之间。
```

或完整版：

```text
{手机号A}和{手机号B}同时发起跨房PK随机匹配，
等待20秒后找50个测试账号在两房随机送礼（Rose {最小}~{最大}钻），
全部送完后等待20秒再结束PK；验收总PK达{目标总PK}、返钻与Sheet2写表。
```

**Web Agent 对话内常用取值**（2026-08-07 实测）：

| 参数 | 取值 |
|------|------|
| 账号 | **13311111111 / 13311111115**（或 11112/11113） |
| 目标总 PK | **10 万 / 20 万 / 50 万**（`--target-combined-pk`） |
| 送礼 | 每人随机 **100～1500** 钻 Rose |
| 个人门槛 | **10000 PK**（服务端 `minMemberRewardPk`） |
| PK 时长 | 10 分钟（sheet2 脚本默认） |

### 4.3 增量修正句（最省力，直接复制）

**补送礼规则（C3）**

```text
送礼时给房主（麦上）随机赠送100到1500钻石的Rose礼物，
全部送礼结束后，等待20秒再结束PK。
```

**参数化重跑（C9 · Web Agent 最常用）**

```text
再跑一轮总PK值20万的，要求每个用户随机送礼100到1500之间。
```

（将 `20万` 换成 `10万` / `50万`，送礼区间按需改。）

**补报告字段（C4）**

```text
结束时记录每个房间PK值、胜负、每个送礼用户贡献PK值及占所在房间总PK的占比。
```

**上升为提款机测试（C5）**

```text
把以上能力结合到PK提款机测试中。
```

**完整验收规格（C6，给 Agent 写脚本）**

```text
测试流程先获取服务配置得到整体和个人PK值门槛和返钻比例，
然后创建跨房PK上麦用户，用测试账号进行麦上送礼，
全部完成后记录双方房间总PK值以及每个送礼人各房间PK值，
记录每个人当前钻石余额和计算出的应得钻石数，
最后结束PK，获取每个人的钻石差值，验证是否和应得钻石预期相符。
```

**PK 赛况页验收（C7，结束前 · 生成式 MOA）**

```text
PK结束前还要测试PK赛况页面展示PK中的信息，
房间对战信息和PK值展示正确，用生成式MOA模拟请求测试（后续补充赛况列表接口）。
```

工作流 `pk-atm-test` 已内置（`workflow/scripts/pk_atm_test_run.py`）：

**开启跨房 PK（仅随机匹配）**：脚本 `_begin_random_match_cross_room_pk` 会

1. 清理残留：`closeAcrossRoomPk`（若两房已在 PK）→ 双向 `rejectAcrossRoomPkInvite` → `cancelAcrossRoomPkMatch`（尽力）
2. **两房并行** `applyAcrossRoomPk`（`acrossPkType=1`）
3. **匹配失败**（apply 失败 / 超时）→ 清理 → 重新发起（默认 `--match-retries 5`）
4. **配错房间**（对手 roomId ≠ 期望）→ 立刻 `closeAcrossRoomPk` → 清理 → 重新发起
5. 轮询直到两房互配成功（每轮 `--match-timeout 90`）
6. 报告 `.md` 含 **「随机匹配开启跨房 PK」** 章节（apply ec、pkId、重试轮次）

| 验收层 | MOA | 当前状态 |
|--------|-----|----------|
| **对战信息与 PK 值** | `getAcrossRoomPkInfo`（room-pk-api） | 已映射，**默认必验** |
| **活动页赛况列表** | `across-room-pk-withdraw-v2-api` 等候选 | **待抓包**；测试环境 MSE 可能未注册；默认跳过，加 `--require-pk-situation-list` 可强制 |

结束前验收项（对战 MOA）：

- `stage` 在 PK 中/惩罚阶段（2～3），非准备/已结束
- 双方 `roomId`、房间名/头像与 Admin 解析一致
- `roomRankValue` / `acrossRoomRankValue` 双方视角一致
- 报告 `.tmp/pk_atm_report_<pkId>.md` 含「PK 赛况与对战验收」章节

单步 MOA（调试）：

```bash
python3 MOA-generative/scripts/run_generative_moa.py \
  --url /service/room/external/room-pk-api \
  --method getAcrossRoomPkInfo \
  --body-file MOA-generative/templates/example-getAcrossRoomPkInfo.body.json \
  --strict 0
```

赛况 **列表** tab 待抓包后登记 `MOA-generative/mappings.md`（句式：`抓包13311111113打开PK提款机赛况tab的tunnel，并记录到MOA`）。

**提款排名验收（C8，结束后 · 生成式 MOA）**

```text
PK结束后还要测试PK提款排名，总排名的用户提款钻石数增加正确，排名正确，
所有用户查看吸底钻石数增加正确，PK提款机本周总提款钻石数正确，
用生成式MOA模拟请求测试（后续补充）。
```

| 验收层 | 字段/规则 | 当前状态 |
|--------|-----------|----------|
| **返钻弹窗** | `getAcrossRoomPkRewardDetail` 等 | **已接入** sheet2 脚本；低于个人门槛用户 **不应有弹窗返钻** |
| **活动页吸底 / 本周总提款** | `getAcrossPkRewardRankV2` + 活动页 query | **已接入** sheet2 脚本 |
| **兜底** | 钱包钻石差值 = 预期返钻（仅 **个人 PK≥1 万** 的胜方用户参与瓜分） | 已实现（C6） |

结束 PK **前**快照排名页 → 发钻等待 → **后**再拉 MOA 对比。接口未映射时 MOA 层跳过、不阻断工作流；`--require-withdraw-rank-api` 可强制。

抓包句式：`抓包13311111113打开PK提款机提款排名tab的tunnel，并记录到MOA`

### 4.5 工作流验收全景（C6 → C7 → C8）

`pk-atm-test` 一键脚本内的 **时序**（对话里用 C6/C7/C8 修正句逐轮补全）：

```mermaid
flowchart TD
  A[拉服务配置] --> B[随机匹配跨房 PK]
  B --> C[麦上机器人 + 送礼]
  C --> D[C7 · getAcrossRoomPkInfo<br>结束前赛况/对战/PK值]
  D --> E[快照余额 + 提款排名页 before]
  E --> F[结束 PK]
  F --> G[等发钻 + 快照余额 after]
  G --> H[C6 · 钻石差值 vs 预期返钻<br>胜方且 PK≥1万]
  H --> I[C8 · 弹窗 + 提款排名/吸底/本周总提款]
  I --> K[Sheet2 钉钉写表 + JSON 报告]
```

| 阶段 | 修正句 | MOA / 断言 | 接口状态 |
|------|--------|------------|----------|
| **C6** | 结束前先记余额，结束后再比钻石差值 | 钱包 query_diamond | 已有；**未达 1 万 PK 预期 0** |
| **C7** | PK 结束前测赛况页对战信息与 PK 值 | `getAcrossRoomPkInfo` | **已映射** |
| **C8** | PK 结束后测弹窗、提款排名、吸底、本周总提款 | 弹窗 + `getAcrossPkRewardRankV2` | **sheet2 已验** |
| **C9** | 对话内改总 PK / 送礼区间重跑 | `pk_atm_dingtalk_sheet2_run.py` | **Web Agent 主路径** |

报告章节对应关系：

| 报告章节 | 来源 |
|----------|------|
| 随机匹配开启跨房 PK | 匹配步骤 |
| PK 赛况与对战验收 | C7 |
| 送礼人 PK 与钻石验收 | C6（含个人门槛 1 万） |
| 返钻弹窗 / 提款排名 / 活动页吸底 | C8 |
| **钉钉 Sheet2「测试结果-*」** | `pk_atm_dingtalk_sheet2_run.py` 自动新建 Sheet |

### 4.4 造数时建议写死的参数

| 信息 | 当前推荐取值 | 说明 |
|------|--------------|------|
| 环境 | 测试环境 | 勿混用「线上环境」除非真要 online |
| 房主 A / B | **13311111111 / 13311111115** | 亦可 11112/11113；AI 反查 userId / roomId |
| 匹配方式 | **随机匹配**（`acrossPkType=1`） | 指定邀请不计入提款机 |
| PK 时长 | `--pk-minute 10`（sheet2 默认） | 可选 5/10/30 |
| 送礼 | 50 账号，**100～1500 钻** Rose，打房主（麦上） | 每账号固定绑定一房 |
| 目标总 PK | `--target-combined-pk`：**100000 / 200000 / 500000** | 未达标会自动 top-up 追加送礼 |
| 个人门槛 | **`--personal-pk-threshold 10000`** | 送礼 PK <1 万：**应得 0、实发 0** |
| 等待 | 送礼前 20s；送完 20s；结束后 20s 查钻 | sheet2 默认 |
| 结束方 | 随机选一方 `closeAcrossRoomPk` | **主动结束方记败** |

---

## 5. 阶段 ⑤：沉淀为可复用资产

当你说「结合到 PK 提款机测试」或「整理文档」时，可附加：

```text
请同时：1) 工作流落库并 record  2) 更新 registry  3) 写人读文档  4) 说明如何一键重跑
```

### 5.1 最终产出（给后来者对照）

| 类型 | 路径 |
|------|------|
| **Sheet2 全流程（推荐）** | `workflow/scripts/pk_atm_dingtalk_sheet2_run.py` → 造数 + 弹窗/吸底验收 + 钉钉写表 |
| 一键工作流 | `workflow/workflows/pk-atm-test.json` → `python3 workflow/workflow_execute.py run pk-atm-test` |
| 执行脚本 | `workflow/scripts/pk_atm_test_run.py`（随机匹配开 PK + C6/C7/C8 验收） |
| 默认配置兜底 | `workflow/config/pk_atm_default_config.json`（**个人门槛 10000**、6 档梯度） |
| 测试结果钉钉簿 | [PK提款机-pkAtmConfig / Sheet2 测试结果](https://alidocs.dingtalk.com/i/nodes/oP0MALyR8k7Aow9wCY9wvqBd83bzYmDO) |
| MSE 配置导出 | `platform/dingtalk_gateway/pk_atm_mse_to_workbook.py` |
| 随机匹配 MOA | `MOA/templates/跨房PK-随机匹配.json`、`MOA-generative/templates/example-applyAcrossRoomPk-random-match.body.json` |
| 赛况 MOA 模板 | `MOA-generative/templates/example-getAcrossRoomPkInfo.body.json` |
| MOA 映射表 | `MOA-generative/mappings.md`（已验证 + 待抓包候选） |
| 全量用例 | `temporary_testcase/PK提款机_2.5.9_测试用例.md` |
| PRD 摘要 | `prd-kb/房间PK.md` |
| 工具台 | `python3 platform/open_catalog.py` → 工作流 → **PK提款机-跨房PK造数验收** |

报告：`.tmp/pk_atm_sheet2_<pkId>.json` + 钉钉 Sheet「测试结果-*」。本地亦可能有 `.tmp/pk_atm_report_<pkId>.md`。

---

## 6. 怎么提问：好 vs 差

| 差 | 好 | 原因 |
|----|-----|------|
| 帮我测 PK 提款机 | **再跑一轮总PK值20万的，每人随机送礼100到1500** | 参数完整、可直跑 sheet2 |
| 写个自动化脚本 | 把以上能力结合到 PK 提款机测试中 | 先有对话内跑通 |
| 送礼测一下 | 100～1500 钻 Rose，50 账号，目标总 PK 20 万 | 缺账号/验收 |
| 查为什么没发奖 | 记录应得钻和实际钻石差值，验证是否相符 | 给可执行断言 |
| 一次录所有 PK 接口 | 13311111113 结束 PK，抓包并记录 MOA | 单接口易验收 |

### 每轮消息建议携带

| 信息 | 必填？ | 示例 |
|------|--------|------|
| 账号 | 造数必填 | **13311111111 / 13311111115** |
| 目标总 PK | 强建议 | **10 万 / 20 万 / 50 万** |
| 送礼区间 | 强建议 | **100～1500 钻** |
| 个人门槛 | 以服务端为准 | **10000 PK** |
| 验收 | 写脚本时必填 | 总 PK、下发总钻、应得/实发、弹窗、吸底 |

---

## 7. Web Agent / Cursor 协作

### 7.1 本次会话配置

```text
外部 Agent：服务端 Agent
未勾选 MDP Agent
batch_key=web:fe0181e7b6ce418e
```

| 选项 | 建议 | 说明 |
|------|------|------|
| **服务端 Agent** | 本场景首选 | 查 room-pk-api / `applyAcrossRoomPk` 等 **后端实现**；Token 配在 `platform/dingtalk_gateway/.env.local` 的 `YAAHLAN_SERVICE_AGENT_TOKEN` |
| MDP Agent | 非必须 | 偏客户端协议 |
| **延续当前对话** | 强建议 | C2～C8 修正句依赖前文 |

勾选服务端 Agent 后，Web Agent 调用 `service_agent_query.py` 时，对话区会显示 **「服务端 Agent 查询中（已 N 秒）…」** 进度行（与「已收到 / 执行中 / 已用时」同区）。

### 7.2 何时延续 vs 新开

| 场景 | 建议 |
|------|------|
| 修正送礼规则、补报告字段、补赛况/排名验收 | **延续**同一 batch |
| 全新无关功能 | 新对话 |
| 工作流已落库，只需重跑 | 「执行工作流 pk-atm-test」或直跑命令 |

### 7.3 人审节点（你自己过一眼）

1. **随机匹配 vs 指定邀请**：提款机必须随机匹配（`acrossPkType=1`）  
2. **梯度命中**：总 PK **≥ 阈值取最高档**；3% = 送礼钻的 3% = 总 PK 的 0.3%  
3. **场次门槛**：alpha MSE **2 万**；PRD 50 万  
4. **个人门槛**：服务端 **1 万 PK**；**未达标胜方用户不应发钻**  
5. **主动结束记败**：结束 PK 的一方为败方  
6. **弹窗 / 吸底**：sheet2 脚本默认验收；低于 1 万 PK 跳过弹窗比对、只验实发=0  

---

## 8. 半天复制路径（按顺序对 AI 说）

1. `读取2.5.9版本prd，生成知识库`  
2. `生成2.5.9 PK提款机全量测试用例`  
3. `抓包13311111113发起跨房PK随机匹配并记录MOA`（结束 PK 抓包一次）  
4. 粘贴 **§4.2 模板①**（两号**随机匹配**），跑通一场  
5. 粘贴 **§4.3 的 C3、C4 修正句**  
6. `把以上能力结合到PK提款机测试中`  
7. 粘贴 **§4.3 的 C6 完整验收句**  
8. 粘贴 **§4.3 的 C7 赛况页验收句**（生成式 MOA · 结束前）  
9. 粘贴 **§4.3 的 C8 提款排名验收句**（生成式 MOA · 结束后）  
10. `把从零分析需求、提供MOA、搭建自动化的过程整理成学习文档`  

验证（**Web Agent 推荐 · Sheet2 全流程**）：

```bash
# 20 万总 PK · 100~1500 钻
python3 workflow/scripts/pk_atm_dingtalk_sheet2_run.py \
  --phone-a 13311111111 --phone-b 13311111115 \
  --target-combined-pk 200000 \
  --gift-min-diamonds 100 --gift-max-diamonds 1500 \
  --gift-count 50 --personal-pk-threshold 10000

# 50 万总 PK（命中 4% 档）
python3 workflow/scripts/pk_atm_dingtalk_sheet2_run.py \
  --target-combined-pk 500000 \
  --gift-min-diamonds 100 --gift-max-diamonds 1500 \
  --personal-pk-threshold 10000

# 10 万总 PK
python3 workflow/scripts/pk_atm_dingtalk_sheet2_run.py \
  --target-combined-pk 100000 \
  --gift-min-diamonds 100 --gift-max-diamonds 1500 \
  --personal-pk-threshold 10000
```

工作流入口：

```bash
python3 workflow/workflow_execute.py run pk-atm-test \
  --phone-a 13311111111 --phone-b 13311111115 \
  --target-combined-pk 200000 \
  --gift-min-diamonds 100 --gift-max-diamonds 1500 \
  --personal-pk-threshold 10000
```

冲 alpha 场次门槛（2 万即达标）：

```bash
python3 workflow/scripts/pk_atm_dingtalk_sheet2_run.py \
  --target-combined-pk 20000 \
  --gift-min-diamonds 100 --gift-max-diamonds 500 \
  --personal-pk-threshold 10000
```

---

## 9. 过程里常见的坑（与怎么问才能避开）

| 现象 | 过程上怎么处理 |
|------|----------------|
| 指定邀请 ec=20210111 | 改 **随机匹配**；工作流会先清理 pending 再 apply |
| 随机匹配长时间不配 | 加大 `--match-timeout` / `--match-retries`；确认两房并行 apply；换空闲测试号 |
| 配到其他房间 | 脚本自动 `closeAcrossRoomPk` 后重试；报告会记 wrongMatch 轮次 |
| 服务端 Agent 401 | 更新 `YAAHLAN_SERVICE_AGENT_TOKEN`（浏览器登录 ai-yaahlan 后复制 Bearer） |
| 送礼了但 PK 不涨 | 修正句强调「送给 **麦上** 用户」+「等 20 秒」 |
| 预期返钻全是 0 | 对照 §2.4：**个人 PK 是否 ≥1 万**、是否胜方、是否主动结束记败 |
| 下发总钻与配置不符 | 检查梯度是否按 **≥ 阈值最高档** 命中；3% 档总 PK 0.3% |
| 低于 1 万 PK 仍发钻 | **缺陷**；sheet2 会标「个人PK未达门槛不应发钻」 |
| 小奖池实发略高于 floor 公式 | 低总 PK 场偶发；弹窗与实发一致时以 **弹窗/实发** 为准，可问服务端 Agent 取整规则 |
| 配置接口 / 报告快照滞后 | 以 `pk_atm_default_config.json` 为准（**个人门槛 10000**）；重写 Sheet 用 `--from-report --rewrite-only` |

---

## 10. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-08-03 | 初版：整合造数流程与工作流 |
| 2026-08-03 | 重构：以「从零 → MOA → 自动化」过程为主，实现细节下沉至代码 |
| 2026-08-04 | C7：PK 结束前生成式 MOA 验收赛况/对战信息与 PK 值；赛况列表接口待抓包 |
| 2026-08-04 | C8：PK 结束后提款排名/吸底/本周总提款 MOA 验收框架；排名 tab 接口待抓包 |
| 2026-08-04 | 工作流改为 **随机匹配开 PK**（清理→双房 apply→轮询配对）；新增 `--pk-minute` |
| 2026-08-04 | MOA：随机匹配模板 + Tunnel `_id=VmdPzJ8BR2LVRzbvVZwa`；实测 13311111112/13 可配对 |
| 2026-08-04 | Web Agent：服务端 Agent 查询进度展示；Token 配置说明 |
| 2026-08-07 | §2.4：MSE alpha `pkAtmConfig` 入文档（门槛 2 万 / 个人 1 千 / 6 档梯度）；钉钉单表导出命令 |
| 2026-08-07 | 随机匹配：失败/配错房间自动重试（并行 apply + close 错配 + `--match-retries`） |
| 2026-08-07 | **Sheet2 全流程** `pk_atm_dingtalk_sheet2_run.py`；弹窗 + 吸底验收；Web Agent 参数化重跑 C9 |
| 2026-08-07 | **梯度匹配修正**：总 PK **≥ 阈值取最高档**；返钻 3% = 总 PK×0.3% |
| 2026-08-07 | **个人门槛以服务端为准：10000 PK**；未达标胜方用户应得/实发均为 0 |
| 2026-08-07 | 实测账号 11111/11115；目标总 PK 10万/20万/50万 + 送礼 100~1500 钻 |
