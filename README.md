# 钉钉测试用例自动生成（Yaahlan 分支）

基于 Cursor Agent Skills 与钉钉 MCP，从钉钉需求文档与项目规则生成结构化测试用例，并可同步到钉钉 Excel。本仓库 **`yaahlan`** 分支主要用于 **Yaahlan** 用例自动化，并附带 **MOA**、**Risk**、**Admin** 等本地测试辅助脚本；其他业务可在同流程下扩展。

> **新同事 / 新电脑**：`git pull` 后 MOA 不能直接用是正常的（Cookie 不入库）。请按 **[新手上手.md](新手上手.md)** 配置 `MOA/.env.local` 等本地文件（约 10 分钟）。

## 功能特性

### 用例生成

- **需求解析**：钉钉普通文档 / Excel 需求读取（`dingtalk-doc-read` + `parse_document` 等）
- **PRD 理解**：生成用例前可按 `prd-review` Skill 做需求摘要与边界梳理（见 `.cursor/skills/prd-review/SKILL.md`）
- **规则驱动**：参考 `rules/testcase_generation_rules.md`（榜单、抽奖、兑换、礼包等通用规则）补充用例
- **业务参考**：`documents/` 下按模块维护说明；**用例知识库**见 `testcase-kb/`，**需求知识库**见 `prd-kb/`（按模块整理的产品需求要点），**Bug 知识库**见 `bug-kb/`；动态用例生成流程见 `moments/`
- **模板对齐**：相似模块参考 `templates/`（如榜单类对齐 `templates/榜单.md`）
- **用例输出**：Markdown 表格等写入 `temporary_testcase/`，经 `testcase-to-excel` 分批写入钉钉 Excel
- **质量工具**：`scripts/check_testcase_md.py` 格式校验、`suggest_kb_for_module.py` 知识库推荐、`doctor.py` 环境自检（见根目录 `SKILL.md`「常用命令」）

### 本地自动化（MOA / Risk / Admin / Tunnel / online）

