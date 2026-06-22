# prd-kb · 产品需求知识库

> **文档类型**：按业务模块整理的产品需求要点（非逐篇 PRD 文档）
> **来源目录**：[产品需求文档](https://alidocs.dingtalk.com/i/nodes/14lgGw3P8vveoPlPC2PdN56v85daZ90D)
> **最近整理**：2026-06-22 16:44:04 +0800

与 `testcase-kb/`（验收要点）互补：本目录保留**产品侧需求规则与业务逻辑**，供 `prd-review`、用例生成前理解需求。
「待排期需求」不纳入知识库。

## 同步与整理

```bash
python3 DingTalk/prd_sync_execute.py --folder-id yaahlan-prd
python3 scripts/prd_kb_build.py --input-dir prd-kb/.raw --output-dir prd-kb
```

## 统计

| 指标 | 值 |
|------|-----|
| 模块文件 | 10 |
| 来源 PRD 篇数 | 1 |

## 模块索引

| 模块 | 文件 |
|------|------|
| 充值提现转账 | [`充值提现转账.md`](充值提现转账.md) |
| 公会 | [`公会.md`](公会.md) |
| 其他 | [`其他.md`](其他.md) |
| 客服 | [`客服.md`](客服.md) |
| 家族 | [`家族.md`](家族.md) |
| 注册登录 | [`注册登录.md`](注册登录.md) |
| 消息 | [`消息.md`](消息.md) |
| 游戏 | [`游戏.md`](游戏.md) |
| 特权VIP | [`特权VIP.md`](特权VIP.md) |
| 超管 | [`超管.md`](超管.md) |

## 已排除

- 待排期需求
