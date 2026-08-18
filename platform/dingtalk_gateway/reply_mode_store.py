"""钉钉机器人回复详略（精简 / 标准 / 详细），全员统一设置。"""

from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
MODE_INDEX = DATA_DIR / "reply_mode.json"
# 兼容旧版按用户存储的文件名
LEGACY_PREFS_INDEX = DATA_DIR / "reply_mode_prefs.json"

_PLATFORM_DIR = GATEWAY_DIR.parent
_WEB_AGENT_DIR = _PLATFORM_DIR / "web_agent"
if str(_WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_WEB_AGENT_DIR))
from web_prompt import normalize_reply_mode  # noqa: E402

MODE_LABELS = {
    "concise": "精简回复",
    "standard": "标准回复",
    "detailed": "详细回复",
}

_VALID_MODES = frozenset(MODE_LABELS)


class ReplyModeStore:
    def __init__(self, index_path: Path = MODE_INDEX) -> None:
        self._index_path = index_path
        self._lock = threading.Lock()
        self._mode: str = self._load()

    def _load(self) -> str:
        mode = self._read_mode_file(self._index_path)
        if mode is not None:
            return mode
        legacy = self._read_legacy_prefs(LEGACY_PREFS_INDEX)
        if legacy is not None:
            self._mode = legacy
            self._save()
            return legacy
        return "standard"

    @staticmethod
    def _read_mode_file(path: Path) -> str | None:
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 %s 失败，将重建: %s", path.name, exc)
            return None
        if isinstance(raw, dict):
            mode = str(raw.get("mode") or "").strip()
            if mode in _VALID_MODES:
                return mode
        return None

    @staticmethod
    def _read_legacy_prefs(path: Path) -> str | None:
        """旧版 reply_mode_prefs.json 为 {user_key: mode}；取任意已设模式作为全员默认。"""
        if not path.is_file():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        for value in raw.values():
            mode = str(value or "").strip()
            if mode in _VALID_MODES:
                return mode
        return None

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps({"mode": self._mode}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self) -> str:
        with self._lock:
            return self._mode

    def set(self, mode: str) -> str:
        normalized = normalize_reply_mode(mode)
        with self._lock:
            self._mode = normalized
            self._save()
        return normalized


_store: ReplyModeStore | None = None


def get_reply_mode_store() -> ReplyModeStore:
    global _store
    if _store is None:
        _store = ReplyModeStore()
    return _store
