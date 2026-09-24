# -*- coding: utf-8 -*-
"""盘古配置中心读取（从 sc_auto_test/helpers/cc-config.ts 迁过来，只保留读）。

MSE 配置中心页面要 SSO，登不进去。实际读数走盘古 config-server：
GET {PANGU_CONFIG_SERVER}?configKey=...
Header: appKey、client-host-name

公会激励新版本开关默认 key：tradeMotivationMaxCycleSwitch
（应用 momo.bpm.biz.gameplatform.overseas-voga-mts-vas / 命名空间 voga-common）
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

import requests

try:
    from utils.env_utils import load_env_file
except ImportError:
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from utils.env_utils import load_env_file

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_SERVER = "http://alpha-stage-config-server.momo.com/configs/getConfig"
DEFAULT_APP_KEY = "momo.bpm.biz.gameplatform.overseas-voga-mts-vas"
TRADE_MOTIVATION_SWITCH_KEY = "tradeMotivationMaxCycleSwitch"


class CcConfigError(RuntimeError):
    pass


class CcConfigUtils:
    @staticmethod
    def config_server() -> str:
        return os.environ.get("PANGU_CONFIG_SERVER", "").strip() or DEFAULT_CONFIG_SERVER

    @staticmethod
    def default_app_key() -> str:
        return os.environ.get("PANGU_APP_KEY", "").strip() or DEFAULT_APP_KEY

    @staticmethod
    def get_raw(config_key: str, app_key: str | None = None, timeout: int = 10) -> str:
        """读配置原始字符串。key 不存在时返回空串。"""
        if not config_key or not str(config_key).strip():
            raise CcConfigError("config_key 不能为空")
        key = str(config_key).strip()
        used_app = (app_key or "").strip() or CcConfigUtils.default_app_key()
        url = CcConfigUtils.config_server()
        try:
            resp = requests.get(
                url,
                params={"configKey": key},
                headers={"appKey": used_app, "client-host-name": "127.0.0.1"},
                timeout=timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            raise CcConfigError(f"读盘古配置失败 key={key} appKey={used_app}: {e}") from e
        try:
            payload = resp.json()
        except ValueError as e:
            raise CcConfigError(f"盘古配置响应不是 JSON: {resp.text[:200]}") from e
        value = payload.get("value")
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def get_config(config_key: str, app_key: str | None = None) -> Any:
        """读配置；值为 JSON 则解析，否则返回原字符串。"""
        raw = CcConfigUtils.get_raw(config_key, app_key=app_key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    @staticmethod
    def get_trade_motivation_switch(app_key: str | None = None) -> dict:
        """公会激励新版本开关：switchOn + whiteList。"""
        data = CcConfigUtils.get_config(TRADE_MOTIVATION_SWITCH_KEY, app_key=app_key)
        if not isinstance(data, dict):
            raise CcConfigError(
                f"{TRADE_MOTIVATION_SWITCH_KEY} 不是 JSON 对象: {data!r}"
            )
        return data


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    load_env_file()
    import sys

    key = sys.argv[1] if len(sys.argv) > 1 else TRADE_MOTIVATION_SWITCH_KEY
    result = CcConfigUtils.get_config(key)
    print(json.dumps(result, ensure_ascii=False, indent=2) if not isinstance(result, str) else result)
