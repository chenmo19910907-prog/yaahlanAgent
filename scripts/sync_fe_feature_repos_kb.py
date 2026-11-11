#!/usr/bin/env python3
"""从钉钉「前端项目汇总」表同步功能→仓库映射到 testcase-kb。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
_DEVCODE = ROOT / "DevCode"
if str(_DEVCODE) not in sys.path:
    sys.path.insert(0, str(_DEVCODE))

from project_paths import testcase_kb_root  # noqa: E402
from devcode.fe_repos import fe_clone_transport, fe_clone_url  # noqa: E402
from devcode.fe_sheet import (  # noqa: E402
    fetch_fe_project_rows,
    fe_projects_sheet_config_path,
    load_fe_projects_sheet_config,
)
from devcode.paths import repos_config_path  # noqa: E402


def _escape_md(value: str) -> str:
    return (value or "—").replace("|", "\\|").replace("\n", " ")


def _enrich_rows(rows: list[dict[str, str]], *, repos_dir: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        repo = row.get("repo_name", "").strip()
        if not repo:
            continue
        item = dict(row)
        item["local_path"] = f"{repos_dir}/{repo}"
        try:
            item["clone_url"] = fe_clone_url(repo)
        except ValueError:
            item["clone_url"] = ""
        out.append(item)
    return out


def build_markdown(
    entries: list[dict[str, str]],
    *,
    workbook_url: str,
    sheet_name: str,
    synced_at: str,
    repos_dir: str,
    clone_transport: str,
) -> str:
    lines = [
        "# 前端 H5 功能与代码仓",
        "",
        "> **文档类型**：开发资源知识库（yaahlan-fe 独立 H5 仓 ↔ 功能映射）",
        "> **数据来源**：`testcase-kb/fe_feature_repos.json`（运行时优先；未命中功能时再读钉钉汇总表）",
        f"> **钉钉汇总表**：[前端项目汇总]({workbook_url}) · Sheet `{sheet_name}`（H 项目 / O 仓名 / P 功能）",
        f"> **最近同步**：{synced_at}",
        "",
        "| 项 | 说明 |",
        "|---|---|",
        "| 用途 | 按功能/项目名查对应 git 仓；与九仓 `voga_pull` 清单分离 |",
        "| 本地路径 | `voga-repos/<O列仓名>/` |",
        f"| Clone | 默认 **{clone_transport.upper()}**（`DevCode/config/repos.json`） |",
        "| 按功能拉仓 | `python3 DevCode/fe_pull_execute.py --feature <关键词>` |",
        "| 维护命令 | `python3 scripts/sync_fe_feature_repos_kb.py` |",
        "",
        "---",
        "",
        "## 查询指引",
        "",
        "- **已知功能名（如 VIP、跨房PK）** → 本表「功能描述」或「项目名」列模糊匹配，读「仓库名」",
        "- **拉代码** → `python3 DevCode/fe_pull_execute.py --feature <关键词>`（先本库；未命中再读钉钉汇总表）",
        "- **已知仓库名** → `python3 DevCode/fe_pull_execute.py --repo <仓库名>`",
        "",
        "## 映射清单",
        "",
        f"共 **{len(entries)}** 条。",
        "",
        "| 行 | 项目名 (H) | 仓库名 (O) | 功能描述 (P) | 本地路径 |",
        "|---:|---|---|---|---|",
    ]
    for e in sorted(entries, key=lambda x: (x.get("repo_name", ""), int(x.get("row", "0") or 0))):
        lines.append(
            "| "
            + " | ".join(
                _escape_md(str(e.get(k, "")))
                for k in ("row", "project_name", "repo_name", "feature_desc", "local_path")
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="同步钉钉前端项目汇总表 → testcase-kb")
    parser.add_argument(
        "--output-dir",
        default=str(testcase_kb_root()),
        help="知识库输出目录（默认 testcase-kb/）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只拉表不写文件")
    args = parser.parse_args()

    cfg = load_fe_projects_sheet_config()
    workbook_url = str(cfg.get("workbook_url") or "").strip()
    sheet_name = str(cfg.get("sheet_name") or "版本").strip()

    with open(repos_config_path(), "r", encoding="utf-8") as f:
        repos_cfg = json.load(f)
    repos_dir = str(repos_cfg.get("repos_dir") or "voga-repos").strip()

    try:
        rows = fetch_fe_project_rows()
    except Exception as e:
        print(f"错误: 读取汇总表失败: {e}", file=sys.stderr)
        return 1

    entries = _enrich_rows(rows, repos_dir=repos_dir)
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    transport = fe_clone_transport()

    payload = {
        "kbPath": "testcase-kb/fe_feature_repos.json",
        "workbookUrl": workbook_url,
        "sheetName": sheet_name,
        "configPath": str(Path(fe_projects_sheet_config_path()).relative_to(ROOT)),
        "syncedAt": synced_at,
        "count": len(entries),
        "reposDir": repos_dir,
        "cloneTransport": transport,
        "entries": entries,
    }

    if args.dry_run:
        print(json.dumps({"ok": True, "count": len(entries), "syncedAt": synced_at}, ensure_ascii=False))
        return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "fe_feature_repos.json"
    md_path = output_dir / "前端H5仓.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        build_markdown(
            entries,
            workbook_url=workbook_url,
            sheet_name=sheet_name,
            synced_at=synced_at,
            repos_dir=repos_dir,
            clone_transport=transport,
        ),
        encoding="utf-8",
    )

    print(f"已同步 {len(entries)} 条 → {md_path}")
    print(f"JSON 索引 → {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
