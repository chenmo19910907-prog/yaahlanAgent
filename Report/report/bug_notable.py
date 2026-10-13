"""从钉钉 AI 表格（bug 地址 / schedule_links 登记）拉取缺陷并按版本汇总。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NOTABLE_DIR = _REPO_ROOT / "platform" / "mcp_notable_read"
if str(_NOTABLE_DIR) not in sys.path:
    sys.path.insert(0, str(_NOTABLE_DIR))

from notable_client import (  # noqa: E402
    extract_node_id,
    fetch_notable_records,
    field_text,
    resolve_notable_target,
)


def fetch_bug_list_records(bug_url: str) -> list[dict[str, Any]]:
    """拉取 bug AI 表格全量记录（Open API 优先，失败则 Cookie 快照）。"""
    url = (bug_url or "").strip()
    if not url:
        raise ValueError("bug_url 为空")
    node_id = extract_node_id(url)
    doc_key, sheet_id, _, source_url, _dentry = resolve_notable_target(
        url=url,
        node_id=node_id,
    )
    return asyncio.run(
        fetch_notable_records(
            doc_key=doc_key,
            sheet_id=sheet_id,
            node_id=node_id,
            url=source_url or url,
        )
    )


def _field(fields: dict[str, Any], *names: str) -> str:
    for name in names:
        if name in fields:
            text = field_text(fields[name])
            if text:
                return text
    return ""


def defect_levels_from_notable_records(
    records: list[dict[str, Any]],
    version: str,
) -> tuple[dict[str, int], dict[str, int]] | None:
    from report.generator import (  # noqa: WPS433
        _SCHEDULE_DEFECT_FINISHED,
        _accumulate_defect_counts,
        _defect_levels_dict_empty,
    )

    target = (version or "").strip()
    if not target:
        return None
    unf = _defect_levels_dict_empty().copy()
    fin = _defect_levels_dict_empty().copy()
    matched = 0
    for rec in records:
        fields = rec.get("fields") if isinstance(rec, dict) else None
        if not isinstance(fields, dict):
            continue
        ver = _field(fields, "版本", "所属版本", "修复版本")
        if ver != target:
            continue
        matched += 1
        status = _field(fields, "任务状态", "状态", "缺陷状态")
        severity = _field(fields, "严重程度", "级别", "优先级") or None
        _accumulate_defect_counts(unf, fin, status=status, severity=severity)
    if matched == 0:
        return None
    return unf, fin


def defect_levels_from_bug_url(
    version: str,
    bug_url: str,
) -> tuple[dict[str, int], dict[str, int]] | None:
    records = fetch_bug_list_records(bug_url)
    return defect_levels_from_notable_records(records, version)
