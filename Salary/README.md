# Salary · Yaahlan 算薪专项自动化测试

已融合进 **auto-generate-testcase** 工具平台。基于 **pytest** 的数据驱动 E2E：MySQL 造数 → MOA 算薪 → 断言表3/表4。

**Agent / 工具台入口**：`python3 Salary/salary_execute.py`

## 目录结构

| 路径 | 作用 |
|------|------|
| `business_case/` | 测试脚本，按业务线分子目录 |
| `data/` | 用例与配置 JSON，与脚本中的 `DATA_SUBDIR` 对应 |
| `utils/` | 通用工具（如 `JsonUtils`、`MySQLUtils`、`MoaUtils`、`CcConfigUtils`；算薪 pytest 调 alpha MOA1/2；盘古配置中心读开关/白名单） |
| `momoKit/` | MOA 客户端（`MoaClient`，供 `utils/moa_utils` 使用） |
| `module/` | 可复用的纯逻辑/封装，供用例调用 |
| `scripts/` | 非 pytest 收集的辅助脚本 |
| `web/` | 可视化测试后台（FastAPI MVP：用例浏览、触发执行、报告查看） |
| `conftest.py` | 项目根、`data` 路径等全局常量 |
| `pytest.ini` | 测试发现路径、markers、日志等 |
| `docs/common/` | 数据驱动测试通用规范（与具体算薪业务解耦） |
| `docs/yaahlan_salary/` | Yaahlan 算薪**业务逻辑**与**算薪政策**文档 |

## 运行

```bash
cd /Users/user/code/yaahlan-calc-salary-test
python3 scripts/check_env.py
pip install -r requirements.txt
pytest
# 公会进步奖：默认 202512 旧口径；新周期切新政策时加 --guild-progress-policy=202608
pytest --guild-progress-policy=202512
# 读公会激励新版本开关 / 白名单（盘古配置中心，无需打开 MSE 页面）
python3 utils/cc_config.py
python3 utils/cc_config.py tradeMotivationMaxCycleSwitch
# 确认应得薪资（按大区写操作，默认跳过）
RUN_CONFIRM_BY_AREA=1 pytest business_case/salary/confirm_salary/test_yaahlan_confirm_salary.py -v
```

### 可视化后台（MVP）

```bash
bash scripts/run_web_dashboard.sh
# 浏览器打开 http://127.0.0.1:8088
# 内网部署时在 .env 配置 DASHBOARD_TOKEN
```

功能：浏览用例表、选中/全量触发 pytest、查看任务日志与历史 HTML/Markdown 报告。

示例用例：`business_case/salary/cycle_salary/test_yaahlan_cycle_salary.py`，数据：`data/salary/cycle_salary/yaahlan_cycle_salary_cases.json`。确认入库：`business_case/salary/confirm_salary/`。

## 扩展业务用例

1. 在 `data/<业务线>/` 增加用例表 JSON（建议顶层含 `cases` 数组）。
2. 在 `business_case/<业务线>/` 增加 `test_*.py`，用 `JsonUtils.jsonfile_to_dict(category, json_name)` 加载后与 `pytest.mark.parametrize` 或统一 `run_cases` 循环配合执行。

## Cursor 与通用规范

- **Agent Skills**：`.cursor/skills/`（数据驱动、文件化计划、`moa-call`、格式示例）；规则：`.cursor/rules/`。算薪 E2E 仍用 `utils/moa_utils.py`；临时调 stage MOA / melon-gateway（含确认应得薪资）用 `.cursor/skills/moa-call/`。
- **文档规范**：`docs/common/`（用例命名、报告、幻觉检查、测试方案等，与业务解耦；编写用例与报告时优先查阅）。
- **算薪业务与政策**：`docs/yaahlan_salary/`（业务逻辑、政策口径、锚点与跨会话记忆等）。
