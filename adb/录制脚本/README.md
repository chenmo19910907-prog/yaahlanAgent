# Yaahlan 录制脚本库

本目录集中存放已验证的 ADB 操作脚本，**统一使用中文名**调用；英文 `id` 仍兼容。

## 目录结构（积木模型）

```
录制脚本/
  索引.json              # 总目录；片段含 module（发版回归一级模块）
  片段/
    注册登录/            # documents/登录注册、冷启动
    首页-游戏帧/          # 底栏 Game
    首页-房间帧/          # 底栏 Room
    消息帧/              # 底栏 Message
    动态帧/              # 底栏 Moment + 动态业务
    我的帧/              # 底栏 Me + 个人页子入口
  组合/
    注册登录/ … 动态帧/ … 我的帧/   # 按一级模块分子目录（compose）
```

**不再有 `流程/`。** 完整路径用 `compose` 搭积木；**首页/Me/房间模块已改 AI 读图**，见 [`../README.md`](../README.md#首页--个人页me--房间--ai-读图禁用固定脚本)。

### AI 读图模块（禁用 macro，除非 `--force-script`）

| 模块 | 说明 |
|------|------|
| 首页-游戏帧 | 底栏 Game → `ai prepare --goal home_tab` |
| 首页-房间帧 | 进房/退房/搜索 → `enter_room` / `exit_room` |
| 我的帧 | Me/设置/退出 → `enter_me` / `logout` |

目录内 JSON **仅作参考坐标**，Agent 须 `capture` 读图后 `tap`。

**RTL 语言**：阿语、中文等下原生 UI 可能左右镜像（WebView 不一定）；`tap_pct` 按英文 LTR 录制，换语言后片段间读图，必要时对 x 做 `1−x`。见 [`../README.md`](../README.md#app-语言与-rtl-镜像)。

模块命名与发版回归一级模块一致（注册登录、首页-*帧、消息帧、动态帧、我的帧等）；底栏切换归入对应「首页-*帧 / *帧」目录。

## 脚本一览（按模块）

### 注册登录

**登录默认**（`索引.json` → `loginDefaults`）：**+86** / 手机 `13311111115` / 验证码 `000000`。

**账号身份与 UI 分离**：公会长/家族长等角色只在 `testAccounts`（phone、userId、role）和 Tunnel/`login verify` 里区分；**登录 UI 统一 `手机号登录`**。组合 JSON 设 `"account": "guildLeader"` 时自动用对应手机号；也可 `macro 手机号登录 --text 13311111111`。

| 中文名 | id |
|--------|-----|
| 启动Yaahlan | launch-yaahlan |
| 跳过开屏广告 | dismiss-splash-ad |
| 验收开屏广告 | verify-splash-ad（冷启后自动验收，可 `--skip verify_splash_ad`） |
| 冷启动回首页 | cold-start-home（不确定当前页时用） |
| 登录-语言下一步 | login-lang-next |
| 登录-勾选协议打开手机 | login-agree-phone |
| 登录-手机号发短信 | login-phone-sms（`--text`） |
| 登录-输入验证码 | login-verify-code（`--text`） |
| 手机号登录 | login-phone-full（`--text` 手机号；组合可用 `account` 取 testAccounts） |
| **关闭常见弹窗** | dismiss-common-popups |
| **关闭Me页弹窗** | dismiss-me-popups（仅 Cancel，Me 专用） |
| 登录后关闭弹窗（→ 上） | login-dismiss-popup |

### 首页-游戏帧 / 首页-房间帧 / 消息帧

| 模块 | 中文名 | id |
|------|--------|-----|
| 首页-游戏帧 | 切换游戏底栏 | game-tab |
| 首页-房间帧 | 切换房间底栏 | room-tab |
| 首页-房间帧 | 搜索进房 | room-search-enter（`--text` roomId） |
| 首页-房间帧 | 打开礼物面板 | open-gift-panel |
| 首页-房间帧 | 礼物面板送Trophy | gift-panel-send-trophy |
| 首页-房间帧 | 退出房间 | room-exit |
| 首页-房间帧 | 搜索页返回房间帧 | room-search-back（退出后落在 Search 时） |
| 消息帧 | 切换消息底栏 | msg-tab |

### 动态帧

| 中文名 | id |
|--------|-----|
| 切换动态底栏 | moment-tab |
| 切换动态关注tab | moment-follow-tab |
| 打开动态发布页 | open-moment-compose |
| 发布纯文本动态 | post-moment（`--text`） |
| 发布视频动态 | post-video-moment |
| 进入我的动态列表 | my-moments-list |

### 我的帧

| 中文名 | id |
|--------|-----|
| 切换我的底栏 | me-tab |
| 进入个人资料详情页 | my-profile |
| 我的页进入个人资料详情 | my-profile-from-me |
| 进入钱包 | wallet |
| 进入设置 | settings |
| 退出登录 | logout |
| 设置页退出登录 | logout-from-settings |

### 组合（按模块）

| 模块 | 中文名 | id | 积木顺序 |
|------|--------|-----|----------|
| 注册登录 | 冷启动登录 | cold-start-login | 启动 → 跳过开屏 → 验收开屏 → 手机号登录 |
| 首页-房间帧 | 家族长搜索进公会长房 | family-search-guild-room | 搜索进房 → 关闭常见弹窗 |
| 首页-房间帧 | 家族长房内送Trophy99钻 | family-send-trophy-99 | 礼物面板送Trophy → 关闭常见弹窗 |
| 动态帧 | 发布纯文本动态 | post-moment-compose | 发布纯文本动态 |
| 动态帧 | 发布视频动态 | post-video-moment-compose | 发布视频动态 |
| 我的帧 | 进入个人资料详情页 | my-profile-compose | 进入个人资料详情页 |

知识库映射见 [`KB对照.md`](KB对照.md)。

## 成功即落库（Agent 必做）

**触发条件**：真机操作验收通过且退出码为 **0**。**已实现脚本/有接口：先抓包，失败再读图**；**未实现脚本：抓包+读图并用**；**提交表单优先抓包**。串联多个 macro 时**片段间**再验收（非逐步 tap）。详见 [`../README.md`](../README.md#片段间验收串联多个-macro-时)。

1. **片段** `片段/<一级模块>/<中文名>.json`（`module` 与目录名一致）
2. **登记** `索引.json`：`kind: fragment`、`module`、`file`
3. **组合**（端到端）`组合/<一级模块>/<中文名>.json` + `tunnelVerify`，索引登记 `module`
4. 更新本 README 与 `KB对照.md`

## 命令示例

```bash
python3 adb/adb_execute.py scripts    # 含 fragmentsByModule 分组
python3 adb/adb_execute.py macro 切换动态底栏   # 中文名或 id，勿写目录路径
python3 adb/adb_execute.py macro 退出登录
python3 adb/adb_execute.py macro 设置页退出登录   # 已在 Settings 时
python3 adb/adb_execute.py macro 发布纯文本动态 --text 5555 --no-capture
python3 adb/adb_execute.py compose 冷启动登录
```

调用 **macro / compose 仍只用片段中文名或 id**，路径由索引解析。

## 开屏广告（约 5s）

冷启后有时出现全屏开屏；**广告未结束就点击**会进入广告 H5，导致后续 macro 全偏。

| 阶段 | 做法 |
|------|------|
| 等待 | `launch_app` **4s** + `跳过开屏广告` **sleep 3s+4s** 再点右上角跳过（合计约 **11s** 再 tap） |
| 片段间验收 | 冷启组合/宏内自动跑 **`验收开屏广告`**（activity；失败 BACK+重跑跳过）；亦可 `splash verify --recover` |
| 误进广告 | 验收步骤内 `--recover`；或手动 `splash verify --recover` |

```bash
python3 adb/adb_execute.py macro 冷启动回首页 --no-capture
# 宏内已含「验收开屏广告」；失败 exit 3。单独验收：
python3 adb/adb_execute.py splash verify --account guildLeader --since 45 --recover
python3 adb/adb_execute.py popup analyze --scene splash --account guildLeader --since 45
```

Tunnel：`ad/getOpenScreenAd`（有广告）→ 之后应有 `getUserConfigs` / `simpleUserInfo`（主页就绪）。

组合 **冷启动登录** = 启动 → 跳过开屏 → 登录。无跳过按钮：`compose 冷启动登录 --skip dismiss_splash_ad`。

## 设备型号适配

见 [`设备适配/README.md`](设备适配/README.md)。
