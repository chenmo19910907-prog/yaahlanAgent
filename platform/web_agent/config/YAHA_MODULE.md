# Web Agent 工具台 · Yaha 模块

Yaha（`com.immomo.yaha`）与 Yaahlan（`com.immomo.biz.yaahlan`）共用本仓库能力与知识库，但**验收场景、投放区、盘古/MSE 分流、测试账号 regApp** 不同。左侧 **Yaha** 目录只收 **Yaha 包专属或验收时必须用 Yaha 包/账号** 的入口，不在此目录重复挂通用 MOA（仍在原「公会 / 用户 / …」模块）。

## 左侧目录（`catalog_nav.json`）

| 子文件夹 | 放什么 |
|---------|--------|
| **大区与 IP 验收** | Yaha 主投放南亚/南美（IN、BR 等）相关造数、IP 核对；可挂共享能力**快捷方式** |
| **签到与任务** | 盘古 workflow（如 `yaha_pangu_task_show_switch`）+ 表单改参发布；registry `category` 建议 `Yaha-盘古配置（workflow）` |
| **测试账号** | `regApp=yaha` 账号查询/发放类能力（勿与 Yaahlan 通用账号混放） |
| **仅 Yaha 生效配置** | MSE/盘古里仅 Yaha 分流读的 key、Banner `packageId` 等 |

新增能力时：

1. **registry** 照旧登记；`category` 以 **`Yaha-`** 开头 → 平台 catalog 一级自动进 **Yaha**（见 `sources.json` → `top_level_rules`）。
2. **仅 Web 入口需要**时，在 `catalog_nav.json` → 上表对应 `folder.children` 增加 `cap` 节点（`sourceId` + `registryId`，`moduleId` 仍为能力真实所属模块，如 `用户`、`公会`）。
3. **禁止**把已在「公会常用moa工具」等处的 `cap` **剪切**走；Yaha 下可用**同 registry 的快捷方式**（复制节点，不改原位置）。

## 真机

ADB 默认 Yaahlan；测 Yaha 包时 `adb_execute.py` 使用 `--app yaha`（见 `adb/adb/apps.py`）。真机片段仍以 `adb/录制脚本` 为主，待登记 registry 后再挂 cap。

## 知识库

Yaha 用例片段见 `testcase-kb/游戏.md` 下 `yaha【…】` 标题；账号资产见 `testcase-kb` / 钉钉目录，**regApp** 字段区分包体。