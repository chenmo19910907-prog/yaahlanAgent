"""按钉钉用户复用独立 Cursor Agent 窗口（同用户多轮对话共享上下文）。"""

from __future__ import annotations

import json
import logging
import threading
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

    def _drop_live(self, user_key: str) -> None:
        self._live.pop(user_key, None)

    def clear_live_agents(self) -> None:
        with self._lock:
            self._live.clear()
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
            live = self._live.get(user_key)
            if live is not None:
                return live, False

            record = self._records.get(user_key)
            if record is not None:
                try:
                    agent = Agent.resume(record.agent_id, options)
                    self._live[user_key] = agent
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
            self._persist(user_key, agent.agent_id, sender_name)
            logger.info("CreateAgent user=%s name=%s agent_id=%s", user_key, display, agent.agent_id)
            return agent, True

    def invalidate(self, user_key: str) -> None:
        with self._lock:
            self._drop_live(user_key)
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
