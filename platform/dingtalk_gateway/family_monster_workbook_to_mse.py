#!/usr/bin/env python3
"""家族怪兽挑战：钉钉表「怪兽挑战配置」→ MSE 保存/发布。"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from family_monster_mse_to_workbook import (  # noqa: E402
    DEFAULT_CONFIG_KEY,
    DEFAULT_NAMESPACE,
    DEFAULT_SHEET,
    DEFAULT_WORKBOOK,
    PARAM_LABELS,
)
from mse_workbook_utils import fetch_workbook_sheets  # noqa: E402

_MSE_DIR = REPO_ROOT / "MSE"
if str(_MSE_DIR) not in sys.path:
    sys.path.insert(0, str(_MSE_DIR))

from mse.mutate import (  # noqa: E402
    fetch_config_item,
    load_context,
    parse_config_value,
)
from mse.publish import publish_config_value, save_config_value  # noqa: E402

_SKIP_BLOCKS = frozenset(
    {
        "",
        "分类",
        "MSE元信息",
        "怪兽",
        "礼物返利",
        "伤害倍率",
        "跳转",
        "UI",
        "其他",
    }
)
_BASE_PARAM_KEYS = frozenset(PARAM_LABELS.keys())


def _cell(row: list[Any], idx: int) -> Any:
    if idx >= len(row) or row[idx] is None:
        return ""
    val = row[idx]
    if isinstance(val, str):
        return val.strip()
    return val


def _cell_str(row: list[Any], idx: int) -> str:
    val = _cell(row, idx)
    if val == "":
        return ""
    return str(val).strip()


def _cell_parsed(row: list[Any], idx: int) -> Any:
    val = _cell(row, idx)
    if val == "":
        return ""
    if isinstance(val, str):
        return _parse_value(val)
    return val


def _parse_value(raw: str) -> Any:
    text = (raw or "").strip()
    if text == "":
        return ""
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if text[0] in "{[\"":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


def _set_dotted(config: dict[str, Any], dotted: str, value: Any) -> None:
    parts = [p for p in dotted.split(".") if p]
    if not parts:
        return
    cur: dict[str, Any] = config
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _coerce_like(new: Any, old: Any) -> Any:
    if isinstance(old, bool):
        if isinstance(new, bool):
            return new
        if isinstance(new, str):
            return new.lower() == "true"
        return bool(new)
    if isinstance(old, int) and not isinstance(old, bool):
        return int(float(new))
    if isinstance(old, float):
        return float(new)
    if isinstance(old, list):
        return new if isinstance(new, list) else old
    if isinstance(old, dict):
        return new if isinstance(new, dict) else old
    if isinstance(old, str):
        if isinstance(new, float) and new.is_integer():
            return str(int(new))
        if isinstance(new, int) and not isinstance(new, bool):
            return str(new)
        return str(new)
    return new


def _excel_serial_to_datetime_text(value: Any) -> str | None:
    """钉钉 Excel 日期单元格常为 serial number。"""
    try:
        serial = float(value)
    except (TypeError, ValueError):
        return None
    if serial < 40000 or serial > 60000:
        return None
    base = datetime(1899, 12, 30)
    dt = base + timedelta(days=serial)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_family_monster_table_patches(matrix: list[list[Any]]) -> list[tuple[str, str, Any]]:
    """解析表格可编辑行 → (kind, key, value)。"""
    patches: list[tuple[str, str, Any]] = []
    for row in matrix:
        block = _cell_str(row, 0)
        if block.startswith("家族怪兽挑战") or block.startswith("生成时间"):
            continue
        if block == "configValue JSON" or block in _SKIP_BLOCKS:
            continue
        key = _cell_str(row, 1)
        if not key:
            continue
        val = _cell_parsed(row, 2)
        if block == "基础参数" and key in _BASE_PARAM_KEYS:
            patches.append(("top", key, val))
        elif block == "发奖配置":
            patches.append(("dotted", key, val))
        elif block == "宝箱资源":
            patches.append(("chest", key, val))
    return patches


def apply_patches_to_config(
    base: dict[str, Any],
    patches: list[tuple[str, str, Any]],
) -> dict[str, Any]:
    """在 MSE 当前 JSON 上应用表格补丁，保留原字段类型。"""
    config = copy.deepcopy(base)
    for kind, key, val in patches:
        if kind == "top":
            old = config.get(key)
            coerced = _coerce_like(val, old) if old is not None else val
            if key in {"startTime", "endTime"}:
                dt_text = _excel_serial_to_datetime_text(val)
                if dt_text:
                    coerced = dt_text
                elif isinstance(coerced, (int, float)):
                    dt_text = _excel_serial_to_datetime_text(coerced)
                    if dt_text:
                        coerced = dt_text
            config[key] = coerced
        elif kind == "dotted":
            parts = [p for p in key.split(".") if p]
            if parts:
                cur: dict[str, Any] = config
                for part in parts[:-1]:
                    nxt = cur.get(part)
                    if not isinstance(nxt, dict):
                        nxt = {}
                        cur[part] = nxt
                    cur = nxt
                old = cur.get(parts[-1])
                cur[parts[-1]] = _coerce_like(val, old) if old is not None else val
        elif kind == "chest":
            chest = config.get("chestResource")
            if not isinstance(chest, dict):
                chest = {}
                config["chestResource"] = chest
            old = chest.get(key)
            chest[key] = _coerce_like(val, old) if old is not None else val
    return config


def load_config_from_workbook(
    workbook_url_or_id: str,
    *,
    sheet_name: str = DEFAULT_SHEET,
    base_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sheets = fetch_workbook_sheets(workbook_url_or_id)
    matrix = sheets.get(sheet_name)
    if not matrix:
        raise RuntimeError(f"未找到工作表: {sheet_name}")
    patches = parse_family_monster_table_patches(matrix)
    if not patches:
        raise ValueError("表格无可应用的基础参数/发奖配置/宝箱资源行")
    if base_config is None:
        raise ValueError("缺少 base_config，须先读取 MSE 当前配置")
    return apply_patches_to_config(base_config, patches)


def _verify_published_config(
    ctx: Any,
    *,
    config_key: str,
    namespace: str,
    expected: dict[str, Any],
    changed_keys: list[str],
) -> dict[str, Any]:
    """发布/保存后回读 MSE，核对变更字段。"""
    item, _ = fetch_config_item(ctx, config_key=config_key, name_space=namespace)
    live = parse_config_value(item.get("configValue"))
    if not isinstance(live, dict):
        return {"ok": False, "error": "回读 configValue 不是 object"}

    mismatches: list[str] = []
    checked: dict[str, Any] = {}
    for key in changed_keys:
        exp_val = expected.get(key)
        live_val = live.get(key)
        checked[key] = live_val
        if exp_val == live_val:
            continue
        if key in {"startTime", "endTime"} and exp_val and live_val:
            try:
                exp_dt = datetime.strptime(str(exp_val), "%Y-%m-%d %H:%M:%S")
                live_dt = datetime.strptime(str(live_val), "%Y-%m-%d %H:%M:%S")
                if abs((exp_dt - live_dt).total_seconds()) <= 1:
                    continue
            except ValueError:
                pass
        mismatches.append(
            f"{key}: expected {json.dumps(exp_val, ensure_ascii=False)}, "
            f"got {json.dumps(live_val, ensure_ascii=False)}"
        )

    return {
        "ok": len(mismatches) == 0,
        "status": item.get("status"),
        "config_id": item.get("id"),
        "checked": checked,
        "mismatches": mismatches,
    }


def _summarize_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    keys = sorted(set(old.keys()) | set(new.keys()))
    for key in keys:
        ov, nv = old.get(key), new.get(key)
        if ov != nv:
            changes.append(
                f"{key}: {json.dumps(ov, ensure_ascii=False)} → {json.dumps(nv, ensure_ascii=False)}"
            )
    return changes


def publish_family_monster_from_workbook(
    workbook_url_or_id: str,
    *,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "stage",
    env: str = "alpha",
    region: str = "alpha",
    confirm_publish: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """读钉钉表 → 保存 MSE → 可选发布。"""
    ctx = load_context(cluster=cluster, env=env, region=region)
    item, display_ns = fetch_config_item(ctx, config_key=config_key, name_space=namespace)
    config_id = int(item.get("id") or 0)
    if config_id <= 0:
        raise RuntimeError("配置缺少 id")

    current = parse_config_value(item.get("configValue"))
    if not isinstance(current, dict):
        raise RuntimeError("当前 configValue 不是 JSON object")

    parsed = load_config_from_workbook(
        workbook_url_or_id,
        base_config=current,
    )
    changes = _summarize_changes(current, parsed)
    new_value = json.dumps(parsed, ensure_ascii=False, indent=4)
    publish_app_key = str(ctx.app_key)

    out: dict[str, Any] = {
        "ok": True,
        "action": "workbook_publish",
        "workbook": workbook_url_or_id.strip(),
        "config_key": config_key,
        "namespace": display_ns,
        "config_id": config_id,
        "app_key": publish_app_key,
        "cluster": cluster,
        "changes": changes,
        "changeCount": len(changes),
        "dry_run": dry_run,
        "saved": False,
        "published": False,
        "record_id": None,
    }

    if dry_run:
        out["before"] = json.dumps(current, ensure_ascii=False, indent=4)
        out["after"] = new_value
        return out

    if not changes:
        out["skipped"] = True
        out["message"] = "表格配置与 MSE 当前值一致，未写入"
        if confirm_publish:
            record_id = publish_config_value(
                base_url=ctx.base_url,
                cookie=ctx.cookie,
                region=ctx.region,
                env=ctx.env,
                cluster=ctx.cluster,
                app_key=publish_app_key,
                config_id=config_id,
                config_value=json.dumps(current, ensure_ascii=False, indent=4),
                skip_grey=True,
                timeout_s=ctx.timeout_s,
            )
            out["published"] = True
            out["record_id"] = record_id
        return out

    save_config_value(
        base_url=ctx.base_url,
        cookie=ctx.cookie,
        region=ctx.region,
        env=ctx.env,
        cluster=ctx.cluster,
        app_key=ctx.app_key,
        config_id=config_id,
        config_value=new_value,
        timeout_s=ctx.timeout_s,
    )
    out["saved"] = True

    if confirm_publish:
        record_id = publish_config_value(
            base_url=ctx.base_url,
            cookie=ctx.cookie,
            region=ctx.region,
            env=ctx.env,
            cluster=ctx.cluster,
            app_key=publish_app_key,
            config_id=config_id,
            config_value=new_value,
            skip_grey=True,
            timeout_s=ctx.timeout_s,
        )
        out["published"] = True
        out["record_id"] = record_id

    if out.get("saved") or out.get("published"):
        changed_keys = [c.split(":", 1)[0] for c in changes]
        out["verify"] = _verify_published_config(
            ctx,
            config_key=config_key,
            namespace=namespace,
            expected=parsed,
            changed_keys=changed_keys,
        )

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="家族怪兽钉钉表 → MSE 保存/发布")
    parser.add_argument("workbook", nargs="?", default=DEFAULT_WORKBOOK)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--cluster", default="stage")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-publish", action="store_true")
    args = parser.parse_args()
    try:
        out = publish_family_monster_from_workbook(
            args.workbook.strip(),
            namespace=args.namespace.strip(),
            config_key=args.config_key.strip(),
            cluster=args.cluster.strip(),
            env=args.env.strip(),
            region=args.region.strip(),
            confirm_publish=bool(args.confirm_publish),
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
