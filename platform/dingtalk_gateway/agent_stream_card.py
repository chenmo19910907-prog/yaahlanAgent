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
CARD_CREATE_MAX_RETRIES = 3
CARD_PUT_MAX_RETRIES = 3
# 排队卡须周期 push 才能离开钉钉模板默认「已受理」
QUEUE_CONTENT_REFRESH_S = 3.0
QUEUE_ORPHAN_FAIL_S = 90.0
# create 后钉钉 Markdown 卡仍可能短暂显示「已受理」，短间隔连推几次
QUEUE_BOOTSTRAP_PUSH_DELAYS_S = (0.4, 1.2)
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

    _put_patch_lock = threading.Lock()

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
        self._last_put_succeeded = True
        self._card_sync_degraded = False
        self._queue_refresh_timer: threading.Timer | None = None
        self._conversation_id = ""
        self._user_key = ""
        self._prompt = ""
        self._queue_ahead_provider: Any = None
        self._orphan_timer: threading.Timer | None = None
        self._queue_bootstrap_timers: list[threading.Timer] = []

        if self._mode == "ai":
            card = dingtalk_stream.AIMarkdownCardInstance(dingtalk_client, incoming)
            card.set_order(list(_CARD_ORDER))
            _patch_ai_card_no_feedback(card)
            self._ai_card = card
            self._md_card = None
        else:
            self._md_card = dingtalk_stream.MarkdownCardInstance(dingtalk_client, incoming)
            self._ai_card = None
        self._install_card_put_hook()

    @property
    def is_active(self) -> bool:
        return self._started

    @property
    def card_sync_degraded(self) -> bool:
        return self._card_sync_degraded

    def _install_card_put_hook(self) -> None:
        """包装 put_card_data：记录成功/失败（SDK 失败仅打日志不抛异常）。"""
        replier = self._md_card or self._ai_card
        if replier is None:
            return
        if getattr(replier, "_gateway_put_hooked", False):
            return
        original_put = replier.put_card_data

        def hooked_put(card_instance_id: str, card_data: dict, **kwargs: Any) -> None:
            for attempt in range(CARD_PUT_MAX_RETRIES):
                if self._put_card_data_once(original_put, card_instance_id, card_data, **kwargs):
                    self._last_put_succeeded = True
                    return
                if attempt + 1 < CARD_PUT_MAX_RETRIES:
                    time.sleep(0.2 * (attempt + 1))
            self._last_put_succeeded = False
            self._card_sync_degraded = True
            logger.warning(
                "卡片更新连续失败 id=%s…，后续依赖文本结果消息",
                (card_instance_id or "")[:12],
            )

        replier.put_card_data = hooked_put  # type: ignore[method-assign]
        replier._gateway_put_hooked = True  # type: ignore[attr-defined]

    @staticmethod
    def _put_card_data_once(
        original_put: Any,
        card_instance_id: str,
        card_data: dict,
        **kwargs: Any,
    ) -> bool:
        import requests

        original_requests_put = requests.put
        success = False

        def tracking_put(*args: Any, **put_kwargs: Any) -> Any:
            nonlocal success
            response = original_requests_put(*args, **put_kwargs)
            try:
                response.raise_for_status()
                success = True
            except Exception:  # noqa: BLE001
                success = False
            return response

        with AgentStreamCard._put_patch_lock:
            requests.put = tracking_put
            try:
                original_put(card_instance_id, card_data, **kwargs)
            finally:
                requests.put = original_requests_put
        return success

    def _put_markdown_body(self, body_md: str) -> bool:
        """Markdown 卡片 update；成功/失败以 put hook 为准（SDK 失败不抛异常）。"""
        if self._md_card is None or not self._card_instance_id:
            self._last_put_succeeded = False
            return False
        try:
            card_data = self._md_card._get_card_data(body_md)
            self._md_card.put_card_data(self._card_instance_id, card_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Markdown 卡片 update 异常 id=%s…: %s",
                (self._card_instance_id or "")[:12],
                exc,
            )
            self._last_put_succeeded = False
            return False
        return bool(self._last_put_succeeded)

    def _create_markdown_card(self, body_md: str) -> None:
        assert self._md_card is not None
        last_error = "card_instance_id 为空"
        replied = False
        for attempt in range(CARD_CREATE_MAX_RETRIES):
            if self._card_title:
                self._md_card.set_title_and_logo(self._card_title, "")
            if not replied:
                self._md_card.reply(body_md)
                replied = True
            self._card_instance_id = self._md_card.card_instance_id or ""
            if self._card_instance_id:
                # reply 后立刻 update：单聊 Markdown 卡否则常停在模板默认「已受理」
                synced = False
                for put_attempt in range(CARD_PUT_MAX_RETRIES):
                    if self._put_markdown_body(body_md):
                        synced = True
                        break
                    if put_attempt + 1 < CARD_PUT_MAX_RETRIES:
                        time.sleep(0.25 * (put_attempt + 1))
                if synced:
                    logger.info(
                        "流式卡片 create 后首次 update 成功 id=%s… len=%d",
                        self._card_instance_id[:12],
                        len(body_md),
                    )
                else:
                    logger.warning(
                        "流式卡片 create 后首次 update 失败 id=%s… len=%d",
                        self._card_instance_id[:12],
                        len(body_md),
                    )
                    raise RuntimeError("流式卡片 create 后首次 update 失败")
                return
            if attempt + 1 < CARD_CREATE_MAX_RETRIES:
                time.sleep(0.25 * (attempt + 1))
        raise RuntimeError(f"流式卡片创建失败（{last_error}）")

    def _ensure_stream_state(self) -> None:
        """兼容旧实例 / 部分初始化，避免缺字段导致 AttributeError。"""
        for name, default in (
            ("_last_flushed_body", ""),
            ("_agent_body", ""),
            ("_status_line", ""),
            ("_batch_progress_line", ""),
            ("_card_title", ""),
            ("_estimate_seconds", None),
            ("_last_put_succeeded", True),
            ("_card_sync_degraded", False),
            ("_queue_refresh_timer", None),
            ("_conversation_id", ""),
            ("_user_key", ""),
            ("_prompt", ""),
            ("_queue_ahead_provider", None),
            ("_orphan_timer", None),
            ("_queue_bootstrap_timers", []),
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

    def _render(self, *, force: bool = False) -> bool:
        """合并三通道后节流刷新卡片（内容未变 / 未到间隔则跳过）。"""
        self._ensure_stream_state()
        if not self._started:
            return False
        composed = self._compose_body()
        if composed == self._last_flushed_body and not force:
            return False
        return self._enqueue(composed, force=force)

    def _cancel_orphan_watchdog(self) -> None:
        if self._orphan_timer is not None:
            self._orphan_timer.cancel()
            self._orphan_timer = None

    def _is_queue_status_body(self, body: str) -> bool:
        return "排队中" in (body or "")

    def _clear_queue_body_if_present(self) -> bool:
        if not self._is_queue_status_body(getattr(self, "_agent_body", "")):
            return False
        self._agent_body = ""
        return True

    def _cancel_queue_bootstrap_burst(self) -> None:
        timers = getattr(self, "_queue_bootstrap_timers", None) or []
        for timer in timers:
            timer.cancel()
        self._queue_bootstrap_timers = []

    def set_queue_ahead_provider(self, provider: Any) -> None:
        """注入排队深度查询（周期刷新卡片「前面约 N 个」）。"""
        self._queue_ahead_provider = provider

    def _refresh_queue_body_from_provider(self) -> None:
        provider = getattr(self, "_queue_ahead_provider", None)
        if not callable(provider):
            return
        try:
            ahead = int(provider())
        except Exception as exc:  # noqa: BLE001
            logger.warning("排队深度查询失败: %s", exc)
            return
        if ahead <= 0:
            if self._clear_queue_body_if_present():
                self._render(force=True)
            return
        from progress_message import build_queue_message

        self._agent_body = (
            f"{build_queue_message(ahead, prompt=self._prompt or None)}\n"
            "可发「中断操作」打断。"
        )

    def _schedule_orphan_watchdog(self) -> None:
        """排队卡长期未被 worker 取走 → 失败收尾，避免永远停在「已受理」。"""
        self._cancel_orphan_watchdog()

        def _fire() -> None:
            self._orphan_timer = None
            if not self._started or self._progress_timer is not None:
                return
            logger.warning(
                "排队卡超时未执行 id=%s… prompt=%s，标记失败",
                (self._card_instance_id or "")[:12],
                (self._prompt or "")[:40],
            )
            self.fail("⚠️ 任务未进入执行队列（可能网关重启丢消息），请重新 @ 发送。")

        timer = threading.Timer(QUEUE_ORPHAN_FAIL_S, _fire)
        timer.daemon = True
        self._orphan_timer = timer
        timer.start()

    def _cancel_queue_content_refresh(self) -> None:
        if self._queue_refresh_timer is not None:
            self._queue_refresh_timer.cancel()
            self._queue_refresh_timer = None

    def _schedule_queue_bootstrap_burst(self) -> None:
        """排队卡 create 后短间隔连推，避免单聊长期停在模板「已受理」。"""
        self._cancel_queue_bootstrap_burst()

        def _schedule(delay: float) -> None:
            def _fire() -> None:
                if not self._started or self._progress_timer is not None:
                    return
                self._refresh_queue_body_from_provider()
                self._render(force=True)

            timer = threading.Timer(delay, _fire)
            timer.daemon = True
            self._queue_bootstrap_timers.append(timer)
            timer.start()

        for delay in QUEUE_BOOTSTRAP_PUSH_DELAYS_S:
            _schedule(delay)

    def _schedule_render_only_bootstrap_burst(self) -> None:
        """首条执行卡：仅连推渲染，不注入排队文案。"""
        self._cancel_queue_bootstrap_burst()

        def _schedule(delay: float) -> None:
            def _fire() -> None:
                if not self._started:
                    return
                self._render(force=True)

            timer = threading.Timer(delay, _fire)
            timer.daemon = True
            self._queue_bootstrap_timers.append(timer)
            timer.start()

        for delay in QUEUE_BOOTSTRAP_PUSH_DELAYS_S:
            _schedule(delay)

    def _schedule_queue_content_refresh(self) -> None:
        """排队等待期间周期 push（单聊 Markdown 卡 create 后只 put 一次常会一直显示「已受理」）。"""
        self._cancel_queue_content_refresh()
        self._cancel_orphan_watchdog()

        def _fire() -> None:
            self._queue_refresh_timer = None
            if not self._started or self._progress_timer is not None:
                return
            self._refresh_queue_body_from_provider()
            self._render(force=True)
            self._schedule_queue_content_refresh()

        timer = threading.Timer(QUEUE_CONTENT_REFRESH_S, _fire)
        timer.daemon = True
        self._queue_refresh_timer = timer
        timer.start()

    def mark_worker_picked_up(self) -> None:
        """Worker 已取到任务：排队/受理态立即切到执行进度，避免连发卡在「已受理」。"""
        self._ensure_stream_state()
        if not self._started:
            return
        self._cancel_queue_content_refresh()
        self._cancel_queue_bootstrap_burst()
        self._cancel_orphan_watchdog()
        had_queue_body = self._clear_queue_body_if_present()
        if self._progress_timer is not None:
            if had_queue_body:
                self._render(force=True)
            return
        self._started_at = time.monotonic()
        self._last_content_at = self._started_at
        self._status_line = self._format_progress_markdown()
        self._schedule_progress_tick()
        self._render(force=True)

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
        conversation_id: str = "",
        user_key: str = "",
        prompt: str = "",
    ) -> None:
        self._ensure_stream_state()
        if self._started:
            logger.warning(
                "忽略重复 start（避免第二张 Markdown 卡）id=%s…",
                (self._card_instance_id or "")[:12],
            )
            return
        self._header = (header or "").strip()
        self._persistent_header = (persistent_header or "").strip()
        self._card_title = (card_title or "").strip()
        self._conversation_id = (conversation_id or "").strip()
        self._user_key = (user_key or "").strip()
        self._prompt = (prompt or "").strip()
        self._estimate_seconds = estimate_seconds
        text = (markdown or "").strip()
        if text and not self._is_progress_status_body(text):
            self._agent_body = text
        else:
            self._status_line = text
        body_md = self._compose_body()
        if self._md_card is not None:
            self._create_markdown_card(body_md)
        else:
            assert self._ai_card is not None
            self._ai_card_bootstrap(body_md)
        if not self._card_instance_id:
            raise RuntimeError("流式卡片创建失败（card_instance_id 为空）")
        if self._card_sync_degraded:
            raise RuntimeError("流式卡片首次同步失败（钉钉可能仍显示已受理）")
        self._started = True
        self._started_at = time.monotonic()
        self._last_content_at = self._started_at
        if start_progress:
            self._status_line = self._format_progress_markdown()
            self._schedule_progress_tick()
            self._render(force=True)
            # 首条也 burst：reply 后钉钉常停在「已受理」，须连推几次（不刷新排队文案）
            self._schedule_render_only_bootstrap_burst()
        else:
            # 排队卡：create 内虽已 put 一次，单聊仍常显示「已受理」，须立刻再推 + 短 burst
            self._render(force=True)
            self._schedule_queue_bootstrap_burst()
            self._schedule_queue_content_refresh()
            self._schedule_orphan_watchdog()
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
        self._cancel_queue_content_refresh()
        self._cancel_queue_bootstrap_burst()
        self._cancel_orphan_watchdog()
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

    def _enqueue(self, body_md: str, *, force: bool = False) -> bool:
        with self._lock:
            self._pending = body_md
            now = time.monotonic()
            elapsed = now - self._last_push_at
            if force or elapsed >= self._min_interval_s:
                return self._flush_locked(force=force)
            if self._timer is not None:
                return False
            delay = max(0.05, self._min_interval_s - elapsed)

            def _fire() -> None:
                with self._lock:
                    self._timer = None
                    self._flush_locked(force=False)

            timer = threading.Timer(delay, _fire)
            timer.daemon = True
            self._timer = timer
            timer.start()
            return False

    def _flush_locked(self, *, force: bool = False) -> bool:
        self._ensure_stream_state()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._pending is None:
            return False
        body_md = self._compose_body()
        if body_md == self._last_flushed_body and not force:
            self._pending = None
            return False
        try:
            if self._md_card is not None:
                if not self._put_markdown_body(body_md):
                    return False
            else:
                assert self._ai_card is not None
                self._ai_card.markdown = body_md
                self._ai_card.ai_streaming(body_md, append=False)
                if not self._last_put_succeeded:
                    return False
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
            self._last_put_succeeded = False
            return False
        self._pending = None
        return True

    def abort_orphan_reply(self, message: str) -> None:
        """reply 已发出但 start 未完成时，尽量把「已受理」改为失败提示（避免 orphan 队列）。"""
        if self._started or not self._card_instance_id:
            return
        body = message if message.startswith("❌") else f"❌ {message}"
        try:
            if self._md_card is not None:
                self._put_markdown_body(body)
            logger.info(
                "已尝试收尾 orphan 已受理卡 id=%s…",
                self._card_instance_id[:12],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("orphan 已受理卡收尾失败 id=%s…: %s", self._card_instance_id[:12], exc)

    def finish(self, markdown: str, *, keep_agent_body: bool = False) -> bool:
        self._ensure_stream_state()
        if not self._started:
            return False
        self._stop_progress_tick()
        self._cancel_queue_content_refresh()
        self._cancel_queue_bootstrap_burst()
        self._cancel_orphan_watchdog()
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
        sync_ok = False
        try:
            if self._md_card is not None:
                if self._card_title:
                    self._md_card.set_title_and_logo(self._card_title, "")
                self._md_card.update(final_body_md)
                sync_ok = self._last_put_succeeded
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
                sync_ok = self._last_put_succeeded
            if sync_ok:
                logger.info(
                    "卡片 finish 成功 mode=%s pushes=%d len=%d",
                    self._mode,
                    self._push_count,
                    len(final_body_md),
                )
            else:
                logger.warning(
                    "卡片 finish 未同步到钉钉 mode=%s pushes=%d len=%d degraded=%s",
                    self._mode,
                    self._push_count,
                    len(final_body_md),
                    self._card_sync_degraded,
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("卡片 finish 失败 mode=%s: %s", self._mode, exc)
            sync_ok = False
        finally:
            self._started = False
        return sync_ok

    def finish_status(self, status_line: str) -> bool:
        """卡片收尾为终态提示（提问留标题区，正文仅完成提示；结果另发新消息）。"""
        return self.finish(status_line, keep_agent_body=True)

    def fail(self, markdown: str) -> bool:
        body = markdown if markdown.startswith("❌") else f"❌ {markdown}"
        return self.finish(body)
