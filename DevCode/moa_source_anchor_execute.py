#!/usr/bin/env python3
"""MOA 方法名 → 本仓模板 + voga-repos Java 验收锚点。"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from devcode.moa_anchor import anchor_moa_method  # noqa: E402


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="MOA method → 本地源码与已登记模板三联锚定")
    p.add_argument("method", help="MOA method，如 queryOwnPropList")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    args = p.parse_args()
    try:
        report = anchor_moa_method(args.method)
    except ValueError as e:
        if args.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"错误: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"方法: {report['method']}")
        if report.get("suggestedCommand"):
            print(f"试跑: {report['suggestedCommand']}")
        for t in report.get("moaTemplates") or []:
            print(f"  模板 {t['template']} url={t.get('url')}")
        for impl in report.get("moaFacades") or []:
            req = impl.get("request") or {}
            print(f"  实现 {impl['file']}:{impl['line']}")
            if req.get("source"):
                print(f"    入参 {req['reqClass']} ← {req['source']}")
        for h in report.get("acceptanceHints") or []:
            print(f"  验收字段: {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
