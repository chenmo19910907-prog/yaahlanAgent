"""从钉钉「前端项目汇总」表解析功能 → 仓库名。"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from devcode.paths import config_dir, repo_root

_SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / ".cursor/skills/code-testcase-review/scripts"


def _col_letter_to_index(letter: str) -> int:
    s = (letter or "").strip().upper()
    if not s or not re.fullmatch(r"[A-Z]+", s):
        raise ValueError(f"无效列名: {letter!r}")
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def fe_projects_sheet_config_path() -> str:
    return str(Path(config_dir()) / "fe_projects_sheet.json")


def load_fe_projects_sheet_config() -> dict[str, Any]:
    path = fe_projects_sheet_config_path()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("fe_projects_sheet.json 必须是 object")
    return data


def _workbook_id_from_url(url: str) -> str:
    m = re.search(r"/nodes/([A-Za-z0-9_-]+)", url or "")
    if m:
        return m.group(1)
    m = re.search(r"workbookId=([A-Za-z0-9_-]+)", url or "")
    if m:
        return m.group(1)
    raise ValueError(f"无法从 URL 解析 workbookId: {url}")


def _cell(row: list, col_index: int) -> str:
    if col_index < 0 or col_index >= len(row):
        return ""
    return str(row[col_index] or "").strip()


def parse_fe_project_rows(values: list[list], *, cfg: dict[str, Any]) -> list[dict[str, str]]:
    cols = cfg.get("columns")
    if not isinstance(cols, dict):
        raise ValueError("fe_projects_sheet.json 缺少 columns")
    idx_project = _col_letter_to_index(str(cols.get("project_name", "H")))
    idx_repo = _col_letter_to_index(str(cols.get("repo_name", "O")))
    idx_feat = _col_letter_to_index(str(cols.get("feature_desc", "P")))
    start = int(cfg.get("data_start_row", 2))
    out: list[dict[str, str]] = []
    for i, row in enumerate(values):
        row_no = i + 1
        if row_no < start:
            continue
        repo = _cell(row, idx_repo).strip()
        if not repo:
            continue
        out.append(
            {
                "row": str(row_no),
                "project_name": _cell(row, idx_project),
                "repo_name": repo,
                "feature_desc": _cell(row, idx_feat),
            }
        )
    return out


async def fetch_fe_project_rows_async() -> list[dict[str, str]]:
    if str(_SKILL_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SKILL_SCRIPTS))
    from dingtalk_sheet import find_sheet_id, get_token, read_range  # noqa: WPS433

    cfg = load_fe_projects_sheet_config()
    url = str(cfg.get("workbook_url") or "").strip()
    sheet_name = str(cfg.get("sheet_name") or "版本").strip()
    max_row = int(cfg.get("max_row", 200))
    workbook_id = _workbook_id_from_url(url)

    token, op = await get_token()
    sheet_id = await find_sheet_id(token, op, workbook_id, sheet_name)
    if not sheet_id:
        raise RuntimeError(f"未找到 Sheet: {sheet_name!r}")

    cols = cfg["columns"]
    letters = sorted(
        {str(cols.get("project_name", "H")), str(cols.get("repo_name", "O")), str(cols.get("feature_desc", "P"))},
        key=_col_letter_to_index,
    )
    range_str = f"{letters[0]}1:{letters[-1]}{max_row}"
    values = await read_range(token, op, workbook_id, sheet_id, range_str)

    # read_range 可能只返回子列；按配置的绝对列号从相对块中取
    base_col = _col_letter_to_index(letters[0])
    idx_project = _col_letter_to_index(str(cols.get("project_name", "H"))) - base_col
    idx_repo = _col_letter_to_index(str(cols.get("repo_name", "O"))) - base_col
    idx_feat = _col_letter_to_index(str(cols.get("feature_desc", "P"))) - base_col
    start = int(cfg.get("data_start_row", 2))
    out: list[dict[str, str]] = []
    for i, row in enumerate(values):
        row_no = i + 1
        if row_no < start:
            continue
        repo = _cell(row, idx_repo).strip()
        if not repo:
            continue
        out.append(
            {
                "row": str(row_no),
                "project_name": _cell(row, idx_project),
                "repo_name": repo,
                "feature_desc": _cell(row, idx_feat),
            }
        )
    return out


def fetch_fe_project_rows() -> list[dict[str, str]]:
    return asyncio.run(fetch_fe_project_rows_async())


def fe_feature_kb_path() -> Path:
    return Path(repo_root()) / "testcase-kb" / "fe_feature_repos.json"


def load_fe_kb_rows() -> list[dict[str, str]] | None:
    """读取 testcase-kb/fe_feature_repos.json；缺失或空则返回 None。"""
    path = fe_feature_kb_path()
    if not path.is_file():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return None
    out: list[dict[str, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        repo = str(item.get("repo_name") or "").strip()
        if not repo:
            continue
        out.append(
            {
                "row": str(item.get("row") or ""),
                "project_name": str(item.get("project_name") or ""),
                "repo_name": repo,
                "feature_desc": str(item.get("feature_desc") or ""),
            }
        )
    return out or None


def list_fe_project_rows(*, force_dingtalk: bool = False) -> list[dict[str, str]]:
    """列举汇总行：默认知识库 JSON，缺表或未同步时回退钉钉在线表。"""
    if not force_dingtalk:
        kb = load_fe_kb_rows()
        if kb:
            return kb
    return fetch_fe_project_rows()


def _norm_query(q: str) -> str:
    return re.sub(r"\s+", "", (q or "").strip().lower())


def _match_feature_rows(query: str, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    nq = _norm_query(query)
    hits: list[tuple[int, dict[str, str]]] = []
    for row in rows:
        project = row.get("project_name", "")
        repo = row.get("repo_name", "")
        desc = row.get("feature_desc", "")
        blob = _norm_query(f"{project}\n{repo}\n{desc}")
        score = 0
        if _norm_query(project) == nq or _norm_query(repo) == nq:
            score = 100
        elif nq in _norm_query(project):
            score = max(score, 80)
        elif nq in _norm_query(repo):
            score = max(score, 70)
        elif nq in blob:
            score = max(score, 50)
        elif len(nq) >= 2 and nq in _norm_query(desc):
            score = 40
        if score > 0:
            hits.append((score, row))
    hits.sort(key=lambda x: (-x[0], int(x[1].get("row", "0"))))
    return [{**row, "match_score": score} for score, row in hits]


def resolve_feature(
    query: str,
    rows: list[dict[str, str]] | None = None,
    *,
    resolve_source: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """按关键词匹配项目名称 / 仓库名 / 功能描述；返回 (命中列表, 数据来源 kb|dingtalk|explicit)。"""
    q = (query or "").strip()
    if not q:
        raise ValueError("请提供功能关键词（如 VIP、跨房PK）")
    if rows is not None:
        matches = _match_feature_rows(q, rows)
        src = resolve_source or "explicit"
        return [{**m, "resolve_source": src} for m in matches], src

    kb = load_fe_kb_rows()
    if kb:
        matches = _match_feature_rows(q, kb)
        if matches:
            return [{**m, "resolve_source": "kb"} for m in matches], "kb"

    try:
        dingtalk_rows = fetch_fe_project_rows()
    except Exception as e:
        raise RuntimeError(f"知识库未匹配 {q!r}，且钉钉汇总表读取失败: {e}") from e
    matches = _match_feature_rows(q, dingtalk_rows)
    return [{**m, "resolve_source": "dingtalk"} for m in matches], "dingtalk"


def resolve_feature_list(query: str, rows: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """兼容旧调用：只返回命中列表（含 resolve_source）。"""
    matches, _ = resolve_feature(query, rows)
    return matches