- **MOA**（`MOA/`）：通过 MSE httpproxy 调用 MOA 接口；JSON 模板在 `MOA/templates/`，详见 [MOA/README.md](MOA/README.md) 与 [MOA/使用方法.md](MOA/使用方法.md)
- **Risk**（`Risk/`）：调用海外风控开放接口 `/open/menu/operate`，支持解除设备/手机号风控、充值/活动风控加白加黑；默认读取 `testcase-kb/test_devices.json` 按平台自动选取 mmuid 或 mmuidv3 值；详见 [Risk/README.md](Risk/README.md)
- **Admin**（`Admin/`）：调用 Yaahlan 测试后台，支持 **按 userId 查询用户全量详情**（`queryUserDetail`）；详见 [Admin/README.md](Admin/README.md) 与 [Admin/使用方法.md](Admin/使用方法.md)
- **online**（`online/`）：**线上/生产**环境统一入口（Admin + MOA overseas + Tunnel overseas）；须提示词含「线上环境」；详见 [online/README.md](online/README.md) 与 [online/使用方法.md](online/使用方法.md)
- **Tunnel**（`Tunnel/`）：查询 [tunnel.wemomo.com](https://tunnel.wemomo.com) 抓包记录，按 userId 拉 HTTP 请求列表与 request/response；Cookie 可复用 MOA；礼物面板 Customize 排序与自定义礼物周榜见 [adb/录制脚本/礼物面板抓包.md](adb/录制脚本/礼物面板抓包.md)；详见 [Tunnel/README.md](Tunnel/README.md) 与 [Tunnel/使用方法.md](Tunnel/使用方法.md)
- **platform**（`platform/`）：**工具平台能力目录**网页（汇总 Admin/MOA/Risk/Tunnel/online/DingTalk registry）；提到「**工具平台**」「**输入工作台**」「**新手引导**」「**说明书**」等时执行 `python3 platform/open_catalog.py` 打开浏览器；详见 [platform/README.md](platform/README.md)
- **DingTalk**（`DingTalk/`）：列举钉钉 alidocs 目录、同步用例到 `testcase-kb/`、同步 PRD 到 `prd-kb/`；详见 [DingTalk/README.md](DingTalk/README.md)
- **Report**（`Report/`）：从版本用例 xlsx 生成内网/外网测试总结 HTML；详见 [Report/README.md](Report/README.md)、[Report/使用方法.md](Report/使用方法.md)
- **adb**（`adb/`）：真机 UI 自动化（截屏 → 读图算坐标 → 点击，仅保留最新 10 张截图）；支持与 **Tunnel** 联动的 `run`（操作 + 截图 + 抓包校验）；**录制脚本库**按发版回归一级模块存放 **片段**，命令 `macro`；**P0 自动化用例**（`autotest`：PRD/手工用例 → 可执行 JSON → 真机跑测 → HTML 报告）见 [adb/自动化用例/README.md](adb/自动化用例/README.md)；详见 [adb/README.md](adb/README.md)、[adb/使用方法.md](adb/使用方法.md)、[adb/录制脚本/README.md](adb/录制脚本/README.md)
- **e2e**（`e2e/`）：**独立于 adb/** 的自然语言安卓自动化（**识别→思考→执行** + 知识库 + MOA/Tunnel）；详见 [e2e/README.md](e2e/README.md)
- **midscene**（`midscene/`）：基于 [Midscene.js](https://midscenejs.com/) 的 **AI 视觉驱动**双端自动化（iOS WDA + Android ADB）；YAML / TypeScript 用例，覆盖登录、充值、游戏中心（greedy / slots / others）等；详见 [midscene/README.md](midscene/README.md)

## 项目结构

```
auto-generate-testcase/
├── README.md                          # 本文件
├── 新手上手.md                        # 新机器本地配置：MOA/Admin/online/Risk/Tunnel/Report/adb/MCP
├── SKILL.md                           # 主流程：营收活动用例自动生成（模块提取与钉钉解析）
├── MOA/                               # MOA httpproxy 本地调用
│   ├── README.md
│   ├── moa_execute.py                 # CLI 入口
│   ├── config/                        # registry + 等级阈值
│   ├── 使用方法.md                    # 能力清单（自动生成）
│   ├── scripts/                       # generate_index / test_all
│   ├── templates/                     # JSON 模板
│   └── moa/                           # Python 实现
├── Risk/                              # 海外风控开放接口（设备/手机/充值/活动）
│   ├── README.md
│   ├── risk_execute.py                # 入口
│   └── config.json
├── Admin/                             # Yaahlan 测试后台（用户详情查询等）
│   ├── README.md
│   ├── admin_execute.py               # 入口
│   └── config.json
├── online/                            # 线上环境（Admin + MOA + Tunnel 统一入口）
│   ├── README.md
│   ├── 使用方法.md                    # 能力清单（自动生成）
│   ├── online_execute.py              # 入口：admin | moa | tunnel
│   ├── config.json
│   └── config/registry.json
├── Tunnel/                            # tunnel.wemomo.com 抓包查询
│   ├── README.md
│   ├── tunnel_execute.py              # 入口
│   ├── config/registry.json
│   └── 使用方法.md
├── DingTalk/                          # 钉钉目录列举 + testcase-kb 同步
│   ├── README.md
│   ├── 使用方法.md                    # 能力清单（自动生成）
│   ├── lookup_execute.py              # 按关键词查目录内文件链接
│   ├── collect_execute.py             # 列举目录表格链接
│   ├── kb_sync_execute.py             # 同步 testcase-kb
│   ├── prd_sync_execute.py            # 同步 prd-kb
│   └── config/
│       ├── registry.json
│       ├── folders.json               # 已登记目录（用例/活动/PRD）
│       ├── kb.json                    # 用例同步选项
│       └── prd.json                   # PRD 同步选项
├── platform/                          # 工具平台能力目录（汇总各模块 registry → catalog.html）
│   ├── README.md
│   ├── open_catalog.py                # 刷新目录并打开浏览器（127.0.0.1:18765）
│   ├── export_catalog.py              # 导出离线 HTML 到桌面
│   ├── catalog.html                   # 能力目录页（自动生成）
│   ├── config/
│   │   └── sources.json               # 模块来源与一级分类归并规则
│   ├── scripts/                       # generate_catalog / cursor_bridge 等
│   └── dingtalk_gateway/              # 钉钉机器人网关（可选）
├── prd-kb/                            # 产品需求知识库（按业务模块整理，非逐篇 PRD）
│   └── README.md
├── Report/                            # 版本用例 xlsx → 内网/外网测试总结 HTML
│   ├── README.md
│   ├── 使用方法.md                    # 命令速查（提示词 ↔ CLI）
│   ├── report_execute.py              # 入口
│   └── requirements.txt
├── adb/                               # ADB 真机 UI 自动化（读图坐标点击）
│   ├── README.md
│   ├── 使用方法.md                    # 命令速查（提示词 ↔ CLI）
│   ├── adb_execute.py                 # 入口（macro / device / capture…）
│   └── 录制脚本/
│       ├── 索引.json                  # 片段总目录（含 module）
│       ├── KB对照.md                  # 知识库 ↔ 脚本映射
│       ├── 片段/<一级模块>/           # 积木：注册登录、动态帧、我的帧等
│       └── 设备适配/                  # 换机坐标换算（基准设备、档案）
├── e2e/                               # 全新 E2E 自动化（独立于 adb/，建设中）
│   ├── README.md
│   ├── 使用方法.md
│   ├── e2e_execute.py                 # 入口
│   ├── cases/                         # 声明式用例 JSON
│   └── reports/                       # 运行报告
├── midscene/                          # Midscene.js AI 视觉驱动双端自动化（iOS + Android）
│   ├── README.md
│   ├── package.json                   # npm 脚本（YAML / Vitest）
│   ├── vitest.config.ts
│   ├── tsconfig.json
│   ├── .env.example                   # AI 模型、WDA、ADB 配置模板
│   ├── scripts/
│   │   ├── midscene-run.mjs           # YAML 执行包装器（验证码轮询 / 注入）
│   │   ├── run-ios-game-ordered.mjs   # iOS 游戏用例有序批量执行
│   │   └── run-ios-game-slots-ordered.mjs
│   ├── game.env/
│   │   ├── games.list                 # 游戏用例列表（供批量脚本读取）
│   │   └── run-ios-games-from-list.mjs
│   ├── utils/
│   │   ├── env.ts                     # 环境变量 + AI_ACTION_CONTEXT
│   │   ├── api.ts                     # getVerifyCode 等接口
│   │   └── sc-webview.ts              # Android WebView CDP 工具
│   ├── testcases-yaml/                # YAML 用例（Midscene 原生格式，推荐维护）
│   │   ├── android/
│   │   │   ├── login-p1.yaml / login-p2.yaml / recharge-p1.yaml
│   │   │   ├── game-greedy/           # GreedyCat2、Lucky77、UEFA 等下注用例
│   │   │   └── game-slots/            # 1001Nights、BookOfDeath 等 spin 用例
│   │   ├── ios/
│   │   │   ├── login/                 # login-p1-trigger / login-p1-complete
│   │   │   ├── login-p1-complete.yaml / recharge-p1.yaml / game-center-p1.yaml
│   │   │   ├── game-greedy/
│   │   │   ├── game-slots/
│   │   │   └── game-others/           # Mines、Crash、Plinko2 等
│   │   └── web/
│   │       └── run-eid2026.yaml
│   └── testcases-ts/                  # TypeScript 用例（Vitest）
│       ├── android/                   # 02-live-room、03-recharge、04-profile、planet…
│       ├── ios/                       # 01-login ~ 04-profile
│       ├── web/
│       │   └── run-eid2026.ts         # Eid 2026 WebView CDP 用例
│       └── temporary_testcase/
│           └── eid2026-cases.json
├── rules/                             # 生成规则与辅助流程说明
│   ├── testcase_generation_rules.md   # 通用：榜单 / 抽奖 / 兑换 / 礼包等
│   ├── version_testcase_generation_rules.md  # 版本用例生成规则（须先读 documents/ 对应模块）
│   └── dingtalk_historical_testcase_to_md.md   # 钉钉历史用例 → Markdown 等（按需）
├── moments/                           # 动态（Moments）用例生成流程（与 SKILL.md 同构）
│   ├── README.md
│   └── moments_testcase_generation.md
├── testcase-kb/                       # 用例知识库（由版本 xlsx 汇总的产品规则/验收要点）
│   └── README.md
├── bug-kb/                            # Bug 知识库（历史缺陷归档）
│   └── README.md
├── documents/                         # 业务模块参考（功能/版本用例生成前优先阅读）
│   ├── gift.md                        # 礼物业务模块梳理
│   └── moments/                       # 动态（Moments）业务说明
│       ├── basic module.md            # 基础能力（文件名含空格）
│       ├── hot.md
│       ├── label.md
│       └── video.md
├── templates/                         # 与钉钉表或模块维度对齐的用例骨架
│   ├── 榜单.md
│   ├── 抽奖.md
│   └── 奖励领取.md
├── temporary_testcase/                # 生成的用例临时存放目录
├── scripts/
│   ├── check_testcase_md.py           # 用例 Markdown 校验
│   ├── suggest_kb_for_module.py       # 按模块推荐知识库路径
│   ├── doctor.py                      # MOA/MCP/目录自检
│   ├── sync_all_kb.py                 # 一键同步 regression/bug/online KB
│   └── export_testcases_to_desktop.py # 导出用例副本
├── .cursor/
│   ├── mcp.json                       # MCP 服务器配置
│   └── skills/
│       ├── dingtalk-doc-read/         # 钉钉文档解析
│       ├── prd-review/                # PRD 理解与审查
│       ├── testcase-generator/        # 用例生成逻辑
│       ├── testcase-to-excel/         # 用例写入钉钉 Excel
│       ├── testpoints-to-testcases/   # 测试点扩写为用例
│       └── ...
```

## 环境要求

- **Cursor**：支持 Agent Skills 和 MCP 的版本
- **Python 3**：运行 `MOA/`、`Risk/` 本地脚本（标准库即可，无额外依赖）
- **钉钉文档权限**：需求文档需开启访问权限
- **MCP 配置**：需配置钉钉文档、钉钉 Excel 读写相关环境变量

## MCP 配置

在 `.cursor/mcp.json` 中配置以下 MCP 服务器：

| 服务器 | 用途 | 环境变量 |
|--------|------|----------|
| `dingtalk-doc` | 解析钉钉文档 | `DINGTALK_COOKIE` |
| `dingtalk-excel-read` | 读取钉钉 Excel | `DINGTALK_AEGIS_KEY`、`DINGTALK_AEGIS_SECRET`、`DINGTALK_WORKID` |
| `dingtalk-excel-write` | 写入钉钉 Excel | 同上 |

> 敏感信息请勿提交到版本库。MOA / Risk 的 Cookie、Token 等请写入各自目录下的 `.env.local`（已加入 `.gitignore`）。

## 使用流程

### 1. 生成测试用例

向 Agent 提供 **钉钉需求文档 URL**（及可选：`documents/` 业务说明、规则/模板路径）。推荐流程：

1. 必要时先按 **prd-review** 梳理需求摘要与异常边界  
2. 使用 **dingtalk-doc** 解析文档（表格模块勿遗漏）  
3. 结合 `testcase_generation_rules.md` 与 `templates/` 补全维度  
4. 输出到 `temporary_testcase/*.md`（或项目约定格式）

### 2. 写入钉钉 Excel

提供 **钉钉 Excel 文档 URL**，由 Agent 使用 **testcase-to-excel** Skill：

1. 从 `temporary_testcase/` 读取 `.md` / `.csv`  
2. 映射列为：`编号` | `功能模块` | `测试步骤` | `预期结果`（可与「用例标题」合并到功能模块列）  
3. `write_sheet_data` 写入；**超过约 50 行时分批**，递增 `startRow`  
4. 写入失败若提示 `InvalidAuthentication`，需更新 Aegis/Cookie 后重试  

### 3. MOA 测试数据构造

```bash
cp MOA/.env.example MOA/.env.local
# 编辑 MOA/.env.local 填入 MOA_ENTRY_URL、MOA_COOKIE

python3 MOA/moa_execute.py --help
python3 MOA/scripts/test_all.py   # 可选：批量自测全部模板
```

常用能力：钻石增减、背包礼物、VIP/贵族、实名认证、家族声望/基金档位/贡献等。完整用法见 [MOA/README.md](MOA/README.md) 与 [MOA/使用方法.md](MOA/使用方法.md)。

### 4. online 线上环境（Admin + MOA + Tunnel）

须提示词含「**线上环境**」；与测试 `Admin/`、`MOA/`、`Tunnel/` 完全隔离。

```bash
cp online/.env.example online/.env.local
# 填入 ADMIN_ONLINE_*、MOA_ONLINE_*、TUNNEL_ONLINE_*（抓包见 online/.env.example 注释）

python3 online/online_execute.py admin --query-user-id <userId>
python3 online/online_execute.py moa --query-user-by-phone <phone>   # 默认区号 +966
python3 online/online_execute.py tunnel --momoid <userId> --since 3600
```

礼物面板 **Customize Tab 排序**（`getGiftTabListV3`）与**自定义礼物周榜**（`getTotalCustomGiftRankList`，`cycle=1` 本周 / `cycle=2` 上周）的线上抓包与导出说明见 [adb/录制脚本/礼物面板抓包.md](adb/录制脚本/礼物面板抓包.md)。

典型链路：**手机号 → MOA 得 userId → Admin 查详情/在线 → Tunnel 验收接口**。完整口令与命令见 [online/README.md](online/README.md) 与 [online/使用方法.md](online/使用方法.md)。

### 5. 风控名单操作

```bash
# 可选：仅当需覆盖 token / 域名时
# cp Risk/.env.example Risk/.env.local

python3 Risk/risk_execute.py --list-test-devices
python3 Risk/risk_execute.py --release-test-device --device-name "GalaxyA80" --reason 测试
```

支持：解除设备/手机号风控、充值/活动风控添加与解除。设备解除默认读取 `testcase-kb/test_devices.json`，Android/鸿蒙取 **mmuidv3 字段值**，iOS 取 **mmuid 字段值**（接口 dimension 均为 `mmuid`）。详见 [Risk/README.md](Risk/README.md)。

### 6. 测试报告生成

```bash
python3 -m venv Report/.venv && source Report/.venv/bin/activate
python -m pip install -r Report/requirements.txt

python3 Report/report_execute.py /path/to/v2.4.4版本用例.xlsx
```

在同目录生成 `{文件名}_内网测试总结.html` 与 `{文件名}_外网测试总结.html`。详见 [Report/README.md](Report/README.md)。

### 7. ADB 真机录制脚本（Yaahlan）

前置：`adb devices` 可见 `device`；目标 App 为 **Yaahlan**（非桌面 Yaha）。换机坐标适配见 `adb/录制脚本/设备适配/README.md`。

```bash
python3 adb/adb_execute.py scripts          # 按模块列出片段
python3 adb/adb_execute.py macro 手机号登录 --text 13311111115 --no-capture
python3 adb/adb_execute.py macro 发布纯文本动态 --text 5555 --no-capture
```

- **片段**：单段已验证操作，`macro <中文名>`（目录仅归档，调用用中文名或 id）；多步流程逐段 macro + 片段间验收
- **落库**：真机探索验收成功后，写入 `adb/录制脚本/片段/<模块>/` 并更新 `索引.json`；模块名与发版回归一级模块一致（见 `adb/录制脚本/README.md`）

详见 [adb/README.md](adb/README.md)、[adb/使用方法.md](adb/使用方法.md)、[adb/录制脚本/KB对照.md](adb/录制脚本/KB对照.md)。

### 7. 用例格式

| 字段 | 说明 |
|------|------|
| 用例ID | 唯一标识，如 `001` |
| 功能模块 | 按需求文档覆盖 |
| 测试步骤 | 1. 2. 3. 分行可执行步骤 |
| 期望结果 | 界面反馈、状态变化、系统响应 |

## 规则与模板

- **`rules/testcase_generation_rules.md`**：榜单、抽奖、兑换、购买礼包等通用片段；生成时覆盖正向 / 反向 / 边界 / 交互。  
- **`rules/version_testcase_generation_rules.md`**：发版 / 版本回归用例；**生成前须先在 `documents/` 查找并阅读对应模块文档**（如 `gift.md`），再叠加版本 PRD。  
- **`templates/`**：与钉钉表结构对齐的模块骨架，可按活动同步更新。  

- **榜单**：数据格式、显示规则、交互、分页、计值、房间榜
- **抽奖**：积分获取、抽奖过程、奖励下发
- **兑换**：积分获取、兑换失败/成功
- **购买礼包**：礼包展示、购买/转赠成功/失败、状态更新

| Skill / 文档 | 说明 |
|--------------|------|
| 根目录 `SKILL.md` | 营收活动用例主流程与模块提取要求 |
| `dingtalk-doc-read` | 读钉钉文档、Cookie 处理 |
| `dingtalk-folder-list` | 列举钉钉目录下全部用例表链接、驱动 testcase-kb 全量同步（入口 `DingTalk/`） |
| `testcase-generator` | 用例生成约定与参数 |
| `testcase-to-excel` | 解析临时用例并写入钉钉 Excel |
| `prd-review` | 生成前 PRD 理解与审查维度 |
| `testpoints-to-testcases` | 测试点扩写为用例 |
| `dingtalk_historical_testcase_to_md.md` | 历史用例导出 Markdown 等（按需） |
| [新手上手.md](新手上手.md) | **新电脑必看**：MOA/Admin/online/Tunnel/Report/adb/MCP 本地配置与验证 |
| [MOA/README.md](MOA/README.md) | MOA 本地调用与目录说明 |
| [online/README.md](online/README.md) | 线上环境统一入口（Admin + MOA + Tunnel） |
| [online/使用方法.md](online/使用方法.md) | online 能力口令与命令（自动生成） |
| [platform/README.md](platform/README.md) | 工具平台能力目录网页（`open_catalog.py`） |
| [Risk/README.md](Risk/README.md) | 海外风控开放接口与测试机解除 |
| [adb/README.md](adb/README.md) | ADB 设计原则、协作流程、自动录制 |
| [adb/使用方法.md](adb/使用方法.md) | ADB 命令速查（提示词 ↔ CLI） |
| [adb/录制脚本/README.md](adb/录制脚本/README.md) | 录制脚本库目录与落库约定 |
| [adb/录制脚本/KB对照.md](adb/录制脚本/KB对照.md) | 知识库路径 ↔ 片段/组合对照 |
| [e2e/README.md](e2e/README.md) | 全新 E2E 自动化方案（独立于 adb/） |
| [midscene/README.md](midscene/README.md) | Midscene.js AI 视觉驱动双端自动化（YAML / Vitest） |

- `榜单.md`：榜单类模块完整用例维度
- `抽奖.md`：抽奖活动用例模板
- `奖励领取.md`：任务型奖励领取用例模板

模板可从钉钉 Excel 的对应 sheet 同步更新。

## 分支说明

- **`yaahlan`**：当前默认开发分支，与远端 `origin/yaahlan` 对齐；README 以本分支为准更新。  
- 其他分支（如 `hanmin`）可能结构不同，切换前请 **stash / 提交** 本地修改，避免与 `.cursor/mcp.json` 等冲突。

## 扩展模板

从钉钉 Excel 同步模板到 `templates/`：

```text
读取 https://alidocs.dingtalk.com/i/nodes/<NODE_ID> 的 [sheet 名]
生成 [模块名].md 放到 templates 目录下
```

## 许可证

内部项目，未指定开源许可证。
