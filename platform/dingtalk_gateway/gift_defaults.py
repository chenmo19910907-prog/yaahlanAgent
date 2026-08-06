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
    cp_love = gateway_cp_love_rule_line()
    return (
        f"**送礼默认路径**：用户说「送礼/送礼物/gift send」等且**未明确**"
        f"「{keywords}…」时，**默认**用 `{execute}` Stage HTTP（`/v2/gift/send`）。"
        "仅当用户明确要背包送礼或背包备货时，才走 MOA 背包模板。"
        f"\n{cp_love}"
    )


def gateway_cp_love_rule_line() -> str:
    try:
        import sys
        from pathlib import Path

        platform_dir = Path(__file__).resolve().parents[1]
        if str(platform_dir) not in sys.path:
            sys.path.insert(0, str(platform_dir))
        from project.loader import gift_cp_love_rule_line

        custom = gift_cp_love_rule_line()
        if custom:
            return custom
    except (ImportError, FileNotFoundError, ValueError):
        pass
    return (
        "**CP 宝箱周期爱意值造数**：无直改 MOA（`addCpLoveValue` 只改 cp-moa 总恩爱值 loveValue，不更新宝箱 currentLoveValue）。须 Stage 私聊送礼（1 钻 = 1 爱意值）。"
        "**默认礼物：面板 Rose `2005000233`（1 钻，名称 Rose；禁止 roses/`2005001776` 及 `2005004730`）。**"
        "先 `python3 Gift/scripts/plan_cp_love_gift.py --delta <增量>`；"
        "**禁止**固定 `--num 10000` 小步循环；优先 1 次 HTTP，`--num` 按规划（Rose 1 钻时 num=增量）。"
    )
