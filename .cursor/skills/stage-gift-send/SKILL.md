---
name: stage-gift-send
description: 在测试环境一键执行 yaahlan-web 送礼 HTTP 测试（/v2/gift/send）。通过 Gift/gift_execute.py 自动查实例 IP、MOA 查礼物与用户设备并发送。支持房间内、私聊、群组、全房间送礼。Use when the user asks for 测试环境送礼、stage 送礼、gift send test、/v2/gift/send、房间内送礼、群组送礼、私聊送礼。
---

# Stage 测试环境送礼

**环境固定 Stage（alpha/stage）**。唯一入口：

```bash
python3 Gift/gift_execute.py \
  --scene <chatroom|private|group> \
  --sender <送礼人> \
  --receivers <收礼人,逗号分隔> \
  --gift-id <礼物productId> \
  [--scene-id <roomId|groupId>] \
  [--num 1] \
  [--package-id 12321312] \
  [--send-room-all] \
  [--dry-run] \
  [--probe]
```

鉴权：`CMDB_TOKEN` 可选（`Gift/.env.local` 覆盖）；未配置时使用内置 fallback。

## Agent 工作流（2 步）

1. **解析参数**：从用户消息提取场景、送礼人、收礼人、giftId、num（默认 1）、sceneId
2. **执行脚本**：一条命令跑完，将 stdout JSON 原样呈现给用户

**禁止**：
- AskQuestion 中间确认
- 拆成多次 MCP `queryMoaService_Stage` 逐步编排
- 未跑脚本就手写 curl

用户说「只 dry-run / 只探测」时加 `--dry-run` 或 `--probe`；否则默认直接 POST 送礼。

## 参数映射

| 用户说法 | CLI |
|----------|-----|
| 房间内 / 语音房 / chatroom | `--scene chatroom --scene-id <roomId>` |
| 群组 / group | `--scene group --scene-id <groupId>` |
| 私聊 / IM | `--scene private`（无需 scene-id） |
| 亲密关系申请送礼 | `--scene private --intimate-invite`（`ext.intimate_invite_gift=1`） |
| 结挚友闭环（发起+同意） | 工作流 `intimate-buddy-form` |
| 结CP闭环（发起+同意） | 工作流 `intimate-cp-form`（`relationshipType=1`，默认 gift `2005004592` Neon Heart） |
| 送礼人 / sender | `--sender` |
| 收礼人 / receivers | `--receivers uid1,uid2` |
| 礼物 id | `--gift-id` |
| 数量 | `--num`（默认 1） |
| 全房间送礼 / send room all | `--send-room-all`（仅 chatroom，自动获取 snapId，无需 receivers） |

## 脚本内部（无需 Agent 逐步执行）

```
CMDB 查 instance_ip → MOA 查礼物 → MOA 查用户设备 → 组装 body → POST /v2/gift/send
```

详见 [reference.md](reference.md)。

## 输出解读

脚本 stdout 为 JSON：

| 字段 | 含义 |
|------|------|
| `ok` | 是否成功 |
| `step` / `error` | 失败步骤与原因 |
| `instance_ip` | yaahlan-web 实例 |
| `gift_meta` | category / giftType / isPackage 等 |
| `user_device` | ua / deviceId / osType / lang |
| `request` | 实际发送 body |
| `response` | WebResponse（ec/em/data） |
| `snap` | 全房间送礼时的快照信息（snapId / recvCnt / needDiamonds） |

`response.ec != 0` 时读 `response.em` 排查（余额不足、礼物不存在等）。

## CP 爱意值造数（私聊送礼 · Rose）

**无直改 MOA**；面板礼物 **1 钻 = 1 爱意值**。

| 项 | 值 |
|---|---|
| 默认礼物 | **Rose** · `2005000233`（Gift Tab，**1 钻**，面板名 **Rose**） |
| 禁止 | `roses` 系列（`2005001776`/`2005001778`/`2005001774`）、`2005004730` |

1. **先规划**：
   ```bash
   python3 Gift/scripts/plan_cp_love_gift.py --delta <爱意值增量>
   ```
2. **执行**（Rose 1 钻：`--num` = 爱意值增量，**1 次 HTTP**）：
   ```bash
   python3 Gift/gift_execute.py --scene private --sender <uid> --receivers <cpUid> \
     --gift-id 2005000233 --num <规划num>
   ```
3. 段后查 `form_cp_love_chest_homepage.py` 验收。

**示例（50 万增量）**：`--gift-id 2005000233 --num 500000`（1 次 HTTP）。

配置：`Gift/config/cp_love_gift.json`

## 与 MOA 背包 / ADB 的分工

| 路径 | 何时用 |
|------|--------|
| **Gift/gift_execute.py** | 快速接口级送礼、多场景批量 |
| **MOA 背包下发** | 仅给 sender 备货，不验收到账 |
| **ADB + Tunnel** | 客户端 UI 流程、背包面板送出验收 |

## 示例

**房间内送礼：**

```bash
python3 Gift/gift_execute.py \
  --scene chatroom --sender 8250 --receivers 100465989,100007541 \
  --gift-id 2005004730 --scene-id 38826842 --num 1
```

**私聊送礼：**

```bash
python3 Gift/gift_execute.py \
  --scene private --sender 8250 --receivers 100465989 \
  --gift-id 2005004730
```

**全房间送礼：**

```bash
python3 Gift/gift_execute.py \
  --scene chatroom --sender 8250 --gift-id 2005004730 \
  --scene-id 38826842 --num 1 --send-room-all
```

## 附加资源

- 固定常量、Probe 响应结构、ext 模板：[reference.md](reference.md)
- 工具台登记：`Gift/config/registry.json`
