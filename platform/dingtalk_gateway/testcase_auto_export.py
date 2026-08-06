"""Agent 生成测试用例后，自动同步 temporary_testcase 到钉钉默认导出目录。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from export_delivery import load_export_config, parse_markdown_table
from project_paths import temporary_testcase_dir

logger = logging.getLogger("dingtalk-gateway")

SUPPORTED_SUFFIXES = {".md", ".csv"}
TESTCASE_PROMPT_RE = re.compile(
    r"(生成|编写|产出|写|整理|补充|扩写).{0,12}(测试用例|用例表|用例|case)",
    re.I,
)


@dataclass
class TestcaseExportItem:
    source: Path
    name: str
    url: str | None = None
    error: str | None = None


def is_testcase_generation_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    if TESTCASE_PROMPT_RE.search(text):
        return True
    try:
        hint = temporary_testcase_dir().name.lower()
        if hint and hint in text.lower():
            return True
    except (ImportError, FileNotFoundError, ValueError, OSError):
        pass
    if "temporary_testcase" in text.lower():
        return True
    return False


def _resolve_testcase_dir(repo_root: Path | str) -> Path:
    try:
        return temporary_testcase_dir()
    except (ImportError, FileNotFoundError, ValueError, OSError):
        return Path(repo_root) / "temporary_testcase"


def find_recent_testcase_files(repo_root: Path | str, *, since_wall_ts: float) -> list[Path]:
    root = Path(repo_root)
    testcase_dir = _resolve_testcase_dir(root)
    if not testcase_dir.is_dir():
        return []
    threshold = since_wall_ts - 1.0
    files: list[Path] = []
    for path in testcase_dir.iterdir():
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if path.stat().st_mtime >= threshold:
            files.append(path)
    return sorted(files, key=lambda item: item.stat().st_mtime)


def _read_markdown_rows(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8")
    rows = parse_markdown_table(text)
    if not rows:
        raise ValueError(f"未找到 Markdown 用例表格：{path.name}")
    return rows


def _workbook_name(path: Path) -> str:
    name = path.stem.strip() or "测试用例"
    return re.sub(r'[\\/:*?"<>|]', "-", name)[:80]


def export_testcase_file(path: Path, *, parent_node_id: str) -> TestcaseExportItem:
    name = _workbook_name(path)
    try:
        if path.suffix.lower() == ".csv":
            from alidocs_excel_export import export_csv_to_folder

            url = export_csv_to_folder(
                path,
                parent_node_id=parent_node_id,
                workbook_name=name,
            )
        else:
            from alidocs_excel_export import export_rows_to_folder

            rows = _read_markdown_rows(path)
            url = export_rows_to_folder(
                rows,
                parent_node_id=parent_node_id,
                workbook_name=name,
            )
        logger.info("测试用例已导出 %s -> %s", path.name, url)
        return TestcaseExportItem(source=path, name=name, url=url)
    except Exception as exc:  # noqa: BLE001
        logger.exception("测试用例导出失败 %s", path.name)
        return TestcaseExportItem(source=path, name=name, error=str(exc))


def export_generated_testcases(
    *,
    repo_root: Path | str,
    prompt: str,
    since_wall_ts: float,
) -> list[TestcaseExportItem]:
    """任务结束后扫描 temporary_testcase，将本任务新写入的用例同步到默认目录。"""
    files = find_recent_testcase_files(repo_root, since_wall_ts=since_wall_ts)
    if not files:
        return []
    if not is_testcase_generation_prompt(prompt):
        logger.info(
            "跳过用例自动导出（非用例生成任务）：files=%s prompt=%s",
            [path.name for path in files],
            prompt[:80],
        )
        return []

    cfg = load_export_config()
    results: list[TestcaseExportItem] = []
    for path in files:
        results.append(export_testcase_file(path, parent_node_id=cfg.node_id))
    return results


def export_generated_testcases_safe(
    *,
    repo_root: Path | str,
    prompt: str,
    since_wall_ts: float,
) -> list[TestcaseExportItem]:
    try:
        return export_generated_testcases(
            repo_root=repo_root,
            prompt=prompt,
            since_wall_ts=since_wall_ts,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("测试用例自动导出失败")
        return [
            TestcaseExportItem(
                source=_resolve_testcase_dir(repo_root),
                name="测试用例",
                error=str(exc),
            )
        ]


def format_testcase_export_message(items: list[TestcaseExportItem]) -> str:
    if not items:
        return ""
    lines: list[str] = []
    for item in items:
        if item.url:
            lines.append(item.url)
        else:
            detail = (item.error or "未知错误").strip()[:200]
            lines.append(f"{item.name} 上传失败：{detail}")
    return "\n".join(lines)
