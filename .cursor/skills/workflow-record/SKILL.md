---
name: workflow-record
description: 工作流录制与参数化复用。用户在 Agent 描述多步流程（MOA/脚本组合）时，落库为 workflow/workflows/*.json，登记 registry，下次用 workflow_execute.py run 改参执行。用于「录制工作流」「复用流程」「参数化跑 MOA 组合」。
---

# 工作流录制与复用

## 何时使用

- 用户描述**多步可重复流程**（如「先清匹配再结算发奖」）
- 同一流程需**改日期/用户等参数**反复执行
- 希望沉淀为**一条命令**而非每次口述全流程

## 工作流文件位置

| 项 | 路径 |
|----|------|
| 定义 | `workflow/workflows/<id>.json` |
| 能力登记 | `workflow/config/registry.json` |
| 执行入口 | `python3 workflow/workflow_execute.py` |

## JSON 结构（最小）

```json
{
  "id": "my-workflow",
  "name": "显示名称",
  "category": "分类（写入 registry）",
  "description": "一句话说明",
  "version": 1,
  "params": {
    "pkDate": {
      "label": "PK日期",
      "type": "date",
      "required": true,
      "prompt": "yyyy-MM-dd"
    }
  },
  "steps": [
    {
      "id": "step_1",
      "name": "步骤名",
      "run": {
        "type": "moa_template",
        "template": "MOA/templates/xxx.json",
        "patch": {
          "params[0].value": "{{pkDate}}"
        },
        "timeout_ms": 180000
      },
      "expect": { "ec": [0, 200] }
    }
  ]
}
```

### 步骤类型

| type | 说明 |
|------|------|
| `moa_template` | 加载 MOA 模板 JSON，`patch` 按路径改字段后调 `moa_execute.py --payload-file` |
| `shell` | `command` + 可选 `cwd`；支持 `{{param}}` 占位符 |

`patch` 路径示例：`params[0].value.date`、`settings.time`。

## Agent 录制流程（必须）

1. 与用户确认**参数**（日期、userId、超时等）和**步骤顺序**
2. 写入 `workflow/workflows/<id>.json`（或 `init` 后编辑）
3. 落库并登记：

```bash
python3 workflow/workflow_execute.py record --file workflow/workflows/<id>.json
```

4. 确认 `python3 workflow/scripts/generate_index.py` 已跑（`record` 会自动调用）
5. 用示例参数试跑验收：

```bash
python3 workflow/workflow_execute.py run <id> --pk-date 2026-06-29
```

## 用户复用命令

```bash
# 列表
python3 workflow/workflow_execute.py list

# 查看定义
python3 workflow/workflow_execute.py show family-pk-daily-rematch

# 带参执行
python3 workflow/workflow_execute.py run family-pk-daily-rematch --pk-date 2026-06-30

# 额外参数
python3 workflow/workflow_execute.py run my-flow --set userId=100486375
```

执行报告写入 `.tmp/workflow_runs/`。

## 空白模板

```bash
python3 workflow/workflow_execute.py init my-workflow --name "我的流程"
```

编辑 JSON 后再 `record`。

## 禁止

- 把工作流当成批量盲跑列表（仍须逐步验收、失败改 JSON）
- 只改 `workflows/*.json` 不 `record` / 不刷新 registry
- 手改 `platform/catalog.html`

## 内置示例

`family-pk-daily-rematch`：清除 `pkDate` 匹配 → `runFamilyPkMatchTask`（前日发奖 + 重匹配）。

`family-pk-config-mse-to-dingtalk`：MSE `familyPkConfig` → 钉钉参数表（merge 更新原表）。

`family-pk-config-pk-list-to-dingtalk`：抓包 `getFamilyPkPage` 指定日期 tab → Sheet2「家族PK列表」（家族/成员/手机号，族长标记）；同时将钉钉文档重命名为 **`家族PK-{pkDate}测试`**（如 `家族PK-2026-07-02测试`）。

`family-pk-config-rank-rematch`：收礼榜随机造数 + 次日 PK 清除重匹配。

`family-pk-config-match-verify`：抓包 PK 列表 + 收礼榜区间验收 → Sheet3「匹配验收」。

`family-pk-config-sheet-to-json`：改完参数表后 → 写回 `configValue_JSON` Sheet。
