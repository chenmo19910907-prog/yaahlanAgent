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

**不再有 `流程/`。** 完整路径用 `compose` 搭积木；位置不确定时由 Agent 读图选块。

模块命名与 [`regression-kb/发版回归用例.md`](../../regression-kb/发版回归用例.md) 一级模块一致；底栏切换归入对应「首页-*帧 / *帧」目录。

## 脚本一览（按模块）

### 注册登录

| 中文名 | id |
|--------|-----|
| 启动Yaahlan | launch-yaahlan |
| 跳过开屏广告 | dismiss-splash-ad |
| 登录-语言下一步 | login-lang-next |
| 登录-勾选协议打开手机 | login-agree-phone |
| 登录-手机号发短信 | login-phone-sms（`--text`） |
| 登录-输入验证码 | login-verify-code（`--text`） |
| 手机号登录 | login-phone-full |
| 登录后关闭弹窗 | login-dismiss-popup |

### 首页-游戏帧 / 首页-房间帧 / 消息帧

| 模块 | 中文名 | id |
|------|--------|-----|
| 首页-游戏帧 | 切换游戏底栏 | game-tab |
| 首页-房间帧 | 切换房间底栏 | room-tab |
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

### 组合（按模块）

| 模块 | 中文名 | id | 积木顺序 |
|------|--------|-----|----------|
| 注册登录 | 冷启动登录 | cold-start-login | 启动Yaahlan → 跳过开屏广告 → 手机号登录 |
| 动态帧 | 发布纯文本动态 | post-moment-compose | 发布纯文本动态 |
| 动态帧 | 发布视频动态 | post-video-moment-compose | 发布视频动态 |
| 我的帧 | 进入个人资料详情页 | my-profile-compose | 进入个人资料详情页 |

知识库映射见 [`KB对照.md`](KB对照.md)。

## 成功即落库（Agent 必做）

1. **片段** `片段/<一级模块>/<中文名>.json`（`module` 与目录名一致）
2. **登记** `索引.json`：`kind: fragment`、`module`、`file`
3. **组合**（可选）`组合/<一级模块>/<中文名>.json`，索引登记 `module`
4. 更新本 README 与 `KB对照.md`

## 命令示例

```bash
python3 adb/adb_execute.py scripts    # 含 fragmentsByModule 分组
python3 adb/adb_execute.py macro 切换动态底栏   # 中文名或 id，勿写目录路径
python3 adb/adb_execute.py macro 发布纯文本动态 --text 5555 --no-capture
python3 adb/adb_execute.py compose 冷启动登录
```

调用 **macro / compose 仍只用片段中文名或 id**，路径由索引解析。

## 开屏广告

组合 **冷启动登录** = 注册登录目录下三块。无跳过按钮：`compose 冷启动登录 --skip dismiss_splash_ad`。

## 设备型号适配

见 [`设备适配/README.md`](设备适配/README.md)。
