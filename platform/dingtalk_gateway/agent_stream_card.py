"""钉钉 Agent 流式卡片推送（节流刷新）。"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

import dingtalk_stream

from progress_message import STREAMING_CARD_LINE_BREAK

logger = logging.getLogger("dingtalk-gateway")

def _stream_render_interval_s() -> float:
    from env_loader import load_env_local

    load_env_local()
    raw = os.environ.get("DINGTALK_AGENT_STREAM_RENDER_INTERVAL_S", "2.0").strip()
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 2.0


DEFAULT_MIN_INTERVAL_S = _stream_render_interval_s()
WEB_STREAM_RENDER_INTERVAL_S = 0.35
# 内存态每秒更新；卡片 API 按 DEFAULT_MIN_INTERVAL_S 合并刷新，减轻抖动
PROGRESS_TICK_S = 1.0
# AI 流式卡片在部分单聊场景 streaming API 不刷新；默认用 Markdown 卡片 update
# AI 卡片：msgTitle=白线上方（提问）；staticMsgContent=白线下方固定区；msgContent=流式正文
# 不含 msgSlider / msgButtons：标准 AI 模板完成态会展示赞踩与反馈标签，order 无法可靠关闭
_CARD_ORDER = ("msgTitle", "staticMsgContent", "msgContent")


def is_agent_streaming_enabled() -> bool:
    from env_loader import load_env_local

    load_env_local()
    raw = os.environ.get("DINGTALK_AGENT_STREAMING", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def is_streaming_agent_task(prompt: str) -> bool:
    """是否走 Agent 流式卡片（非 fast 路由且开关开启）。"""
    from route_patterns import is_likely_fast_route

    text = (prompt or "").strip()
    return bool(text) and is_agent_streaming_enabled() and not is_likely_fast_route(text)


def _ai_card_feedback_enabled() -> bool:
    from env_loader import load_env_local

    load_env_local()
    raw = os.environ.get("DINGTALK_AGENT_STREAMING_CARD_FEEDBACK", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _card_mode() -> str:
    from env_loader import load_env_local

    load_env_local()
    raw = os.environ.get("DINGTALK_AGENT_STREAMING_CARD", "markdown").strip().lower()
    if raw != "ai":
        return "markdown"
    # 标准 AI 卡片模板完成态自带赞踩反馈；未显式开启时回退 Markdown 卡片
    if not _ai_card_feedback_enabled():
        return "markdown"
    return "ai"


def _patch_ai_card_no_feedback(card: Any) -> None:
    """尽量从 sys_full_json_obj 去掉 msgSlider / msgButtons（模板仍可能展示反馈）。"""
    original = card.get_card_data

    def get_card_data(flow_status: Any | None = None) -> dict[str, Any]:
        data = original(flow_status)
        try:
            obj = json.loads(data.get("sys_full_json_obj") or "{}")
        except json.JSONDecodeError:
            obj = {}
        obj["order"] = list(_CARD_ORDER)
        obj["msgSlider"] = []
        obj["msgButtons"] = []
        data["sys_full_json_obj"] = json.dumps(obj, ensure_ascii=False)
        return data

    card.get_card_data = get_card_data  # type: ignore[method-assign]


def try_create_agent_stream_card(
    handler: Any,
    incoming: dingtalk_stream.ChatbotMessage,
) -> AgentStreamCard | None:
    client = getattr(handler, "dingtalk_client", None)
    if client is None:
        logger.warning("流式卡片不可用：handler 无 dingtalk_client")
        return None
    try:
        return AgentStreamCard(client, incoming)
    except Exception:  # noqa: BLE001
        logger.exception("创建流式卡片失败，回退文本回复")
        return None


class AgentStreamCard:
    """Markdown 卡片全量 update（默认）或 AI 流式卡片（可选）。"""

    def __init__(
        self,
        dingtalk_client: Any,
        incoming: dingtalk_stream.ChatbotMessage,
        *,
        min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    ) -> None:
        self._mode = _card_mode()
        self._min_interval_s = min_interval_s
        self._lock = threading.Lock()
        self._started = False
        self._last_push_at = 0.0
        self._pending: str | None = None
        self._timer: threading.Timer | None = None
        self._push_count = 0
        self._last_flushed_body = ""
        self._card_instance_id = ""
        self._started_at = 0.0
        self._last_content_at = 0.0
        self._progress_timer: threading.Timer | None = None
        self._header = ""
        self._persistent_header = ""
        self._card_title = ""
        # 三个独立通道：Agent 文本 / 批量进度 / 已用时
        self._agent_body = ""
        self._status_line = ""
        self._batch_progress_line = ""
        self._estimate_seconds: float | None = None

        if self._mode == "ai":
            card = dingtalk_stream.AIMarkdownCardInstance(dingtalk_client, incoming)
            card.set_order(list(_CARD_ORDER))
            _patch_ai_card_no_feedback(card)
            self._ai_card = card
            self._md_card = None
        else:
            self._md_card = dingtalk_stream.MarkdownCardInstance(dingtalk_client, incoming)
            self._ai_card = None

    @property
    def is_active(self) -> bool:
        return self._started

    def _ensure_stream_state(self) -> None:
        """兼容旧实例 / 部分初始化，避免缺字段导致 AttributeError。"""
        for name, default in (
            ("_last_flushed_body", ""),
            ("_agent_body", ""),
            ("_status_line", ""),
            ("_batch_progress_line", ""),
            ("_card_title", ""),
            ("_estimate_seconds", None),
        ):
            if not hasattr(self, name):
                setattr(self, name, default)

    def _normalize_agent_text(self, text: str) -> str:
        """卡片内用 <br> 代替段落换行，避免高度跳动。"""
        body = (text or "").strip().replace("\r", "")
        if not body:
            return ""
        body = body.replace("\n\n", STREAMING_CARD_LINE_BREAK).replace("\n", STREAMING_CARD_LINE_BREAK)
        return body

    def _compose_body(self) -> str:
        """白线下方正文：三通道各占一行（确认语 + Agent 文本 + 批量进度 + 已用时）。"""
        parts = [
            part.strip()
            for part in (
                self._header,
                self._normalize_agent_text(getattr(self, "_agent_body", "")),
                getattr(self, "_batch_progress_line", ""),
                getattr(self, "_status_line", ""),
            )
            if part and part.strip()
        ]
        return STREAMING_CARD_LINE_BREAK.join(parts)

    def _compose(self, body: str) -> str:
        """完整 Markdown（含标题区内容，仅测试/兼容）。"""
        top = (getattr(self, "_card_title", "") or self._persistent_header or "").strip()
        rest = self._compose_body()
        if top and rest:
            return f"{top}{STREAMING_CARD_LINE_BREAK}{rest}"
        return top or rest

    def _apply_ai_card_title(self) -> None:
        if self._ai_card is None:
            return
        title = (getattr(self, "_card_title", "") or "").strip()
        if title:
            self._ai_card.set_title_and_logo(title, "")

    def _compose_ai_static(self, *, extra: str = "") -> str:
        """AI 卡片 static 区（白线下方、流式区上方）：仅放完成提示等，提问走 msgTitle。"""
        return (extra or "").strip()

    def _ai_card_bootstrap(self, body_md: str) -> None:
        """创建 AI 卡片并携带 msgTitle（白线上方提问），避免 ai_start({}) 导致标题区空白。"""
        assert self._ai_card is not None
        self._apply_ai_card_title()
        self._ai_card.static_markdown = ""
        self._ai_card.markdown = body_md
        initial = self._ai_card.get_card_data()
        self._ai_card.card_instance_id = self._ai_card.start(
            self._ai_card.card_template_id,
            initial,
        )
        self._card_instance_id = self._ai_card.card_instance_id or ""
        if self._card_instance_id:
            self._ai_card.ai_streaming(body_md, append=False)

    def _sync_ai_card_shell(self, *, flow_status: Any | None = None) -> None:
        """刷新 AI 卡片 msgTitle（白线上方提问）；static 区不写提问。"""
        if self._ai_card is None or not self._card_instance_id:
            return
        self._apply_ai_card_title()
        self._ai_card.static_markdown = self._compose_ai_static()
        card_data = self._ai_card.get_card_data(flow_status=flow_status)
        self._ai_card.put_card_data(self._card_instance_id, card_data)

    def _agent_body_for_finish(self) -> str:
        """完成态不保留 Agent 流式正文（结果另发新消息，卡片仅展示完成提示）。"""
        return ""

    def _is_progress_status_body(self, body: str) -> bool:
        text = (body or "").strip()
        return not text or text.startswith("⏳")

    def _render(self, *, force: bool = False) -> None:
        """合并三通道后节流刷新卡片（内容未变 / 未到间隔则跳过）。"""
        self._ensure_stream_state()
        if not self._started:
            return
        composed = self._compose_body()
        if composed == self._last_flushed_body:
            return
        self._enqueue(composed, force=force)

    def set_batch_progress(self, line: str) -> None:
        """批量进度通道更新（仅写内存，由进度 tick / Agent push 统一渲染）。"""
        self._ensure_stream_state()
        self._batch_progress_line = (line or "").strip()

    def clear_batch_progress(self) -> None:
        self._ensure_stream_state()
        if not self._batch_progress_line:
            return
        self._batch_progress_line = ""

    def start(
        self,
        markdown: str = "⏳ Agent 启动中…",
        *,
        header: str = "",
        persistent_header: str = "",
        card_title: str = "",
        start_progress: bool = True,
        estimate_seconds: float | None = None,
    ) -> None:
        self._ensure_stream_state()
        self._header = (header or "").strip()
        self._persistent_header = (persistent_header or "").strip()
        self._card_title = (card_title or "").strip()
        self._estimate_seconds = estimate_seconds
        text = (markdown or "").strip()
        if text and not self._is_progress_status_body(text):
            self._agent_body = text
        else:
            self._status_line = text
        body_md = self._compose_body()
        if self._md_card is not None:
            if self._card_title:
                self._md_card.set_title_and_logo(self._card_title, "")
            self._md_card.reply(body_md)
            self._card_instance_id = self._md_card.card_instance_id or ""
        else:
            assert self._ai_card is not None
            self._ai_card_bootstrap(body_md)
        if not self._card_instance_id:
            raise RuntimeError("流式卡片创建失败（card_instance_id 为空）")
        self._started = True
        self._started_at = time.monotonic()
        self._last_content_at = self._started_at
        if start_progress:
            self._status_line = self._format_progress_markdown()
            self._schedule_progress_tick()
        self._last_flushed_body = self._compose_body()
        logger.info("流式卡片已投放 mode=%s id=%s…", self._mode, self._card_instance_id[:12])

    def begin_running(
        self,
        header: str,
        markdown: str = "⏳ Agent 启动中…",
        *,
        estimate_seconds: float | None = None,
    ) -> None:
        """排队态卡片转入执行态：刷新确认区、重置计时并启动进度节流。"""
        self._ensure_stream_state()
        if not self._started:
            return
        self._header = (header or "").strip()
        if estimate_seconds is not None:
            self._estimate_seconds = estimate_seconds
        self._started_at = time.monotonic()
        self._last_content_at = self._started_at
        # 排队态文案写入 _agent_body；转入执行态须先清空，避免与确认语/进度并存
        self._agent_body = ""
        text = (markdown or "").strip()
        if text and not self._is_progress_status_body(text):
            self._agent_body = text
        self._status_line = self._format_progress_markdown()
        if self._progress_timer is None:
            self._schedule_progress_tick()
        if self._ai_card is not None and self._card_instance_id:
            self._sync_ai_card_shell()
        self._render(force=True)

    def _format_progress_markdown(self) -> str:
        from progress_message import build_streaming_progress_status_line

        elapsed = max(0.0, time.monotonic() - self._started_at)
        return build_streaming_progress_status_line(
            elapsed,
            estimate_s=getattr(self, "_estimate_seconds", None),
        )

    def _schedule_progress_tick(self) -> None:
        if not self._started:
            return

        def _fire() -> None:
            self._progress_timer = None
            if not self._started:
                return
            # 内存态每秒更新已用时；卡片 API 由 _render 节流合并
            self._status_line = self._format_progress_markdown()
            self._render()
            self._schedule_progress_tick()

        timer = threading.Timer(PROGRESS_TICK_S, _fire)
        timer.daemon = True
        self._progress_timer = timer
        timer.start()

    def _stop_progress_tick(self) -> None:
        if self._progress_timer is not None:
            self._progress_timer.cancel()
            self._progress_timer = None

    def push(self, markdown: str) -> None:
        """Agent 文本通道更新（思考/工具/回答）；占位状态交给已用时通道。"""
        self._ensure_stream_state()
        if not self._started:
            return
        text = (markdown or "").strip()
        if text and not self._is_progress_status_body(text):
            normalized = self._normalize_agent_text(text)
            if normalized == self._agent_body:
                return
            self._agent_body = normalized
            self._last_content_at = time.monotonic()
        self._render()

    def _enqueue(self, body_md: str, *, force: bool = False) -> None:
        with self._lock:
            self._pending = body_md
            now = time.monotonic()
            elapsed = now - self._last_push_at
            if force or elapsed >= self._min_interval_s:
                self._flush_locked()
                return
            if self._timer is not None:
                return
            delay = max(0.05, self._min_interval_s - elapsed)

            def _fire() -> None:
                with self._lock:
                    self._timer = None
                    self._flush_locked()

            timer = threading.Timer(delay, _fire)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _flush_locked(self) -> None:
        self._ensure_stream_state()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._pending is None:
            return
        body_md = self._compose_body()
        if body_md == self._last_flushed_body:
            self._pending = None
            return
        try:
            if self._md_card is not None:
                self._md_card.update(body_md)
            else:
                assert self._ai_card is not None
                self._ai_card.markdown = body_md
                self._ai_card.ai_streaming(body_md, append=False)
            self._last_push_at = time.monotonic()
            self._last_flushed_body = body_md
            self._push_count += 1
            if self._push_count <= 2 or self._push_count % 8 == 0:
                logger.info(
                    "卡片 push #%d mode=%s len=%d",
                    self._push_count,
                    self._mode,
                    len(body_md),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("卡片 push 失败 mode=%s: %s", self._mode, exc)

    def finish(self, markdown: str, *, keep_agent_body: bool = False) -> None:
        self._ensure_stream_state()
        if not self._started:
            return
        self._stop_progress_tick()
        self._header = ""
        self._batch_progress_line = ""
        status = (markdown or "").strip()
        if keep_agent_body:
            self._agent_body = self._agent_body_for_finish()
            self._status_line = status
        else:
            self._status_line = ""
            self._agent_body = status
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending = None
        final_body_md = self._compose_body()
        try:
            if self._md_card is not None:
                if self._card_title:
                    self._md_card.set_title_and_logo(self._card_title, "")
                self._md_card.update(final_body_md)
            else:
                assert self._ai_card is not None
                self._apply_ai_card_title()
                if keep_agent_body:
                    # 完成态：提问留在 msgTitle（白线上方），流式区仅完成提示
                    self._apply_ai_card_title()
                    self._ai_card.static_markdown = ""
                    self._ai_card.markdown = status
                    self._ai_card.ai_finish()
                else:
                    self._ai_card.static_markdown = self._compose_ai_static()
                    self._ai_card.markdown = final_body_md
                    self._ai_card.ai_streaming(final_body_md, append=False)
                    self._ai_card.ai_finish(markdown=final_body_md)
            logger.info(
                "卡片 finish 成功 mode=%s pushes=%d len=%d",
                self._mode,
                self._push_count,
                len(final_body_md),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("卡片 finish 失败 mode=%s: %s", self._mode, exc)
        finally:
            self._started = False

    def finish_status(self, status_line: str) -> None:
        """卡片收尾为终态提示（提问留标题区，正文仅完成提示；结果另发新消息）。"""
        self.finish(status_line, keep_agent_body=True)

    def fail(self, markdown: str) -> None:
        body = markdown if markdown.startswith("❌") else f"❌ {markdown}"
        self.finish(body)
