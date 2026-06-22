#!/usr/bin/env python3
"""钉钉网关专用：生成复制按钮版工具平台 HTML，打包 zip 发到群（不生成本地执行版）。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent
PLATFORM_DIR = REPO_ROOT / "platform"
SCRIPTS_DIR = PLATFORM_DIR / "scripts"
EXPORT_DIR = GATEWAY_DIR / "exports" / "catalog"
HTML_NAME = "Yaahlan智能工具平台.html"
ZIP_NAME = "Yaahlan智能工具平台.zip"


def _ensure_scripts_path() -> None:
    scripts = str(SCRIPTS_DIR)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)


def export_catalog_for_dingtalk() -> dict[str, object]:
    _ensure_scripts_path()
    from generate_catalog import _load_catalog_data, refresh_catalog_standalone  # noqa: WPS433

    refresh_catalog_standalone(quiet=True)

    standalone = PLATFORM_DIR / "catalog-standalone.html"
    if not standalone.is_file():
        raise RuntimeError("catalog-standalone.html 未生成")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = EXPORT_DIR / HTML_NAME
    shutil.copy2(standalone, html_path)

    zip_path = EXPORT_DIR / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(html_path, arcname=HTML_NAME)

    data = _load_catalog_data()
    total_items = int(data.get("total_items") or 0)
    module_count = int(data.get("module_count") or 0)

    return {
        "ok": True,
        "html": html_path,
        "html_name": HTML_NAME,
        "zip": zip_path,
        "zip_name": ZIP_NAME,
        "total_items": total_items,
        "module_count": module_count,
        "summary": (
            f"共 {module_count} 个一级模块、{total_items} 项能力；"
            "离线版提示语为「复制」按钮，粘贴到 Cursor 使用。"
        ),
    }


def _format_success(result: dict[str, object]) -> str:
    modules = result.get("module_count")
    items = result.get("total_items")
    html_name = str(result.get("html_name") or HTML_NAME)
    zip_name = str(result.get("zip_name") or ZIP_NAME)
    lines = [
        "[OK] 工具平台离线版已生成。",
        f"附件 {zip_name} 内含复制按钮版 HTML（{html_name}），请下载解压后用浏览器打开。",
        f"共 {modules} 个一级模块、{items} 项能力。",
    ]
    summary = str(result.get("summary") or "").strip()
    if summary and summary not in lines[-1]:
        lines.append(summary)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="钉钉网关：生成复制按钮版工具平台 HTML 并打包 zip")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供网关解析附件路径）")
    args = parser.parse_args(argv)

    try:
        result = export_catalog_for_dingtalk()
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        else:
            print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.json:
        serializable = {
            "ok": True,
            "html": str(result["html"]),
            "html_name": result["html_name"],
            "zip": str(result["zip"]),
            "zip_name": result["zip_name"],
            "total_items": result["total_items"],
            "module_count": result["module_count"],
            "summary": result["summary"],
        }
        print(json.dumps(serializable, ensure_ascii=False))
        return 0

    print(_format_success(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
