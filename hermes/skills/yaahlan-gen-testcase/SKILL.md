---
name: yaahlan-gen-testcase
description: Yaahlan 用例生成：读 KB/PRD，写 temporary_testcase 并校验
version: 1.0.0
platforms: [macos, linux]
metadata:
  hermes:
    tags: [yaahlan, testcase, kb]
    category: yaahlan
    requires_toolsets: [terminal]
    config:
      - key: yaahlan.repo
        description: auto-generate-testcase 仓库绝对路径
        default: "~/CursorProjects/auto-generate-testcase"
        prompt: Yaahlan 仓库路径
---

# Yaahlan 用例自动生成

## When to Use

用户要「根据需求/KB 生成测试用例」「扩写测试点」「版本/活动用例」「写 temporary_testcase」时加载本 Skill。

## Procedure

1. **定位仓库**：`REPO` = `skills.config.yaahlan.repo`（展开 `~`）。所有命令在该目录执行：`cd "$REPO"`。

2. **确认输入**（缺一项就问用户）：
   - 模块名或关键词（如 `礼物`、`注册登录`）
   - 需求类型：`版本` / `活动|其他`
   - 需求来源：钉钉 URL、本地 md、或对话描述
   - 输出用途：`知识库5列` 或 `钉钉Excel3列`

3. **推荐知识库路径**：
   ```bash
   python3 scripts/suggest_kb_for_module.py <模块关键词...>
   ```
   按输出顺序阅读存在的 `documents/` → `testcase-kb/` → `bug-kb/`；活动/营收务必扫 `bug-kb` 同模块严重缺陷。

4. **需求理解**（生成前必须）：
   - 钉钉文档 → 用可用的文档读取工具 / MCP；否则请用户粘贴要点
   - 输出简短需求摘要：功能类型、核心场景、规则、边界、待确认点；有模糊项先确认

5. **规则文件**：
   - 版本 → `rules/version_testcase_generation_rules.md` + 对应 `documents/`
   - 活动/其他 → `rules/testcase_generation_rules.md`
   - 总流程摘要见仓库根 `SKILL.md`

6. **写用例**到 `temporary_testcase/<清晰文件名>.md`：
   - 覆盖模块与子功能点；正反、边界分条
   - 功能模块列只写模块名；同模块后续行留空；多预期分行、步骤列留空

7. **校验**：
   ```bash
   python3 scripts/check_testcase_md.py temporary_testcase/<文件>.md --strict
   ```
   失败则改文件直到通过。

8. **可选下一步**：若用户要自动化，提示 `/yaahlan-intent` 用 `md2intent` 转意图；勿在本 Skill 里直接跑真机。

## Pitfalls

- 不要跳过 KB 建议直接盲写
- 不要把 `testcase-kb` 当成逐步执行脚本（那是规则库）
- 不要提交含密钥的环境文件
- 不要发明批量 Python 代替逐步验收

## Verification

- `temporary_testcase/` 下存在新/更新 md
- `check_testcase_md.py --strict` 退出码 0
- 回复中给出文件路径 + 模块覆盖摘要（3～8 条）
