---
name: intent-test
description: 意图驱动 UI 自动化：基于 midscene AI 视觉，用自然语言 intent.action + expected 执行真机测试。在用户要「意图测试」「AI 视觉自动化」「从手工用例转自动化」时使用。
---

# 意图测试（intent-test）

## 何时使用

- 新功能需要 **快速 UI 自动化**，不想写逐步坐标/步骤
- 已有 `temporary_testcase/*.md` 手工用例，需转为可执行自动化
- 与 `midscene/` 步骤型用例互补：固定链路用 midscene，探索/验收用 intent-test
- 从需求文档/PRD 生成可执行的意图测试 YAML

## 目录

- 工程根：`intent-test/`
- 意图定义：`intent-test/intents/<功能域>/<模块>/xxx.yaml`
- 模块注册：`intent-test/intents/catalog.json`
- 验证片段：`intent-test/intents/_fragments/moments-verify.yaml` 等
- 运行器：`intent-test/runners/`
- 复用环境：`../midscene/.env` + `../midscene/scripts/midscene-run.mjs`

## 模块化组织（必须遵循）

### 文件组织规则

**每个业务模块独立一个 YAML 文件**，禁止将所有 case 堆在一个大文件中：

```
intent-test/intents/
├── 动态/
│   └── 语音动态/
│       ├── voice-record.yaml        # 录制弹窗模块
│       ├── voice-editor.yaml        # 编辑页语音条模块
│       ├── voice-publish-combo.yaml  # 发布组合模块
│       ├── voice-browse.yaml        # 浏览播放模块
│       ├── voice-profile.yaml       # 个人主页语音条模块
│       └── voice-regression.yaml    # 回归模块
├── catalog.json                     # 模块注册表
```

### 模块粒度

按「业务操作对象」或「功能页面」拆分模块，每个模块内 case 数量控制在 **10-20 条**：
- 一个独立页面/弹窗 = 一个模块（如录制弹窗、编辑页）
- 一个操作链路 = 一个模块（如发布组合、浏览播放）
- 回归 case 独立一个模块

### catalog.json 注册

每个模块文件必须注册到 `intents/catalog.json`，支持按模块执行：

```json
{
  "modules": {
    "语音动态-录制弹窗": {
      "label": "语音动态 · 录制弹窗",
      "intents": ["intents/动态/语音动态/voice-record.yaml"]
    }
  }
}
```

### 按模块执行

```bash
# 执行单个模块
npm run intent -- --module 语音动态-录制弹窗

# 执行单个文件
npm run intent -- intents/动态/语音动态/voice-record.yaml

# 执行单条 case
npm run intent -- --id IT-MOM-VOICE-PUB-001
```

## 从需求文档生成意图 case 的规则

### 生成前置（必须）

遵循 `testcase-generator` SKILL 及 `rules/version_testcase_generation_rules.md` 的知识库查找规则：
1. 先读 `documents/` 对应模块文档
2. 动态域另读 `documents/moments/` 对应文件
3. 用 `testcase-kb/` 补充
4. 若涉及 bug 回归，查 `bug-kb/`

### UI 设计稿驱动（必须）

生成意图 case 时**必须结合 UI 设计稿**（截图/原型图），用于：
1. **精确描述 UI 元素**：按钮样式（圆形/方形/颜色）、位置（左侧/右上角/底部工具栏）、状态（高亮/置灰/动画）
2. **明确交互层级**：弹窗类型（底部半屏/居中弹窗/全屏）、动画（波纹/流动/淡入）
3. **确认页面布局**：元素排列顺序（上下/左右/并排）、各区域相对位置关系
4. **补充文案与图标**：按钮文案（中英文）、图标含义、状态指示

**规则：**
- 若用户提供了 UI 设计稿，expected 中的 UI 描述**必须与设计稿一致**，不可凭空猜测
- action/expected 中涉及 UI 操作时，使用设计稿中可见的元素描述（如「大圆形紫色录制按钮」而非「录制按钮」）
- waitFor 中使用设计稿可验证的视觉特征作为判定依据
- 未提供设计稿时，使用通用描述，后续用户补充设计稿后细化

