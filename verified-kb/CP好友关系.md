# CP好友关系

> **文档类型**：真机跑通功能验收知识库  
> **对齐**：`testcase-kb/CP好友关系.md`

| 项 | 说明 |
|---|---|
| 验收账号 | familyLeader |
| 关联脚本目录 | `adb/录制脚本/片段/CP好友关系/` |

## 目录

- Me 帧·关系列表
- Me 帧·关系空间
- 消息帧·关系入口

---

## Me 帧·关系列表

### 好友 / 关注 / 粉丝

**Friends 列表**
- Me 页 Friends 统计 → RelationActivity 好友列表

**Following 列表**
- Me 页 Following 统计 → 关注列表

**Followers 列表**
- Me 页 Followers 统计 → 粉丝列表

---

## Me 帧·关系空间

### 我的关系与访客

**My Relationship**
- Me 页 My Relationship → ProfileActivity Relationship Tab

**Viewed me**
- Me 页 Viewed me 区域 → VisitorActivity（展示访客列表）

---

## 消息帧·关系入口

### Everyone 列表

**好友入口（右上角图标）**
- Message Everyone → RelationActivity

**Super like 通知行**
- → SuperLikeComposeActivity

**Friend request 通知行**
- → FriendBoxActivity

> 消息列表各行纵向顺序会随通知增减变化，验收前须 capture 读图确认目标行。
