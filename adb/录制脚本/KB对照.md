# 知识库 ↔ 录制脚本对照

真机验收（1080×2340，vivo V1838A）后落库。片段按 **发版回归一级模块** 分目录。

## 注册登录 · `片段/注册登录/`

**默认（`索引.json` → `loginDefaults`）**：区号 **+86**，手机号 **13311111115**，验证码 **000000**。分步片段可省略 `--text`。

**测试账号（`testAccounts`）**：角色/手机号/userId 在此登记，**与登录 UI 流程无关**。

| 键名 | 角色 | 手机号 | userId |
|------|------|--------|--------|
| guildLeader | 公会长 | 13311111111 | 100465989 |
| familyLeader | 家族长 | 13311111112 | 100486375 |

| 知识库 | 脚本 | id |
|--------|------|-----|
| 启动 Yaahlan | 启动Yaahlan | launch-yaahlan |
| 冷启动开屏广告 | 跳过开屏广告 | dismiss-splash-ad |
| 验收开屏 | 验收开屏广告 | verify-splash-ad |
| **不确定当前页 → 回首页** | **冷启动回首页** | cold-start-home |
| 语言选择 Next | 登录-语言下一步 | login-lang-next |
| 勾选协议 + 手机入口 | 登录-勾选协议打开手机 | login-agree-phone |
| 输入手机号 + Get via SMS | 登录-手机号发短信 | login-phone-sms（默认 QA 号） |
| 输入验证码 | 登录-输入验证码 | login-verify-code（默认 000000） |
| **手机号登录（统一 UI）** | 手机号登录 | login-phone-full（`--text` 或组合 `account`） |
| 完善资料注册 | 完成注册 | register-profile（`--text` 手机号；昵称 C+后三位） |
| MOA 查号后登录/注册 | `accounts status` / `accounts enter --text` | — |
| 登录后/切页偶发弹窗 | **关闭常见弹窗**（Me 等页 Cancel） | dismiss-common-popups |
| **登录后签到半屏** | **关闭签到弹窗** / **登录后处理弹窗** | dismiss-sign-in-popup / login-post-popups |
| 同上（兼容旧名） | 登录后关闭弹窗 | login-dismiss-popup |

**常见弹窗**（测试包偶发）：运营礼包全屏、Account Security 绑定提示、Crowd Testing 众测、退出 Yaahlan 双按钮。脚本默认尝试关闭；误点风险用 `--skip dismiss_popup_taps`。

```bash
python3 adb/adb_execute.py compose 冷启动登录
python3 adb/adb_execute.py compose 冷启动登录 --text 13311111111   # 指定手机号
python3 adb/adb_execute.py macro 冷启动回首页   # 已登录：杀进程回首页底栏
python3 adb/adb_execute.py compose 家族长发布图片动态   # account 自动取号
python3 adb/adb_execute.py macro 关闭常见弹窗
python3 adb/adb_execute.py macro 手机号登录 --text 13311111112 --skip login_lang
python3 adb/adb_execute.py macro 发布图片动态 --skip dismiss_popup_taps
python3 adb/adb_execute.py login verify --account guildLeader --since 90   # 身份验收
```

## 首页-游戏帧 · `片段/首页-游戏帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Game | 切换游戏底栏 | game-tab |
| Game 点头像 → 资料页 | 游戏帧进入个人资料 | game-profile |
| 余额区 → 充值 | 游戏帧进入充值页 | game-enter-wallet |
| 活动中心 | 游戏帧进入活动中心 | game-enter-event-center |
| 任务礼包 | 游戏帧进入任务礼包 | game-enter-task-pack |
| Ludo King | 游戏帧进入Ludo | game-enter-ludo |
| Casual More | 游戏帧CasualGamesMore / 游戏帧进入游戏列表 | game-casual-more / game-enter-game-list |
| Snakes and Ladders | 游戏帧进入SnakesLadders | game-enter-snakes-ladders |
| Domino | 游戏帧进入Domino | game-enter-domino |
| Activities 横幅 | 游戏帧进入ActivitiesBanner | game-enter-activities-banner |
| Online players 私聊 | 游戏帧进入OnlinePlayer聊天 | game-enter-online-player-chat |
| Online Visit 进房 | 游戏帧OnlinePlayerVisit进房 | game-enter-visit-room |

## 首页-房间帧 · `片段/首页-房间帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Room | 切换房间底栏 | room-tab |
| 搜索 roomId 进房 | **搜索进房**（点结果行房间信息，**勿点输入框**） | room-search-enter |
| 房内开礼物面板 | **打开礼物面板**（橙色礼物盒，勿点快捷礼物） | open-gift-panel |
| 礼物面板送 99 钻 Trophy | **礼物面板送Trophy**（Gift Tab + 上下滑） | gift-panel-send-trophy |
| 退出房间 | 退出房间 | room-exit |
| 网络诊断 Excellent | 关闭网络诊断弹窗 | room-dismiss-network-diagnostic |
| Mic invitation | 拒绝Mic邀请 | room-reject-mic-invitation |
| Wealth Ranking | 房间帧进入财富榜 | room-wealth-ranking |
| Egypt tab | 房间帧切换EgyptTab | room-egypt-tab |
| Mine tab | 房间帧切换MineTab | room-mine-tab |
| Hot 分类 | 房间帧切换Hot分类 | room-hot-chip |
| 列表首卡进房 | 房间帧点击首个房间卡片 | room-tap-first-card |
| Mine Follow/Joined/Family/Viewed | 房间帧Mine切换Follow 等 | room-mine-follow 等 |
| 创建房间菜单 | 房间帧打开创建房间菜单 | room-open-create-menu |
| 搜索页返回 Room 帧 | 搜索页返回房间帧 | room-search-back |

