"""testcase-kb 来源版本与人员元数据（xlsx 文件名、表头上方信息行）。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

VERSION_TUPLE_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)", re.I)

VER_SOURCE_RE = re.compile(r"\*\*来源版本\*\*：`([^`]*)`")
FILE_SOURCE_RE = re.compile(r"\*\*来源文件\*\*：`([^`]*)`")
VER_KB_LINE_RE = re.compile(
    r"^> \*\*版本\*\*：`([^`]*)`(?:\s*·\s*\*\*摘录自\*\*：`([^`]*)`)?\s*$"
)
PERSONNEL_KB_LINE_RE = re.compile(r"^> \*\*人员\*\*：(.+?)\s*$")

# xlsx 表头上方常见标签 → 知识库字段
PERSONNEL_FIELDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("designer", ("设计人", "设计", "用例设计")),
    ("tester", ("测试人", "测试", "測試人", "測試", "QA")),
    ("product", ("产品", "产品负责人", "产品经理")),
    ("developer", ("开发", "开发负责人", "研发", "客户端")),
)

PERSONNEL_DISPLAY: Dict[str, str] = {
    "designer": "设计",
    "tester": "测试",
    "product": "产品",
    "developer": "开发",
}

VERSION_TABLE_BLURB = (
    "各条目标注同步时的来源版本号（`vX.Y.Z`）及可选人员（设计/测试/产品/开发，来自用例表头上方）；"
    "同功能点冲突时保留较新条目，元数据对应该条实际来源"
)

LABEL_VALUE_RE = re.compile(
    r"^(设计人|设计|用例设计|测试人|测试|測試人|測試|QA|产品|产品负责人|产品经理|"
    r"开发|开发负责人|研发|客户端)\s*[:：]\s*(.+)$",
    re.UNICODE,
)


def parse_version_tuple(label: str) -> Tuple[int, int, int]:
    m = VERSION_TUPLE_RE.search(label or "")
    if not m:
        return (0, 0, 0)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def version_label_from_text(text: str) -> str:
    m = VERSION_TUPLE_RE.search(text or "")
    if not m:
        return ""
    return f"v{m.group(1)}.{m.group(2)}.{m.group(3)}"


def normalize_version_display(label: str) -> str:
    v = (label or "").strip()
    if not v or v == "—":
        return ""
    return v


def effective_version_label(version_label: str, source_file: str = "") -> str:
    """优先显式版本，否则从来源 xlsx 文件名推断。"""
    v = normalize_version_display(version_label)
    if v:
        return v
    if source_file:
        inferred = version_label_from_text(source_file)
        if inferred:
            return inferred
    return "—"


def _normalize_personnel_value(raw: str) -> str:
    v = (raw or "").strip()
    if not v or v in ("—", "-", "/", "无", "N/A", "n/a"):
        return ""
    return v


def _field_for_label(label: str) -> Optional[str]:
    lab = (label or "").strip()
    for key, aliases in PERSONNEL_FIELDS:
        if lab in aliases:
            return key
    return None


def parse_personnel_from_text(text: str) -> Dict[str, str]:
    """从「设计人：张三」或「设计 `张三`」等自由文本解析人员字段。"""
    out: Dict[str, str] = {}
    if not text:
        return out

    # 反引号包裹：设计 `张三`
    for m in re.finditer(r"(设计|测试|測試|产品|开发)\s*`([^`]+)`", text):
        key = _field_for_label(m.group(1))
        if key:
            val = _normalize_personnel_value(m.group(2))
            if val:
                out[key] = val

    # 标签：值（分号、斜杠分隔）
    for segment in re.split(r"[;；/／|｜]", text):
        segment = segment.strip()
        if not segment:
            continue
        m = LABEL_VALUE_RE.match(segment)
        if m:
            key = _field_for_label(m.group(1))
            if key:
                val = _normalize_personnel_value(m.group(2))
                if val:
                    out[key] = val
    return out


def parse_personnel_meta_line(line: str) -> Optional[Dict[str, str]]:
    m = PERSONNEL_KB_LINE_RE.match(line.rstrip())
    if not m:
        return None
    return parse_personnel_from_text(m.group(1))


def merge_personnel(*maps: Optional[Dict[str, str]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for mp in maps:
        if not mp:
            continue
        for k, v in mp.items():
            val = _normalize_personnel_value(v)
            if val:
                out[k] = val
    return out


def extract_sheet_personnel(rows: List[List[Any]], header_idx: int) -> Dict[str, str]:
    """从 xlsx 表头行之上提取设计/测试/产品/开发等信息。"""
    found: Dict[str, str] = {}
    if header_idx <= 0:
        return found

    def cell_str(row: List[Any], ci: int) -> str:
        if ci >= len(row) or row[ci] is None:
            return ""
        return str(row[ci]).strip().replace("\r", "")

    for row in rows[:header_idx]:
        cells = [cell_str(row, c) for c in range(min(len(row), 12))]
        cells = [c for c in cells if c]
        if not cells:
            continue
        line = " / ".join(cells)
        if not any(
            k in line
            for k in ("设计", "测试", "測試", "产品", "开发", "研发", "QA", "用例总计")
        ):
            continue
        if line.startswith("用例总计") or line.startswith("---"):
            continue

        # 逐格：「设计人」+ 下一格姓名
        for ci, c in enumerate(cells):
            m = LABEL_VALUE_RE.match(c)
            if m:
                key = _field_for_label(m.group(1))
                if key:
                    val = _normalize_personnel_value(m.group(2))
                    if val:
                        found[key] = val
                continue
            key = _field_for_label(c.rstrip("：:"))
            if key and ci + 1 < len(cells):
                val = _normalize_personnel_value(cells[ci + 1])
                if val and not _field_for_label(val):
                    found[key] = val

        found = merge_personnel(found, parse_personnel_from_text(line))

    return found


def parse_version_meta_line(line: str) -> Tuple[Optional[str], Optional[str]]:
    """
    解析单行元数据。返回 (version_label, source_file)，未识别则 (None, None)。
    """
    stripped = line.rstrip()
    m = VER_KB_LINE_RE.match(stripped)
    if m:
        ver = normalize_version_display(m.group(1))
        sf = (m.group(2) or "").strip()
        return (ver or None, sf or None)

    vm = VER_SOURCE_RE.search(stripped)
    if vm:
        ver = normalize_version_display(vm.group(1))
        return (ver or None, None)

    fm = FILE_SOURCE_RE.search(stripped)
    if fm:
        return (None, fm.group(1).strip())

    return (None, None)


def render_personnel_header(personnel: Optional[Dict[str, str]] = None) -> str:
    mp = merge_personnel(personnel)
    if not mp:
        return ""
    parts: List[str] = []
    for key in ("designer", "tester", "product", "developer"):
        val = mp.get(key)
        if val:
            parts.append(f"{PERSONNEL_DISPLAY[key]} `{val}`")
    if not parts:
        return ""
    return "> **人员**：" + " · ".join(parts)


def render_version_header(
    version_label: str,
    source_file: str = "",
    personnel: Optional[Dict[str, str]] = None,
) -> str:
    ver = effective_version_label(version_label, source_file)
    sf = (source_file or "").strip()
    if sf and ("/" in sf or "\\" in sf):
        from pathlib import Path as _P

        sf = _P(sf).name
    line = f"> **版本**：`{ver}`"
    if sf:
        line += f" · **摘录自**：`{sf}`"
    personnel_line = render_personnel_header(personnel)
    if personnel_line:
        return line + "\n" + personnel_line
    return line


def render_meta_header(
    version_label: str,
    source_file: str = "",
    personnel: Optional[Dict[str, str]] = None,
) -> str:
    return render_version_header(version_label, source_file, personnel)


def peel_version_prefix_from_body(
    body: str,
) -> Tuple[str, str, Dict[str, str], str]:
    """从正文开头剥离版本/来源/人员行，返回 (version, source_file, personnel, 剩余正文)。"""
    lines = body.splitlines()
    ver = ""
    sf = ""
    personnel: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        v_upd, f_upd = parse_version_meta_line(lines[i])
        p_upd = parse_personnel_meta_line(lines[i])
        if v_upd is None and f_upd is None and p_upd is None:
            break
        if v_upd:
            ver = v_upd
        if f_upd:
            sf = f_upd
        if p_upd:
            personnel = merge_personnel(personnel, p_upd)
        i += 1
    rest = "\n".join(lines[i:]).strip()
    return ver, sf, personnel, rest