### 排除范围（不生成）

以下场景 **不生成** 意图测试 case：
- **屏幕适配**：大屏/小屏适配验证（意图测试固定一台设备执行）
- **多语言**：EN/AR/TR/RU 语言环境切换验证（意图测试固定一种语言环境）
- **RTL 镜像**：阿语从右到左布局验证
- **纯后端逻辑**：无 UI 交互的纯服务端验证（用 Tunnel/接口测试覆盖）
- **安装/升级路径**：安装、增量升级、跨版本升级（非 UI 自动化范畴）
- **数据迁移/缓存兼容**：本地缓存、登录态迁移等依赖多版本环境的验证
- **老版本回归/新旧对比**：老版本功能回测、升级前后对比（意图测试只验证当前版本行为）
- **跨端验证**：iOS/Android 双端对比、平台兼容性验证（意图测试固定单一平台执行）

---

### 系统覆盖方法（强制遵循）

#### 1. 模块内聚原则

**以「业务操作对象」为单位内聚，一个对象的全链路写完再写下一个。**

每个操作对象内推荐用例顺序：
1. **页面展示**：进入页面后 UI 元素是否正确渲染（布局、文案、图标、初始状态）
2. **核心操作流程**：正向执行路径（触发操作 → 确认/提交 → 操作成功）
3. **边界值 & 反向用例**：必填项为空、字数/数量上限、频控、并发等
4. **数据联动 & 状态验证**：操作完成后数据展示是否正确（列表、详情、计数等）
5. **消息通知**（如适用）：操作触发的通知是否正确下发

❌ 禁止按技术层级横向拆分（如先写所有页面展示，再写所有操作流程）
✅ 每个对象写完全链路再下一个

#### 2. 矩阵式组合覆盖

对 PRD 中涉及的**状态 × 行为 × 角色**维度，逐条生成用例，不合并覆盖：

- **状态维度**：如已有/新增、开启/关闭、满足条件/不满足、首次/非首次
- **行为维度**：如录制/暂停/取消/播放/删除/替换/重新录制
- **角色维度**：如本人/他人、普通用户/VIP、关注/陌生人

示例：若录制语音有 3 种操作状态 × 2 种结果，至少生成 6 条用例。

#### 3. 边界值显式覆盖

每个数值约束生成 **3 条**：临界点本身、超过上限、不足下限。

| 约束类型 | 覆盖要求 |
|---------|---------|
| 时长限制 | 最小时长录制、刚好最大时长、超过最大时长（自动停止） |
| 数量限制 | 0 个（空态）、1 个（最小有效）、达到上限、超过上限 |
| 文本长度 | 空字符、1 字符、最大字符、超最大字符（截断/提示） |
| 文件大小 | 正常大小、接近上限、超过上限 |

#### 4. 正向 + 反向 + 异常全覆盖

每个功能点至少覆盖以下三类：

| 类型 | 说明 | 示例 |
|------|------|------|
| 正向 | 正常流程走通 | 录制 → 发布成功 |
| 反向 | 主动操作中断/取消 | 录制中取消、编辑页返回放弃 |
| 异常 | 系统或环境异常 | 无麦克风权限、网络断开、存储满 |

#### 5. 新接口空态/异常覆盖

涉及新接口时**必须**额外覆盖：
- **data 为空（空态）**：接口正常但无数据，UI 展示空态占位
- **服务异常**：接口报错/超时，UI 展示错误提示且不崩溃

#### 6. 跨场景/跨入口回归

若 `documents/` 中定义了功能的多个入口或场景，意图测试须抽样覆盖：
- 同一功能在不同入口的表现（如：动态发布 → 首页入口 vs 个人主页入口）
- 同一内容在不同页面的展示（如：语音条 → 动态列表 vs 动态详情 vs 个人主页）

#### 7. Tunnel 抓包验证（UI 不适合验证时）

