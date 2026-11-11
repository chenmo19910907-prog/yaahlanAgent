#!/usr/bin/env python3
"""代码×用例交叉审查：输出 Web 面板场景清单 JSON。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
PANEL_PATH = REPO / "DevCode/config/code_testcase_review_panel.json"


def load_catalog() -> dict[str, Any]:
    with PANEL_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError("code_testcase_review_panel.json 格式错误")
    return data


def scenarios_for_web() -> dict[str, Any]:
    catalog = load_catalog()
    scenarios_out: list[dict[str, Any]] = []
    for raw in catalog.get("scenarios") or []:
        if not isinstance(raw, dict):
            continue
        scenarios_out.append(
            {
                "key": raw.get("key"),
                "docIndex": raw.get("doc_index"),
                "name": raw.get("name"),
                "guideShort": str(raw.get("guide_short") or "").strip(),
                "usageNote": str(raw.get("usage_note") or "").strip(),
                "promptTemplate": str(raw.get("prompt") or "").strip(),
            }
        )
    web_usage = catalog.get("web_usage") or {}
    return {
        "docNote": catalog.get("doc_note") or "",
        "panelTitle": str(web_usage.get("title") or "").strip(),
        "web_usage": web_usage,
        "skillPath": catalog.get("skill_path") or "",
        "registryId": catalog.get("registry_id") or "code_testcase_review",
        "scenarios": scenarios_out,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="用例审查 Web 面板配置")
    parser.add_argument("--scenarios-json", action="store_true", help="输出场景清单（Web 用）")
    args = parser.parse_args()
    if args.scenarios_json:
        print(json.dumps(scenarios_for_web(), ensure_ascii=False))
        return 0
    print("需要 --scenarios-json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
