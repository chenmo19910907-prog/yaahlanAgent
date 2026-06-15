# 自动化用例（按需求分文件夹）

每个需求独立目录，内含 `catalog.json`、`registry.json`（可选）、`cases/`、`docs/`（可选）。根目录 `catalog.json` 为总索引；`reports/` 为全局报告。

## 目录结构

```
自动化用例/
├── catalog.json
├── reports/                # 固定单报告：report.html + report.json（每次 run 覆盖）
├── 注册登录/
├── 动态-基础/
└── 动态支持视频发布/      # ← 动态支持视频发布需求（主需求示例）
    ├── catalog.json
    ├── registry.json
    ├── cases/
    └── docs/
```

## 新增需求

1. 建 `自动化用例/<需求名>/`（文件夹名与需求一致，如 `动态支持视频发布`）
2. 写 `catalog.json`、`cases/`、可选 `registry.json` / `docs/`
3. 根 `catalog.json` 的 `requirements[]` 登记 `id` + `folder`

## 命令

```bash
python3 adb/adb_execute.py autotest list
python3 adb/adb_execute.py autotest run --requirement req-动态支持视频发布
python3 adb/adb_execute.py autotest generate --requirement req-动态支持视频发布 --id ... 
```

技能：`.cursor/skills/autotest-p0/SKILL.md`
