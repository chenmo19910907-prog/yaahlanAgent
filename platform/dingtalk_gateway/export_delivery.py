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


@dataclass
class ExportConfig:
    node_id: str
    folder_url: str
    inline_max_chars: int = 3500
    inline_max_table_rows: int = 8
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
    rows = parse_markdown_table(text)
    lines = [
        "**Agent 已完成**",
        f"- 时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"- 请求：{prompt[:200]}",
    ]
    if rows:
        header = rows[0]
        data_rows = rows[1:]
        lines.append(f"- 表格：{len(data_rows)} 行 × {len(header)} 列")
        lines.append(f"- 列：{' · '.join(header[:6])}{'…' if len(header) > 6 else ''}")
    elif _looks_like_json_blob(text):
        lines.append("- 类型：JSON")
    else:
        lines.append(f"- 正文长度：{len(text)} 字")
    lines.append(f"- 文件：{file_name}")
    if file_url:
        lines.append(f"- 链接：{file_url}")
    else:
        lines.append("- 链接：上传失败，请联系管理员检查开放平台存储权限")
    lines.append("")
    lines.append("完整内容已导出到 Agent 导出目录，请点击链接查看。")
    return "\n".join(lines)


def deliver_reply(text: str, prompt: str) -> DeliveryResult:
    """判断是否需要导出；需要则上传并返回摘要消息。"""
    cfg = load_export_config()
    if not needs_export(text, cfg):
        return DeliveryResult(message=text, exported=False)

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
        summary = build_summary(text, prompt=prompt, file_name=file_name, file_url=None)
        summary += f"\n\n（上传异常：{exc}）"
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
