# -*- coding: utf-8 -*-
"""测试报告扫描与静态文件服务路径。"""
from __future__ import annotations

import os
from datetime import datetime

from web.config import PROJECT_ROOT, SUITES, suite_by_id
from web.models import ReportItem


def _scan_report_dir(report_dir: str, suite_id: str | None, suite_name: str | None) -> list[ReportItem]:
    abs_dir = PROJECT_ROOT / report_dir
    if not abs_dir.is_dir():
        return []
    items: list[ReportItem] = []
    for path in sorted(abs_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in (".html", ".md"):
            continue
        stat = path.stat()
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        items.append(
            ReportItem(
                filename=path.name,
                suite_id=suite_id,
                suite_name=suite_name,
                format="html" if suffix == ".html" else "markdown",
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                url_path=f"/api/reports/files/{rel}",
            )
        )
    return items


def list_reports(suite_id: str | None = None, limit: int = 50) -> list[ReportItem]:
    items: list[ReportItem] = []
    suites = [suite_by_id(suite_id)] if suite_id else list(SUITES)
    for suite in suites:
        if not suite:
            continue
        items.extend(_scan_report_dir(suite.report_dir, suite.id, suite.name))
    items.sort(key=lambda x: x.modified_at, reverse=True)
    return items[: max(1, limit)]


def resolve_report_file(relative_path: str) -> str | None:
    """校验并返回报告文件的绝对路径。"""
    rel = relative_path.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return None
    abs_path = (PROJECT_ROOT / rel).resolve()
    try:
        abs_path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    if not abs_path.is_file():
        return None
    suffix = abs_path.suffix.lower()
    if suffix not in (".html", ".md"):
        return None
    allowed_roots = {(PROJECT_ROOT / suite.report_dir).resolve() for suite in SUITES}
    if abs_path.parent.resolve() not in allowed_roots:
        return None
    return str(abs_path)
