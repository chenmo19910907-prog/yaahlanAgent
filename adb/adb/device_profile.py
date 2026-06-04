"""设备型号适配：基准分辨率 tap_pct → 按档案线性换算。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .device import AdbError, display_size, run_adb

_ADAPT_DIR = Path(__file__).resolve().parent.parent / "录制脚本" / "设备适配"
_REFERENCE_FILE = _ADAPT_DIR / "基准设备.json"
_INDEX_FILE = _ADAPT_DIR / "索引.json"
_PROFILES_DIR = _ADAPT_DIR / "档案"


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    model: str
    manufacturer: str
    brand: str
    product_device: str
    width: int
    height: int


@dataclass(frozen=True)
class PctTransform:
    x_scale: float
    x_offset: float
    y_scale: float
    y_offset: float

    def apply(self, x_pct: float, y_pct: float) -> tuple[float, float]:
        x = self.x_scale * x_pct + self.x_offset
        y = self.y_scale * y_pct + self.y_offset
        return _clamp_pct(x), _clamp_pct(y)


@dataclass(frozen=True)
class AdaptationContext:
    status: str  # matched | identity | uncalibrated
    profile_id: str | None
    profile_name: str | None
    device: DeviceInfo
    reference: dict[str, Any]
    transform: PctTransform
    message: str
    reuse_saved: bool = False
    warnings: tuple[str, ...] = ()


def adapt_dir() -> Path:
    return _ADAPT_DIR


def _clamp_pct(v: float) -> float:
    return max(0.0, min(1.0, v))


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 须为 object")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_reference() -> dict[str, Any]:
    if not _REFERENCE_FILE.is_file():
        raise FileNotFoundError(f"缺少基准设备文件: {_REFERENCE_FILE}")
    return _read_json(_REFERENCE_FILE)


def transform_from_dict(raw: dict[str, Any] | None) -> PctTransform:
    if not raw:
        return PctTransform(1.0, 0.0, 1.0, 0.0)
    x = raw.get("x") or {}
    y = raw.get("y") or {}
    return PctTransform(
        float(x.get("scale", 1.0)),
        float(x.get("offset", 0.0)),
        float(y.get("scale", 1.0)),
        float(y.get("offset", 0.0)),
    )


def transform_to_dict(t: PctTransform) -> dict[str, Any]:
    return {
        "type": "pct_linear",
        "x": {"scale": t.x_scale, "offset": t.x_offset},
        "y": {"scale": t.y_scale, "offset": t.y_offset},
    }


def get_device_info(serial: str) -> DeviceInfo:
    w, h = display_size(serial)
    model = _getprop(serial, "ro.product.model") or "unknown"
    manufacturer = _getprop(serial, "ro.product.manufacturer") or ""
    brand = _getprop(serial, "ro.product.brand") or ""
    product_device = _getprop(serial, "ro.product.device") or ""
    return DeviceInfo(
        serial=serial,
        model=model.strip(),
        manufacturer=manufacturer.strip(),
        brand=brand.strip(),
        product_device=product_device.strip(),
        width=w,
        height=h,
    )


def _getprop(serial: str, key: str) -> str:
    proc = run_adb(["shell", "getprop", key], serial=serial, check=True)
    return proc.stdout.decode("utf-8", errors="replace").strip()


def list_profile_paths() -> list[Path]:
    if not _PROFILES_DIR.is_dir():
        return []
    return sorted(_PROFILES_DIR.glob("*.json"))


def load_profile(path: Path) -> dict[str, Any]:
    return _read_json(path)


def _profile_matches(device: DeviceInfo, profile: dict[str, Any]) -> bool:
    match = profile.get("match") or {}
    serials = match.get("serials") or []
    if device.serial in serials:
        return True
    models = match.get("models") or []
    if device.model in models:
        return True
    model_contains = match.get("modelContains") or []
    for frag in model_contains:
        if frag and frag in device.model:
            return True
    return False


def find_profile_path_for_device(device: DeviceInfo) -> Path | None:
    """按机型型号优先匹配；同机型多档案时取最近校准的一条。"""
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    for path in list_profile_paths():
        try:
            profile = load_profile(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if _profile_matches(device, profile):
            ts = str(profile.get("updatedAt") or profile.get("calibratedAt") or "")
            candidates.append((ts, path, profile))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def find_profile_for_device(device: DeviceInfo) -> dict[str, Any] | None:
    path = find_profile_path_for_device(device)
    return load_profile(path) if path else None


def profile_device_snapshot(device: DeviceInfo) -> dict[str, Any]:
    return {
        "model": device.model,
        "manufacturer": device.manufacturer,
        "brand": device.brand,
        "productDevice": device.product_device,
        "width": device.width,
        "height": device.height,
    }


def _profile_resolution_warnings(
    device: DeviceInfo,
    profile: dict[str, Any],
) -> list[str]:
    saved = profile.get("device") or {}
    warnings: list[str] = []
    sw, sh = saved.get("width"), saved.get("height")
    if sw and sh and (int(sw), int(sh)) != (device.width, device.height):
        warnings.append(
            f"当前分辨率 {device.width}x{device.height} 与档案记录 {sw}x{sh} 不一致，"
            "仍沿用已保存换算；若点击不准请 device recalibrate 更正"
        )
    return warnings


def fit_linear_1d(
    ref_vals: list[float],
    dev_vals: list[float],
    *,
    fix_offset: bool = False,
) -> tuple[float, float]:
    if not ref_vals or len(ref_vals) != len(dev_vals):
        raise ValueError("校准点数量无效")
    if fix_offset or len(ref_vals) == 1:
        scales = [d / r for r, d in zip(ref_vals, dev_vals) if abs(r) > 1e-9]
        if not scales:
            return 1.0, 0.0
        return sum(scales) / len(scales), 0.0
    n = len(ref_vals)
    sum_r = sum(ref_vals)
    sum_d = sum(dev_vals)
    sum_rr = sum(r * r for r in ref_vals)
    sum_rd = sum(r * d for r, d in zip(ref_vals, dev_vals))
    denom = n * sum_rr - sum_r * sum_r
    if abs(denom) < 1e-12:
        scales = [d / r for r, d in zip(ref_vals, dev_vals) if abs(r) > 1e-9]
        scale = sum(scales) / len(scales) if scales else 1.0
        return scale, 0.0
    scale = (n * sum_rd - sum_r * sum_d) / denom
    offset = (sum_d - scale * sum_r) / n
    return scale, offset


def fit_transform_from_anchors(
    anchors: list[dict[str, Any]],
    *,
    fix_offset: bool = False,
) -> PctTransform:
    ref_x: list[float] = []
    ref_y: list[float] = []
    dev_x: list[float] = []
    dev_y: list[float] = []
    for a in anchors:
        rp = a.get("refPct") or a.get("referencePct")
        dp = a.get("devicePct")
        if not isinstance(rp, (list, tuple)) or len(rp) != 2:
            raise ValueError(f"校准点缺少 refPct: {a}")
        if not isinstance(dp, (list, tuple)) or len(dp) != 2:
            raise ValueError(f"校准点缺少 devicePct: {a}")
        ref_x.append(float(rp[0]))
        ref_y.append(float(rp[1]))
        dev_x.append(float(dp[0]))
        dev_y.append(float(dp[1]))
    xs, xo = fit_linear_1d(ref_x, dev_x, fix_offset=fix_offset)
    ys, yo = fit_linear_1d(ref_y, dev_y, fix_offset=fix_offset)
    return PctTransform(xs, xo, ys, yo)


def resolve_adaptation(serial: str) -> AdaptationContext:
    device = get_device_info(serial)
    reference = load_reference()
    profile = find_profile_for_device(device)
    if profile:
        t = transform_from_dict(profile.get("transform"))
        warnings = tuple(_profile_resolution_warnings(device, profile))
        model_label = profile.get("deviceModel") or (profile.get("device") or {}).get(
            "model", device.model
        )
        msg = (
            f"复用已保存档案「{profile.get('name', profile.get('id'))}」"
            f"（型号 {model_label}），沿用基准 tap_pct 的已存换算，无需重新拟合"
        )
        if warnings:
            msg += f"；注意: {warnings[0]}"
        return AdaptationContext(
            status="matched",
            profile_id=str(profile.get("id", "")),
            profile_name=str(profile.get("name", "")),
            device=device,
            reference=reference,
            transform=t,
            message=msg,
            reuse_saved=True,
            warnings=warnings,
        )
    ref_w = int(reference.get("width", device.width))
    ref_h = int(reference.get("height", device.height))
    if device.width == ref_w and device.height == ref_h:
        t = PctTransform(1.0, 0.0, 1.0, 0.0)
        return AdaptationContext(
            status="identity",
            profile_id=None,
            profile_name=None,
            device=device,
            reference=reference,
            transform=t,
            message="分辨率与基准一致，无需换算",
        )
    t = PctTransform(1.0, 0.0, 1.0, 0.0)
    return AdaptationContext(
        status="uncalibrated",
        profile_id=None,
        profile_name=None,
        device=device,
        reference=reference,
        transform=t,
        message=(
            f"未找到机型 {device.model!r} 的换算档案（{device.width}x{device.height} "
            f"≠ 基准 {ref_w}x{ref_h}）。请先截图校准: device calibrate"
        ),
    )


def transform_step_pct(
    step: dict[str, Any],
    ctx: AdaptationContext,
) -> dict[str, Any]:
    """返回带 tap_pct 换算后的步骤副本（仅 pct_linear）。"""
    if "tap_pct" not in step:
        return step
    pct = step["tap_pct"]
    if not isinstance(pct, (list, tuple)) or len(pct) != 2:
        return step
    x_ref, y_ref = float(pct[0]), float(pct[1])
    x_dev, y_dev = ctx.transform.apply(x_ref, y_ref)
    out = dict(step)
    out["tap_pct_ref"] = [x_ref, y_ref]
    out["tap_pct"] = [round(x_dev, 6), round(y_dev, 6)]
    return out


def adapt_steps(
    steps: list[dict[str, Any]],
    ctx: AdaptationContext,
) -> list[dict[str, Any]]:
    return [transform_step_pct(s, ctx) if isinstance(s, dict) else s for s in steps]


def adaptation_payload(ctx: AdaptationContext) -> dict[str, Any]:
    return {
        "status": ctx.status,
        "reuseSavedTransform": ctx.reuse_saved,
        "canRunRecordedScripts": ctx.status in ("matched", "identity"),
        "profileId": ctx.profile_id,
        "profileName": ctx.profile_name,
        "message": ctx.message,
        "warnings": list(ctx.warnings),
        "device": {
            "serial": ctx.device.serial,
            "model": ctx.device.model,
            "manufacturer": ctx.device.manufacturer,
            "brand": ctx.device.brand,
            "productDevice": ctx.device.product_device,
            "width": ctx.device.width,
            "height": ctx.device.height,
        },
        "reference": {
            "id": ctx.reference.get("id"),
            "width": ctx.reference.get("width"),
            "height": ctx.reference.get("height"),
            "name": ctx.reference.get("name"),
            "model": ctx.reference.get("model"),
        },
        "transform": transform_to_dict(ctx.transform),
    }


def collect_reference_anchors_from_steps(
    steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    anchors: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        pct = step.get("tap_pct")
        if not isinstance(pct, (list, tuple)) or len(pct) != 2:
            continue
        anchors.append(
            {
                "note": step.get("note", ""),
                "refPct": [float(pct[0]), float(pct[1])],
                "devicePct": None,
            }
        )
    return anchors


def register_profile(
    *,
    profile_id: str,
    name: str,
    device: DeviceInfo,
    transform: PctTransform,
    anchors: list[dict[str, Any]],
    notes: str = "",
    reason: str = "initial",
) -> Path:
    path = _PROFILES_DIR / f"{profile_id}.json"
    reference = load_reference()
    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any]
    if path.is_file():
        payload = _read_json(path)
        history = payload.setdefault("history", [])
        if isinstance(history, list):
            history.append(
                {
                    "at": now,
                    "reason": reason,
                    "transform": payload.get("transform"),
                    "notes": payload.get("notes", ""),
                }
            )
    else:
        payload = {
            "calibratedAt": now,
            "history": [],
        }

    match = payload.get("match") if isinstance(payload.get("match"), dict) else {}
    models = list(match.get("models") or [])
    serials = list(match.get("serials") or [])
    if device.model and device.model not in models:
        models.append(device.model)
    if device.serial and device.serial not in serials:
        serials.append(device.serial)

    payload.update(
        {
            "id": profile_id,
            "name": name,
            "deviceModel": device.model,
            "match": {"models": models, "serials": serials},
            "device": profile_device_snapshot(device),
            "reference": {
                "id": reference.get("id", "reference"),
                "width": reference.get("width"),
                "height": reference.get("height"),
                "name": reference.get("name"),
                "model": reference.get("model"),
            },
            "reusePolicy": "use_saved_transform",
            "transform": transform_to_dict(transform),
            "anchors": anchors,
            "updatedAt": now,
            "notes": notes,
            "lastChangeReason": reason,
        }
    )
    payload.setdefault("calibratedAt", now)
    _write_json(path, payload)
    _register_in_index(profile_id, name, path, device_model=device.model, device=device)
    return path


def update_reference_from_device(device: DeviceInfo) -> dict[str, Any]:
    """在基准机上记录型号，便于对照「录制基准」。"""
    ref = load_reference()
    ref["model"] = device.model
    ref["manufacturer"] = device.manufacturer
    ref["brand"] = device.brand
    ref["productDevice"] = device.product_device
    ref["width"] = device.width
    ref["height"] = device.height
    ref["recordedAt"] = datetime.now(timezone.utc).isoformat()
    _write_json(_REFERENCE_FILE, ref)
    return ref


def _register_in_index(
    profile_id: str,
    name: str,
    path: Path,
    *,
    device_model: str,
    device: DeviceInfo,
) -> None:
    index = _read_json(_INDEX_FILE) if _INDEX_FILE.is_file() else {"profiles": []}
    profiles = index.setdefault("profiles", [])
    if not isinstance(profiles, list):
        profiles = []
        index["profiles"] = profiles
    rel = path.relative_to(_ADAPT_DIR).as_posix()
    profiles = [p for p in profiles if not (isinstance(p, dict) and p.get("id") == profile_id)]
    profiles.append(
        {
            "id": profile_id,
            "name": name,
            "deviceModel": device_model,
            "width": device.width,
            "height": device.height,
            "file": rel,
        }
    )
    index["profiles"] = profiles
    _write_json(_INDEX_FILE, index)


def get_profile_by_id(profile_id: str) -> tuple[Path, dict[str, Any]]:
    path = _PROFILES_DIR / f"{profile_id}.json"
    if not path.is_file():
        raise ValueError(f"未找到档案 {profile_id!r}")
    return path, load_profile(path)


def load_calibrate_draft(path: Path) -> dict[str, Any]:
    return _read_json(path)


def save_calibrate_draft(path: Path, data: dict[str, Any]) -> None:
    _write_json(path, data)


def default_draft_path(serial: str) -> Path:
    safe = serial.replace("/", "_")[:32]
    return _ADAPT_DIR / "校准草稿" / f"{safe}.json"
