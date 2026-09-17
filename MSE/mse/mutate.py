"""MSE 配置改参 API — 供 CLI / platform MCP 直接调用。"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from .client import get_configs_by_namespace, get_session_user
from .env import load_local_env
from .namespaces import resolve_namespace
from .patch import apply_set_args, parse_config_value
from .paths import config_json_path, mse_dir
from .publish import publish_config_value, save_config_value

_EC_RE = re.compile(r"ec=(\d+)")
_EM_RE = re.compile(r"em=([^,)]+)")


@dataclass(frozen=True)
class MseContext:
    base_url: str
    region: str
    env: str
    cluster: str
    app_key: str
    cookie: str
    timeout_s: float


def _load_defaults() -> dict[str, object]:
    path = config_json_path()
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    defaults = data.get("defaults")
    return defaults if isinstance(defaults, dict) else {}


def load_context(
    *,
    base_url: str | None = None,
    region: str | None = None,
    env: str | None = None,
    cluster: str | None = None,
    app_key: str | None = None,
    cookie: str | None = None,
    timeout_s: float | None = None,
) -> MseContext:
    load_local_env(mse_dir())
    defaults = _load_defaults()
    resolved_cookie = (cookie or os.environ.get("MSE_COOKIE") or os.environ.get("MOA_COOKIE") or "").strip()
    if not resolved_cookie:
        raise RuntimeError("缺少 Cookie：请设置 MSE_COOKIE 或 MOA/.env.local 中的 MOA_COOKIE")
    return MseContext(
        base_url=str(base_url or os.environ.get("MSE_BASE_URL") or defaults.get("base_url") or "https://mse.wemomo.com"),
        region=str(region or os.environ.get("MSE_REGION") or defaults.get("region") or "alpha"),
        env=str(env or os.environ.get("MSE_ENV") or defaults.get("env") or "alpha"),
        cluster=str(cluster or os.environ.get("MSE_CLUSTER") or defaults.get("cluster") or "stage"),
        app_key=str(
            app_key
            or os.environ.get("MSE_APP_KEY")
            or defaults.get("app_key")
            or "momo.bpm.biz.gameplatform.overseas-voga-mts-vas"
        ),
        cookie=resolved_cookie,
        timeout_s=float(timeout_s if timeout_s is not None else 30.0),
    )


def parse_mse_error(message: str) -> tuple[int | None, str | None, str]:
    text = (message or "").strip()
    ec_match = _EC_RE.search(text)
    em_match = _EM_RE.search(text)
    ec = int(ec_match.group(1)) if ec_match else None
    em = em_match.group(1).strip() if em_match else None
    if ec == 300:
        code = "mse_permission_denied"
    elif ec is not None:
        code = "mse_api_error"
    else:
        code = "mse_error"
    return ec, em, code


def error_result(
    exc: Exception | str,
    *,
    action: str,
    config_key: str = "",
    namespace: str = "",
    app_key: str = "",
    cluster: str = "",
) -> dict[str, Any]:
    message = str(exc)
    ec, em, code = parse_mse_error(message)
    return {
        "ok": False,
        "action": action,
        "code": code,
        "ec": ec,
        "error": em or message,
        "config_key": config_key,
        "namespace": namespace,
        "app_key": app_key,
        "cluster": cluster,
    }


def _set_dict_to_args(set_values: dict[str, Any]) -> list[str]:
    if not set_values:
        raise ValueError("set 不能为空")
    args: list[str] = []
    for key, value in set_values.items():
        key_s = str(key).strip()
        if not key_s:
            raise ValueError("set 中存在空 key")
        if isinstance(value, str):
            rendered = json.dumps(value, ensure_ascii=False)
        else:
            rendered = json.dumps(value, ensure_ascii=False)
        args.append(f"{key_s}={rendered}")
    return args


def plan_config_patch(
    item: dict[str, Any],
    set_values: dict[str, Any],
) -> tuple[str, list[str], str]:
    current_value = str(item.get("configValue") or "")
    active_name = str(item.get("activeName") or "json")
    set_args = _set_dict_to_args(set_values)
    parsed = parse_config_value(current_value)
    if not isinstance(parsed, dict):
        raise RuntimeError("仅支持对 JSON object 类型的 configValue 使用 set")
    updated, changes = apply_set_args(parsed, set_args)
    if active_name == "json":
        new_value = json.dumps(updated, ensure_ascii=False, indent=4)
    else:
        new_value = json.dumps(updated, ensure_ascii=False)
    return new_value, changes, current_value


def fetch_config_item(
    ctx: MseContext,
    *,
    config_key: str,
    name_space: str = "voga-common",
) -> tuple[dict[str, Any], str]:
    api_namespace, display_namespace = resolve_namespace(name_space)
    items = get_configs_by_namespace(
        base_url=ctx.base_url,
        cookie=ctx.cookie,
        region=ctx.region,
        env=ctx.env,
        cluster=ctx.cluster,
        app_key=ctx.app_key,
        name_space=api_namespace,
        config_key=config_key,
        timeout_s=ctx.timeout_s,
    )
    if not items:
        raise RuntimeError(f"未找到 configKey={config_key}")
    return items[0], display_namespace


def mse_save_config(
    config_key: str,
    set_values: dict[str, Any],
    *,
    name_space: str = "voga-common",
    dry_run: bool = True,
    ctx: MseContext | None = None,
) -> dict[str, Any]:
    context = ctx or load_context()
    try:
        item, display_namespace = fetch_config_item(
            context,
            config_key=config_key,
            name_space=name_space,
        )
        config_id = item.get("id")
        if config_id is None:
            raise RuntimeError("配置缺少 id，无法写入")
        new_value, changes, current_value = plan_config_patch(item, set_values)
        resolved_app_key = str(item.get("appKey") or context.app_key)
        base = {
            "ok": True,
            "action": "save",
            "config_key": config_key,
            "config_id": int(config_id),
            "namespace": display_namespace,
            "app_key": resolved_app_key,
            "cluster": context.cluster,
            "changes": changes,
            "dry_run": bool(dry_run),
            "saved": False,
        }
        if dry_run:
            base["before"] = current_value
            base["after"] = new_value
            return base

        save_config_value(
            base_url=context.base_url,
            cookie=context.cookie,
            region=context.region,
            env=context.env,
            cluster=context.cluster,
            app_key=context.app_key,
            config_id=int(config_id),
            config_value=new_value,
            timeout_s=context.timeout_s,
        )
        base["saved"] = True
        base["after"] = new_value
        return base
    except Exception as exc:  # noqa: BLE001
        return error_result(
            exc,
            action="save",
            config_key=config_key,
            namespace=name_space,
            app_key=context.app_key if context else "",
            cluster=context.cluster if context else "",
        )


def mse_publish_config(
    config_key: str,
    *,
    name_space: str = "voga-common",
    confirm_publish: bool = False,
    config_id: int | None = None,
    config_value: str | None = None,
    ctx: MseContext | None = None,
) -> dict[str, Any]:
    context = ctx or load_context()
    if not confirm_publish:
        return {
            "ok": False,
            "action": "publish",
            "code": "confirm_required",
            "error": "发布须显式 confirm_publish=true",
            "config_key": config_key,
            "namespace": name_space,
            "cluster": context.cluster,
        }
    try:
        item, display_namespace = fetch_config_item(
            context,
            config_key=config_key,
            name_space=name_space,
        )
        resolved_id = int(config_id if config_id is not None else item.get("id") or 0)
        if resolved_id <= 0:
            raise RuntimeError("配置缺少 id，无法发布")
        resolved_value = config_value if config_value is not None else str(item.get("configValue") or "")
        if not resolved_value:
            raise RuntimeError("configValue 为空，无法发布")
        publish_app_key = str(context.app_key)
        record_id = publish_config_value(
            base_url=context.base_url,
            cookie=context.cookie,
            region=context.region,
            env=context.env,
            cluster=context.cluster,
            app_key=publish_app_key,
            config_id=resolved_id,
            config_value=resolved_value,
            skip_grey=True,
            timeout_s=context.timeout_s,
        )
        operator: dict[str, Any] = {}
        try:
            session = get_session_user(
                base_url=context.base_url,
                cookie=context.cookie,
                timeout_s=context.timeout_s,
            )
            operator = {
                "user_id": str(session.get("userId") or ""),
                "user_name": str(session.get("userCnName") or session.get("userName") or ""),
            }
        except RuntimeError:
            pass
        return {
            "ok": True,
            "action": "publish",
            "config_key": config_key,
            "config_id": resolved_id,
            "namespace": display_namespace,
            "app_key": publish_app_key,
            "cluster": context.cluster,
            "publish_record_id": record_id,
            "operator": operator,
        }
    except Exception as exc:  # noqa: BLE001
        return error_result(
            exc,
            action="publish",
            config_key=config_key,
            namespace=name_space,
            app_key=context.app_key if context else "",
            cluster=context.cluster if context else "",
        )
