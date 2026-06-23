# Gift · Stage HTTP 送礼

测试环境直连 `yaahlan-web` 的 `/v2/gift/send`，覆盖房间内、私聊、群组、全房送礼。

## 快速开始

```bash
cp Gift/.env.example Gift/.env.local
# 编辑 Gift/.env.local 填入 CMDB_TOKEN

python3 Gift/gift_execute.py \
  --scene chatroom --sender 8250 --receivers 100465989 \
  --gift-id 2005004730 --scene-id 38826842
```

## 与 MOA 背包

| 能力 | 入口 | 说明 |
|------|------|------|
| HTTP 送礼 | `Gift/gift_execute.py` | 直连 `/v2/gift/send`，收礼方到账 |
| 背包下发 | `MOA/moa_execute.py --package-gift-*` | 仅备货，不触发真实送礼 |
| UI 验收 | ADB macro + Tunnel | 客户端流程验证 |

详见 `Gift/使用方法.md`（自动生成）与 `.cursor/skills/stage-gift-send/SKILL.md`。
