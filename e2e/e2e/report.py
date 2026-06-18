"""运行报告。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .paths import reports_dir


def new_report(*, case_id: str, case_path: str) -> dict[str, Any]:
    return {
        "caseId": case_id,
        "casePath": case_path,
        "startedAt": time.time(),
        "loop": "perceive-think-act",
        "iterations": [],
        "fixtures": [],
        "status": "running",
    }


def save_report(report: dict[str, Any], *, name: str | None = None) -> Path:
    reports_dir().mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    file_name = name or f"report-{report.get('caseId', 'case')}-{stamp}.json"
    path = reports_dir() / file_name
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
