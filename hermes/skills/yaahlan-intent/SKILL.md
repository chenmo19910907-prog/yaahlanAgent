---
name: yaahlan-intent
description: Yaahlan Midscene 意图测试：md2intent / 编译 / 按条执行
version: 1.0.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [yaahlan, midscene, intent, e2e]
    category: yaahlan
    requires_toolsets: [terminal]
    config:
      - key: yaahlan.repo
        description: auto-generate-testcase 仓库绝对路径
        default: "~/CursorProjects/auto-generate-testcase"
        prompt: Yaahlan 仓库路径
---

# Yaahlan Midscene 意图测试

## When to Use

用户要「意图测试」「跑 Midscene 意图」「md 转意图」「验收某模块 UI 意图」时加载本 Skill。

目标 App：`com.immomo.biz.yaahlan`（配置在 `midscene/.env`）。步骤型 YAML（`midscene/testcases-yaml/`）仍用于登录/充值/游戏固定回归；本 Skill 只管 `intent-test/`。

## Procedure

1. **定位仓库**：`REPO` = `skills.config.yaahlan.repo`。  
   ```bash
   cd "$REPO/intent-test"
   ```

2. **环境自检**（执行前必做）：
   ```bash
   npm run doctor
   ```
   失败则根据输出修 `midscene/.env` / ADB / WDA，不要硬跑。

3. **选型**：
   | 用户意图 | 命令 |
   |----------|------|
   | 列已有意图 | `npm run catalog` |
   | 手工 md → 意图草稿 | `npm run md2intent -- ../temporary_testcase/<文件>.md` |
   | 仅编译 | `npm run compile -- intents/<模块>/<文件>.yaml` |
   | 跑单条 | `npm run intent -- intents/<模块>/<文件>.yaml` |
   | 跑模块 | `npm run intent:module -- <模块名>` |
   | 礼物等需 Tunnel 数据 | 先 `npm run preflight` / `ensure-data` |

4. **编写/改意图**（若无现成 yaml）：
   - 复制 `templates/intent.template.yaml`
   - `intent.action` 写自然语言目标，**禁止坐标 / resource-id**
   - `intent.expected` 每条可观测，将编译为 `aiAssert`
   - setup 优先 `include:` `_fragments/`（如 `base-navigation`）
   - 业务上下文写 `aiContext`；弹窗默认全局策略

5. **执行铁律**：
   - **一次一条或一个明确模块**；跑完读报告/失败断言再下一条
   - **禁止**写脚本 for 循环盲跑全部 intents
   - 需抓包验收时按 intent 内 `tunnel:` 或 `npm run tunnel`
   - 固定链路（登录验证码、游戏 spin）优先 `midscene/testcases-yaml/`，不要硬转意图

6. **从 KB 起草意图**（可选）：
   - 读 `testcase-kb/<模块>.md` 验收要点 → 写成 1～N 条 intent yaml（P1 优先）
   - 或先 `/yaahlan-gen-testcase` 出 md，再 `md2intent`

## Pitfalls

- 意图失败时先看 Midscene 报告与截图，再收紧 `action`/`expected`/`aiContext`，不要改去抄坐标进 yaml
- `launchApp: true` 冷启成本高；能复用会话则 `false` + setup 导航
- Android 包名勿写成 SoulChill / Yaha

## Verification

- `doctor` 通过（或已说明阻塞项）
- 单条：`intent` 退出成功，或给出失败断言原文路径
- 新意图：文件在 `intent-test/intents/`，且 `npm run compile -- <path>` 成功
