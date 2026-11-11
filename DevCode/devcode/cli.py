"""DevCode CLI。"""

from __future__ import annotations

import argparse
import json
import sys

from devcode.pull import pull_repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="拉取 voga-repos 下服务端、Android/iOS 与 yaahlan-fe H5 开发代码（清单见 DevCode/config/repos.json）"
    )
    parser.add_argument("--repo", help="仅拉取指定仓库名（见 DevCode/config/repos.json）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    try:
        report = pull_repos(only=args.repo)
    except ValueError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"错误: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for row in report["results"]:
            name = row["name"]
            if not row.get("ok"):
                print(f"[FAIL] {name}: {row.get('error', 'unknown')}")
                continue
            head = row.get("head", "")
            branch = row.get("branch", "")
            msg = row.get("pull_stdout", "") or "Already up to date."
            print(f"[OK] {name} ({branch} @ {head}) — {msg}")
        if report["failed"]:
            print(f"\n失败 {report['failed']} / {len(report['results'])}", file=sys.stderr)

    return 0 if report["ok"] else 1
