"""钉钉网关：送礼默认路径（HTTP vs MOA 背包）。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
GIFT_DEFAULTS_CONFIG = GATEWAY_DIR / "config" / "gift_defaults.json"

_BACKPACK_KEYWORDS_FALLBACK = (
    "背包送礼",
    "背包下发",
    "MOA背包",
    "addPackageGift",
    "sendMiddlePackageGift",
    "背包礼物-下发",
    "背包礼物-送礼",
)

_GIFT_INTENT_RE = re.compile(
    r"(送礼|送礼物|gift\s*send|/v2/gift/send|stage\s*送礼)",
    re.I,
)


@lru_cache(maxsize=1)
def load_gift_defaults() -> dict:
    if not GIFT_DEFAULTS_CONFIG.is_file():
        return {}
    try:
        data = json.loads(GIFT_DEFAULTS_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def backpack_keywords() -> tuple[str, ...]:
    cfg = load_gift_defaults()
    raw = cfg.get("backpackKeywords")
    if isinstance(raw, list) and raw:
        return tuple(str(x) for x in raw if str(x).strip())
    return _BACKPACK_KEYWORDS_FALLBACK


def is_backpack_gift_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    lower = t.lower()
    return any(kw.lower() in lower for kw in backpack_keywords())


def looks_like_gift_send_request(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(_GIFT_INTENT_RE.search(t))


def should_use_gift_http(text: str) -> bool:
    """未强调背包送礼时，默认走 Gift HTTP。"""
    if not looks_like_gift_send_request(text):
        return False
    return not is_backpack_gift_request(text)


def gateway_gift_rule_line() -> str:
    cfg = load_gift_defaults()
    execute = str(cfg.get("defaultExecute") or "Gift/gift_execute.py")
    keywords = " / ".join(backpack_keywords()[:4])
    return (
        f"**送礼默认路径**：用户说「送礼/送礼物/gift send」等且**未明确**"
        f"「{keywords}…」时，**默认**用 `{execute}` Stage HTTP（`/v2/gift/send`）。"
        "仅当用户明确要背包送礼或背包备货时，才走 MOA 背包模板。"
    )
