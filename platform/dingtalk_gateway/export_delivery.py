"""将 Agent 大结果导出到钉钉 alidocs 目录，并生成群消息摘要 + 链接。"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from env_loader import GATEWAY_DIR

EXPORT_CONFIG = GATEWAY_DIR / "config" / "export_folder.json"
EXPORTS_DIR = GATEWAY_DIR / "exports"
ALIDOCS_NODE_URL = "https://alidocs.dingtalk.com/i/nodes/{node_id}"

TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
TABLE_SEP_RE = re.compile(r"^\|[\s:\-|]+\|\s*$", re.MULTILINE)
DINGTALK_REPLY_MAX_CHARS = 3800
DEFAULT_USER_LIST_ROWS = 10
TRUNCATE_HINT = "…（正文过长已截断）"
TRUNCATE_GUIDE = (
    f"{TRUNCATE_HINT}\n"
    "💡 回复「查看全部数据」看完整内容，或「导出到钉钉文档」写入钉钉。"
)
USER_LIST_LIMIT_HINT = (
    "…（用户列表共 {total} 条，已展示前 {shown} 条；"
    "回复「查看全部数据」可看完整列表，回复「导出到钉钉文档」可导出）"
)
EXPLICIT_DOC_EXPORT_RE = re.compile(
    r"(导出到钉钉文档|导出到钉钉|完整表格|完整结果|全量导出|导出完整|发到钉钉|同步到钉钉|"
    r"上传钉钉|生成到钉钉(文档)?|导出.{0,8}完整|完整.{0,8}导出)",
    re.I,
)
VIEW_ALL_DATA_RE = re.compile(
    r"(查看全部数据|查看全部|看全部数据|看全部|显示全部|全部数据|完整列表|"
    r"展示全部|看完整列表|全部用户|全量列表|显示完整)",
    re.I,
)
VIEW_ALL_FOLLOW_UP_RE = re.compile(
    r"^(查看全部数据|查看全部|看全部数据|看全部|显示全部|全部数据|"
    r"看完整列表|显示完整列表|展示全部数据)[。.!？!?]*$",
    re.I,
)
USER_LIST_HEADER_RE = re.compile(
    r"(user\s*id|userid|用户\s*id|用户id|\buid\b|momoid|momo\s*id|账号|用户编号)",
    re.I,
)


@dataclass
class ExportConfig:
    node_id: str
    folder_url: str
    inline_max_chars: int = 3500
    inline_max_table_rows: int = 8
    inline_max_user_list_rows: int = DEFAULT_USER_LIST_ROWS
    prefer_online_spreadsheet_for_table: bool = True


@dataclass
class DeliveryResult:
    """群消息正文（摘要 + 链接）；完整内容已导出时不内联大段正文。"""
    message: str
    exported: bool
    file_url: str | None = None
    local_path: str | None = None


def load_export_config() -> ExportConfig:
    data = json.loads(EXPORT_CONFIG.read_text(encoding="utf-8"))
    return ExportConfig(
        node_id=str(data["nodeId"]),
        folder_url=str(data["folderUrl"]),
        inline_max_chars=int(data.get("inlineMaxChars", 3500)),
        inline_max_table_rows=int(data.get("inlineMaxTableRows", 8)),
        inline_max_user_list_rows=int(data.get("inlineMaxUserListRows", DEFAULT_USER_LIST_ROWS)),
        prefer_online_spreadsheet_for_table=bool(data.get("preferOnlineSpreadsheetForTable", True)),
    )


def node_url(node_id: str) -> str:
    return ALIDOCS_NODE_URL.format(node_id=node_id)


def _slug_name(prompt: str, ext: str) -> str:
    base = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", prompt[:40]).strip("-") or "export"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{base}-{ts}.{ext}"


def parse_markdown_table(text: str) -> list[list[str]] | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    table_lines = [ln for ln in lines if ln.startswith("|") and ln.endswith("|")]
    if len(table_lines) < 2:
        return None
    rows: list[list[str]] = []
    for ln in table_lines:
        if TABLE_SEP_RE.match(ln):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        rows.append(cells)
    return rows if len(rows) >= 2 else None


def count_table_rows(text: str) -> int:
    rows = parse_markdown_table(text)
    if not rows:
        return 0
    return max(0, len(rows) - 1)


def _looks_like_json_blob(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            json.loads(stripped)
            return True
        except json.JSONDecodeError:
            return False
    return False


def wants_document_export(prompt: str) -> bool:
    """用户明确要求完整表格/结果写入钉钉文档时才导出。"""
    text = (prompt or "").strip()
    if not text:
        return False
    return bool(EXPLICIT_DOC_EXPORT_RE.search(text))


def wants_view_all_data(prompt: str) -> bool:
    """用户要求查看完整列表（非导出文档）。"""
    text = (prompt or "").strip()
    if not text:
        return False
    return bool(VIEW_ALL_DATA_RE.search(text))


def is_view_all_follow_up(prompt: str) -> bool:
    """短句「查看全部」类跟进，可复用上一条完整结果。"""
    text = (prompt or "").strip()
    if wants_document_export(text):
        return False
    return bool(VIEW_ALL_FOLLOW_UP_RE.match(text))


def is_user_list_table(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    header_line = " ".join(rows[0])
    return bool(USER_LIST_HEADER_RE.search(header_line))


def _markdown_table_block(rows: list[list[str]], *, with_separator: bool = True) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    normalized = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(normalized[0]) + " |"]
    if with_separator:
        lines.append("| " + " | ".join("---" for _ in range(width)) + " |")
        body = normalized[1:]
    else:
        body = normalized[1:] if len(normalized) > 1 else []
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _replace_first_table(text: str, new_table: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    replaced = False
    while i < len(lines):
        line = lines[i]
        if not replaced and line.strip().startswith("|") and line.strip().endswith("|"):
            block: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|") and lines[i].strip().endswith("|"):
                block.append(lines[i])
                i += 1
            out.append(new_table)
            replaced = True
            continue
        out.append(line)
        i += 1
    if not replaced:
        return text
    return "\n".join(out)


def limit_user_list_reply(
    text: str,
    prompt: str,
    cfg: ExportConfig | None = None,
) -> str:
    """用户列表默认只展示前 N 条；用户说「查看全部数据」时展示完整列表。"""
    cfg = cfg or load_export_config()
    if is_view_all_follow_up(prompt) or wants_document_export(prompt):
        return text
    rows = parse_markdown_table(text)
    if not rows or not is_user_list_table(rows):
        return text
    data_rows = rows[1:]
    total = len(data_rows)
    limit = max(1, cfg.inline_max_user_list_rows)
    if total <= limit:
        return text
    limited_rows = [rows[0], *data_rows[:limit]]
    new_table = _markdown_table_block(limited_rows)
    body = _replace_first_table(text, new_table)
    hint = USER_LIST_LIMIT_HINT.format(total=total, shown=limit)
    return f"{body.rstrip()}\n\n{hint}"


def _truncate_inline(text: str, max_chars: int = DINGTALK_REPLY_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    budget = max_chars - len(TRUNCATE_GUIDE) - 2
    if budget < 200:
        budget = max_chars - len(TRUNCATE_HINT) - 2
        return text[:budget].rstrip() + "\n\n" + TRUNCATE_HINT
    return text[:budget].rstrip() + "\n\n" + TRUNCATE_GUIDE


def _prepare_inline_reply(text: str, prompt: str, cfg: ExportConfig | None = None) -> str:
    cfg = cfg or load_export_config()
    text = limit_user_list_reply(text, prompt, cfg)
    limit = min(cfg.inline_max_chars, DINGTALK_REPLY_MAX_CHARS)
    return _truncate_inline(text, limit)


def needs_export(text: str, cfg: ExportConfig | None = None) -> bool:
    cfg = cfg or load_export_config()
    if len(text) > cfg.inline_max_chars:
        return True
    if count_table_rows(text) > cfg.inline_max_table_rows:
        return True
    if _looks_like_json_blob(text):
        return True
    return False


def _write_csv(rows: list[list[str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def _write_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_export_file(text: str, prompt: str) -> tuple[Path, str]:
    """落盘待上传文件，返回 (本地路径, 建议文件名)。"""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = parse_markdown_table(text)
    if rows:
        name = _slug_name(prompt, "csv")
        path = EXPORTS_DIR / name
        _write_csv(rows, path)
        return path, name
    if _looks_like_json_blob(text):
        name = _slug_name(prompt, "json")
        path = EXPORTS_DIR / name
        _write_json(json.loads(text.strip()), path)
        return path, name
    name = _slug_name(prompt, "txt")
    path = EXPORTS_DIR / name
    path.write_text(text, encoding="utf-8")
    return path, name


def build_summary(text: str, *, prompt: str, file_name: str, file_url: str | None) -> str:
    """导出成功时群内只回在线表格/文件链接，不附带目录入口。"""
    del text, prompt, file_name  # 保留签名供调用方；摘要不再展开元数据
    if file_url and file_url.strip():
        return file_url.strip()
    return "导出失败，未能生成在线表格链接，请联系管理员检查钉钉文档上传权限。"


def deliver_reply(text: str, prompt: str) -> DeliveryResult:
    """默认群内直接展示查询结果；用户列表默认前 10 条；按需查看全部或导出钉钉文档。"""
    cfg = load_export_config()
    if not wants_document_export(prompt):
        return DeliveryResult(message=_prepare_inline_reply(text, prompt, cfg), exported=False)
    if not needs_export(text, cfg):
        return DeliveryResult(message=_prepare_inline_reply(text, prompt, cfg), exported=False)

    local_path, file_name = prepare_export_file(text, prompt)
    file_url: str | None = None
    try:
        if file_name.endswith(".csv"):
            from alidocs_excel_export import export_csv_to_folder

            file_url = export_csv_to_folder(
                local_path,
                parent_node_id=cfg.node_id,
                workbook_name=Path(file_name).stem,
            )
        else:
            from alidocs_upload import upload_file_to_folder

            file_url = upload_file_to_folder(
                local_path,
                parent_node_id=cfg.node_id,
                file_name=file_name,
                convert_to_online_doc=False,
            )
    except Exception as exc:
        file_url = None
        summary = f"导出失败：{exc}"
        return DeliveryResult(
            message=summary,
            exported=True,
            file_url=None,
            local_path=str(local_path),
        )

    summary = build_summary(text, prompt=prompt, file_name=file_name, file_url=file_url)
    return DeliveryResult(
        message=summary,
        exported=True,
        file_url=file_url,
        local_path=str(local_path),
    )
