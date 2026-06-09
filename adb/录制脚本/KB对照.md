# 知识库 ↔ 录制脚本对照

片段目录按 **testcase-kb** 模块划分（与 `testcase-kb/*.md` 文件名一致）。

**默认登录**（`loginDefaults`）：+86 / 13311111115 / 000000。
**测试账号**：guildLeader 13311111111、familyLeader 13311111112（见 `索引.json` → `testAccounts`）。

## 通用 · `片段/通用/`

| 脚本 | id |
|------|-----|
| CharmPK横幅收起拖走 | dismiss-charm-pk-banner |

## 注册登录 · `片段/注册登录/`

| 脚本 | id |
|------|-----|
| 关闭Me页弹窗 | dismiss-me-popups |
| 关闭常见弹窗 | dismiss-common-popups |
| 关闭签到弹窗 | dismiss-sign-in-popup |
| 冷启动回首页 | cold-start-home |
| 启动Yaahlan | launch-yaahlan |
| 完成注册 | register-profile |
| 手机号登录 | login-phone-full |
| 注销账号 | cancel-account |
| 登录-勾选协议打开手机 | login-agree-phone |
| 登录-手机号发短信 | login-phone-sms |
| 登录-语言下一步 | login-lang-next |
| 登录-输入验证码 | login-verify-code |
| 登录后关闭弹窗 | login-dismiss-popup |
| 登录后处理弹窗 | login-post-popups |
| 设置页切换语言 | settings-switch-language |
| 设置页切换语言阿语 | settings-switch-language-ar |
| 设置页清除缓存 | settings-clear-cache |
| 设置页进入关于 | settings-about |
| 设置页进入游戏支持 | settings-game-support |
| 设置页进入语言 | settings-language |
| 设置页进入账号管理 | settings-account-management |
| 设置页进入通知 | settings-notifications |
| 设置页进入隐身设置 | settings-stealth |
| 设置页进入黑名单 | settings-blacklist |
| 设置页退出登录 | logout-from-settings |
| 跳过开屏广告 | dismiss-splash-ad |
| 进入设置 | settings |
| 退出登录 | logout |
| 验收开屏广告 | verify-splash-ad |

## 游戏 · `片段/游戏/`

| 脚本 | id |
|------|-----|
| 切换游戏底栏 | game-tab |
| 游戏帧CasualGamesMore | game-casual-more |
| 游戏帧进入Domino | game-enter-domino |
| 游戏帧进入Ludo | game-enter-ludo |
| 游戏帧进入OnlinePlayer聊天 | game-enter-online-player-chat |
| 游戏帧进入SnakesLadders | game-enter-snakes-ladders |
| 游戏帧进入WorldCup | game-enter-world-cup |
| 游戏帧进入任务礼包 | game-enter-task-pack |
| 游戏帧进入游戏列表 | game-enter-game-list |

## 房间 · `片段/房间/`

| 脚本 | id |
|------|-----|
| 关闭网络诊断弹窗 | room-dismiss-network-diagnostic |
| 切换房间底栏 | room-tab |
| 我的页进入MyRoom | me-enter-my-room |
| 房内三方游戏最小化 | room-minimize-third-party-game |
| 房间帧Mine切换Family | room-mine-family |
| 房间帧Mine切换Follow | room-mine-follow |
| 房间帧Mine切换Joined | room-mine-joined |
| 房间帧Mine切换Viewed | room-mine-viewed |
| 房间帧切换Chat分类 | room-chat-chip |
| 房间帧切换EgyptTab | room-egypt-tab |
| 房间帧切换Game分类 | room-game-chip |
| 房间帧切换Hot分类 | room-hot-chip |
| 房间帧切换MineTab | room-mine-tab |
| 房间帧创建菜单进入MyVoiceRoom | room-create-my-voice-room |
| 房间帧打开创建房间菜单 | room-open-create-menu |
| 房间帧打开搜索页 | room-open-search |
| 房间帧点击首个房间卡片 | room-tap-first-card |
| 拒绝Mic邀请 | room-reject-mic-invitation |
| 搜索进房 | room-search-enter |
| 搜索页返回房间帧 | room-search-back |
| 游戏帧OnlinePlayerVisit进房 | game-enter-visit-room |
| 退出房间 | room-exit |

## 房间PK · `片段/房间PK/`

| 脚本 | id |
|------|-----|
| 房间帧切换PK分类 | room-pk-chip |

## 礼物 · `片段/礼物/`

| 脚本 | id |
|------|-----|
| 打开礼物面板 | open-gift-panel |
| 礼物面板送Trophy | gift-panel-send-trophy |

## 消息 · `片段/消息/`

| 脚本 | id |
|------|-----|
| 切换消息底栏 | msg-tab |
| 消息帧TasksSayHi | msg-tasks-say-hi |
| 消息帧Tasks切换Acquire | msg-tasks-acquire |
| 消息帧Tasks切换Ongoing | msg-tasks-ongoing |
| 消息帧Transfer空态刷新 | msg-transfer-refresh |
| 消息帧切换EveryoneTab | msg-everyone-tab |
| 消息帧切换FriendsTab | msg-friends-tab |
| 消息帧切换TasksTab | msg-tasks-tab |
| 消息帧切换TransferTab | msg-transfer-tab |
| 消息帧进入DailyTaskRewards | msg-daily-task-rewards |

## 动态 · `片段/动态/`

