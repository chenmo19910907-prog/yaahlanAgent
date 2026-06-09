# verified-kb · 真机跑通功能验收知识库

> **文档类型**：基于 ADB 真机页面学习沉淀的**功能验收要点**（按业务域组织，体例对齐 `testcase-kb/`）  
> **非**：片段坐标手册（见 `adb/录制脚本/`）、非版本 xlsx 全量产品规则（见 `testcase-kb/`）

| 项 | 说明 |
|---|---|
| 收录范围 | 已在真机 **capture + activity / 读图** 验收通过的用户功能路径 |
| 验收基准 | 1080×2340 · 设备 `ba69021e` · 账号 **familyLeader**（13311111112 / CCVC 家族长） |
| 组织方式 | `## 业务域` → `### 功能点` → **场景** + 验收要点列表 |
| 自动化关联 | 每条可对应 `adb/录制脚本/片段/` 中 macro 片段；回放用 `python3 adb/adb_execute.py macro <中文名>` |
| 进度源 | `adb/.state/learn_progress.json`（会话级）；正文以本目录 md 为准 |

## 与 testcase-kb 的关系

| 库 | 用途 |
|----|------|
| **testcase-kb/** | 从版本用例 xlsx 提炼的**产品规则全量**（设计/回归设计参考） |
| **verified-kb/**（本目录） | 真机已跑通的**功能子集**（自动化探索、冒烟路径、Agent 续学起点） |
| **adb/录制脚本/** | 可执行片段 JSON + 索引（坐标与步骤） |

同名 md（如 `动态.md`）内容互补：testcase-kb 讲「产品应怎样」；verified-kb 讲「当前真机已验证能怎样」。

## 文件列表

| 文件 | 业务域 |
|------|--------|
| [`个人主页.md`](个人主页.md) | Me 底栏、资料页、Honor/Relationship、装扮/贵族/等级/特权/收藏/公会入口等 |
| [`CP好友关系.md`](CP好友关系.md) | 好友/关注/粉丝、My Relationship、Viewed me、消息帧关系入口 |
| [`充值提现转账.md`](充值提现转账.md) | 钱包 |
| [`游戏.md`](游戏.md) | 游戏帧、Casual Games、棋牌、OnlinePlayer、活动中心 |
| [`房间.md`](房间.md) | 房间帧 Explore/Mine、分类 chip、搜索、进房退房 |
| [`消息.md`](消息.md) | 消息帧 Tab、Tasks、Transfer、系统通知类入口 |
| [`动态.md`](动态.md) | 发布（文/图/视频）、Discover/Follow、话题、互动、我的动态 |
| [`家族.md`](家族.md) | 家族主页、成员、榜单、任务、群聊 |
| [`榜单与活动.md`](榜单与活动.md) | Me 签到/兑换/明星榜、游戏活动中心、消息 Tasks、家族日周榜 |
| [`注册登录.md`](注册登录.md) | 登录、设置子页 |

## 维护

1. 真机验收新功能 → 在对应 md 增 **场景** 与验收要点  
2. 同步 `adb/.state/learn_progress.json`（可选，供 Agent 续学）  
3. 落 macro 片段 → `adb/录制脚本/`（坐标层，不写入本库正文）

## 已知限制（全局）

- Room **Mine → Family** 子 Tab 当前账号空态，无进房路径  
- 游戏帧 **Activities 横幅** 部分活动已结束，需换有效活动再扩  
- 设置 **Help** 现为 WebView，非历史 RoomChatActivity  
- Me 页 **CharmPK 横幅/奖杯挂件** 任意页出现须先拖走再继续操作  
