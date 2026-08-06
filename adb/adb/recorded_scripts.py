"""从 adb 录制脚本库加载片段（支持中文名与英文 id）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .paths import scripts_root as _scripts_root
from .standard_nickname import standard_nickname


def scripts_root() -> Path:
    return _scripts_root()


def _index_path() -> Path:
    return scripts_root() / "索引.json"


def _load_index() -> dict[str, Any]:
    data = json.loads(_index_path().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("索引.json 根节点须为 object")
    return data


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 根节点须为 object")
    return data


def list_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in _load_index().get("items", []):
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "kind": entry.get("kind"),
                "module": entry.get("module"),
                "file": entry.get("file"),
                "params": entry.get("params", []),
            }
        )
    return items


def list_fragments_by_module() -> dict[str, list[dict[str, Any]]]:
    """按 testcase-kb 模块分组片段（与 索引.json fragmentModules 顺序一致）。"""
    index = _load_index()
    order = [str(m) for m in index.get("fragmentModules", []) if m]
    grouped: dict[str, list[dict[str, Any]]] = {m: [] for m in order}
    other_key = "其他"
    for item in list_catalog():
        if item.get("kind") != "fragment":
            continue
        mod = str(item.get("module") or other_key)
        if mod not in grouped:
            grouped[mod] = []
        grouped[mod].append(item)
    if grouped.get(other_key):
        order = order + [other_key]
    return {k: grouped[k] for k in order if grouped.get(k)}


def resolve_key(key: str, *, kind: str | None = None) -> tuple[str, str, Path]:
    """将中文名 / 英文 id 解析为 (id, 中文名, 文件路径)。"""
    key = key.strip()
    if not key:
        raise ValueError("脚本名不能为空")
    root = scripts_root()
    matches: list[tuple[dict[str, Any], Path]] = []
    for entry in _load_index().get("items", []):
        if not isinstance(entry, dict):
            continue
        if kind and entry.get("kind") != kind:
            continue
        eid = str(entry.get("id", ""))
        name = str(entry.get("name", ""))
        if key not in (eid, name):
            continue
        rel = entry.get("file")
        if not rel:
            continue
        path = root / str(rel)
        matches.append((entry, path))
    if not matches:
        hint = _format_known(kind)
        raise ValueError(f"未知脚本 {key!r}，{hint}")
    entry, path = matches[0]
    return str(entry["id"]), str(entry.get("name", entry["id"])), path


def login_defaults() -> dict[str, str]:
    """QA 登录默认值（索引 loginDefaults，可被片段 defaults 覆盖）。"""
    raw = _load_index().get("loginDefaults") or {}
    if not isinstance(raw, dict):
        raw = {}
    return {
        "countryCode": str(raw.get("countryCode", "+86")).strip() or "+86",
        "phone": str(raw.get("phone", "13311111115")).strip(),
        "verifyCode": str(raw.get("verifyCode", "000000")).strip(),
    }


def load_test_accounts() -> dict[str, Any]:
    raw = _load_index().get("testAccounts") or {}
    return raw if isinstance(raw, dict) else {}


def resolve_login_phone(*, text: str | None = None, account: str | None = None) -> str:
    """登录用手机号：显式 text > testAccounts.account > loginDefaults。"""
    if text is not None and str(text).strip():
        return str(text).strip()
    if account is not None and str(account).strip():
        key = str(account).strip()
        entry = load_test_accounts().get(key)
        if isinstance(entry, dict):
            phone = str(entry.get("phone", "")).strip()
            if phone:
                return phone
        known = "、".join(sorted(load_test_accounts().keys())) or "（无）"
        raise ValueError(f"未知 account {key!r}，可选: {known}")
    return login_defaults()["phone"]


PHONE_LOGIN_KEYS = frozenset({"手机号登录", "login-phone-full"})


def _default_text_for_script(spec: dict[str, Any]) -> str | None:
    defaults = spec.get("defaults")
    if isinstance(defaults, dict) and defaults.get("text") is not None:
        return str(defaults["text"]).strip()
    spec_id = str(spec.get("id", ""))
    login = login_defaults()
    if spec_id == "login-verify-code":
        return login["verifyCode"]
    if spec_id == "login-phone-sms":
        return login["phone"]
    if spec_id == "login-phone-full":
        return login["phone"]
    return None


def _format_known(kind: str | None) -> str:
    names: list[str] = []
    for entry in _load_index().get("items", []):
        if isinstance(entry, dict) and (not kind or entry.get("kind") == kind):
            names.append(str(entry.get("name", entry.get("id"))))
    return "可选: " + "、".join(dict.fromkeys(names)) if names else "（索引为空）"


def _phone_text_templates(phone: str) -> dict[str, str]:
    digits = re.sub(r"\D", "", str(phone).strip())
    last2 = digits[-2:] if len(digits) >= 2 else digits
    last3 = digits[-3:] if len(digits) >= 3 else digits
    return {
        "{{text}}": digits,
        "{{text_last2}}": last2,
        "{{text_last3}}": last3,
        "{{nickname}}": standard_nickname(digits),
    }


def _substitute_phone_templates(raw: str, templates: dict[str, str]) -> str:
    out = raw
    for key, value in templates.items():
        out = out.replace(key, value)
    return out


def _apply_params(spec: dict[str, Any], *, text: str | None) -> dict[str, Any]:
    params = spec.get("params") or []
    if not params:
        return spec
    if "text" in params:
        content = str(text).strip() if text is not None and str(text).strip() else None
        if content is None:
            content = _default_text_for_script(spec)
        if content is None:
            raise ValueError(
                f"{spec.get('name', spec.get('id'))} 需要 --text <正文>，"
                "或未配置 defaults / 索引 loginDefaults"
            )
    else:
        content = None
    templates = _phone_text_templates(content) if content else {}
    steps_out: list[dict[str, Any]] = []
    for step in spec.get("steps", []):
        if not isinstance(step, dict):
            steps_out.append(step)
            continue
        step_copy = dict(step)
        if "text" in step_copy and content is not None:
            raw = str(step_copy["text"])
            step_copy["text"] = _substitute_phone_templates(raw, templates)
        steps_out.append(step_copy)
    out = dict(spec)
    out["steps"] = steps_out
    if content is not None:
        out["description"] = f"{spec.get('description', '')}：{content!r}"
    return out


def load_fragment(
    key: str,
    *,
    text: str | None = None,
) -> dict[str, Any]:
    _id, _name, path = resolve_key(key, kind="fragment")
    spec = _read_json(path)
    spec.setdefault("id", _id)
    spec.setdefault("name", _name)
    return _apply_params(spec, text=text)


def load_flow_file(key: str) -> dict[str, Any]:
    raise ValueError(f"已移除流程脚本，请用 macro {key!r} 执行录制片段")
