"""房间公屏表情 preset（Tunnel 抓包校验）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

ROOM_EMOTE_PRESETS: dict[str, dict[str, Any]] = {
    "chaoxiao": {
        "appVersion": "1.0.0",
        "approveStatus": -1,
        "emojiId": "",
        "id": 0,
        "isAddOne": False,
        "memberLevel": 0,
        "name": "chaoxiao",
        "tabId": "",
        "thumbnail": "https://oversea.hellogroupcdn.com/s1/u/baihafdhga/voga-mts-components/5783341A-70C0-4F68-AD43-C26618F8171F20231109_L.jpg",
        "url": "https://oversea.hellogroupcdn.com/s1/u/baihafdhga/voga-mts-components/chaoxiao.png",
        "vipLevel": 0,
        "webPUrl": "https://oversea.hellogroupcdn.com/s1/u/jhhaiicbi/chaoxiao.webp",
    },
}


def resolve_room_emote(*, name: str | None = None, emote: dict[str, Any] | None = None) -> dict[str, Any]:
    preset_name = str(name or (emote or {}).get("name") or "").strip().lower()
    if not preset_name:
        raise ValueError("房间公屏表情须提供 --room-chat-emote-name 或完整 --room-chat-emote-json（含 url/thumbnail）")
    base = ROOM_EMOTE_PRESETS.get(preset_name)
    if base is None:
        known = ", ".join(sorted(ROOM_EMOTE_PRESETS))
        raise ValueError(f"未知表情 preset: {preset_name}；可选: {known}")
    merged = deepcopy(base)
    if emote:
        merged.update(emote)
    if not str(merged.get("url") or "").strip() or not str(merged.get("thumbnail") or "").strip():
        raise ValueError(f"表情 {preset_name} 缺少 url/thumbnail，请使用已知 preset 或补全 emote JSON")
    return merged
