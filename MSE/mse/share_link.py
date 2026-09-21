"""MSE 控制台配置页分享链接生成。"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from .namespaces import PRIVATE_APPLICATION_LABEL, resolve_namespace
from .paths import config_json_path


def _load_share_link_defaults() -> dict[str, Any]:
    path = config_json_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    defaults = data.get("defaults")
    share = data.get("share_link")
    out: dict[str, Any] = {}
    if isinstance(defaults, dict):
        out.update(defaults)
    if isinstance(share, dict):
        out.update(share)
    return out


def _display_namespace(name_space: str) -> str:
    _, display = resolve_namespace(name_space)
    if display == PRIVATE_APPLICATION_LABEL:
        return "Application"
    return display or name_space or "Application"


def resolve_share_link_params(
    config_key: str,
    *,
    app_key: str = "",
    name_space: str = "",
    corp: str = "",
    env: str = "",
) -> dict[str, str]:
    """按 configKey 与可选参数解析分享链接所需字段。"""
    key = (config_key or "").strip()
    if not key:
        raise ValueError("configKey 不能为空")

    cfg = _load_share_link_defaults()
    resolved_app_key = (app_key or "").strip()
    resolved_name_space = (name_space or "").strip()
    resolved_corp = (corp or str(cfg.get("corp") or cfg.get("region") or "alpha")).strip()
    resolved_env = (env or str(cfg.get("env") or cfg.get("cluster") or "stage")).strip()

    if not resolved_app_key or not resolved_name_space:
        hints = cfg.get("hints")
        if isinstance(hints, list):
            for hint in hints:
                if not isinstance(hint, dict):
                    continue
                pattern = str(hint.get("pattern") or hint.get("match") or "").strip()
                if not pattern or pattern not in key:
                    continue
                if not resolved_app_key:
                    resolved_app_key = str(hint.get("app_key") or "").strip()
                if not resolved_name_space:
                    resolved_name_space = str(hint.get("name_space") or hint.get("namespace") or "").strip()
                if resolved_app_key and resolved_name_space:
                    break

    if not resolved_app_key:
        resolved_app_key = str(cfg.get("default_app_key") or cfg.get("app_key") or "").strip()
    if not resolved_name_space:
        resolved_name_space = str(cfg.get("default_name_space") or cfg.get("name_space") or "Application").strip()
    if not resolved_app_key:
        raise ValueError(
            f"无法推断 configKey={key} 的 appKey，请显式指定 --app-key"
        )

    return {
        "config_key": key,
        "app_key": resolved_app_key,
        "name_space": resolved_name_space,
        "corp": resolved_corp,
        "env": resolved_env,
        "base_url": str(cfg.get("base_url") or "https://mse.wemomo.com").rstrip("/"),
    }


def build_mse_config_share_link(
    config_key: str,
    *,
    app_key: str = "",
    name_space: str = "",
    corp: str = "",
    env: str = "",
    base_url: str = "",
) -> str:
    params = resolve_share_link_params(
        config_key,
        app_key=app_key,
        name_space=name_space,
        corp=corp,
        env=env,
    )
    url_base = (base_url or params["base_url"]).rstrip("/")
    query = urlencode(
        {
            "corp": params["corp"],
            "env": params["env"],
            "appKey": params["app_key"],
            "nameSpace": _display_namespace(params["name_space"]),
            "configKey": params["config_key"],
        }
    )
    return f"{url_base}/#/config/app?{query}"


def format_share_link_output(config_key: str, *, app_key: str = "", name_space: str = "") -> str:
    link = build_mse_config_share_link(config_key, app_key=app_key, name_space=name_space)
    params = resolve_share_link_params(config_key, app_key=app_key, name_space=name_space)
    return "\n".join(
        [
            f"**{params['config_key']}** MSE 分享链接",
            f"- appKey：`{params['app_key']}`",
            f"- namespace：`{_display_namespace(params['name_space'])}`",
            f"- 环境：corp={params['corp']} env={params['env']}",
            "",
            link,
        ]
    )
