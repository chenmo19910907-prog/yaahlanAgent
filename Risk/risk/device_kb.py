"""测试机知识库增量落库（解除风控时补录未登记设备）。"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_yaahlan_ua(ua: str) -> dict[str, str]:
    """从 Yaahlan User-Agent 解析机型信息。"""
    ua = (ua or "").strip()
    if not ua:
        return {}

    inner_match = re.search(r"\(([^)]+)\)", ua)
    if not inner_match:
        return {}

    parts = [part.strip() for part in inner_match.group(1).split(";") if part.strip()]
    if not parts:
        return {}

    if "ios" in ua.casefold() or parts[0].casefold() == "iphone":
        os_version = ""
        for part in parts:
            if part.casefold().startswith("ios"):
                os_version = part.split()[-1] if " " in part else part[3:].strip()
        return {
            "设备品牌": "Apple",
            "设备名称": parts[0],
            "设备系统": "iOS",
            "系统版本": os_version,
        }

    model = parts[0]
    android_ver = ""
    brand = ""
    for part in parts:
        lowered = part.casefold()
        if lowered.startswith("android"):
            android_ver = part.split()[-1] if " " in part else ""
        elif lowered in {"gapps 0", "zh_cn"} or part.isdigit():
            continue
        elif part != model and not lowered.startswith("android"):
            brand = part
    if not brand and len(parts) >= 2:
        brand = parts[-1]

    return {
        "设备品牌": brand,
        "设备名称": model,
        "设备系统": "Android",
        "系统版本": android_ver,
    }


def find_device_record_index(
    devices: list[dict[str, Any]],
    *,
    mmuid: str = "",
    mmuidv3: str = "",
) -> int | None:
    """按 mmuidv3 优先、mmuid 次之匹配知识库记录索引。"""
    mmuid = mmuid.strip()
    mmuidv3 = mmuidv3.strip()
    if mmuidv3:
        for index, record in enumerate(devices):
            if str(record.get("mmuidv3") or "").strip() == mmuidv3:
                return index
    if mmuid:
        for index, record in enumerate(devices):
            if str(record.get("mmuid") or "").strip() == mmuid:
                return index
    return None


def device_record_needs_update(record: dict[str, Any], login_device: dict[str, Any]) -> bool:
    """知识库记录是否缺少最近登录设备字段。"""
    mmuid = str(login_device.get("mmuid") or "").strip()
    mmuidv3 = str(login_device.get("mmuidv3") or "").strip()
    if mmuidv3 and not str(record.get("mmuidv3") or "").strip():
        return True
    if mmuid and not str(record.get("mmuid") or "").strip():
        return True
    if not str(record.get("设备名称") or "").strip():
        ua_info = parse_yaahlan_ua(str(login_device.get("ua") or ""))
        if ua_info.get("设备名称"):
            return True
    return False


def _default_project_id() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[2] / "platform"
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.loader import get_project_id

        return get_project_id()
    except (ImportError, FileNotFoundError, ValueError):
        return "yaahlan"


def build_device_record_from_login(
    login_device: dict[str, Any],
    *,
    phone: str = "",
    user_id: str = "",
    project: str | None = None,
) -> dict[str, str]:
    """由 Admin loginDevice 构造知识库设备条目。"""
    project = (project or _default_project_id()).strip() or "yaahlan"
    mmuid = str(login_device.get("mmuid") or "").strip()
    mmuidv3 = str(login_device.get("mmuidv3") or "").strip()
    ua_info = parse_yaahlan_ua(str(login_device.get("ua") or ""))
    os_name = ua_info.get("设备系统") or ("iOS" if mmuid and not mmuidv3 else "Android")
    note_parts = [f"自动落库 {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"]
    if phone:
        note_parts.append(f"phone={phone}")
    if user_id:
        note_parts.append(f"userId={user_id}")
    if login_device.get("ip"):
        note_parts.append(f"ip={login_device.get('ip')}")

    return {
        "项目": project,
        "资产编号": "待补编号",
        "设备品牌": ua_info.get("设备品牌", ""),
        "设备名称": ua_info.get("设备名称", ""),
        "mmuid": mmuid,
        "mmuidv3": mmuidv3,
        "设备系统": os_name,
        "系统版本": ua_info.get("系统版本", ""),
        "归属人": "",
        "持有人": "",
        "备注": "；".join(note_parts),
    }


def merge_device_record(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, str]:
    """合并知识库记录：仅补全空字段，备注追加来源。"""
    merged = {key: str(existing.get(key) or "") for key in incoming}
    for key, value in incoming.items():
        if not str(merged.get(key) or "").strip() and str(value or "").strip():
            merged[key] = str(value).strip()
    old_note = str(existing.get("备注") or "").strip()
    new_note = str(incoming.get("备注") or "").strip()
    if new_note and new_note not in old_note:
        merged["备注"] = f"{old_note}；{new_note}" if old_note else new_note
    else:
        merged["备注"] = old_note
    return merged


def load_kb_payload(kb_path: str | Path) -> dict[str, Any]:
    path = Path(kb_path)
    if not path.is_file():
        raise ValueError(f"测试机知识库不存在: {path}")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("devices"), list):
        raise ValueError(f"测试机知识库格式错误: {path}")
    return payload


def upsert_login_device_record(
    kb_path: str | Path,
    login_device: dict[str, Any],
    *,
    phone: str = "",
    user_id: str = "",
    project: str | None = None,
) -> dict[str, Any]:
    """将最近登录设备写入知识库；已存在则补全缺失字段。"""
    path = Path(kb_path)
    payload = load_kb_payload(path)
    devices: list[dict[str, Any]] = payload["devices"]

    mmuid = str(login_device.get("mmuid") or "").strip()
    mmuidv3 = str(login_device.get("mmuidv3") or "").strip()
    if not mmuid and not mmuidv3:
        raise ValueError("loginDevice 缺少 mmuid / mmuidv3，无法落库")

    incoming = build_device_record_from_login(
        login_device,
        phone=phone,
        user_id=user_id,
        project=project,
    )
    index = find_device_record_index(devices, mmuid=mmuid, mmuidv3=mmuidv3)
    if index is None:
        devices.append(incoming)
        action = "added"
        record = incoming
    else:
        existing = devices[index]
        if not device_record_needs_update(existing, login_device):
            return {"action": "unchanged", "record": existing, "kbPath": str(path)}
        record = merge_device_record(existing, incoming)
        devices[index] = record
        action = "updated"

    _save_kb_payload(path, payload, devices, note=f"upsert loginDevice phone={phone} userId={user_id}")
    return {"action": action, "record": record, "kbPath": str(path)}


def _save_kb_payload(
    json_path: Path,
    payload: dict[str, Any],
    devices: list[dict[str, Any]],
    *,
    note: str = "",
) -> None:
    synced_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload["devices"] = devices
    payload["count"] = len(devices)
    payload["syncedAt"] = synced_at
    if note:
        payload["lastIncrementalUpdate"] = note

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    scripts_dir = _project_root() / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from sync_test_devices_kb import build_markdown

    md_path = json_path.parent / "测试机.md"
    import_source = str(payload.get("importSource") or "增量自动落库")
    md_path.write_text(
        build_markdown(devices, source_path=import_source, synced_at=synced_at),
        encoding="utf-8",
    )


def _fetch_online_admin_user(user_id: str) -> dict[str, Any]:
    root = _project_root()
    admin_cmd = [
        sys.executable,
        str(root / "online" / "online_execute.py"),
        "admin",
        "--query-user-id",
        user_id,
    ]
    admin_proc = subprocess.run(admin_cmd, cwd=str(root), capture_output=True, text=True, check=False)
    if admin_proc.returncode != 0:
        raise RuntimeError(admin_proc.stderr.strip() or admin_proc.stdout.strip() or "Admin 查询失败")

    admin_text = admin_proc.stdout
    admin_data = json.loads(admin_text[admin_text.find("{") :])
    login_device = admin_data.get("loginDevice")
    if not isinstance(login_device, dict):
        raise ValueError(f"userId {user_id} 缺少 loginDevice")

    phone_raw = admin_data.get("phone")
    phone = str(phone_raw).strip() if phone_raw else ""
    return {
        "phone": phone,
        "areaCode": str(admin_data.get("areaCode") or "").strip(),
        "userId": str(admin_data.get("userId") or user_id).strip(),
        "nickname": str(admin_data.get("nickname") or "").strip(),
        "loginDevice": login_device,
    }


def fetch_online_login_context_by_user_id(user_id: str) -> dict[str, Any]:
    """线上环境：userId → Admin 最近登录设备。"""
    user_id = user_id.strip()
    if not user_id:
        raise ValueError("请提供 userId")
    return _fetch_online_admin_user(user_id)


def fetch_online_login_context(phone: str) -> dict[str, Any]:
    """线上环境：手机号 → userId → Admin 最近登录设备。"""
    phone = phone.strip()
    if not phone:
        raise ValueError("请提供手机号")

    root = _project_root()
    moa_cmd = [
        sys.executable,
        str(root / "online" / "online_execute.py"),
        "moa",
        "--query-user-by-phone",
        phone,
    ]
    moa_proc = subprocess.run(moa_cmd, cwd=str(root), capture_output=True, text=True, check=False)
    if moa_proc.returncode != 0:
        raise RuntimeError(moa_proc.stderr.strip() or moa_proc.stdout.strip() or "MOA 查询失败")

    moa_text = moa_proc.stdout
    moa_data = json.loads(moa_text[moa_text.rfind("{") :])
    user_id = str(moa_data.get("userId") or moa_data.get("data") or "").strip()
    if not user_id:
        raise ValueError(f"手机号 {phone} 未查到 userId")

    context = _fetch_online_admin_user(user_id)
    if not context.get("phone"):
        context["phone"] = phone
    return context
