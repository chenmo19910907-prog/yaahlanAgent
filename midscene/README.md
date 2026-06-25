# Midscene.js 移动端 AI 自动化测试指南

基于 [Midscene.js](https://midscenejs.com/) 的 AI 视觉驱动自动化测试工程，支持 **iOS** 和 **Android** 双端。  
测试使用自然语言描述操作意图，由 AI 模型（GPT-4o 等）理解截图并执行，无需 XPath / ID 选择器。

---

## 目录

1. [核心概念](#一核心概念)
2. [工程结构](#二工程结构)
3. [环境准备（从零开始）](#三环境准备从零开始)
   - [Node.js 与依赖](#1-nodejs-与依赖)
   - [AI 模型配置](#2-ai-模型配置)
   - [iOS 环境](#3-ios-环境准备)
   - [Android 环境](#4-android-环境准备)
4. [配置文件说明](#四配置文件说明)
5. [用例设计规范](#五用例设计规范)
6. [运行测试](#六运行测试)
7. [查看测试报告](#七查看测试报告)
8. [常见问题排查](#八常见问题排查)
9. [调试记录与经验沉淀](#九调试记录与经验沉淀)

---

## 一、核心概念

### Midscene.js 是什么？

Midscene.js 是一个 AI 视觉驱动的自动化测试框架：

- **截图驱动**：每次操作前对设备屏幕截图，AI 模型理解界面内容
- **自然语言指令**：用中文或英文描述操作，AI 定位并执行
- **无需元素选择器**：不依赖 XPath、AccessibilityID、坐标等脆性定位方式
- **双端支持**：iOS 通过 WebDriverAgent，Android 通过 ADB

### 核心 API

| API | 作用 |
|-----|------|
| `aiAct('点击登录按钮')` | 执行一个操作，AI 理解并定位元素 |
| `aiWaitFor('出现首页底部导航栏')` | 等待某个状态出现（有超时机制） |
| `aiAssert('当前在登录页面')` | 断言当前界面满足某个条件 |
| `aiQuery({ text: '用户名' })` | 从界面提取信息并返回结构化数据 |

---

## 二、工程结构

```
midscene-e2e/
├── testcases-yaml/                     # ★ YAML 用例目录（Midscene 原生格式，推荐优先维护）
│   ├── android/
│   │   ├── login-p1.yaml              # 登录模块 P1（手机号验证码登录）
│   │   ├── login-p2.yaml              # 登录模块 P2（异常场景）
│   │   └── recharge-p1.yaml           # 充值模块 P1（EGP50.60 钱包充值）
│   ├── ios/
│   │   ├── login-p1-trigger.yaml      # iOS 登录 P1 阶段1：启动 App → 触发 SMS
│   │   ├── login-p1-complete.yaml     # iOS 登录 P1 阶段2：填入验证码 → 断言首页
│   │   └── recharge-p1.yaml           # iOS 充值模块 P1
│   └── web/
│       └── run-eid2026.yaml           # Eid 2026 活动页加载验证（Midscene web 模式）
├── testcases-ts/                       # TypeScript 用例目录
│   ├── android/
│   │   ├── 02-live-room.test.ts       # 直播间模块
│   │   ├── 03-recharge.test.ts        # 充值模块
│   │   ├── 04-profile.test.ts         # 个人主页模块
│   │   └── planet.test.ts             # 星球模块
│   ├── ios/
│   │   ├── 01-login.test.ts
│   │   ├── 02-live-room.test.ts
│   │   ├── 03-recharge.test.ts
│   │   └── 04-profile.test.ts
│   ├── web/
│   │   └── run-eid2026.ts             # Eid 2026 活动页（Android WebView raw CDP 模式）
│   └── temporary_testcase/
│       └── eid2026-cases.json         # eid2026 测试用例数据
├── scripts/
│   └── midscene-run.mjs               # YAML 测试执行包装器
│                                      #   Android：并行轮询验证码 + adb push 写入设备
│                                      #   iOS：两阶段执行 + 动态注入 TEST_VERIFY_CODE
├── utils/
│   ├── env.ts                         # 环境变量统一读取 + AI 上下文常量
│   ├── api.ts                         # getVerifyCode 接口封装
│   └── sc-webview.ts                  # SoulChill WebView CDP 连接工具（Android）
├── .env                               # 本地配置（不提交 git）
├── .env.example                       # 配置模板（提交 git，给团队成员参考）
├── vitest.config.ts                   # TypeScript 测试框架配置
└── package.json
```

---

## 三、环境准备（从零开始）

### 1. Node.js 与依赖

要求 **Node.js >= 18**。

```bash
# 检查版本
node -v

# 克隆 / 进入项目目录后安装依赖
npm install
```

---

### 2. AI 模型配置

Midscene 通过视觉大模型分析截图，必须配置 AI API Key。

```bash
cp .env.example .env
```

编辑 `.env`，填入模型配置：

```dotenv
# https://midscenejs.com/zh/model-common-config#doubao-seed-model
```

---

### 3. iOS 环境准备

iOS 自动化基于 **WebDriverAgent（WDA）**，WDA 是苹果官方 XCTest 框架封装的 HTTP 服务，Midscene 通过它控制 App。

#### 前置要求

- macOS + Xcode（含命令行工具）
- 目标设备：iOS 真机或模拟器

#### 方式 A：模拟器

1. 在 Xcode 中打开 Simulator，启动目标模拟器
2. 参考 [Appium WDA 文档](https://appium.github.io/appium-xcuitest-driver/5.12/run-prebuilt-wda/) 编译并启动 WDA：

   ```bash
   # 本项目已有 WDA 源码（本地路径）
   # /Users/momo/sc-qa-code/WebDriverAgent
   # /Users/momo/WebDriverAgent

   cd /Users/momo/sc-qa-code/WebDriverAgent
   xcodebuild -project WebDriverAgent.xcodeproj \
     -scheme WebDriverAgentRunner \
     -destination 'platform=iOS Simulator,name=iPhone 15' \
     test
   ```

3. 看到 `ServerURLHere->http://localhost:8100<-ServerURLHere` 即表示 WDA 启动成功

#### 方式 B：真机

1. 参考 [Real Device Configuration](https://appium.github.io/appium-xcuitest-driver/5.12/real-device-config/) 配置开发者证书和 WDA 签名

2. 编译并安装 WDA 到真机，启动后用 `iproxy` 做端口转发（**必须**，WDA 端口在设备上，需映射到 Mac）：

   ```bash
   # 安装 iproxy（如未安装）
   brew install libusbmuxd

   # 将设备 8100 端口映射到本机 8100
   iproxy 8100 8100
   ```

   > `iproxy` 需持续运行，建议开一个独立终端窗口。

3. 验证 WDA 是否正常：

   ```bash
   curl http://localhost:8100/status
   # 返回包含 "ready":true 的 JSON 即正常
   ```

4. 在 `.env` 中配置：

   ```dotenv
   WDA_HOST=localhost
   WDA_PORT=8100
   IOS_APP_ID=live.soulchill.ios
   ```

---

### 4. Android 环境准备

Android 自动化基于 **ADB（Android Debug Bridge）**，Midscene 通过 ADB 截图并向设备发送操作。

#### 安装 ADB

```bash
# 方式一：通过 Android Studio（推荐，安装后 adb 在 ~/Library/Android/sdk/platform-tools/）
# 方式二：单独安装命令行工具
brew install android-platform-tools

# 验证安装
adb --version
```

如果 `adb` 命令不存在，将 ADB 路径加入环境变量：

```bash
# 加到 ~/.zshrc 或 ~/.bash_profile
export ANDROID_HOME=$HOME/Library/Android/sdk
export PATH=$PATH:$ANDROID_HOME/platform-tools
```

#### 连接设备

**USB 真机：**

```bash
# 1. 手机开启"开发者选项" > "USB 调试"
# 2. 用 USB 线连接，手机上点击"允许 USB 调试"
# 3. 确认设备状态
adb devices
# 正常输出：
# List of devices attached
# R3CN70WXLNJ     device    ← "device" 表示已授权
```

**无线调试（Android 11+）：**

```bash
# 手机开启"无线调试"，记录显示的 IP:端口
adb connect 192.168.1.100:5555
adb devices
```

**模拟器：**

```bash
# 启动 Android Studio 中的 AVD 后自动连接
adb devices
# emulator-5554   device
```

#### 验证 App 包名

```bash
# 查看当前前台 App 的包名
adb shell dumpsys window | grep mCurrentFocus
# 或列出已安装的 App
adb shell pm list packages | grep soulchill
```

在 `.env` 中配置：

```dotenv
ANDROID_DEVICE_ID=           # 留空自动选第一台设备，多设备时填 UDID
ANDROID_APP_ID=com.live.soulchill
```

---

## 四、配置文件说明

### `.env` 与 `.env.example` 的区别

| 文件 | 用途 | 是否提交 Git |
|------|------|-------------|
| `.env.example` | **模板文件**，记录所有可配置项和说明，值为示例占位符，随代码一起提交 | ✅ 提交 |
| `.env` | **本地实际配置**，填入真实 API Key、手机号等敏感信息，已加入 `.gitignore` | ❌ 不提交 |

**使用流程：**

```bash
# 1. 首次拿到项目，复制模板
cp .env.example .env

# 2. 编辑 .env，填入真实值
# （.env.example 只是参考，永远不要在里面填真实 Key）
```

**原则：** `.env.example` 是"配置说明书"，`.env` 是"实际执行配置"。换台电脑或新同事接手时，只需 `cp .env.example .env` 再填真实值即可。

---

### `.env` 完整字段说明

```dotenv
# ---- AI 模型（必填）----
# Midscene 通过此接口调用视觉大模型分析截图

# 方案 A：火山引擎（当前使用，国内推荐）
MIDSCENE_MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
MIDSCENE_MODEL_API_KEY=your-ark-api-key
MIDSCENE_MODEL_NAME=doubao-seed-2-0-lite   # 需在 ARK 控制台开通该模型
MIDSCENE_MODEL_FAMILY=doubao-seed



# AI 调用失败重试（防止模型服务偶发限流）
MIDSCENE_MODEL_RETRY_COUNT=3
MIDSCENE_MODEL_RETRY_INTERVAL=5000

# ---- iOS ----
WDA_HOST=localhost
WDA_PORT=8100
IOS_APP_ID=live.soulchill.ios

# ---- Android ----
ANDROID_DEVICE_ID=                           # 留空自动选第一台连接设备，多设备时填 UDID
ANDROID_APP_ID=com.live.soulchill
ANDROID_MAIN_ACTIVITY=.module.login.LoginActivity  # 冷启动入口 Activity（相对包名格式）



> **注意**：YAML 脚本中用 `${变量名}` 引用上述变量，TypeScript 测试文件通过 `utils/env.ts` 读取，两者共用同一个 `.env` 文件。

### `vitest.config.ts` 关键配置

| 配置项 | 当前值 | 说明 |
|--------|--------|------|
| `testTimeout` | 180,000ms | 单个用例最长 3 分钟（AI 推理较慢） |
| `hookTimeout` | 60,000ms | beforeAll/afterAll 最长 1 分钟 |
| `pool: 'forks'` | - | 每个测试文件独立进程，防止设备连接互扰 |
| `concurrent: false` | - | 串行执行，防止多用例同时操作同一设备 |
| `retry: 0` | - | 失败不重试，保留现场方便排查 |

---

## 五、用例设计规范

### 文件组织

- 按业务模块拆分文件，文件名以数字前缀排序（`01-login`、`02-live-room`…）
- 同一模块的 iOS 和 Android 用例保持对称结构，便于维护

### 连接方式

**iOS 用例模板：**

```typescript
import { agentFromWebDriverAgent, IOSAgent } from '@midscene/ios';
import { describe, it, beforeAll, afterAll } from 'vitest';
import { config, AI_ACTION_CONTEXT, sleep } from '../../utils/env';

let agent: IOSAgent;

describe('模块名称 - iOS', () => {
  beforeAll(async () => {
    agent = await agentFromWebDriverAgent({
      wdaHost: config.wdaHost,
      wdaPort: config.wdaPort,
      aiActionContext: AI_ACTION_CONTEXT,
    });
    // URL Scheme 启动 App
    await agent.page.launch('soulchill://');
    await sleep(3000);
  });

  afterAll(async () => {
    await agent.page.destroy();
  });

  it('用例描述', async () => {
    await agent.aiWaitFor('期望的界面状态', { timeoutMs: 15000 });
    await agent.aiAct('执行某个操作');
    await agent.aiAssert('操作后的断言');
  });
});
```

**Android 用例模板：**

```typescript
import { agentFromAdbDevice, getConnectedDevices, AndroidAgent } from '@midscene/android';
import { describe, it, beforeAll, afterAll } from 'vitest';
import { config, AI_ACTION_CONTEXT, sleep } from '../../utils/env';

let agent: AndroidAgent;

async function createAgent(): Promise<AndroidAgent> {
  let deviceId = config.androidDeviceId;
  if (!deviceId) {
    const devices = await getConnectedDevices();
    if (!devices.length) throw new Error('未找到已连接的 Android 设备');
    deviceId = devices[0].udid;
  }
  return agentFromAdbDevice(deviceId, {
    aiActionContext: AI_ACTION_CONTEXT,
    autoDismissKeyboard: true,   // 操作后自动收起键盘
  });
}

describe('模块名称 - Android', () => {
  beforeAll(async () => {
    agent = await createAgent();
    // ADB 冷启动（首次登录用）
    await agent.launch(`adb shell am start -n ${config.androidAppId}/.MainActivity`);
    await sleep(3000);
  });

  afterAll(async () => {
    await agent.page.destroy();
  });
});
```

### AI 指令编写原则

**好的指令（具体、有上下文）：**

```typescript
// 明确输入内容
await agent.aiAct(`在手机号输入框中输入 "${config.testPhone}"`);

// 提供备选项，兼容界面文案差异
await agent.aiAct('点击"获取验证码"或"发送验证码"按钮');

// 等待时说明期望状态
await agent.aiWaitFor('登录成功，页面跳转到首页，显示底部导航栏', { timeoutMs: 30000 });
```

**避免的写法：**

```typescript
// 过于模糊
await agent.aiAct('点击按钮');

// 混入多个步骤（AI 可能只执行一个）
await agent.aiAct('输入手机号然后点击获取验证码再输入验证码');
```

### AI_ACTION_CONTEXT（全局弹窗处理）

在 `utils/env.ts` 中统一配置 AI 上下文，告诉 AI 如何处理干扰弹窗：

```typescript
export const AI_ACTION_CONTEXT =
  '如果出现位置权限、通知权限、麦克风权限、摄像头权限等系统弹窗，点击"允许"或"好"。' +
  '如果出现用户协议或隐私政策弹窗，点击同意。' +
  '如果出现青少年模式弹窗，点击关闭。' +
  '如果出现广告或活动弹窗，点击右上角关闭按钮。';
```

遇到新类型的弹窗导致用例失败时，在此处补充描述即可。

---

## 六、运行测试

### iOS（TypeScript 用例）

```bash
# 前置条件：WDA 已启动（curl http://localhost:8100/status 返回正常）

npm run test:ios            # 全部 iOS 用例
npm run test:ios:login      # 仅登录模块
npm run test:ios:live       # 仅直播间模块
npm run test:ios:recharge   # 仅充值模块
npm run test:ios:profile    # 仅个人主页模块
```

### Android（TypeScript 用例）

```bash
# 前置条件：adb devices 能看到已授权设备

npm run test:android            # 全部 Android 用例
npm run test:android:login
npm run test:android:live
npm run test:android:recharge
npm run test:android:profile
```

### 双端全量

```bash
npm run test:all
```

### YAML 脚本（推荐用于轻量冒烟测试）

YAML 格式既是测试文档也是可执行脚本，使用 Midscene CLI 直接运行，无需 Vitest：

**Android：**

```bash
npm run yaml:android:login      # 登录模块 P1
npm run yaml:android:recharge   # 充值模块 P1
npm run yaml:android:p1         # 全部 P1 用例
npm run yaml:android:p2         # 全部 P2 用例
npm run yaml:android:all        # 全部 Android YAML 用例（遇错继续）
```

**iOS（两阶段登录 + 验证码自动注入）：**

```bash
npm run yaml:ios:login      # iOS 登录 P1（自动触发 SMS → 拉取验证码 → 完成登录）
npm run yaml:ios:recharge   # iOS 充值模块 P1
```

**Web H5（Midscene web 模式，不依赖 App）：**

```bash
npm run yaml:web:eid2026    # Eid 2026 活动页加载验证
# 等价于：npx midscene ./testcases-yaml/web/run-eid2026.yaml
```

> YAML 脚本从当前目录的 `.env` 自动读取环境变量，支持 `${变量名}` 语法引用。

### Web H5（Android WebView raw CDP 模式）

适用于需要在真实 App WebView 内执行 JS 断言、操作 DOM 的 H5 测试。  
**前置条件**：设备安装 debug 包（需开启 WebView 调试），`adb forward` 已配置。

```bash
npm run test:eid2026:app:smoke   # Eid 2026 前 5 条 smoke 用例
npm run test:eid2026:app          # Eid 2026 全部 9 条用例
```

> 脚本会自动：检测 WebView 调试接口 → 通过 CDP 导航到目标 H5 → 运行用例 → 输出结果。  
> 若页面显示地区限制提示（"This event is not open for this area"），视为正常通过。

### 调试单个用例

```bash
# 直接用 vitest 运行单个文件，加 --reporter=verbose 看详细输出
npx vitest run testcases-ts/android/01-login.test.ts --reporter=verbose
```

---

## 七、查看测试报告

每次运行后，Midscene 会在 `midscene_run/` 目录生成可视化报告，包含：

- 每步操作的截图
- AI 的推理过程和定位结果
- 用例通过/失败状态

```bash
open midscene_run/report/index.html
```

> `midscene_run/` 已加入 `.gitignore`，不会提交到仓库。

---

## 八、常见问题排查

### iOS 相关

| 现象 | 排查步骤 |
|------|---------|
| `curl http://localhost:8100/status` 无响应 | 1. 确认 WDA 进程在运行；2. 真机需要 `iproxy 8100 8100` 做端口转发 |
| WDA 启动后立即崩溃 | 检查证书签名是否过期，重新 build WDA |
| `agent.page.launch('soulchill://')` 无反应 | 确认 App 已安装且 URL Scheme 正确 |
| AI 找不到元素 | 等待时间不够，增加 `sleep()` 或调高 `aiWaitFor` 的 `timeoutMs` |

### Android 相关

| 现象 | 排查步骤 |
|------|---------|
| `adb devices` 显示 `unauthorized` | 手机上弹窗点击"允许 USB 调试" |
| `adb devices` 显示 `offline` | 拔插 USB 线，或 `adb kill-server && adb start-server` |
| 找不到已连接设备 | 确认 `ANDROID_DEVICE_ID` 填写正确，或留空让代码自动选择 |
| App 无法启动（`am start` 失败） | 用 `adb shell pm list packages` 确认包名，检查 `MainActivity` 类名 |
| 截图全黑 | 部分 App 开启了截图保护，需在 Debug 包中关闭 `FLAG_SECURE` |

### AI / 模型相关

| 现象 | 排查步骤 |
|------|---------|
| `OPENAI_API_KEY` 报错 | 检查 `.env` 是否在项目根目录，Key 是否有效且有余额 |
| AI 操作超时 | 增大 `vitest.config.ts` 的 `testTimeout`，或检查网络是否能访问 API |
| AI 定位错误 | 优化 `aiAct` 指令描述，在 `AI_ACTION_CONTEXT` 中补充界面说明 |
| 验证码无法自动填写 | 需后端在测试账号配置固定验证码，联系后端设置 `TEST_VERIFY_CODE` 对应的 magic code |

---

## 九、调试记录与经验沉淀

> 本节记录每次调试过程中发现的问题和有效的解决方案，持续更新。

### 2026-03-27 — 工程初始化

**背景**：从零搭建 Midscene.js 双端自动化测试工程。

**完成内容**：
- 初始化 `package.json`，引入 `@midscene/ios`、`@midscene/android` v1.6.0
- 编写双端 4 大业务模块用例：登录、直播间、充值、个人主页
- 配置 Vitest 串行执行（`concurrent: false`）+ 长超时（180s），适配 AI 操作节奏
- 封装 `utils/env.ts` 统一管理环境变量和 `AI_ACTION_CONTEXT`
- Android 登录首次冷启动用 `adb shell am start`，后续模块用 URL Scheme `soulchill://login` 进入已登录态

**待验证**：实际在真机上运行通过率，以及各弹窗类型是否都被 `AI_ACTION_CONTEXT` 正确处理。

---

### 2026-03-27 ~ 2026-04-03 — Android 环境调试全记录

**设备**：OPPO PDCM00 / Android 12（SDK 31）/ UDID `YTZHBEKNG6LBR4RO`

#### 问题 1：`MIDSCENE_MODEL_FAMILY` 未配置
- **现象**：`MIDSCENE_MODEL_FAMILY is not set to a visual language model`
- **修复**：`.env` 增加 `MIDSCENE_MODEL_FAMILY=gpt-5`（适用 OpenAI 兼容接口）；火山引擎用 `doubao-seed`

#### 问题 2：`agent.launch()` 参数传法错误
- **现象**：`java.lang.IllegalArgumentException: Bad component name: adb`
- **原因**：`agent.launch()` 内部已封装 `adb am start-activity`，不能传完整命令
- **修复**：只传组件名 `com.live.soulchill/.module.login.LoginActivity`

#### 问题 3：deeplink 格式错误
- **现象**：`ADB error: Activity not started, unable to resolve Intent`
- **原因**：`soulchill://login` 格式错误，该 App 的 deeplink 需要带 Authority
- **修复**：改为 `soulchill://com.live.soulchill/login`（所有 Android 测试文件统一修复）
- **验证命令**：`adb shell dumpsys package com.live.soulchill | grep -A3 "Scheme:"`



#### 首次通过用例
- `planet.test.ts` > **底部导航 Tab 切换正常** ✅（2026-04-03）
- 框架完全跑通，AI 截图分析、设备操作均正常

---

### 2026-03-27 — Android 环境调试

**设备信息**：OPPO PDCM00 / Android 12（SDK 31）/ UDID `YTZHBEKNG6LBR4RO`

**问题：App 启动 Activity 名写错**

测试代码中冷启动命令用了 `.MainActivity`，但该 App 实际入口 Activity 为 `.module.login.LoginActivity`。  
原命令会静默失败（`am start` 不报错但 App 不启动），导致后续所有断言失败。

**修复方式**：
1. 将 `androidMainActivity` 提取到 `utils/env.ts` 的 `config` 对象中，默认值为 `.module.login.LoginActivity`
2. `01-login.test.ts` 改为引用 `config.androidMainActivity`
3. 如换测试包 Activity 变化，只需在 `.env` 中增加 `ANDROID_MAIN_ACTIVITY=xxx` 覆盖

**验证命令**：
```bash
adb shell am start -n com.live.soulchill/.module.login.LoginActivity
# 输出 Starting: Intent { cmp=com.live.soulchill/.module.login.LoginActivity } 即正常
```

**`ANDROID_DEVICE_ID` 配置**：当前 `.env` 留空，代码自动选第一台连接设备（目前只连一台），无需修改。

---

### 2026-04-13 — Android WebView CDP H5 测试调试记录

**背景**：为 Eid 2026 活动页（`testcases-ts/web/run-eid2026.ts`）实现基于 Android WebView raw CDP 的 H5 自动化测试。

**设备**：OPPO PDCM00 / Android 12 / UDID `YTZHBEKNG6LBR4RO`

#### 问题 1：生产包无 WebView 调试接口
- **现象**：`adb shell cat /proc/net/unix | grep webview_devtools` 无输出
- **原因**：生产包默认关闭 `WebContentsDebuggingEnabled`
- **修复**：安装 debug 包（`debuggable=true`），重新确认接口出现：`@webview_devtools_remote_<pid>`

#### 问题 2：CDP WebSocket 连接 403
- **现象**：`ws.on('error')` 报 `Unexpected server response: 403`
- **原因**：Chrome 146 WebView 对非受信 origin 的 WebSocket 握手进行拒绝
- **修复**：WebSocket 连接时指定 `origin: ''`（空字符串），绕过 origin 校验

#### 问题 3：CDP `/json` 页面列表始终为空
- **现象**：WebView 接口存在，`/json/version` 正常，但 `/json` 返回 `[]`
- **原因**：SoulChill 尚未打开任何 H5 页面，WebView 进程空闲中
- **修复**：测试脚本自动点击屏幕底部 Banner 触发任意 H5，再用 `Page.navigate` 通过 CDP 导向目标 eid2026 URL

#### 问题 4：transit 深链打开 H5 失败
- **现象**：`am start -n TransitActivity -d soulchill://...` 发出后 Activity 立即 finishing（`t-1 f`），页面未加载
- **原因**：TransitActivity 处理后把控制权交回 MainActivity，但 WebView 没有渲染 H5（可能有 URL 白名单或登录态检查）
- **修复**：改为先用 adb tap 点击 App 内 Banner 打开已有 H5，再 CDP navigate 到目标页

#### 最终通过
- `npm run test:eid2026:app:smoke` 5/5 通过（2026-04-13）
- 地区限制场景（"This event is not open for this area"）已作为合法结果处理，不计失败
