"""自动化用例目录路径（按需求分文件夹）。"""

from __future__ import annotations

from pathlib import Path

from ..paths import ADB_ROOT

AUTOTEST_ROOT = ADB_ROOT / "自动化用例"
LEGACY_CASES_DIR = AUTOTEST_ROOT / "cases"
REPORTS_DIR = AUTOTEST_ROOT / "reports"
REPORT_JSON_PATH = REPORTS_DIR / "report.json"
REPORT_HTML_PATH = REPORTS_DIR / "report.html"
REPORT_META_PATH = REPORTS_DIR / "latest.json"
CATALOG_PATH = AUTOTEST_ROOT / "catalog.json"
P0_CATALOG_PATH = AUTOTEST_ROOT / "p0_catalog.json"
LEGACY_REGISTRY_DIR = AUTOTEST_ROOT / "registry"
TEMPLATES_DIR = AUTOTEST_ROOT / "templates"


def requirement_dir(folder: str) -> Path:
    return AUTOTEST_ROOT / folder.strip()


def requirement_cases_dir(folder: str) -> Path:
    return requirement_dir(folder) / "cases"


def requirement_catalog_path(folder: str) -> Path:
    return requirement_dir(folder) / "catalog.json"


def requirement_registry_path(folder: str) -> Path:
    return requirement_dir(folder) / "registry.json"


def ensure_reports_dir() -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR


def ensure_requirement_cases_dir(folder: str) -> Path:
    path = requirement_cases_dir(folder)
    path.mkdir(parents=True, exist_ok=True)
    return path