当 UI 界面不适合直接验证结果时（如：数据是否正确写入后端、接口参数是否正确、异步处理结果），**必须结合接口文档使用 Tunnel 抓包验证**：

**适用场景：**
- 发布/提交后需验证请求参数正确性（如语音条时长、文件 URL 等）
- UI 上看不到的后端状态变更（如审核状态、统计数据）
- 接口返回值校验（如错误码、业务字段）
- 数据一致性验证（如列表接口返回的内容与发布内容一致）

**配置来源：** 抓包 uid（momoid）从 `intent-test/config/base-profile.yaml` 中 `account.tunnelMomoid` 获取，无需硬编码。

**YAML 写法：** 在 intent YAML 中添加 `tunnel` 块指定需验证的接口：

```yaml
tunnel:
  api: /api/v1/moment/publish
  method: POST
  assertions:
    - field: request.body.voice_duration
      op: gte
      value: 3
    - field: response.data.moment_id
      op: exists
```

**注意事项：**
- Tunnel 验证在 UI 操作通过后自动执行
- 需提供接口文档或已知的接口路径与字段结构
- 通过 `INTENT_TUNNEL=0` 可临时跳过 Tunnel 验证仅跑 UI

#### 8. 神秘人逻辑评估（语音房功能）

凡需求涉及语音房内展示或操作，**必须评估是否影响神秘人逻辑**：
- 若影响：补充「神秘人作为操作方」「神秘人作为被展示方」「非神秘人视角」用例
- 若不影响：在 YAML 注释中注明「已评估，与神秘人逻辑无关」

---

### 优先级选择

意图测试主要覆盖 **P0（核心功能）和 P1（重要功能）**：
- P0：核心用户路径、主链路必须通过的功能
- P1：常用功能、重要交互流程
- P2/P3：仅在资源充裕时选择性覆盖

---

### 生成后质量自检（必须）

生成完成后逐项确认：
- [ ] 每个操作对象的全链路（展示→操作→数据联动）在同一模块内写完
- [ ] PRD 中每条变更至少对应 1 条正向 + 1 条反向/边界用例
- [ ] 涉及数值约束的场景已显式覆盖边界值（上限/下限/临界点）
- [ ] 状态 × 行为的组合矩阵已逐条覆盖，无合并遗漏
- [ ] 涉及新接口已覆盖空态和服务异常
- [ ] UI 不适合验证的场景已配置 Tunnel 抓包验证（uid 来自 base-profile.yaml）
- [ ] 涉及语音房已评估神秘人逻辑
- [ ] 未包含排除范围内的用例（适配/多语言/纯后端/升级路径/老版本回归/跨端）

---

### 用例 ID 命名规范

格式：`IT-{模块缩写}-{子模块缩写}-{三位序号}`

| 模块 | 缩写示例 |
|------|---------|
| 动态 Moment | `MOM` |
| 礼物 Gift | `GIFT` |
| 房间 Room | `ROOM` |
| 消息 Message | `MSG` |
| 个人 Me | `ME` |

子模块示例：`TXT-PUB`(文字发布)、`VOICE-PUB`(语音发布)、`IMG-PUB`(图片发布)

### verify 验证片段使用

发布类用例推荐使用 `verify` 字段引用常用验证片段（在 intent.action 之后执行）：

```yaml
verify:
  include:
    - moments-verify/verify_text_publish_and_visible
```

可用验证片段（`_fragments/moments-verify.yaml`）：
- `verify_publish_success` — 发布成功 toast + 跳转
- `verify_text_publish_and_visible` — 文字动态完整验证
- `verify_image_publish_and_visible` — 图片动态完整验证
- `verify_video_publish_and_visible` — 视频动态完整验证
- `verify_voice_publish_and_visible` — 语音动态完整验证
- `verify_publish_blocked` — 发布按钮不可点击
- `verify_publish_toast_error` — 错误 toast 提示
- `delete_latest_moment` — 删除刚发布动态（清理数据）

## 执行步骤

