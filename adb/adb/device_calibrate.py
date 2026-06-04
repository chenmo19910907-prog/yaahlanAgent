"""换机校准：截图读点 → 拟合 pct 线性换算 → 写入设备档案。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .coords import pixel_to_pct
from .device_profile import (
    collect_reference_anchors_from_steps,
    default_draft_path,
    find_profile_for_device,
    fit_transform_from_anchors,
    get_device_info,
    get_profile_by_id,
    load_calibrate_draft,
    register_profile,
    resolve_adaptation,
    save_calibrate_draft,
    transform_to_dict,
    update_reference_from_device,
)
from .recorded_scripts import load_fragment
from .screenshot import capture_screenshot


def _slug_model(model: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", model.strip()).strip("_").lower()
    return s[:48] or "unknown_model"


def device_info_payload(serial: str) -> dict[str, Any]:
    ctx = resolve_adaptation(serial)
    out: dict[str, Any] = {
        "adaptation": {
            "status": ctx.status,
            "reuseSavedTransform": ctx.reuse_saved,
            "canRunRecordedScripts": ctx.status in ("matched", "identity"),
            "message": ctx.message,
            "warnings": list(ctx.warnings),
            "profileId": ctx.profile_id,
            "profileName": ctx.profile_name,
            "transform": transform_to_dict(ctx.transform),
        },
        "device": {
            "serial": ctx.device.serial,
            "model": ctx.device.model,
            "manufacturer": ctx.device.manufacturer,
            "brand": ctx.device.brand,
            "productDevice": ctx.device.product_device,
            "width": ctx.device.width,
            "height": ctx.device.height,
        },
        "reference": ctx.reference,
    }
    if ctx.status == "matched":
        out["nextStep"] = (
            "直接 macro/compose；若操作失败再 device recalibrate --script <片段> 更正换算"
        )
    elif ctx.status == "uncalibrated":
        out["nextStep"] = "device calibrate --script 发布纯文本动态 → set → commit"
        out["suggestedProfileId"] = _slug_model(ctx.device.model)
    return out


def calibrate_init(
    *,
    serial: str,
    script_key: str,
    screenshot_dir: Path,
    max_screenshots: int,
    draft_path: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    ctx = resolve_adaptation(serial)
    if ctx.status == "matched" and not force:
        profile = find_profile_for_device(ctx.device)
        return {
            "skipped": True,
            "reason": "profile_exists",
            "message": (
                f"型号 {ctx.device.model!r} 已有档案「{ctx.profile_name}」，"
                "将复用已保存换算，无需重新校准。"
                "若点击不准: device recalibrate --script <片段名>"
            ),
            "profileId": ctx.profile_id,
            "profileName": ctx.profile_name,
            "deviceModel": (profile or {}).get("deviceModel", ctx.device.model),
            "transform": transform_to_dict(ctx.transform),
            "adaptation": device_info_payload(serial)["adaptation"],
        }

    spec = load_fragment(script_key, text=None)
    anchors = collect_reference_anchors_from_steps(list(spec.get("steps", [])))
    device = get_device_info(serial)
    cap = capture_screenshot(
        serial=serial,
        directory=screenshot_dir,
        max_keep=max_screenshots,
    )
    is_correction = ctx.status == "matched" and force
    draft: dict[str, Any] = {
        "mode": "correction" if is_correction else "initial",
        "script": spec.get("name", script_key),
        "scriptId": spec.get("id", script_key),
        "device": {
            "serial": device.serial,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "brand": device.brand,
            "productDevice": device.product_device,
            "width": device.width,
            "height": device.height,
        },
        "suggestedProfileId": _slug_model(device.model),
        "screenshot": cap,
        "anchors": anchors,
        "agentInstruction": (
            "读 screenshot，对每个 anchor: device set --note <note> --pixel <x> <y>；"
            f"完成后: device commit --id { _slug_model(device.model) } "
            f"--name \"{device.model}\" "
            + ("--reason correction" if is_correction else "")
        ),
    }
    path = draft_path or default_draft_path(serial)
    save_calibrate_draft(path, draft)
    draft["draftPath"] = str(path.resolve())
    return draft


def calibrate_set_point(
    *,
    draft_path: Path,
    note: str,
    device_pct: tuple[float, float] | None = None,
    pixel: tuple[int, int] | None = None,
    device_width: int | None = None,
    device_height: int | None = None,
) -> dict[str, Any]:
    draft = load_calibrate_draft(draft_path)
    anchors = draft.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("草稿缺少 anchors")
    if pixel is not None:
        w = device_width or int(draft["device"]["width"])
        h = device_height or int(draft["device"]["height"])
        device_pct = pixel_to_pct(w, h, pixel[0], pixel[1])
    if device_pct is None:
        raise ValueError("须提供 --device-pct 或 --pixel")
    matched = 0
    for a in anchors:
        if not isinstance(a, dict):
            continue
        n = str(a.get("note", ""))
        if note != n and note not in n and n not in note:
            continue
        a["devicePct"] = [device_pct[0], device_pct[1]]
        matched += 1
    if matched == 0:
        known = [str(a.get("note", "")) for a in anchors if isinstance(a, dict)]
        raise ValueError(f"未匹配 note={note!r}，可选: {known}")
    save_calibrate_draft(draft_path, draft)
    draft["matched"] = matched
    return draft


def calibrate_commit(
    *,
    draft_path: Path,
    profile_id: str,
    name: str,
    fix_offset: bool = False,
    notes: str = "",
    reason: str = "initial",
) -> dict[str, Any]:
    draft = load_calibrate_draft(draft_path)
    anchors = draft.get("anchors")
    if not isinstance(anchors, list):
        raise ValueError("草稿缺少 anchors")
    pending = [
        a for a in anchors if isinstance(a, dict) and not a.get("devicePct")
    ]
    if pending:
        labels = [str(a.get("note", "")) for a in pending]
        raise ValueError(f"仍有未校准点: {labels}")
    device_raw = draft.get("device") or {}
    serial = str(device_raw.get("serial", ""))
    if not serial:
        raise ValueError("草稿缺少 device.serial")
    device = get_device_info(serial)
    transform = fit_transform_from_anchors(anchors, fix_offset=fix_offset)
    if reason == "correction":
        notes = notes or "操作失败后更正换算"
    path = register_profile(
        profile_id=profile_id,
        name=name,
        device=device,
        transform=transform,
        anchors=anchors,
        notes=notes,
        reason=reason,
    )
    existed = reason == "correction"
    return {
        "profileId": profile_id,
        "profileName": name,
        "deviceModel": device.model,
        "profilePath": str(path.resolve()),
        "transform": transform_to_dict(transform),
        "anchors": anchors,
        "reason": reason,
        "message": (
            f"已{'更新' if existed else '写入'}型号 {device.model!r} 的档案，"
            "后续将复用此换算；基准 tap_pct 不变"
        ),
    }


def record_reference_device(serial: str) -> dict[str, Any]:
    device = get_device_info(serial)
    ref = update_reference_from_device(device)
    return {
        "message": "已把当前连接设备记入基准设备.json（录制 tap_pct 的参考机）",
        "reference": ref,
        "device": device_info_payload(serial)["device"],
    }


def profile_show(profile_id: str) -> dict[str, Any]:
    path, profile = get_profile_by_id(profile_id)
    return {"path": str(path.resolve()), "profile": profile}
