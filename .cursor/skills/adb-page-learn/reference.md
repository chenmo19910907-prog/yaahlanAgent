# ADB 页面学习 — 参考

## 片段 JSON 模板

```json
{
  "id": "module-action-target",
  "name": "中文名（与文件名一致）",
  "recordedOn": { "width": 1080, "height": 2340 },
  "capture": "end",
  "description": "前置条件 → 操作 → 验收 Activity/页面特征（一句话）",
  "kbRef": [
    "documents/xxx.md（章节）",
    "testcase-kb/yyy.md（区块）"
  ],
  "steps": [
    { "sleep_ms": 400 },
    { "run_script": "前置片段名", "note": "可选" },
    { "tap_pct": [0.500, 0.547], "note": "读图标定的控件" },
    {
      "swipe": { "x1": 540, "y1": 1700, "x2": 540, "y2": 900, "duration_ms": 350 },
      "note": "上滑浏览"
    },
    { "sleep_ms": 1200 }
  ]
}
```

### id 命名

- 格式：`{页面}-{动作}-{目标}`，kebab-case，如 `family-home-tasks-rewards`、`game-enter-wallet`
- 与 `索引.json` 中 `id` 一致；勿用 `dirty_*` 等临时名

### description / kbRef

- **description**：写清 **前置**（已在哪一页）、**点击谁**、**落到哪**（`PayActivity` / `WebViewActivity` / 页面标题）
- **kbRef**：从 `testcase-kb/`、`documents/` 找对应章节；无文档时写「待补 KB」并在 KB对照 备注

### steps 约定

| 字段 | 说明 |
|------|------|
| `tap_pct` | 相对 1080×2340；`note` 写控件文案或 bounds |
| `run_script` | 嵌套已有片段中文名 |
| `swipe` | 列表/Profile Tab / 家族主页等须单独片段或合在 browse 片段 |
| `sleep_ms` | WebView/进房后适当加长（1200–2500） |

## 索引.json 登记

```json
{
  "id": "family-home-tasks-rewards",
  "name": "家族主页进入任务与奖励",
  "kind": "fragment",
  "module": "我的帧",
  "file": "片段/我的帧/家族主页进入任务与奖励.json"
}
```

`module` 与目录名一致：`注册登录` | `首页-游戏帧` | `首页-房间帧` | `消息帧` | `动态帧` | `我的帧`。

## KB对照.md 增行

```markdown
| 知识库条目 | 脚本 | id |
| Tasks & Rewards | 家族主页进入任务与奖励 | family-home-tasks-rewards |
```

## uiautomator 精确定位 Tab

Profile 等 Tab 文字 y 随折叠头变化，勿死记一次 tap：

```bash
adb -s <serial> shell uiautomator dump /sdcard/ui.xml
adb -s <serial> shell cat /sdcard/ui.xml | python3 -c "
import sys,re
xml=sys.stdin.read()
for m in re.finditer(r'text=\"(Profile|Honor|Relationship)\"[^>]*bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"', xml):
    t,x1,y1,x2,y2=m.group(1),*map(int,m.groups()[1:])
    print(t, (x1+x2)//2, (y1+y2)//2)
"
```

## learn scan（仅辅助）

```bash
python3 adb/adb_execute.py learn scan --tab me
python3 adb/adb_execute.py learn probe --limit 10   # 仅调试，不可替代读图
```

产出 **不得** 直接写入 `页面地图.json` 当正式片段；须读图确认后手写片段。

## 账号与 MOA / Admin

### 查 userId

```bash
python3 MOA/moa_execute.py --payload-file MOA/templates/用户-按手机号查userId.json \
  --query-user-by-phone 13311111113 --phone-output summary
```

### VIP 体验卡

```bash
python3 adb/adb_execute.py vip try --account familyLeader --level 5 --days 1 --clear-first
python3 adb/adb_execute.py vip query --account familyLeader
```

### 解除客服身份

```bash
python3 Admin/admin_execute.py --query-cs-data --cs-user-id <userId>
python3 Admin/admin_execute.py --save-cs-data \
  --cs-user-id <userId> --cs-role-list 1 --cs-enable 0 --cs-taking-order 0 --cs-opt-type 2
```

### 换号登录

```bash
python3 adb/adb_execute.py macro 退出登录 --force-script --no-popup-gate
python3 adb/adb_execute.py macro 手机号登录 --text 13311111113 --force-script --no-popup-gate
# 或逐段：macro 启动Yaahlan → macro 跳过开屏广告 → macro 手机号登录 --text 13311111113
```

## 特殊场景清单

### 房内三方游戏 + 退房

```bash
python3 adb/adb_execute.py key 4                    # Game Rewards 等弹窗
python3 adb/adb_execute.py macro 房内三方游戏最小化 --force-script
python3 adb/adb_execute.py macro 退出房间 --force-script --no-popup-gate
python3 adb/adb_execute.py activity                 # 不应再 in_room
```

片段：`片段/首页-房间帧/房内三方游戏最小化.json`、`退出房间.json`。

### Ludo 进 RoomGameActivity 退房

Ludo 房左上角 **X**（非 voice room-exit 面板）；若进房后拉起三方游戏，仍须 **Minimize** 再退房。

### 游戏帧常见落点

| 入口 | 典型 Activity |
|------|----------------|
| 顶部钻石余额 | PayActivity |
| 活动中心 | EventActivity |
| game_task | WebViewActivity |
| Casual games More | GameListActivity |
| Ludo 卡片 | RoomGameActivity |
| Online player 行 | ChatActivity |

### 资料页 / 家族

| 入口 | 说明 |
|------|------|
| Family 卡片 | WebView 家族主页 |
| Tasks & Rewards | WebView Tasks / Family Fund Tab |
| Group Chat | GroupChatActivity |
| Members **More >** | 标题行右侧，非头像 |
| Honor / Relationship Tab | dump bounds |
| Voice Room 卡片 | RoomChatActivity；退房见上 |

## 已学片段速查

运行前读 `adb/录制脚本/索引.json` 与 `KB对照.md`，**跳过已有 id**，只补缺口。

## activity hint 快验

| hint | 含义 |
|------|------|
| `home` | MainActivity 底栏 |
| `in_room` | RoomChatActivity |
| `search` | 搜索页（退房后常见） |
| `login` | LoginActivity |
| `webview` | WebViewActivity |

```bash
python3 adb/adb_execute.py activity
```