1. **环境**：`cd midscene && cp .env.example .env`（若未配置）；`cd intent-test && npm install`
2. **数据预检**（定制礼物等依赖 Tunnel 数据的模块）：真机进房开礼物面板后 `npm run preflight -- --write-env`
3. **自检**：`npm run doctor`
4. **编写/转化意图**：
   - 复制 `templates/intent.template.yaml`
   - 或 `npm run md2intent -- ../temporary_testcase/xxx.md`
5. **编译**：`npm run compile -- intents/模块/xxx.yaml`
6. **执行**：
   - 单端 Android：`npm run intent -- intents/模块/xxx.yaml` 或 `npm run intent:module -- 房间`
   - 双端并行：`npm run intent:dual -- intents/模块/xxx.yaml`（按 YAML `platform` 分流到 Android/iOS 真机）
   - 仅 iOS：`npm run intent:platform -- --platform ios intents/模块/xxx.yaml`
7. **报告**：
   - 单端：`midscene/midscene_run/report/<模块>-summary/index.html`
   - 双端：各端 `<id>-android|ios/` + 汇总 `*-dual-summary/index.html`

## 意图格式要点

- `intent.action`：用户目标（自然语言，不写坐标）
- `intent.expected`：每条 → 一次 `aiAssert`
- `verify.include`：action 之后、assert 之前执行的验证步骤片段
- `preconditions`：给人看；账号/数据用 MOA/Admin 准备
- `setup.include`：引用 `intents/_fragments/base-navigation.yaml` 等（Room/Message/Moment/Me 进帧）
- `setup.deeplink` / `launchApp`：进已登录态或冷启动

## 与 midscene 关系

```
intent YAML → compile-intent.mjs → .generated/*.midscene.yaml → midscene-run.mjs → 报告 → generate-report.mjs → 聚合报告
```

- 相关文档：[intent-test/README.md](../../intent-test/README.md)、[tunnel-read](../tunnel-read/SKILL.md)

## Case 间智能回退

执行多条 case 时，**不再每条都重启 App**，而是智能回退：

1. 第一条 case 正常冷启动
2. 后续 case 执行前：按 back 键最多 2 次，检测是否回到主界面（首五帧：游戏/房间/消息/动态/我的）
3. 若已在主界面 → 跳过 force-stop + 重启，直接从当前页面开始导航
4. 若 2 次 back 仍未回到主界面 → 执行完整的 force-stop + 重启

此策略大幅减少执行时间（省去每条约 5-6s 的冷启动等待），通过 `INTENT_SKIP_RELAUNCH` 环境变量自动控制，无需手动配置。

## 自动调试模式（默认开启）

`config/base-profile.yaml` 中 `intent.autoDebug: true` 时，**所有模块**跑批时自动启用（voice-record 验证沉淀）：

| 能力 | 环境变量 | 行为 |
|------|----------|------|
| 失败继续 | `INTENT_CONTINUE=1` | 单条失败不中断，跑完全部再汇总 |
| setup 重试 | `INTENT_SETUP_RETRY=1` | setup/导航失败或 replan 超限时，**强制冷启动 App 重跑 1 次** |
| 断言 auto-fix | `INTENT_AUTO_FIX=1` | 跑完后分析 Midscene Reason，自动修正 YAML 中可识别的断言措辞 |
| 聚合报告 | （内置） | 每条 case 结束生成卡片报告，截图可点击查看大图 |

关闭：`intent.autoDebug: false` 或分别设 `setupRetry: false` / `autoFix: false`。

### Agent / 人工调试规则（必须）

1. **case 失败直接改 YAML**，不要停下来问用户（坐标、断言、步骤、skip）
2. **优先稳定手段**：弹窗内固定按钮用 `tap: [x%, y%]`；位置不固定的用 `act`；时长用 `sleep` 不用「录制约 X 秒」
3. **断言只用正面描述**：写「可见 Post 按钮」，不写「Record 弹窗不再可见」（AI 易误判）
4. **禁止动态视觉断言**：不写「图标变化」「波纹动画」「播放进度变化」
5. **弹窗场景**加 `skipPopupDismiss: true`，避免全局 dismiss 干扰
6. **坐标校准**：uiautomator dump 取 bounds → 换算 `[cx/W, cy/H]`，沉淀到 `_fragments/*-coords.yaml`
7. **产品行为变更**：确认后直接改 case 或 `skip: true` + `skipReason`，不要保留过时流程（如已废弃的确认弹窗）