公会长房 roomId **38826842**（Sheikh's Cottage，账号 13311111111）：

```bash
python3 adb/adb_execute.py compose 家族长搜索进公会长房
python3 adb/adb_execute.py compose 家族长房内送Trophy99钻   # 已在房内；Tunnel gift/send
python3 adb/adb_execute.py gift panel find --account familyLeader --price 99 --tab Gift
```

## 动态帧 · `片段/动态帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Moment | 切换动态底栏 | moment-tab |
| 发布纯文本 | 发布纯文本动态 | post-text-moment |
| 发布单图 | 发布图片动态 | post-image-moment |
| 发布视频 | 发布视频动态 | post-video-moment |
| 我的动态列表 | 进入我的动态列表 | my-moment-list |

## 我的帧 · `片段/我的帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Me | 切换我的底栏 | me-tab |
| 个人资料详情 | 进入个人资料详情页 | my-profile |
| Friends 统计 | 进入好友列表 | me-friends-list |
| Following 统计 | 进入关注列表 | me-following-list |
| Followers 统计 | 进入粉丝列表 | me-followers-list |
| 钱包 | 进入钱包 | wallet |
| 设置 | 进入设置 | settings |
| 设置 · Language | 设置页进入语言 | settings-language |
| 设置 · 切换语言（默认 English） | 设置页切换语言 | settings-switch-language |
| 设置 · Notifications | 设置页进入通知 | settings-notifications |
| 设置 · Blacklist | 设置页进入黑名单 | settings-blacklist |
| 设置 · Account Management | 设置页进入账号管理 | settings-account-management |
| 设置 · Stealth | 设置页进入隐身设置 | settings-stealth |
| 设置 · Clear cache | 设置页清除缓存 | settings-clear-cache |
| 设置 · Help（进客服房） | 设置页进入帮助 | settings-help |
| 设置 · Game Support | 设置页进入游戏支持 | settings-game-support |
| 设置 · About | 设置页进入关于 | settings-about |
| 设置页 Log out | 设置页退出登录 | logout-from-settings |
| 退出登录 | 退出登录 | logout |
| 注销账号（Me→设置→账号安全→Delete account） | 注销账号 | cancel-account |

## 组合索引（节选）

| 模块 | 场景 | 组合名 | 目录 |
|------|------|--------|------|
| 注册登录 | 冷启动登录 | 冷启动登录 | `组合/注册登录/` |
| 首页-房间帧 | 家族长搜索进公会长房 | 家族长搜索进公会长房 | `组合/首页-房间帧/` |
| 首页-房间帧 | 房内送 Trophy 99 钻 | 家族长房内送Trophy99钻 | `组合/首页-房间帧/` |
| 动态帧 | 冷启动并发图 | 公会长/家族长发布图片动态 | `组合/动态帧/` |

## 消息帧 · `片段/消息帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Message | 切换消息底栏 | msg-tab |
| Everyone 子 tab | 消息帧切换EveryoneTab | msg-everyone-tab |
| Friends 子 tab | 消息帧切换FriendsTab | msg-friends-tab |
| Tasks 子 tab | 消息帧切换TasksTab | msg-tasks-tab |
| Transfer 子 tab | 消息帧切换TransferTab | msg-transfer-tab |
| Transfer 空态 Refresh | 消息帧Transfer空态刷新 | msg-transfer-refresh |
| Daily Task Rewards | 消息帧进入DailyTaskRewards | msg-daily-task-rewards |
| 家族群聊 CCVC | 消息帧进入家族群聊 | msg-enter-group-chat |
| Super like | 消息帧进入SuperLike | msg-enter-super-like |
| Friend request | 消息帧进入FriendRequest | msg-enter-friend-request |
| 右上角好友入口 | 消息帧进入好友入口 | msg-friend-entrance |
| Tasks Acquire | 消息帧Tasks切换Acquire | msg-tasks-acquire |
| Tasks Ongoing | 消息帧Tasks切换Ongoing | msg-tasks-ongoing |
| Tasks Say hi | 消息帧TasksSayHi | msg-tasks-say-hi |

## 动态帧 · `片段/动态帧/`（补充）

