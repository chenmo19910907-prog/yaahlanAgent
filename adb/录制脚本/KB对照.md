# 知识库 ↔ 录制脚本对照

真机验收（1080×2340，vivo V1838A）后落库。片段按 **发版回归一级模块** 分目录（与 `regression-kb` 一致）。

## 注册登录 · `片段/注册登录/`

**默认（`索引.json` → `loginDefaults`）**：区号 **+86**，手机号 **13311111115**，验证码 **000000**。分步片段可省略 `--text`。

| 知识库 | 脚本 | id |
|--------|------|-----|
| 启动 Yaahlan | 启动Yaahlan | launch-yaahlan |
| 冷启动开屏广告 | 跳过开屏广告 | dismiss-splash-ad |
| 语言选择 Next | 登录-语言下一步 | login-lang-next |
| 勾选协议 + 手机入口 | 登录-勾选协议打开手机 | login-agree-phone |
| 输入手机号 + Get via SMS | 登录-手机号发短信 | login-phone-sms（默认 QA 号） |
| 输入验证码 | 登录-输入验证码 | login-verify-code（默认 000000） |
| QA 全流程 +86 | 手机号登录 | login-phone-full |
| **公会长** +86 13311111111（userId 100465989） | 公会长手机号登录 | login-guild-leader |
| **家族长** +86 13311111112（userId 100486375，家族 CCVC） | 家族长手机号登录 | login-family-leader |
| 登录后/切页偶发弹窗 | **关闭常见弹窗**（推荐） | dismiss-common-popups |
| 同上（兼容旧名） | 登录后关闭弹窗 | login-dismiss-popup |

**常见弹窗**（测试包偶发）：运营礼包全屏、Account Security 绑定提示、Crowd Testing 众测、退出 Yaahlan 双按钮。脚本默认尝试关闭；误点风险用 `--skip dismiss_popup_taps`。

测试账号见 `索引.json` → `testAccounts`（`guildLeader` / `familyLeader`）。

```bash
python3 adb/adb_execute.py compose 冷启动登录
python3 adb/adb_execute.py compose 公会长冷启动登录
python3 adb/adb_execute.py compose 家族长发布图片动态
python3 adb/adb_execute.py macro 关闭常见弹窗
python3 adb/adb_execute.py macro 手机号登录 --skip login_lang
python3 adb/adb_execute.py macro 发布图片动态 --skip dismiss_popup_taps   # 仅 BACK，不点 Cancel 坐标
python3 adb/adb_execute.py macro 登录-输入验证码          # 默认 000000
python3 adb/adb_execute.py macro 登录-手机号发短信        # 默认 13311111115
```

## 首页-游戏帧 · `片段/首页-游戏帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Game | 切换游戏底栏 | game-tab |

## 首页-房间帧 · `片段/首页-房间帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Room | 切换房间底栏 | room-tab |

## 消息帧 · `片段/消息帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Message | 切换消息底栏 | msg-tab |

## 动态帧 · `片段/动态帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Moment | 切换动态底栏 | moment-tab |
| 关注 tab | 切换动态关注tab | moment-follow-tab |
| 发布【➕】/ 编辑页 | 打开动态发布页 | open-moment-compose |
| 发布纯文本 | 发布纯文本动态 | post-moment |
| 发布视频 | 发布视频动态 | post-video-moment |
| 发布单图 | 发布图片动态 | post-image-moment |
| 个人动态列表 | 进入我的动态列表 | my-moments-list |

## 我的帧 · `片段/我的帧/`

| 知识库 | 脚本 | id |
|--------|------|-----|
| 底栏 Me | 切换我的底栏 | me-tab |
| 点头像 → 资料详情 | 进入个人资料详情页 / 我的页进入个人资料详情 | my-profile |
| 钱包 | 进入钱包 | wallet |
| 设置 | 进入设置 | settings |
| 设置页 Log out | 设置页退出登录 | logout-from-settings |
| 退出登录（Me→设置→Log out） | 退出登录 | logout |

## 组合（按模块）

| 模块 | 场景 | 组合名 | 路径 |
|------|------|--------|------|
| 注册登录 | 冷启动 + 登录 | 冷启动登录 | `组合/注册登录/` |
| 注册登录 | 公会长冷启动 | 公会长冷启动登录 | `组合/注册登录/` |
| 动态帧 | 发动态（已在 App） | 发布纯文本 / 视频 / **图片** 动态 | `组合/动态帧/` |
| 动态帧 | 公会长冷启动并发图 | 公会长发布图片动态 | `组合/动态帧/` |
| 我的帧 | 进资料页（已在 App） | 进入个人资料详情页 | `组合/我的帧/` |

## 暂不可 ADB 固化

- 第三方授权、完善资料多步、支付、进房深度操作等（待补模块目录：语音房、支付、公会…）