| 脚本 | id |
|------|-----|
| 切换动态关注tab | moment-follow-tab |
| 切换动态底栏 | moment-tab |
| 动态帧Discover进入动态详情 | moment-discover-feed-detail |
| 动态帧Discover进入话题详情 | moment-discover-topic-detail |
| 动态帧Follow进入动态详情 | moment-follow-feed-detail |
| 动态帧切换DiscoverTab | moment-discover-tab |
| 动态帧话题切换MostLikedTab | moment-topic-most-liked-tab |
| 动态帧话题切换PopularTab | moment-topic-popular-tab |
| 动态帧进入TopicsMore | moment-topics-more |
| 动态帧进入动态详情 | moment-enter-feed-detail |
| 动态帧进入话题详情 | moment-enter-topic-detail |
| 发布图片动态 | post-image-moment |
| 发布纯文本动态 | post-moment |
| 发布视频动态 | post-video-moment |
| 打开动态发布页 | open-moment-compose |
| 进入我的动态列表 | my-moments-list |

## 个人主页 · `片段/个人主页/`

| 脚本 | id |
|------|-----|
| 切换我的底栏 | me-tab |
| 我的页下滑浏览 | me-scroll-lower-menu |
| 我的页进入Badge | me-enter-badge |
| 我的页进入InviteFriends | me-enter-invite-friends |
| 我的页进入个人资料详情 | my-profile-from-me |
| 游戏帧进入个人资料 | game-profile |
| 资料页HonorTab下滑浏览 | profile-honor-tab-scroll |
| 资料页ProfileTab下滑浏览 | profile-scroll-profile-tab |
| 资料页切换HonorTab | profile-honor-tab |
| 资料页切换RelationshipTab | profile-relationship-tab |
| 资料页打开发布动态 | profile-open-moment-compose |
| 资料页进入VoiceRoom | profile-enter-voice-room |
| 资料页进入编辑页 | profile-enter-edit |
| 进入个人资料详情页 | my-profile |

## 家族 · `片段/家族/`

| 脚本 | id |
|------|-----|
| 家族主页下滑浏览 | family-home-scroll |
| 家族主页进入任务与奖励 | family-home-tasks-rewards |
| 家族主页进入成员列表 | family-home-members-list |
| 家族主页进入日榜 | family-home-daily-ranking |
| 家族主页进入群聊 | family-home-group-chat |
| 家族任务页浏览 | family-tasks-browse |
| 我的页进入Family | me-enter-family |
| 消息帧进入家族群聊 | msg-enter-group-chat |
| 资料页进入家族主页 | profile-enter-family |

## CP好友关系 · `片段/CP好友关系/`

| 脚本 | id |
|------|-----|
| 我的页进入MyRelationship | me-enter-relationship |
| 我的页进入ViewedMe | me-enter-viewed-me |
| 消息帧进入FriendRequest | msg-enter-friend-request |
| 消息帧进入SuperLike | msg-enter-super-like |
| 消息帧进入好友入口 | msg-friend-entrance |
| 进入关注列表 | me-following-list |
| 进入好友列表 | me-friends-list |
| 进入粉丝列表 | me-followers-list |

## 充值提现转账 · `片段/充值提现转账/`

| 脚本 | id |
|------|-----|
| 游戏帧进入充值页 | game-enter-wallet |
| 进入钱包 | wallet |

## 特权VIP · `片段/特权VIP/`

| 脚本 | id |
|------|-----|
| 我的页进入Privilege | me-enter-privilege |

## 贵族 · `片段/贵族/`

| 脚本 | id |
|------|-----|
| 我的页进入Nobility | me-enter-nobility |

## 财富等级 · `片段/财富等级/`

| 脚本 | id |
|------|-----|
| 我的页进入Level | me-enter-level |

## 收藏展馆 · `片段/收藏展馆/`

| 脚本 | id |
|------|-----|
| 我的页进入CollectionExhibition | me-enter-collection |

## 装扮 · `片段/装扮/`

| 脚本 | id |
|------|-----|
| 我的页进入MyOutfits | me-enter-my-outfits |
| 我的页进入OutfitStore | me-enter-outfit-store |

## 公会 · `片段/公会/`

| 脚本 | id |
|------|-----|
| 我的页进入MyAgency | me-enter-my-agency |

## 客服 · `片段/客服/`

| 脚本 | id |
|------|-----|
| 设置页进入帮助 | settings-help |

## 榜单与活动 · `片段/榜单与活动/`

| 脚本 | id |
|------|-----|
| 我的页签到 | me-check-in |
| 我的页进入PrizeCollection | me-enter-prize-collection |
| 我的页进入Redeem | me-enter-redeem |
| 我的页进入YaahlanStar | me-enter-yaahlan-star |
| 房间帧进入财富榜 | room-wealth-ranking |
| 游戏帧Activities进入StarAmbassador | game-activities-star-ambassador |
| 游戏帧进入ActivitiesBanner | game-enter-activities-banner |
| 游戏帧进入活动中心 | game-enter-event-center |

## 常用命令

```bash
python3 adb/adb_execute.py scripts
python3 adb/adb_execute.py macro 关闭常见弹窗
python3 adb/adb_execute.py macro 手机号登录 --text 13311111115
```

## AI 读图模块（默认禁用 macro）

见 `索引.json` → `aiOperateModules`：`游戏`、`房间`、`礼物`、`个人主页` 等。
调试旧坐标加 `--force-script`。

## 暂不可 ADB 固化

- 第三方授权、支付链路、游戏内玩法（仅支持房内 Minimize 收起）等
