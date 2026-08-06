"""MOA-generative 脚本读取 AGENT_PROJECT API 前缀与 ServiceUrl。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PLATFORM = _REPO / "platform"
if str(_PLATFORM) not in sys.path:
    sys.path.insert(0, str(_PLATFORM))

from project.loader import (  # noqa: E402
    api_endpoint,
    api_family_pk_h5_path,
    api_http_prefix,
    api_moa_service_prefix,
    api_moa_trick_service_prefix,
    get_repo_root,
    moa_generative_root,
    stage_gateway_url,
)


def service_url(key: str, default: str) -> str:
    return api_endpoint(key, default)


def repo_root() -> Path:
    return get_repo_root()


def generative_root() -> Path:
    return moa_generative_root()


def load_body_template(relative: str) -> Path:
    return generative_root() / relative


__all__ = [
    "api_family_pk_h5_path",
    "api_http_prefix",
    "api_moa_service_prefix",
    "api_moa_trick_service_prefix",
    "generative_root",
    "load_body_template",
    "repo_root",
    "service_url",
    "stage_gateway_url",
]
