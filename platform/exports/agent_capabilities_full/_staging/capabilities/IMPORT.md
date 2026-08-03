# 导入说明

本压缩包由 Yaahlan 工具平台导出，供**其他智能体平台**完整导入能力清单。

## 文件

| 文件 | 用途 |
|------|------|
| `agent_capabilities_bundle.json` | **主文件**：机器可读，含全部 registry 字段 |
| `agent_capabilities.md` | 人类可读摘要（模块与能力索引） |
| `IMPORT.md` | 本说明 |

## JSON 结构

- `schema_version`: 1.0
- `modules[]`: 各模块完整 registry（含 `items[]` 的 id/name/category/description/prompts/command）
- `catalog`: 工具台分组视图（一级模块 → 分类 → 能力）
- `sources`: platform/config/sources.json 原文（模块登记与分组规则）
- `import_hints`: 字段说明与环境映射

## 导入步骤（通用）

1. 读取 `agent_capabilities_bundle.json`
2. 遍历 `modules[].items[]`，写入目标平台能力库（建议保留 `id` 作唯一键）
3. 将 `prompts` 映射为触发词/意图示例，`command` 映射为执行模板
4. 若有 Playbook，读取 `catalog.playbooks` 或 workflow 模块的 `playbooks`
5. 按 `env` 区分测试/线上：`test` 禁止误调 `online/`

## 统计

- 模块：10
- 能力：218
- Playbook：0