### setup 重试触发条件

`runners/auto-fix-assertions.mjs` 识别以下失败为可重试：
- Reason 含 Discover/发现页、未到编辑页、不存在 Post/Record/弹窗等
- Midscene replan 超限（`Replanned N times`）
- XML 解析错误（flaky）

重试流程：`失败 → 强制 INTENT_SKIP_RELAUNCH=0 重新编译 → 冷启动重跑 1 次`

### Case 编写模板（稳定弹窗/录制类）

```yaml
setup:
  launchApp: true
  skipPopupDismiss: true          # 弹窗内操作必加
  include:
    - moments-navigation/open_moment_publish_editor
  steps:
    - act: 点击 "+ Add Voice" 按钮   # 位置不固定 → AI
    - waitFor: 出现 Record 弹窗，可见 "Tap to Record"
    - tap: [0.50, 0.785]           # 弹窗内固定按钮 → 坐标
      afterSleep: 500
    - sleep: 4000                   # 精确控时长
    - tap: [0.50, 0.785]
      afterSleep: 2000

intent:
  action: 观察停止录制后的界面
  expected:
    - 可见 "Re-record" 和 "Use" 按钮文字   # 正面文字断言
```

### 推荐执行命令

```bash
# 按模块跑（自动调试模式默认开启）
npm run intent:module -- 语音动态-录制弹窗

# 单条调试
npm run intent -- --id IT-MOM-VOICE-PUB-009

# 临时关闭 auto-fix / setup 重试
INTENT_AUTO_FIX=0 INTENT_SETUP_RETRY=0 npm run intent -- intents/xxx.yaml
```

## 超时控制

每条用例默认 **5 分钟**超时限制（`CASE_TIMEOUT_MS` 环境变量，毫秒）。超时后进程被 SIGTERM 中断，自动继续下一条用例。聚合报告中超时用例以**橙色"超时"**标签标注。

```bash
# 使用默认 5 分钟超时
npm run intent -- intents/动态/voice-moment-publish.yaml

# 自定义超时（如 3 分钟）
CASE_TIMEOUT_MS=180000 npm run intent -- intents/动态/voice-moment-publish.yaml
```

## 双端并行

`config/base-profile.yaml` 中维护 `platforms.android` / `platforms.ios`（设备 ID、WDA、包名、分辨率）。跑前：

```bash
npm run doctor                    # 检查 ADB + WDA（iOS 可选）
npm run sync-profile              # Android env → midscene/.env
npm run sync-profile -- --ios     # iOS env

INTENT_CONTINUE=1 npm run intent:dual -- intents/动态/moment-discover-common.yaml
```

- orchestrator 只跑一次数据准备；worker 设 `INTENT_SKIP_DATA_PREP=1`
- 用例需显式标注 `platform: android` 或 `platform: ios` 才会被对应 worker 执行
- 结果 JSON：`.generated/runs/android-latest.json` / `ios-latest.json`

## Tunnel 集成

意图 YAML 可含 `tunnel:` 块；`intent-run` 在 UI 通过后自动调用 `runners/tunnel-verify.py`（复用 `adb.adb.tunnel_verify.wait_for_tunnel`）。

**跑用例前预检**（从 Tunnel 拉榜/面板数据，写入 `midscene/.env`）：

```bash
npm run preflight -- --write-env
python3 intent-test/runners/tunnel-preflight.py --momoid <userId> --since 7200 --write-env
```

```bash
# 仅 UI
INTENT_TUNNEL=0 npm run intent -- --id IT-GIFT-UID-001

# UI + Tunnel（默认）
npm run intent -- --id IT-GIFT-UID-001
```
