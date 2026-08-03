# HTTP ↔ MOA 已验证对照

> 仅记录在测试环境（alpha / stage）用质量平台 httpproxy **实测通过**的映射。新接口验证后请按表追加一行。

| 日期 | HTTP 路径 | MOA `url` | `method` | 备注 |
|------|-----------|-----------|----------|------|
| 2026-07-14 | `/yaahlan/sign/signIn` | `/service/yaahlan-trick/external/app-task` | `signIn` | `signin` 会 Method not found；须 header+params 双写 |
| 2026-07-14 | `/yaahlan/feed-interact/likeContent` | `/service/feed/external/feed-interact-stage` | `likeContent` | body 含 `action=LIKE_FEED`、`contentId`；列表页会换帖，赞的是当时抓包里的那批评 |
| 2026-07-15 | `/yaahlan/user/intimate/acceptIntimateInvitation` | `/service/yaahlan/user/intimate-api` | `acceptIntimateInvitation` | body：`userId`（接受方）、`intimateId`（小-大）、`relationshipType`（2=挚友）；已同意再调常见业务失败/Network error，可先 `intimateDismiss` |
| 2026-07-15 | `/yaahlan/user/intimate/intimateDismiss` | `/service/yaahlan/user/intimate-api` | `intimateDismiss` | 解除亲密关系；同 ServiceUrl |
| 2026-07-15 | `/yaahlan/user/intimate/intimateInvitationInfo` | `/service/yaahlan/user/intimate-api` | `intimateInvitationInfo` | 查申请状态 |
| 2026-07-15 | `/yaahlan/user/intimate/intimateHomePage` | `/service/yaahlan/user/intimate-api` | `intimateHomePage` | CP/挚友空间主页；body 需 `userId`、`intimateId`、`relationshipType`；返回 `cpMedalTab.list`（CP 勋章：medalName/num/obtainTime/imageUrl/dynamicImageUrl）、`intimateInfo` 等；无关系 ec=404；MOA 实测 `100486375`（13311111112） |
| 2026-07-15 | `/yaahlan/room/member/apply` | `/service/room/external/room-member-stage` | `apply` | body：`userId`（申请人）、`roomId`；Tunnel 未录到 apply 包，body 由 agree 抓包推断，MOA 实测 ec=200 |
| 2026-07-15 | `/yaahlan/room/member/agree` | `/service/room/external/room-member-stage` | `agree` | body：`userId`（房主）、`roomId`、`remoteId`（申请人）；已加入再调 ec=20210111 |
| 2026-08-03 | `/yaahlan/room/acrossRoomPk/applyAcrossRoomPk` | `/service/room/external/room-pk-api` | `applyAcrossRoomPk` | body：`userId`、`roomId`（发起方）、`acrossRoomId`（目标）、`acrossPkType`（2=指定邀请）、`pkMinute`（5/10/30）、`hostSeat`（0=无主持人位）；Tunnel `100079102` `_id=ZPxoxp8Bpk1mjMPPZg6N`；MOA 实测 ec=200 |
| 2026-08-03 | `/yaahlan/room/acrossRoomPk/acceptAcrossRoomPkInvite` | `/service/room/external/room-pk-api` | `acceptAcrossRoomPkInvite` | body：`userId`、`roomId`（被邀请方）、`acrossRoomId`（发起方）、`inviteId`；Tunnel `100006869` `_id=_QBtxp8Bpk1mjMPPugzU`；MOA 代理调通；重放需有效 inviteId |
| 2026-08-03 | `/yaahlan/room/acrossRoomPk/closeAcrossRoomPk` | `/service/room/external/room-pk-api` | `closeAcrossRoomPk` | body：`userId`、`roomId`、`acrossRoomId`（对方房间）、`acrossRoomPkId`（当前 PK 场次）；Tunnel `100079102` `_id=jANzxp8Bpk1mjMPPm_ig`；MOA 实测 ec=200 |
| 2026-07-16 | `/yaahlan/vas/familyPk/getFamilyPkPage` | `/service/vas/activity/family-pk-v2-api` | `getFamilyPkPage` | body：`userId`/`uid`、`date`（tab 日期）、`area`；返回 `pkList`/`current`/`tierList`。旧版 `family-pk` + `home` 仅活动入口摘要，非本页 |
| 2026-07-16 | `/yaahlan/vas/familyPk/getFamilyPkUserList` | `/service/vas/activity/family-pk-v2-api` | `getFamilyPkUserList` | body：`userId`、`familyId`、`date`、`limit`、`offset`；点击贡献 top3 头像弹窗；返回 `memberList`/`userInfo`/`hasNext` |
| 2026-07-17 | `/yaahlan/component/giftPanel/getGiftTabListV3` | `/service/yh-components/gift-panel` | `getGiftTabListV3` | MOA Redis 直连 + httpproxy；背包 Tab 读 `package.remain`；无需打开礼物面板 |
| 2026-07-17 | `/yaahlan/component/giftPanel/propPackageList` | `/service/yh-components/gift-panel` | `propPackageList` | 背包道具列表；与 getGiftTabListV3 背包 Tab 礼物不同 |
| 2026-07-17 | `/yaahlan/feed-comment/publishComment` | `/service/feed/external/feed-comment-stage` | `publishComment` | body：`userId`/`uid`、`feedId`、`content`、`source`（discover）；返回 `commentId`；100 账号批量评论已验证 |
| 2026-07-27 | `/yaahlan/components/wallet/diamondHistory` | `/service/yaahlan/components/wallet-api` | `diamondHistory` | 钱包钻石记录页；Tunnel `100007541` `_id=QuvEop8Bpk1mjMPP3A5W`；`data.list[]` 含 `desc`/`rechargeMethod`/`diamondDiff`/`createTime`/`balance` |
| 2026-07-27 | `/yaahlan/userProfile/nameplatePageData` | （Tunnel 抓包；gw-api 需 SESSIONID） | — | 铭牌页；Tunnel `100486375` `_id=rBgAo58Bpk1mjMPP_JqB`；`data.unlockedNameplates[]`/`lockedNameplates[]`（`id`/`unlockTime`/`remainTime`/`wearState`）；CP 宝箱 sweet CP **1138** |
| 2026-07-28 | `/yaahlan/trick/cpLoveChest/getCpLoveChestHomepage` | `/service/yaahlan-trick/external/cp-love-chest` | `getCpLoveChestHomepage` | params=`userId`,`cpUserId`；读 `data.currentLoveValue`（15天周期爱意值）；**不是** cp-moa loveValue |
| 2026-07-28 | （MOA 后门） | `/service/yaahlan/user/cp-moa` | `addCpLoveValue` | params=`userId`,`remoteId`,`value`(long)；**CP 总恩爱值 loveValue**；须已有 CP；**不更新**宝箱 currentLoveValue |
| 2026-07-28 | （MOA 后门） | `/service/vas/external/cp-stage` | `addCpFerrisWheelValue` | params=`userId1`,`userId2`,`value`(long)；摩天轮活动期周期榜；**不是**宝箱 currentLoveValue |

