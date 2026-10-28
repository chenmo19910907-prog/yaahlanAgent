"""版本用例钉钉表格命名：`{x.y.z}版本用例（功能概况…）`。"""

from __future__ import annotations

import re
from typing import Any

_VERSION_IN_NAME_RE = re.compile(r"(?:[vV])?(\d+)\.(\d+)\.(\d+)")
_PAREN_AFTER_CASE_RE = re.compile(r"版本用例\s*[（(]")
_OVERVIEW_IN_CELL_RE = re.compile(r"功能概况\s*[：:]\s*(.+)")
_SHEET1_NAMES = frozenset({"Sheet1", "sheet1"})


def parse_version_tuple(name: str) -> tuple[int, int, int] | None:
    m = _VERSION_IN_NAME_RE.search(name or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def version_label_from_tuple(ver: tuple[int, int, int]) -> str:
    return f"{ver[0]}.{ver[1]}.{ver[2]}"


def workbook_name_has_feature_suffix(name: str) -> bool:
    return bool(_PAREN_AFTER_CASE_RE.search(name or ""))


def _sheet_title_short(name: str) -> str:
    text = (name or "").strip()
    idx = text.find("（")
    if idx >= 0:
        return text[:idx].strip()
    return text


def _is_skipped_sheet(name: str) -> bool:
    n = (name or "").strip()
    if n in _SHEET1_NAMES:
        return True
    if "技术优化" in n or n.endswith("优化需求") or n == "优化需求":
        return True
    if n.upper().startswith("AI"):
        return True
    return False


def parse_feature_overview_from_rows(rows: list[list[Any]]) -> str:
    for row in rows[:40]:
        if not isinstance(row, list):
            continue
        for i, cell in enumerate(row):
            text = str(cell or "").strip()
            if not text or "功能概况" not in text:
                continue
            m = _OVERVIEW_IN_CELL_RE.match(text)
            if m:
                return m.group(1).strip()
            if i + 1 < len(row):
                nxt = str(row[i + 1] or "").strip()
                if nxt:
                    return nxt
    return ""


def _dedupe_preserve_order(parts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        s = (raw or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _split_prefix_suffix(title: str) -> tuple[str, str]:
    text = (title or "").strip()
    for sep in ("-", "－", "—", "·"):
        if sep in text:
            left, right = text.split(sep, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                return left, right
    return "", text


def summarize_name_parts(parts: list[str]) -> list[str]:
    """合并同前缀需求名（如 跨房PK吃鸡-A、跨房PK吃鸡-B → 跨房PK吃鸡）。"""
    deduped = _dedupe_preserve_order(parts)
    groups: dict[str, list[str]] = {}
    for title in deduped:
        prefix, suffix = _split_prefix_suffix(title)
        if prefix and suffix:
            groups.setdefault(prefix, []).append(suffix)
    summarized: list[str] = []
    seen_prefix: set[str] = set()
    for title in deduped:
        prefix, suffix = _split_prefix_suffix(title)
        if prefix and suffix:
            if prefix in seen_prefix:
                continue
            seen_prefix.add(prefix)
            suffixes = groups[prefix]
            if len(suffixes) >= 2:
                summarized.append(prefix)
            else:
                summarized.append(f"{prefix}-{suffixes[0]}")
        else:
            summarized.append(title)
    return summarized


def simplify_overview_phrase(text: str) -> str:
    """概况文案：拆项、合并同前缀、再拼接。"""
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    chunks = re.split(r"[、,，;；/|]", raw)
    chunks = [c.strip() for c in chunks if c.strip()]
    if len(chunks) <= 1:
        return raw
    return "、".join(summarize_name_parts(chunks))


def compose_feature_overview(
    *,
    sheet_names: list[str],
    sheet1_rows: list[list[Any]] | None = None,
) -> str:
    if sheet1_rows:
        overview = parse_feature_overview_from_rows(sheet1_rows)
        if overview:
            return simplify_overview_phrase(overview)
    parts: list[str] = []
    for raw in sheet_names:
        if _is_skipped_sheet(raw):
            continue
        short = _sheet_title_short(raw)
        if short:
            parts.append(short)
    return "、".join(summarize_name_parts(parts))


def normalize_overview_text(text: str, *, max_len: int = 80) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    s = s.replace("(", "（").replace(")", "）")
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s


def build_version_case_workbook_title(
    version: tuple[int, int, int] | str,
    overview: str,
) -> str:
    if isinstance(version, tuple):
        label = version_label_from_tuple(version)
    else:
        label = str(version).strip().lstrip("vV")
    base = f"{label}版本用例"
    ov = normalize_overview_text(overview)
    if not ov:
        return base
    return f"{base}（{ov}）"


def compute_version_case_workbook_title(
    current_name: str,
    *,
    sheet_names: list[str],
    sheet1_rows: list[list[Any]] | None = None,
) -> str | None:
    ver = parse_version_tuple(current_name)
    if not ver:
        return None
    overview = compose_feature_overview(sheet_names=sheet_names, sheet1_rows=sheet1_rows)
    if not normalize_overview_text(overview):
        return None
    return build_version_case_workbook_title(ver, overview)


def proposed_workbook_title(
    current_name: str,
    *,
    sheet_names: list[str],
    sheet1_rows: list[list[Any]] | None = None,
) -> str | None:
    if workbook_name_has_feature_suffix(current_name):
        return None
    return compute_version_case_workbook_title(
        current_name,
        sheet_names=sheet_names,
        sheet1_rows=sheet1_rows,
    )


def workbook_title_base_for_compare(name: str) -> str:
    """比较标题时去掉扩展名。"""
    base, _ = _strip_spreadsheet_extension(name)
    return base


_SPREADSHEET_EXTS = ("axls", "xlsx", "xls", "sheet", "able")


def _strip_spreadsheet_extension(name: str) -> tuple[str, str]:
    base = (name or "").strip()
    ext = ""
    while True:
        lowered = base.lower()
        matched = False
        for candidate in _SPREADSHEET_EXTS:
            suffix = f".{candidate}"
            if lowered.endswith(suffix):
                base = base[: -len(suffix)]
                ext = candidate
                matched = True
                break
        if not matched:
            break
    return base, ext


def apply_workbook_filename_extension(old_name: str, new_title: str) -> str:
    """保留 .axls 等扩展名（Box 展示名与浏览器一致）。"""
    _, ext = _strip_spreadsheet_extension(old_name)
    base, _ = _strip_spreadsheet_extension(new_title)
    if not base:
        return new_title.strip()
    if ext:
        return f"{base}.{ext}"
    return base
