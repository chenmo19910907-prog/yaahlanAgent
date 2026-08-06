"""P2P CUSTOM 消息 preset（客户端已支持 eventId + dataInfo）。"""

from __future__ import annotations

from typing import Any

P2P_CUSTOM_PRESETS = frozenset({"text_goto", "notice", "small_image_goto", "big_image_goto"})

_DEFAULT_IMAGE = "https://oversea.hellogroupcdn.com/s1/u/baihafdhga/voga-mts-room/task-invite-seat.png"


def build_p2p_custom_preset(
    preset: str,
    from_uid: str,
    to_uid: str,
    *,
    text: str | None = None,
    url: str | None = None,
    goto_text: str | None = None,
    goto_click: str | None = None,
) -> tuple[int, dict[str, Any]]:
    name = str(preset or "text_goto").strip().lower()
    if name not in P2P_CUSTOM_PRESETS:
        raise ValueError(
            f"p2p-custom-preset 不支持 {name}，可选: {', '.join(sorted(P2P_CUSTOM_PRESETS))}"
        )
    content = str(text or "").strip() or f"Test message from {from_uid}"
    btn = str(goto_text or "").strip() or "View"
    click = str(goto_click or "").strip() or f"yaahlan://userProfile?userId={to_uid}"
    img = str(url or "").strip() or _DEFAULT_IMAGE

    if name == "notice":
        return 1001, {
            "content": content,
            "highlightList": [],
        }
    if name == "text_goto":
        return 1000090, {
            "fromUid": from_uid,
            "content": content,
            "gotoText": btn,
            "gotoClick": click,
        }
    if name == "small_image_goto":
        return 1000089, {
            "fromUid": from_uid,
            "image": img,
            "content": content,
            "gotoText": btn,
            "gotoClick": click,
        }
    return 1000088, {
        "fromUid": from_uid,
        "content": content,
        "image": img,
        "gotoText": btn,
        "gotoClick": click,
    }