## 配套 HTTP（非 MOA，仅对照）

| HTTP | 用途 |
|------|------|
| `/yaahlan/sign/signInList` | 签到页/列表 |
| `/yaahlan/feed-list/listUserFeed` | 个人动态列表（取 contentId） |
| `/yaahlan/feed-list/listFollowFeedV2` | 关注流动态列表 |
| `/yaahlan/v2/gift/send`（`ext.intimate_invite_gift=1`） | **发起**亲密申请：用 `Gift/gift_execute.py --intimate-invite`，不走生成式 MOA |
| `/yaahlan/trick/cpLoveChest/getCpLoveChestHomepage` | 打开 CP 爱意宝箱主页；读 `data.currentLoveValue`（15天周期爱意值；**≠** cp-moa loveValue） |
| `/yaahlan/components/wallet/diamondHistory` | 钱包钻石记录页；读 `data.list[]`（`diamondDiff`/`desc`/`rechargeMethod`/`createTime`） |
| `/yaahlan/userProfile/nameplatePageData` | 铭牌页；读 `data.unlockedNameplates[]` / `lockedNameplates[]`；**Tunnel 自动读取 + `.tmp/nameplate_cache/` 缓存兜底**（`form_nameplate_page.py`） |
| `/yaahlan/user/intimate/intimateHomePage` | 打开 CP 空间页；读 `data.cpMedalTab.list`（CP 勋章列表） |

## 调用链辅助线索

客户端点赞时下游可能还有 `content-platform-yaahlan` 的 `likeContext` / `queryPost`；主入口仍是 `feed-interact-stage` + `likeContent`。单独调 `likeContext` 缺 BusinessLine 会失败，不作为首要生成目标。

亲密关系：`intimate-api` 同服务挂多个 method；发起靠 Gift HTTP，同意/解除/查询走 MOA。

## 结挚友 / 结CP 一键（已入库工作流）

```bash
# 挚友 relationshipType=2，默认 gift 2005007129
python3 workflow/workflow_execute.py run intimate-buddy-form \
  --from-user-id <发起方> \
  --to-user-id <接受方>

# CP relationshipType=1，默认 gift 2005004592（Neon Heart，cpGiftList 1500钻）
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
