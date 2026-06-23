"""按钉钉用户复用独立 Cursor Agent 窗口（同用户多轮对话共享上下文）。"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

from conversation_store import ConversationStore
from env_loader import GATEWAY_DIR

logger = logging.getLogger("dingtalk-gateway")

DATA_DIR = GATEWAY_DIR / "data"
AGENT_INDEX = DATA_DIR / "user_agents.json"
AGENT_IDLE_TTL_S = 30 * 60
AGENT_MAX_LIVE = 20
SWEEPER_INTERVAL_S = 300


@dataclass
class UserAgentRecord:
    agent_id: str
    sender_name: str = ""
    updated_at: str = ""


class UserAgentPool:
    def __init__(self, index_path: Path = AGENT_INDEX) -> None:
        self._index_path = index_path
        self._lock = threading.Lock()
        self._live: dict[str, Agent] = {}
        self._last_used: dict[str, float] = {}
        self._records: dict[str, UserAgentRecord] = self._load()

    @staticmethod
    def user_key(
        *,
        conversation_id: str | None,
        sender_id: str | None = None,
        sender_staff_id: str | None = None,
        conversation_type: str | None = None,
    ) -> str:
        return ConversationStore.conversation_key(
            conversation_id,
            sender_id,
            sender_staff_id=sender_staff_id,
            conversation_type=conversation_type,
        )

    @staticmethod
    def display_name(sender_nick: str | None, user_key: str) -> str:
        nick = (sender_nick or "").strip()
        if nick:
            return f"钉钉-{nick}"
        suffix = user_key.rsplit(":", 1)[-1]
        return f"钉钉-{suffix[:12]}"

    def _load(self) -> dict[str, UserAgentRecord]:
        if not self._index_path.is_file():
            return {}
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 user_agents.json 失败，将重建索引: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        records: dict[str, UserAgentRecord] = {}
        for key, item in raw.items():
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agent_id") or "").strip()
            if not agent_id:
                continue
            records[str(key)] = UserAgentRecord(
                agent_id=agent_id,
                sender_name=str(item.get("sender_name") or ""),
                updated_at=str(item.get("updated_at") or ""),
            )
        return records

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            key: {
                "agent_id": record.agent_id,
                "sender_name": record.sender_name,
                "updated_at": record.updated_at,
            }
            for key, record in self._records.items()
        }
        self._index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _persist(self, user_key: str, agent_id: str, sender_name: str) -> None:
        self._records[user_key] = UserAgentRecord(
            agent_id=agent_id,
            sender_name=sender_name,
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        self._save()

    def _touch_locked(self, user_key: str) -> None:
        if user_key in self._live:
            self._last_used[user_key] = time.monotonic()

    def touch(self, user_key: str) -> None:
        with self._lock:
            self._touch_locked(user_key)

    def _close_live_locked(self, user_key: str) -> None:
        agent = self._live.pop(user_key, None)
        self._last_used.pop(user_key, None)
        if agent is None:
            return
        try:
            agent.close()
            logger.info("已关闭 idle Agent user=%s", user_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭 idle Agent 失败 user=%s: %s", user_key, exc)

    def _evict_if_idle_locked(self, user_key: str) -> bool:
        """True 表示已因超时空闲而关闭。"""
        if user_key not in self._live:
            return False
        last = self._last_used.get(user_key, 0.0)
        if time.monotonic() - last <= AGENT_IDLE_TTL_S:
            return False
        self._close_live_locked(user_key)
        return True

    def _evict_lru_if_full_locked(self) -> None:
        if len(self._live) < AGENT_MAX_LIVE:
            return
        if not self._last_used:
            return
        lru_key = min(self._last_used, key=self._last_used.get)
        logger.info("Agent 池已满(%s)，淘汰最久未用 user=%s", AGENT_MAX_LIVE, lru_key)
        self._close_live_locked(lru_key)

    def evict_idle(self) -> int:
        """关闭超过 TTL 的空闲 Agent，返回关闭数量。"""
        with self._lock:
            stale = [
                key
                for key in list(self._live)
                if time.monotonic() - self._last_used.get(key, 0.0) > AGENT_IDLE_TTL_S
            ]
        closed = 0
        for key in stale:
            with self._lock:
                if key in self._live and time.monotonic() - self._last_used.get(key, 0.0) > AGENT_IDLE_TTL_S:
                    self._close_live_locked(key)
                    closed += 1
        if closed:
            logger.info("空闲 sweep 关闭 %s 个 Agent", closed)
        return closed

    def start_idle_sweeper(self, interval_s: float = SWEEPER_INTERVAL_S) -> None:
        def loop() -> None:
            while True:
                time.sleep(interval_s)
                try:
                    self.evict_idle()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Agent 空闲 sweep 失败: %s", exc)

        threading.Thread(target=loop, daemon=True, name="agent-pool-sweeper").start()
        logger.info("Agent 空闲 sweep 已启动（TTL=%ss，间隔=%ss）", AGENT_IDLE_TTL_S, interval_s)

    def clear_live_agents(self) -> None:
        with self._lock:
            keys = list(self._live)
            for key in keys:
                self._close_live_locked(key)
        logger.info("已清空内存中的用户 Agent 句柄（下次消息将 ResumeAgent）")

    def acquire(
        self,
        user_key: str,
        *,
        api_key: str,
        workdir: str,
        model: str,
        sender_name: str,
        mcp_servers: dict[str, Any] | None,
    ) -> tuple[Agent, bool]:
        """返回 (Agent, is_new_session)。is_new_session=True 表示首次创建窗口。"""
        local_opts = LocalAgentOptions(cwd=workdir, setting_sources=["all"])
        options = AgentOptions(
            api_key=api_key,
            model=model,
            local=local_opts,
            mcp_servers=mcp_servers or None,
        )
        display = self.display_name(sender_name, user_key)

        with self._lock:
            if self._evict_if_idle_locked(user_key):
                pass
            live = self._live.get(user_key)
            if live is not None:
                self._touch_locked(user_key)
                return live, False

            self._evict_lru_if_full_locked()

            record = self._records.get(user_key)
            if record is not None:
                try:
                    agent = Agent.resume(record.agent_id, options)
                    self._live[user_key] = agent
                    self._touch_locked(user_key)
                    logger.info("ResumeAgent user=%s agent_id=%s", user_key, agent.agent_id)
                    return agent, False
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "ResumeAgent 失败 user=%s agent_id=%s: %s，将新建窗口",
                        user_key,
                        record.agent_id,
                        exc,
                    )
                    self._records.pop(user_key, None)

            agent = Agent.create(options, name=display)
            self._live[user_key] = agent
            self._touch_locked(user_key)
            self._persist(user_key, agent.agent_id, sender_name)
            logger.info("CreateAgent user=%s name=%s agent_id=%s", user_key, display, agent.agent_id)
            return agent, True

    def invalidate(self, user_key: str) -> None:
        with self._lock:
            self._close_live_locked(user_key)
            self._records.pop(user_key, None)
        self._save()


_pool: UserAgentPool | None = None
_pool_lock = threading.Lock()


def get_user_agent_pool() -> UserAgentPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = UserAgentPool()
        return _pool


def reset_user_agent_pool() -> None:
    get_user_agent_pool().clear_live_agents()
