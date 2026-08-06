# 多项目 Agent 配置

通过 **`AGENT_PROJECT`**（或 `PROJECT`）选择项目，默认 `yaahlan`。**adb 录制脚本 / 自动化用例 / App 包名** 亦随 `paths.adbScriptsRoot`、`paths.adbAutotestRoot` 与 `app.androidPackage` 切换；**adb 运行时代码**（`adb_execute.py`、Python 库）仍固定于仓库 `adb/`。

## 目录

```text
projects/
  yaahlan/
    project.json       # 品牌 + 全模块路径 + appId/tunnel 等
    sources.json       # 工具台模块登记
  _template/           # 新项目模板
```

## 切换项目

```bash
export AGENT_PROJECT=yaahlan
python3 platform/open_catalog.py
python3 Admin/admin_execute.py --query-user-id 100465989
```

## `project.json` 路径（`paths`）

| 键 | 用途 |
|----|------|
| `sources` | 工具台 catalog 模块列表 |
| `adminConfig` | Admin 测试后台 API |
| `onlineConfig` | 线上 Admin/MOA/Tunnel |
| `moaThresholds` / `moaTemplates` / `moaRuntimeYaml` / `moaRegistry` | MOA 阈值、模板库、运行时、能力 registry |
| `adminRegistry` / `mseRegistry` / `giftRegistry` / … | 各模块 catalog registry（bootstrap 复制到 `config/*-registry.json`） |
| `moaGenerativeRoot` / `workflowRoot` | MOA-generative 映射表、工作流 JSON（可 symlink 共用） |
| `mseConfig` | MSE 服务配置 |
| `riskConfig` | 风控接口与测试机 KB |
| `giftCpLoveConfig` | CP 宝箱送礼规划 |
| `dingtalkKb` / `dingtalkFolders` | 用例同步钉钉目录 |
| `testcaseKbRoot` / `prdKbRoot` / `bugKbRoot` | 知识库根目录 |
| `testDevices` / `onlineTestAccounts` | 测试机与账号池 |
| `temporaryTestcase` | 生成用例落盘目录 |
| `adbScriptsRoot` / `adbAutotestRoot` | ADB 录制脚本库、P0 自动化用例根（新项目 bootstrap 默认 symlink 至 `adb/录制脚本`、`adb/自动化用例`） |

## 环境与业务（`app` / `tunnel`）

| 键 | 用途 |
|----|------|
| `app.appId` | Gift Stage 送礼、MOA 默认 appId |
| `app.cmdbAppKey` / `cmdbCorp` / `cmdbEnv` | CMDB 查实例 |
| `tunnel.mockBaseUrl` | Tunnel Mock 相对 URI 补全 |
| `tunnel.defaultGAppid` / `defaultGEnv` | 抓包默认过滤 |

## 新建第二个 App

### 快速验证（已有 `projects/example`）

```bash
# 若尚未 bootstrap，先从 Yaahlan 复制 config 到项目目录：
python3 projects/scripts/bootstrap_project_configs.py example

export AGENT_PROJECT=example
python3 platform/project/verify_second_project.py
python3 platform/open_catalog.py          # 标题随 AGENT_PROJECT 品牌变化
```

`open_catalog` / `generate_catalog.py` 会按 `AGENT_PROJECT` 解析 **全部模块** registry 路径（Admin/MOA/MSE/Gift/…），并刷新 catalog 标题。

`example` 已有 **独立** `config/`、`knowledge/`、`temporary_testcase/`、`moa/config/registry.json`；以下默认为 **symlink** 至仓库共享目录（bootstrap 可一键创建）：

| 项目路径 | 默认指向 |
|----------|----------|
| `moa/templates` | `MOA/templates` |
| `workflow` | `workflow/` |
| `moa-generative` | `MOA-generative/` |
| `adb/scripts` | `adb/录制脚本` |
| `adb/autotest` | `adb/自动化用例` |

**运行时**（`moa_execute.py`、`workflow_execute.py`、Python 库）始终共用仓库 `MOA/`、`workflow/`，仅 **数据目录** 随 `paths.*` 切换。

### 从零新建

1. `cp -R projects/_template projects/myapp`
2. `python3 projects/scripts/bootstrap_project_configs.py myapp`
3. 按需改 `projects/myapp/project.json` 的 `agent` / `app` / `api` 及 `config/*.json`
4. `export AGENT_PROJECT=myapp`

## 新建项目（模板）

1. `cp -R projects/_template projects/myapp`
2. 复制并改写各 `config/*.json`、`moa/templates/`、知识库到 `projects/myapp/`
3. 更新 `project.json` 中全部 `paths` 与 `agent` 品牌
4. `AGENT_PROJECT=myapp python3 platform/scripts/generate_catalog.py`

## `api`（Stage 网关 / ServiceUrl / H5）

| 键 | 用途 |
|----|------|
| `stageGatewayBase` | Admin CMS / 部分 Stage API 网关域名 |
| `httpPrefix` | HTTP 路径前缀（如 `/yaahlan`） |
| `moaServicePrefix` / `moaTrickServicePrefix` | MOA ServiceUrl 前缀 |
| `familyPkH5Path` | 家族 PK 活动 H5 |
| `endpoints.*` | 主播列表、wallet-api、intimate-api 等 endpoint |

## 脚本路径助手

| 模块 | 路径 |
|------|------|
| `platform/project/repo_paths.py` | `moa_execute_path()` / `moa_template()` / `tmp_dir()` |
| `platform/project/catalog_paths.py` | catalog 模块 registry 路径（MOA / workflow / generative） |
| `platform/dingtalk_gateway/repo_paths.py` | 网关 family PK / anchor 脚本 |
| `scripts/project_paths.py` | 知识库 / 用例目录 |
| `MOA/scripts/moa_script_paths.py` | MOA 脚本：`moa_template_repo_rel()` / 网关 / tmp |
| `adb/adb/project_paths.py` / `adb/scripts/adb_script_paths.py` | ADB 录制脚本根、MOA/Admin execute |
| `MOA-generative/scripts/project_api.py` | ServiceUrl / body 模板 |
| `workflow/scripts/project_api.py` | 工作流 MOA 路径 |

平台代码（Web Agent、钉钉网关、registry 机制）不变；**换项目 = 换 `projects/<id>/` 数据包**。