| 知识库 | 脚本 | id |
|--------|------|-----|
| 关注 tab | 切换动态关注tab | moment-follow-tab |
| 发现 tab | 动态帧切换DiscoverTab | moment-discover-tab |
| Topics More | 动态帧进入TopicsMore | moment-topics-more |
| 话题详情 #My Family | 动态帧进入话题详情 | moment-enter-topic-detail |
| Discover 横滑话题卡片 | 动态帧Discover进入话题详情 | moment-discover-topic-detail |
| 话题 Popular | 动态帧话题切换PopularTab | moment-topic-popular-tab |
| 话题 Most liked | 动态帧话题切换MostLikedTab | moment-topic-most-liked-tab |
| 动态详情（评论入口） | 动态帧进入动态详情 / 动态帧Discover进入动态详情 | moment-enter-feed-detail / moment-discover-feed-detail |
| 发布【➕】/ 编辑页 | 打开动态发布页 | open-moment-compose |
| 发布纯文本 | 发布纯文本动态 | post-moment |
| 发布视频 | 发布视频动态 | post-video-moment |
| 发布单图 | 发布图片动态 | post-image-moment |
| 个人动态列表 | 进入我的动态列表 | my-moments-list |

## 我的帧 · `片段/我的帧/`（补充）

| 知识库 | 脚本 | id |
|--------|------|-----|
| 点头像 → 资料详情 | 进入个人资料详情页 / 我的页进入个人资料详情 | my-profile |
| Profile Tab 上滑 | 资料页ProfileTab下滑浏览 | profile-scroll-profile-tab |
| Profile → 家族卡片 | 资料页进入家族主页 | profile-enter-family |
| 家族主页上滑 | 家族主页下滑浏览 | family-home-scroll |
| Tasks & Rewards | 家族主页进入任务与奖励 / 家族任务页浏览 | family-home-tasks-rewards / family-tasks-browse |
| Group Chat | 家族主页进入群聊 | family-home-group-chat |
| Family Members More | 家族主页进入成员列表 | family-home-members-list |
| Daily/Weekly Ranking | 家族主页进入日榜 | family-home-daily-ranking |
| Honor Tab | 资料页切换HonorTab / 资料页HonorTab下滑浏览 | profile-honor-tab / profile-honor-tab-scroll |
| Relationship Tab | 资料页切换RelationshipTab | profile-relationship-tab |
| Voice Room 卡片 | 资料页进入VoiceRoom | profile-enter-voice-room |
| 编辑资料 | 资料页进入编辑页 | profile-enter-edit |
| My Moments + | 资料页打开发布动态 | profile-open-moment-compose |
| 设置页 Log out | 设置页退出登录 | logout-from-settings |
| 退出登录（Me→设置→Log out） | 退出登录 | logout |
| 注销预申请（15s+确认；blocked 则 toast 结束） | 注销账号 | cancel-account |
| Me 上滑露出下半菜单 | 我的页下滑浏览 | me-scroll-lower-menu |
| My Room | 我的页进入MyRoom | me-enter-my-room |
| My Relationship | 我的页进入MyRelationship | me-enter-relationship |
| Viewed me | 我的页进入ViewedMe | me-enter-viewed-me |
| Check-in 签到 | 我的页签到 | me-check-in |
| Redeem | 我的页进入Redeem | me-enter-redeem |
| Family（Me 入口） | 我的页进入Family | me-enter-family |
| Privilege VIP | 我的页进入Privilege | me-enter-privilege |
| Nobility 贵族 | 我的页进入Nobility | me-enter-nobility |
| Level 等级 | 我的页进入Level | me-enter-level |
| Collection Exhibition | 我的页进入CollectionExhibition | me-enter-collection |
| Badge 徽章 | 我的页进入Badge | me-enter-badge |
| Outfit store | 我的页进入OutfitStore | me-enter-outfit-store |
| Invite Friends | 我的页进入InviteFriends | me-enter-invite-friends |
| Prize Collection | 我的页进入PrizeCollection | me-enter-prize-collection |
| My Agency | 我的页进入MyAgency | me-enter-my-agency |
| My Outfits | 我的页进入MyOutfits | me-enter-my-outfits |
| Yaahlan star | 我的页进入YaahlanStar | me-enter-yaahlan-star |
| Wallet（坐标已校正） | 进入钱包 | wallet |

## 组合（按模块）

| 模块 | 场景 | 组合名 | 路径 |
|------|------|--------|------|
| 注册登录 | 冷启动 + 登录 | 冷启动登录 | `组合/注册登录/` |
| 首页-房间帧 | 家族长搜索进公会长房 | 家族长搜索进公会长房 | `组合/首页-房间帧/` |
| 首页-房间帧 | 房内送 Trophy 99 钻 | 家族长房内送Trophy99钻 | `组合/首页-房间帧/` |
| 动态帧 | 发动态（已在 App） | 发布纯文本 / 视频 / **图片** 动态 | `组合/动态帧/` |
| 动态帧 | 冷启动并发图 | 公会长/家族长发布图片动态 | `组合/动态帧/` |
| 我的帧 | 进资料页（已在 App） | 进入个人资料详情页 | `组合/我的帧/` |

## 暂不可 ADB 固化

- 第三方授权、完善资料多步、支付等（待补模块目录：支付、公会…）
