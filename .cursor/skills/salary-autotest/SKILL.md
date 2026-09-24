---
name: salary-autotest
description: Yaahlan 算薪专项 pytest E2E 自动化：半月结算薪、主播豁免、公会进步奖、退款黑名单、确认应得薪资。在用户要跑算薪测试、算薪回归、半月结冒烟、公会进步奖验证、算薪报告时使用。
---

# 算薪专项自动化测试

## 何时使用

- 用户说：**算薪测试**、**半月结算薪**、**公会进步奖**、**退款黑名单算薪**、**确认应得薪资**、**算薪回归/冒烟/报告**
- 需要验证扣减系数、等级边界、预提、进步奖 `motivation_amount` 等

## 统一入口

```bash
python3 Salary/salary_execute.py <子命令>
```

| 子命令 | 说明 |
|--------|------|
| `check-env` | 环境检查（Python、pytest、MySQL 依赖） |
| `list-suites` | 列出套件 |
| `list-cases <suite>` | 列出用例名 |
| `run <suite> [--smoke\|--report\|--case NAME]` | 执行 pytest |
| `cc-config [key]` | 读盘古配置（公会激励开关） |
| `dashboard` | 可视化后台 :8088 |

**suite**：`cycle` | `exempt` | `guild-progress` | `refund-blacklist` | `confirm`

## 前置条件

1. `Salary/.env`（从 `.env.example` 复制）填 `MYSQL_HOST/USER/PASSWORD`
2. 内网 MOA lookup（Redis）；算薪 MOA：`/service/yaahlan-cms/anchor-salary-moa` · alpha
3. `pip install -r Salary/requirements.txt`
4. **确认应得薪资**（写操作）：`RUN_CONFIRM_BY_AREA=1` + CMS 凭证（见 `utils/cms_gateway.py`）

## 常用命令

```bash
# 环境检查
python3 Salary/salary_execute.py check-env

# 半月结冒烟（P0 预提等）
python3 Salary/salary_execute.py run cycle --smoke -v

# 半月结全量 + MD/HTML 报告 + 钉钉（已配 Webhook）
python3 Salary/salary_execute.py run cycle --report -v

# 单条用例
python3 Salary/salary_execute.py run cycle --case cycle_salary_factor_0_6_double_fail -v

# 公会进步奖（新政策）
python3 Salary/salary_execute.py run guild-progress --guild-progress-policy=202608 -v

# 确认应得薪资（须用户明确允许写操作）
RUN_CONFIRM_BY_AREA=1 python3 Salary/salary_execute.py run confirm -v
```

## 执行流程（每条 E2E）

1. MySQL 造数 / 清理 → 写 `anchor_work_statistic`（表1）
2. MOA1 `testUpdateSnapshotData` → 表2 半月快照
3. MOA2 `generateAnchorSalary` → 表3/表4
4. 断言 `expected_t3` / `expected_t4`（JSON 在 `Salary/data/salary/`）

## 业务文档

- `Salary/docs/yaahlan_salary/算薪业务逻辑.md`
- 工具台：`python3 platform/open_catalog.py` → 筛选 **算薪**

## Agent 注意

- **测试环境 only**；不写线上
- `confirm` 套件会改确认表，默认跳过；用户未明确要求不要跑
- 失败时读 pytest 输出 + `Salary/docs/yaahlan_salary/cycle_salary/reports/` 最新报告
- 用例数据在 JSON，扩场景优先改 `data/salary/*_cases.json`
