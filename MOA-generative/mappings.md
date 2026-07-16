# HTTP ↔ MOA 已验证对照

> 仅记录在测试环境（alpha / stage）用质量平台 httpproxy **实测通过**的映射。新接口验证后请按表追加一行。

| 日期 | HTTP 路径 | MOA `url` | `method` | 备注 |
|------|-----------|-----------|----------|------|
| 2026-07-14 | `/yaahlan/sign/signIn` | `/service/yaahlan-trick/external/app-task` | `signIn` | `signin` 会 Method not found；须 header+params 双写 |
| 2026-07-14 | `/yaahlan/feed-interact/likeContent` | `/service/feed/external/feed-interact-stage` | `likeContent` | body 含 `action=LIKE_FEED`、`contentId`；列表页会换帖，赞的是当时抓包里的那批评 |
| 2026-07-15 | `/yaahlan/user/intimate/acceptIntimateInvitation` | `/service/yaahlan/user/intimate-api` | `acceptIntimateInvitation` | body：`userId`（接受方）、`intimateId`（小-大）、`relationshipType`（2=挚友）；已同意再调常见业务失败/Network error，可先 `intimateDismiss` |
| 2026-07-15 | `/yaahlan/user/intimate/intimateDismiss` | `/service/yaahlan/user/intimate-api` | `intimateDismiss` | 解除亲密关系；同 ServiceUrl |
| 2026-07-15 | `/yaahlan/user/intimate/intimateInvitationInfo` | `/service/yaahlan/user/intimate-api` | `intimateInvitationInfo` | 查申请状态 |
| 2026-07-15 | `/yaahlan/user/intimate/intimateHomePage` | `/service/yaahlan/user/intimate-api` | `intimateHomePage` | 关系主页；无关系时 ec=404 |
| 2026-07-15 | `/yaahlan/room/member/apply` | `/service/room/external/room-member-stage` | `apply` | body：`userId`（申请人）、`roomId`；Tunnel 未录到 apply 包，body 由 agree 抓包推断，MOA 实测 ec=200 |
| 2026-07-15 | `/yaahlan/room/member/agree` | `/service/room/external/room-member-stage` | `agree` | body：`userId`（房主）、`roomId`、`remoteId`（申请人）；已加入再调 ec=20210111 |

## 配套 HTTP（非 MOA，仅对照）

| HTTP | 用途 |
|------|------|
| `/yaahlan/sign/signInList` | 签到页/列表 |
| `/yaahlan/feed-list/listUserFeed` | 个人动态列表（取 contentId） |
| `/yaahlan/feed-list/listFollowFeedV2` | 关注流动态列表 |
| `/yaahlan/v2/gift/send`（`ext.intimate_invite_gift=1`） | **发起**亲密申请：用 `Gift/gift_execute.py --intimate-invite`，不走生成式 MOA |

## 调用链辅助线索

客户端点赞时下游可能还有 `content-platform-yaahlan` 的 `likeContext` / `queryPost`；主入口仍是 `feed-interact-stage` + `likeContent`。单独调 `likeContext` 缺 BusinessLine 会失败，不作为首要生成目标。

亲密关系：`intimate-api` 同服务挂多个 method；发起靠 Gift HTTP，同意/解除/查询走 MOA。

## 结挚友 / 结CP 一键（已入库工作流）

```bash
# 挚友 relationshipType=2，默认 gift 2005007129
python3 workflow/workflow_execute.py run intimate-buddy-form \
  --from-user-id <发起方> \
  --to-user-id <接受方>

# CP relationshipType=1，默认 gift 2005006943
python3 workflow/workflow_execute.py run intimate-cp-form \
  --from-user-id <发起方> \
  --to-user-id <接受方>
```

脚本等价：`python3 MOA-generative/scripts/form_intimate_pair.py --from-user ... --to-user ... [--relationship-type 1|2]`

## 快速添加房间成员（已入库工作流）

```bash
python3 workflow/workflow_execute.py run room-member-quick-add-form \
  --applicant-user-id <申请人userId> \
  --owner-user-id <房主userId> \
  --room-id <roomId>
```

脚本等价：`python3 MOA-generative/scripts/form_room_member_quick_add.py --applicant-user ... --owner-user ... --room-id ...`

单步 MOA（生成式）：

```bash
# 申请
python3 MOA-generative/scripts/run_generative_moa.py \
  --url /service/room/external/room-member-stage \
  --method apply \
  --body-file MOA-generative/templates/example-room-member-apply.body.json \
  --strict 1

# 同意
python3 MOA-generative/scripts/run_generative_moa.py \
  --url /service/room/external/room-member-stage \
  --method agree \
  --body-file MOA-generative/templates/example-room-member-agree.body.json \
  --strict 0
```
