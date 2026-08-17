"""平台源文件（Skills/Rules/能力源码包等）导出权限。"""

from __future__ import annotations

import re
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent

STAFF_ID_ENV = "WEB_AGENT_STAFF_ID"
DINGTALK_STAFF_ID_ENV = "DINGTALK_SENDER_STAFF_ID"

SOURCE_FILE_INTENT_RE = re.compile(
    r"("
    r"源文件|源代码|源码|"
    r"skill.{0,16}(发|给|打包|压缩|导出|下载|传)|"
    r"(发|给|导出|下载|打包|传).{0,16}skill|"
    r"rules?.{0,16}(发|给|打包|压缩|导出|下载)|"
    r"压缩包.{0,16}(skill|源码|源文件|脚本|规则|能力)|"
    r"完整导入|agent_capabilities|agent_capabilities_full|"
    r"runtime/|testcase-design-skills|"
    r"将所有能力导出|能力导出包|全量导出包|"
    r"用例设计.{0,12}skill"
    r")",
    re.I,
)

SOURCE_FILE_POLICY_EXCLUDE_RE = re.compile(
    r"(应该|需要|希望|要求|限制|开通|授权).{0,24}(管理员|权限)|"
    r"(管理员|权限).{0,24}(应该|需要|希望|要求|限制|开通|授权)|"
    r"只有管理员.{0,12}权限",
    re.I,
)
SOURCE_FILE_EXCLUDE_RE = re.compile(
    r"(导出到钉钉|钉钉文档|在线表格|temporary_testcase|"
    r"生成测试用例|测试用例生成|MOA检查|探活|"
    r"查询|升级|VIP|抓包|客诉)",
    re.I,
)

PROTECTED_REL_PREFIXES = (
    ".cursor/skills",
    ".cursor/rules",
    "platform/web_agent",
    "platform/dingtalk_gateway",
    "platform/exports/testcase-design-skills-pack",
    "platform/exports/agent_capabilities",
    "platform/exports/agent_capabilities_full",
    "platform/exports/cursor-platform-guide",
)

PROTECTED_ZIP_NAME_RE = re.compile(
    r"(skills|capabilities|agent_capabilities|testcase-design|platform-guide).*\.zip$",
    re.I,
)

SOURCE_DELIVERY_REPLY_RE = re.compile(
    r"("
    r"platform/exports/.*\.zip|"
    r"yaahlan-testcase-design-skills|"
    r"agent_capabilities_import\.zip|"
    r"agent_capabilities_full|"
    r"testcase-design-skills-pack|"
    r"\.cursor/skills|"
    r"web_share_file.*platform/"
    r")",
    re.I,
)

DENY_MESSAGE = (
    "你没有获取平台源文件（Skills/Rules/能力源码包等）的权限。"
    "请联系管理员开通，或由管理员代发压缩包。"
)


def source_file_denial_message() -> str:
    return DENY_MESSAGE


def looks_like_source_file_request(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    if SOURCE_FILE_POLICY_EXCLUDE_RE.search(text):
        return False
    if SOURCE_FILE_EXCLUDE_RE.search(text) and not SOURCE_FILE_INTENT_RE.search(text):
        return False
    return bool(SOURCE_FILE_INTENT_RE.search(text))


def _repo_relative(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return None


def is_protected_source_path(path: str | Path) -> bool:
    """本地路径是否属于须管理员才能对外交付的平台源文件。"""
    target = Path(path).expanduser()
    if not target.exists():
        target = (REPO_ROOT / str(path).lstrip("/")).resolve()
    if not target.exists():
        name = Path(path).name
        return bool(PROTECTED_ZIP_NAME_RE.search(name))

    rel = _repo_relative(target)
    if rel:
        for prefix in PROTECTED_REL_PREFIXES:
            if rel == prefix or rel.startswith(f"{prefix}/"):
                return True
        if rel.startswith("platform/exports/") and target.suffix.lower() == ".zip":
            return True

    return bool(PROTECTED_ZIP_NAME_RE.search(target.name))


def resolve_staff_id_from_env() -> str:
    import os

    for key in (STAFF_ID_ENV, DINGTALK_STAFF_ID_ENV):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def is_source_file_allowed(*, staff_id: str | None = None) -> bool:
    from code_modify_permission import is_code_modify_allowed

    uid = (staff_id or resolve_staff_id_from_env() or "").strip()
    if not uid:
        return False
    import os

    from env_loader import load_env_local

    load_env_local()
    local_admin = os.environ.get("WEB_AGENT_LOCAL_ADMIN_STAFF_ID", "admin").strip() or "admin"
    if uid == local_admin:
        return True
    return is_code_modify_allowed(sender_staff_id=uid, sender_id=None)


def assert_source_file_share_allowed(
    path: str | Path,
    *,
    staff_id: str | None = None,
) -> None:
    if not is_protected_source_path(path):
        return
    if is_source_file_allowed(staff_id=staff_id):
        return
    raise PermissionError(source_file_denial_message())


def mentions_protected_source_delivery(reply: str) -> bool:
    text = (reply or "").strip()
    if not text:
        return False
    return bool(SOURCE_DELIVERY_REPLY_RE.search(text))
