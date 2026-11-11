#!/usr/bin/env python3
"""从前端项目汇总表解析功能对应仓，仅 clone/pull 该 H5 仓（SSH 默认）。"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devcode.fe_pull import ensure_fe_repo, pull_fe_by_feature  # noqa: E402
from devcode.fe_sheet import list_fe_project_rows, resolve_feature  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="读钉钉前端项目汇总表，按功能关键词或仓库名仅拉取对应 yaahlan-fe 独立仓"
    )
    parser.add_argument("--feature", help="功能/项目关键词（匹配 H/O/P 列，如 VIP）")
    parser.add_argument("--repo", help="直接指定仓库名（跳过表解析，如 yaahlan-h5-vip）")
    parser.add_argument("--branch", help="checkout 后 pull 的分支")
    parser.add_argument("--pick", type=int, default=0, help="多命中时取第 N 条（0 起）")
    parser.add_argument("--list", action="store_true", help="列出汇总表全部前端仓（默认知识库，可 --dingtalk 强制在线表）")
    parser.add_argument("--dingtalk", action="store_true", help="解析/列举时跳过知识库，直接读钉钉汇总表")
    parser.add_argument("--resolve-only", action="store_true", help="只解析匹配，不 git")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    try:
        if args.list:
            from devcode.fe_sheet import load_fe_kb_rows  # noqa: WPS433

            rows = list_fe_project_rows(force_dingtalk=args.dingtalk)
            if args.dingtalk:
                src = "dingtalk"
            else:
                src = "kb" if load_fe_kb_rows() else "dingtalk"
            payload = {"ok": True, "count": len(rows), "rows": rows, "resolve_source": src}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                for r in rows:
                    print(f"{r['repo_name']:40} {r.get('project_name', '')}")
            return 0

        if args.repo:
            if args.resolve_only:
                payload = {"ok": True, "repo_name": args.repo.strip()}
            else:
                payload = ensure_fe_repo(args.repo.strip(), branch=args.branch)
                payload = {"ok": payload.get("ok"), "pull": payload}
        elif args.feature:
            if args.resolve_only:
                if args.dingtalk:
                    from devcode.fe_sheet import fetch_fe_project_rows  # noqa: WPS433

                    matches, resolve_source = resolve_feature(
                        args.feature, fetch_fe_project_rows(), resolve_source="dingtalk"
                    )
                else:
                    matches, resolve_source = resolve_feature(args.feature)
                payload = {
                    "ok": bool(matches),
                    "feature_query": args.feature,
                    "resolve_source": resolve_source,
                    "matches": matches,
                }
            else:
                if args.dingtalk:
                    parser.error("--dingtalk 仅用于 --resolve-only 或 --list")
                payload = pull_fe_by_feature(args.feature, branch=args.branch, pick=args.pick)
        else:
            parser.error("请指定 --feature、--repo 或 --list")
            return 2
    except (ValueError, RuntimeError) as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"错误: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.resolve_only and args.feature:
            src = payload.get("resolve_source", "")
            if src:
                print(f"数据来源: {src}")
            for m in payload.get("matches", []):
                print(
                    f"[{m.get('match_score')}] {m.get('repo_name')} — {m.get('project_name')} "
                    f"(行{m.get('row')})"
                )
        elif payload.get("pull"):
            p = payload["pull"]
            if p.get("ok"):
                print(f"[OK] {p.get('repo_name')} ({p.get('branch')} @ {p.get('head')})")
            else:
                print(f"[FAIL] {p.get('repo_name')}: {p.get('error')}", file=sys.stderr)
        elif payload.get("ok") and payload.get("repo_name"):
            print(f"将拉取: {payload['repo_name']}")
        elif isinstance(payload.get("ok"), bool) and payload.get("head"):
            print(f"[OK] {payload.get('repo_name')} ({payload.get('branch')} @ {payload.get('head')})")
        elif not payload.get("ok"):
            print(payload.get("error", "失败"), file=sys.stderr)

    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
