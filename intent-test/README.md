# 意图测试（Intent Test）

基于 [Midscene.js](https://midscenejs.com/) 的 **AI 视觉 + 自然语言意图** 测试层。与 `midscene/` 的步骤型 YAML/TS 用例互补：

| 维度 | `midscene/` | `intent-test/`（本目录） |
|------|-------------|-------------------------|
| 用例表达 | 逐步 `aiAct` / `sleep` / `runAdbShell` | **用户意图 + 预期结果** |
| 维护成本 | 界面变动需改步骤 | 意图稳定，执行路径由 AI 自适应 |
| 适用场景 | 登录/充值等固定链路、游戏 spin 批量回归 | 新功能验收、手工用例快速自动化、探索性回归 |
| 执行引擎 | Midscene CLI / Vitest | 编译意图 → Midscene YAML → 复用 `midscene/scripts/midscene-run.mjs` |

**目标 App**：Yaahlan Android 包 `com.immomo.biz.yaahlan`（见 `midscene/.env`，与 `adb/adb/apps.py` 一致，勿用 SoulChill / Yaha）。

---

## 目录结构

```
intent-test/
├── README.md                 # 本文件
├── package.json              # npm 脚本（compile / run / md2intent）
├── .env.example              # 指向复用 midscene/.env
├── intents/                  # ★ 意图定义（人工维护或从用例转化）
│   ├── catalog.json          # 意图索引
│   ├── _fragments/           # setup.include 可复用片段
│   │   ├── base-navigation.yaml
│   │   └── gift-custom-search.yaml
│   └── 礼物/
│       └── custom-gift-uid-search.yaml
├── runners/
│   ├── compile-intent.mjs    # 意图 YAML → Midscene YAML
│   ├── intent-run.mjs        # 编译并执行（调 midscene-run）
│   └── md-to-intent.mjs      # temporary_testcase/*.md → intents/
├── templates/
│   └── intent.template.yaml  # 新建意图模板
└── .generated/               # 编译产物（gitignore）
```

---

## 快速开始

### 1. 环境（复用 midscene）

```bash
# 若 midscene 尚未配置
cd ../midscene && cp .env.example .env   # 填入 AI Key、设备、账号

cd ../intent-test
npm run doctor    # 检查 midscene/.env 与 ADB/WDA
```

### 2. 编写意图

复制 `templates/intent.template.yaml`，填入：

- **preconditions**：数据/角色/页面前提（给人看，也可写入 `aiContext`）
- **intent.action**：一句自然语言操作目标
- **intent.expected**：可验证的预期列表（每条编译为 `aiAssert`）

### 3. 运行

```bash
# 单条意图（Android）
npm run intent -- intents/房间/admin-ludo-billiards.yaml

# 按模块批量
npm run intent:module -- 房间

# 从 Markdown 用例表生成意图草稿
npm run md2intent -- ../temporary_testcase/房间管理员-更多面板Ludo台球.md

# 仅编译不执行
npm run compile -- intents/礼物/custom-gift-uid-search.yaml
```

---

## 意图 YAML 规范

```yaml
id: IT-ROOM-LUDO-001
name: 房间编辑管理员开启Ludo
module: 房间管理员-Ludo台球
platform: android          # android | ios
priority: P1
tags: [房间, 游戏, 管理员]

preconditions:
  - 账号拥有房间编辑权限且已在语音房

setup:
  launchApp: true
  steps:
    - act: 进入任意语音房
    - waitFor: 已在语音房内，可见礼物按钮
    - act: 打开礼物面板并切到定制礼物 tab

intent:
  action: 打开右下角更多面板，点击Ludo游戏入口开启游戏
  expected:
    - 房间进入Ludo游戏模式
    - 房内用户可见游戏界面

aiContext: >
  补充业务上下文即可；弹窗由全局策略默认处理（X 关闭、邀请拒绝）。

timeoutMs: 120000
```

**设计原则**

1. **action 写意图不写坐标**：「打开礼物面板搜索 uid」而非「点击 (540,960)」
2. **expected 可观测**：每条预期对应一次 `aiAssert`，避免「正常」「没问题」
3. **前置放 preconditions/setup**：角色权限、账号数据在 setup 或 MOA/Admin 脚本中准备，意图层只描述 UI 目标
4. **与手工用例对齐**：`对应测试点` → `tags` / `name`；`测试步骤+预期` → `action` + `expected`
5. **setup.include + setup.steps**：通用进帧用 `_fragments/` 片段；业务路径再写 `steps`（见下文）

### 全局弹窗策略（默认注入）

`compile-intent` 对**每条用例**自动：

1. 在 `agent.aiActContext` 合并弹窗规则（X 关闭、邀请拒绝、权限允许）
2. 在 setup 第一步注入 `popup-handling/dismiss_blocking_popups`（act + waitFor）

| 场景 | 默认行为 |
|------|----------|
| 带 X / × / Close 的业务弹窗、广告、活动 | 点 **X** 关闭，不点弹窗主体 |
| 邀请类（进房/游戏/语音房/好友） | 点 **拒绝** / Decline / Reject / 不了 |
| 系统权限、用户协议 | 点 **允许** / 好 / **同意** |
| 用例需通过弹窗进入场景 | `setup.acceptInvites: true` 或在 `aiContext` 写明 |

跳过或例外：

```yaml
setup:
  skipPopupDismiss: true   # 不注入 dismiss_blocking_popups 首步
  acceptInvites: true      # 邀请弹窗可点接受
  popupPolicy: none        # 不注入全局弹窗 aiContext
```

片段：`intents/_fragments/popup-handling.yaml` → `popup-handling/dismiss_blocking_popups`

### setup.include 基础片段

`intents/_fragments/base-navigation.yaml` 提供五底栏进帧路径，编译时展开为 `aiAct` / `aiWaitFor`：

| 片段名 | 效果 |
|--------|------|
| `base-navigation/enter_room_frame` | 底部 **Room** → 房间帧（默认推荐 tab） |
| `base-navigation/enter_message_frame` | 底部 **Message** → 消息帧 |
| `base-navigation/enter_moment_frame` | 底部 **Moment** → 动态帧（默认 Discover） |
| `base-navigation/enter_me_frame` | 底部 **Me** → 我的帧 |
| `base-navigation/enter_voice_room` | 进任意语音房（含 Room tab → 点房间） |
| `base-navigation/open_gift_panel` | 房内打开橙色礼物盒面板 |
| `base-navigation/tap_gift_panel_to_customize_tab` | 面板已开：点 tab → **滑动 tab 栏** → 点 Customize，全程不关面板 |
| `base-navigation/open_gift_panel_customize_tab` | 房内开面板 + 点 tab 到 Customize |
| `base-navigation/enter_voice_room_gift_customize_tab` | **完整路径**：进房 → 开面板 → 点 tab 到 Customize |
| `popup-handling/dismiss_blocking_popups` | 全局弹窗处理（compile 默认自动注入，也可手动 include） |
| `ensure_home_bottom_nav` | 回到首页并看见五底栏 |

`intents/_fragments/moments-navigation.yaml` 提供动态帧内导航（语音/视频动态回测共用）：

| 片段名 | 效果 |
|--------|------|
| `moments-navigation/enter_moment_discover_tab` | 进动态帧并停在 **Discover** |
| `moments-navigation/enter_moment_follow_tab` | 切到 **Follow** 关注 tab |
| `moments-navigation/open_moment_publish_editor` | 点 **+** 进入发布编辑页 |
| `moments-navigation/reset_moment_discover_ready` | 从详情/发布页返回 Discover 列表 |

```yaml
setup:
  launchApp: true
  include:
    - base-navigation/enter_room_frame
  steps:
    - act: 点击第一个推荐房间进入语音房
    - waitFor: 已在语音房内
```

业务片段见 `gift-custom-search.yaml`（兼容别名 `enter_voice_room_gift_custom`，推荐 `base-navigation/enter_voice_room_gift_customize_tab`）。

---

## 基础测试上下文（`config/base-profile.yaml`）

账号、房间、设备等**固定测试上下文**集中维护：

| 字段 | 说明 |
|------|------|
| `account.userId` | 当前真机登录 userId（如 `100261858`） |
| `account.tunnelMomoid` | Tunnel 抓包 momoid（默认与 userId 一致） |
| `room.voiceRoomId` | 默认语音房 roomId（如 `80954536`） |
| `device.androidDeviceId` | ADB 设备序列号 |
| `env.*` | 同步到 `midscene/.env` 的变量名 |

```bash
# 编辑 intent-test/config/base-profile.yaml 后，同步到 midscene/.env
npm run sync-profile

# compile / intent / preflight 会自动加载 base-profile（不覆盖 midscene/.env 已有值）
```

---

## 自动抓包写测试数据（跑用例前）

跑**定制礼物**意图时，`npm run intent` 会自动：

1. **preflight** — 从 Tunnel 抓包解析 `ownerUid` / `ownerNickname` / `giftName`，写入 `midscene/.env`
2. 若仍缺数据 → **seed UI**（`IT-SEED-GIFT-TUNNEL`：进 `TEST_VOICE_ROOM_ID` 指定房 → Customize → 切周榜 + 搜索）
3. **二次 preflight** — 再次写 env，然后执行正式用例

```bash
# 默认已含上述流程，直接跑即可
INTENT_CONTINUE=1 npm run intent -- intents/礼物/custom-gift-nickname-search.yaml

# 仅手动触发数据准备
npm run ensure-data -- intents/礼物/custom-gift-nickname-search.yaml

# 跳过自动准备（调试 UI 路径）
INTENT_SKIP_DATA_PREP=1 npm run intent -- intents/礼物/custom-gift-nickname-search.yaml

# 有抓包但不跑 seed UI
INTENT_SKIP_TUNNEL_SEED=1 npm run intent -- ...

# 数据未就绪则直接退出（不跑用例）
INTENT_REQUIRE_DATA=1 npm run intent -- ...
```

| 环境变量 | 说明 |
|----------|------|
| `INTENT_SKIP_DATA_PREP` | 跳过 preflight + seed |
| `INTENT_SKIP_TUNNEL_SEED` | 只 preflight，不跑 seed UI |
| `INTENT_REQUIRE_DATA` | 缺 uid/昵称时 exit 1 |
| `INTENT_PREFLIGHT_SINCE` | 抓包回溯秒数，默认 7200 |

---

## Tunnel 数据预检（跑用例前）

执行意图测试前，先用 Tunnel 抓包校验**测试数据是否就绪**，并自动生成 `midscene/.env` 中的定制礼物变量：

```bash
# 须在 App 内：登录 TEST_TUNNEL_MOMOID 对应账号 → 进房 → 打开礼物面板 Customize Tab
# 可选：切换定制礼物周榜、执行一次 uid/昵称搜索（便于发现搜索接口 keyword）
npm run preflight -- --write-env

# 指定 momoid / 缩短回溯窗口
npm run preflight -- --momoid 100312107 --since 3600 --write-env
```

| 输出 | 说明 |
|------|------|
| `.generated/preflight/latest.json` | 预检报告（checks + intents 就绪表 + 建议 env） |
| `.generated/preflight/gift-custom-search.<momoid>.json` | 按 momoid 归档 |
| `midscene/.env`（`--write-env`） | 写入 `TEST_CUSTOM_GIFT_*` / `TEST_TUNNEL_MOMOID` / `TUNNEL_KEYWORD_*` |

预检项：Tunnel Cookie、**getGiftTabListV3 Customize Tab**（`extra.userId` + `name`）、searchCustomGift 搜索命中、getTotalCustomGiftRankList（昵称补全）、8 条意图就绪。抓包建议 `g_appid=yaahlan`（见 `TUNNEL_G_APPID`）。

---

## Tunnel 抓包验收（UI + 接口双验）

与 `adb-tunnel-verify` / `Tunnel/tunnel_execute.py` 同源：**Midscene 验 UI，`tunnel-verify.py` 验接口**。

```
intents/*.yaml（含 tunnel: 块）
        │  compile-intent.mjs
        ▼
.generated/*.midscene.yaml + *.tunnel.json
        │  intent-run.mjs（逐条）
        ├─► Midscene AI 视觉
        └─► python3 runners/tunnel-verify.py（wait_for_tunnel）
```

### tunnel 块示例

```yaml
tunnel:
  catalogId: gift_custom_search          # 合并 adb/config/tunnel_capture_catalog.json
  keyword: ${TUNNEL_KEYWORD_CUSTOM_GIFT_SEARCH}
  momoid: ${TEST_TUNNEL_MOMOID}          # 须与真机登录 userId 一致
  waitSeconds: 45
  expectResponseEc: 200
  requestContains:
    - ${TEST_CUSTOM_GIFT_UID}
```

| 字段 | 说明 |
|------|------|
| `catalogId` | 可选，从抓包 catalog 继承 keyword / expectEc |
| `keyword` | URL 子串（客户端过滤），见 [Tunnel 技能](../.cursor/skills/tunnel-read/SKILL.md) |
| `requestContains` / `responseContains` | 抓包 body 须含的子串 |
| `account` | 或用 `adb/录制脚本/索引.json` 的 testAccounts 键 |

**前置**：`Tunnel/.env.local` 或 `MOA/.env.local` 配置 `TUNNEL_COOKIE`；`TEST_TUNNEL_MOMOID` 写入 `midscene/.env`。

**环境变量**：

| 变量 | 用途 |
|------|------|
| `INTENT_TUNNEL=0` | 仅跑 UI，跳过抓包 |
| `INTENT_CONTINUE=1` | 单条失败后继续 |
| `TUNNEL_KEYWORD_CUSTOM_GIFT_SEARCH` | 搜索接口 keyword（上线后按实际 URL 修改） |
| `TEST_CUSTOM_GIFT_GIFT_NAME` | 定制礼物展示名（preflight 从 searchCustomGift / 周榜 / Customize Tab 抓包写入） |

验收结果：`.generated/<id>.tunnel.result.json`，含 `tunnelUrl` 可打开 Tunnel 详情页。

---

## 与手工用例工作流

```
PRD / 手工用例 (temporary_testcase/*.md)
        │  md-to-intent.mjs（草稿）
        ▼
   intents/*.yaml（人工精简 action/expected + tunnel）
        │  compile-intent.mjs
        ▼
   .generated/*.midscene.yaml + *.tunnel.json
        │  intent-run.mjs
        ├─► Midscene 报告（midscene/midscene_run/）
        └─► Tunnel 结果 JSON
```

---

## 动态 · 文字 / 图片 / 视频回测（优先）

对照 `documents/moments/basic module.md` 与 `video.md`，按内容类型拆分意图文件。**语音动态**用例在 `voice-moment-*.yaml`，当前暂缓执行（见 `catalog.json` → `deferred`）。

| 类型 | 意图文件 | 说明 |
|------|----------|------|
| 通用入口 | `moment-discover-common.yaml` | Discover 入口、tab 切换、发布 + |
| 文字 | `text-moment-publish.yaml` / `text-moment-list-detail.yaml` | 纯文字发布、列表省略、详情点赞评论 |
| 图片 | `image-moment-publish.yaml` / `image-moment-list-detail.yaml` | 选图发布、列表/详情大图 |
| 视频 | `video-moment-publish.yaml` / `video-moment-list-detail.yaml` | 选视频、互斥、全屏播放 |

```bash
# 建议顺序：通用 → 文字发布造数 → 文字列表详情 → 图片 → 视频
INTENT_CONTINUE=1 npm run intent -- intents/动态/moment-discover-common.yaml
INTENT_CONTINUE=1 npm run intent -- intents/动态/text-moment-publish.yaml
INTENT_CONTINUE=1 npm run intent -- intents/动态/text-moment-list-detail.yaml
INTENT_CONTINUE=1 npm run intent -- intents/动态/image-moment-publish.yaml
INTENT_CONTINUE=1 npm run intent -- intents/动态/image-moment-list-detail.yaml
INTENT_CONTINUE=1 npm run intent -- intents/动态/video-moment-publish.yaml
INTENT_CONTINUE=1 npm run intent -- intents/动态/video-moment-list-detail.yaml
```

**数据前置**：列表/详情用例依赖 Discover 已有对应类型动态；各类型 P0 发布用例（TXT-PUB-002 / IMG-PUB-002 / VID-PUB-004）可先行造数。

---

## 动态 · 语音动态（暂缓）

对照 `documents/moments/basic module.md` 一级模块的语音扩展用例，文件已就绪，待文字/图片/视频回测稳定后再跑：

- `intents/动态/voice-moment-list.yaml`
- `intents/动态/voice-moment-publish.yaml`
- `intents/动态/voice-moment-detail.yaml`

```bash
# 暂缓；需要时再执行
INTENT_CONTINUE=1 npm run intent -- intents/动态/voice-moment-publish.yaml
```

---

## 相关文档

- Midscene 环境与 API：[../midscene/README.md](../midscene/README.md)
- 手工用例格式：`scripts/check_testcase_md.py`
- ADB 坐标录制（与意图互补）：[../adb/自动化用例/README.md](../adb/自动化用例/README.md)
