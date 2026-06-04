"""testcase-kb 来源版本解析（xlsx 文件名、元数据行）。"""

from __future__ import annotations

import re
from typing import Optional, Tuple

VERSION_TUPLE_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)", re.I)

VER_SOURCE_RE = re.compile(r"\*\*来源版本\*\*：`([^`]*)`")
FILE_SOURCE_RE = re.compile(r"\*\*来源文件\*\*：`([^`]*)`")
VER_KB_LINE_RE = re.compile(
    r"^> \*\*版本\*\*：`([^`]*)`(?:\s*·\s*\*\*摘录自\*\*：`([^`]*)`)?\s*$"
)

VERSION_TABLE_BLURB = (
    "各条目标注上传时的来源版本号（`vX.Y.Z`）；同功能点冲突时保留较新条目，"
    "版本号对应该条实际来源，非占位符"
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


def render_version_header(version_label: str, source_file: str = "") -> str:
    ver = effective_version_label(version_label, source_file)
    sf = (source_file or "").strip()
    if sf and ("/" in sf or "\\" in sf):
        from pathlib import Path as _P

        sf = _P(sf).name
    line = f"> **版本**：`{ver}`"
    if sf:
        line += f" · **摘录自**：`{sf}`"
    return line


def peel_version_prefix_from_body(body: str) -> Tuple[str, str, str]:
    """从正文开头剥离版本/来源行，返回 (version, source_file, 剩余正文)。"""
    lines = body.splitlines()
    ver = ""
    sf = ""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        v_upd, f_upd = parse_version_meta_line(lines[i])
        if v_upd is None and f_upd is None:
            break
        if v_upd:
            ver = v_upd
        if f_upd:
            sf = f_upd
        i += 1
    rest = "\n".join(lines[i:]).strip()
    return ver, sf, rest
