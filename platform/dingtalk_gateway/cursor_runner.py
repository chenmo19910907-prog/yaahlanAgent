"""Cursor SDK 单次 Agent 调用封装（无人值守 + MCP + 仓库规则）。"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions, SDKImage, UserMessage
from cursor_sdk.errors import NetworkError

from agent_stream_renderer import (
    AgentStreamRenderer,
    append_process_summary,
    assistant_text_chunk,
    thinking_text_from_step,
    tool_name_from_step,
)
from bridge_manager import (
    AGENT_RUN_MAX_RETRIES,
    is_retryable_agent_error,
    is_transient_sdk_error,
    reset_sdk_bridge,
)
from user_agent_pool import get_user_agent_pool

from env_loader import GATEWAY_DIR, load_env_local, require_env
from gateway_prompt import batch_progress_instruction, build_gateway_prompt
from code_modify_permission import is_moa_registry_open_to_all
from mcp_config import build_stdio_mcp_servers, inject_scripts_path
from batch_progress import waive_agent_timeout_deadline
from task_session import TaskInterrupted, TaskSession, safe_cancel_run

REPO_ROOT = GATEWAY_DIR.parent.parent
EXECUTOR_CONFIG = GATEWAY_DIR / "config" / "executor.local.json"
DEFAULT_MODEL = "composer-2.5"
DEFAULT_TIMEOUT_S = 600
DINGTALK_MAX_REPLY_CHARS = 3800
logger = logging.getLogger("dingtalk-gateway")


def repo_cwd() -> str:
    load_env_local()
    if EXECUTOR_CONFIG.is_file():
        data = json.loads(EXECUTOR_CONFIG.read_text(encoding="utf-8"))
        root = data.get("repo_root")
        if isinstance(root, str) and root.strip():
            return root.strip()
    return str(REPO_ROOT)


def _should_reset_bridge_for_retry(exc: BaseException) -> bool:
    message = str(exc).lower()
    return is_transient_sdk_error(exc) or "unknown agent" in message


def _format_agent_run_failure(exc: BaseException, *, retries: int) -> str:
    if isinstance(exc, (CursorAgentError, NetworkError)):
        detail = exc.message if hasattr(exc, "message") else exc
        prefix = f"Agent 启动失败: {detail}"
    else:
        prefix = str(exc).strip() or type(exc).__name__
    if retries > 0:
        return f"{prefix}（已自动重试 {retries} 次仍失败）"
    return prefix


def _build_prompt_text(
    text: str,
    *,
    image_count: int,
    links: list[str],
    use_gateway_rules: bool,
    is_new_session: bool,
    allow_code_modify: bool = True,
    allow_moa_registry: bool = False,
    batch_progress_key: str = "",
) -> str:
    link_list = [str(link).strip() for link in links if str(link).strip()]
    if use_gateway_rules and is_new_session:
        return build_gateway_prompt(
            text,
            image_count=image_count,
            links=link_list or None,
            allow_code_modify=allow_code_modify,
            allow_moa_registry=allow_moa_registry,
            batch_progress_key=batch_progress_key,
        )
    if use_gateway_rules:
        extras: list[str] = []
        if not allow_code_modify:
            if allow_moa_registry or is_moa_registry_open_to_all():
                extras.append(
                    "【只读 · 可 MOA 入库】当前用户无网关代码修改权限，但可登记 MOA 能力："
                    "仅允许改动 MOA/templates/、运行 sync_registry.py（自动刷新文档与 catalog）、"
                    "更新 MOA/config/registry.json；禁止改 gateway/.cursor 等。"
                )
            else:
                extras.append(
                    "【只读模式】当前用户无代码修改权限：禁止改动仓库源代码与网关逻辑；"
                    "仅允许查询脚本、导出与 temporary_testcase/ 用例写入。"
                )
        batch_note = batch_progress_instruction(batch_progress_key, compact=True)
        if batch_note:
            extras.append(batch_note)
        if image_count > 0:
            extras.append(
                f"用户附带了 {image_count} 张图片（已随消息传入），请结合附图理解需求并作答。"
            )
        if link_list:
            extras.append("用户消息中的链接：\n" + "\n".join(f"- {url}" for url in link_list))
        body = text.strip()
        if extras:
            ctx = "\n".join(extras)
            ctx_block = f"<!-- 会话上下文\n{ctx}\n-->"
            body = "\n\n".join([body, ctx_block]) if body else ctx_block
        return f"用户消息（钉钉群 @，延续当前 Agent 对话）：\n{body}"
    return text


def _next_agent_deadline(
    deadline: float | None,
    *,
    user_key: str | None,
) -> float | None:
    return waive_agent_timeout_deadline(deadline, user_key)


def _consume_run_stream(
    run,
    *,
    timeout_s: float,
    session: TaskSession | None,
    user_key: str | None = None,
    on_render: Callable[[str], None] | None,
    show_thinking: bool = True,
    card_compact: bool = False,
    web_stream: bool = False,
    render_min_interval_s: float = 2.0,
) -> AgentStreamRenderer:
    """消费 run.events()，节流回调 on_render；结束后 run.wait() 可取终态。"""
    renderer = AgentStreamRenderer(show_thinking=show_thinking)
    deadline = time.monotonic() + timeout_s if timeout_s > 0 else None
    rendered = False
    seen_tool_steps: set[str] = set()
    last_render_at = 0.0

    def _render_markdown() -> str:
        if web_stream:
            return renderer.markdown_for_web()
        if card_compact:
            return renderer.markdown_for_card()
        return renderer.markdown()

    def _maybe_render(*, force: bool = False) -> None:
        nonlocal rendered, last_render_at
        if not on_render:
            return
        md = _render_markdown()
        if card_compact and not web_stream and not md:
            return
        now = time.monotonic()
        # Web 流式：每次增量都下推，避免思考区长时间冻结在首帧。
        if (
            not force
            and not web_stream
            and not card_compact
            and now - last_render_at < render_min_interval_s
        ):
            return
        if web_stream:
            on_render(md, renderer.web_process_payload())
        else:
            on_render(md)
        last_render_at = now
        rendered = True

    if not card_compact:
        renderer.set_status_hint("Agent 已启动…")
    _maybe_render(force=True)

    for event in run.events():
        if session:
            session.check_cancelled()
        deadline = _next_agent_deadline(deadline, user_key=user_key)
        if deadline is not None and time.monotonic() > deadline:
            safe_cancel_run(run)
            raise RuntimeError(
                f"Agent 执行超时（>{int(timeout_s)}s），可发「重新执行」重试"
            )

        changed = False
        force_render = False
        update = event.interaction_update
        if update is not None:
            changed = renderer.apply(update) or changed
            utype = getattr(update, "type", "") if not isinstance(update, Mapping) else str(update.get("type") or "")
            if utype in ("tool-call-started", "tool-call-completed"):
                force_render = True

        sdk_message = event.sdk_message
        if sdk_message is not None:
            msg_type = getattr(sdk_message, "type", "")
            if msg_type == "assistant":
                chunk = assistant_text_chunk(sdk_message)
                if renderer.update_answer(chunk):
                    changed = True
            elif msg_type == "status":
                status = str(getattr(sdk_message, "status", "") or "")
                if status in ("running", "in_progress", "IN_PROGRESS"):
                    if renderer.set_status_hint("Agent 执行中…"):
                        changed = True

        step = event.step
        if step is not None:
            thinking = thinking_text_from_step(step)
            if thinking and renderer.update_thinking(thinking):
                changed = True
            name = tool_name_from_step(step)
            if name:
                key = f"{getattr(step, 'type', '')}:{name}"
                if key not in seen_tool_steps:
                    seen_tool_steps.add(key)
                    if renderer.append_tool_step(name):
                        changed = True
                        force_render = True

        if changed:
            _maybe_render(force=force_render)

        if event.done and event.result is not None and event.result_is_full:
            break

    if on_render and not rendered:
        _maybe_render(force=True)
    return renderer


def _finalize_run_result(result, *, session: TaskSession | None) -> str:
    if session:
        session.check_cancelled()
    if result.status == "cancelled":
        raise TaskInterrupted()
    if result.status == "error":
        detail = getattr(result, "result", None) or getattr(result, "id", "unknown")
        raise RuntimeError(f"Agent 执行失败: {detail}")
    output = (result.result or "").strip()
    if not output:
        raise RuntimeError("Agent 未返回文本结果")
    return output


def _run_cancellable(
    func: Callable[..., Any],
    /,
    *args: Any,
    session: TaskSession | None = None,
    **kwargs: Any,
) -> Any:
    """在子线程执行阻塞调用，主线程轮询 session 中断（如 Agent.create / pool.acquire）。"""
    if session is None:
        return func(*args, **kwargs)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(func, *args, **kwargs)
    try:
        while True:
            session.check_cancelled()
            try:
                return future.result(timeout=0.5)
            except concurrent.futures.TimeoutError:
                continue
    except TaskInterrupted:
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _wait_run(
    run,
    *,
    timeout_s: float,
    session: TaskSession | None,
    user_key: str | None = None,
):
    """带超时与中断检查的 run.wait()；中断时不阻塞等待 run 自然结束。"""
    if timeout_s <= 0:
        return run.wait()

    deadline: float | None = time.monotonic() + timeout_s
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(run.wait)
    try:
        while True:
            if session:
                session.check_cancelled()
            deadline = _next_agent_deadline(deadline, user_key=user_key)
            if deadline is None:
                remaining = 0.5
            else:
                remaining = deadline - time.monotonic()
            if deadline is not None and remaining <= 0:
                try:
                    run.cancel()
                except Exception:  # noqa: BLE001
                    pass
                raise RuntimeError(
                    f"Agent 执行超时（>{int(timeout_s)}s），可发「重新执行」重试"
                )
            try:
                return future.result(timeout=min(0.5, remaining))
            except concurrent.futures.TimeoutError:
                continue
    except TaskInterrupted:
        safe_cancel_run(run)
        raise
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def run_agent_prompt(
    prompt: str,
    *,
    image_paths: Sequence[str | Path] | None = None,
    links: Sequence[str] | None = None,
    cwd: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    model: str = DEFAULT_MODEL,
    use_gateway_rules: bool = True,
    enable_mcp: bool = True,
    session: TaskSession | None = None,
    user_key: str | None = None,
    sender_name: str | None = None,
    allow_code_modify: bool = True,
    allow_moa_registry: bool = False,
    stream: bool = False,
    on_render: Callable[[str], None] | None = None,
    show_thinking: bool = True,
    card_compact: bool = False,
    web_stream: bool = False,
    render_min_interval_s: float = 2.0,
    include_process_in_final: bool = False,
) -> str:
    """运行本地 Agent，返回 assistant 最终文本。支持附图（最多 5 张）与链接上下文。"""
    text = prompt.strip()
    paths = [Path(p) for p in (image_paths or [])]
    if not text and not paths:
        raise ValueError("prompt 与附图不能同时为空")

    inject_scripts_path()
    api_key = require_env("CURSOR_API_KEY")
    workdir = cwd or repo_cwd()
    if not Path(workdir).is_dir():
        raise FileNotFoundError(f"仓库路径不存在: {workdir}")

    link_list = [str(link).strip() for link in (links or []) if str(link).strip()]
    mcp_servers = build_stdio_mcp_servers() if enable_mcp else None
    local_opts = LocalAgentOptions(
        cwd=workdir,
        setting_sources=["all"],
    )
    use_pool = bool(user_key)
    pool = get_user_agent_pool() if use_pool else None

    if session:
        session.check_cancelled()

    agent = None
    interrupted = False
    result = None
    last_error: Exception | None = None
    final_text: str | None = None
    keep_agent_open = False
    is_new_session = not use_pool
    active_run = None
    max_attempts = AGENT_RUN_MAX_RETRIES + 1

    for attempt in range(max_attempts):
        agent = None
        keep_agent_open = False
        active_run = None
        try:
            if use_pool and pool is not None:
                agent, is_new_session = _run_cancellable(
                    pool.acquire,
                    user_key,
                    session=session,
                    api_key=api_key,
                    workdir=workdir,
                    model=model,
                    sender_name=sender_name or "",
                    mcp_servers=mcp_servers,
                )
                keep_agent_open = True
                if session:
                    session.register_agent(agent)
            else:
                agent = _run_cancellable(
                    Agent.create,
                    AgentOptions(
                        api_key=api_key,
                        model=model,
                        local=local_opts,
                        mcp_servers=mcp_servers or None,
                    ),
                    session=session,
                )
                is_new_session = True
                keep_agent_open = False
                if session:
                    session.register_agent(agent)

            full_prompt = _build_prompt_text(
                text,
                image_count=len(paths),
                links=link_list,
                use_gateway_rules=use_gateway_rules,
                is_new_session=is_new_session,
                allow_code_modify=allow_code_modify,
                allow_moa_registry=allow_moa_registry,
                batch_progress_key=user_key or "",
            )

            if paths:
                images = []
                for path in paths[:5]:
                    if not path.is_file():
                        raise FileNotFoundError(f"附图不存在: {path}")
                    images.append(SDKImage.from_file(path))
                message: str | UserMessage = UserMessage(text=full_prompt, images=images)
            else:
                message = full_prompt

            if session:
                session.check_cancelled()

            run = agent.send(message)
            active_run = run
            if session:
                session.register_run(agent, run)
                session.check_cancelled()
            if stream:
                renderer = _consume_run_stream(
                    run,
                    timeout_s=float(timeout_s),
                    session=session,
                    user_key=user_key,
                    on_render=on_render,
                    show_thinking=show_thinking,
                    card_compact=card_compact,
                    web_stream=web_stream,
                    render_min_interval_s=render_min_interval_s,
                )
                result = _wait_run(
                    run,
                    timeout_s=float(timeout_s),
                    session=session,
                    user_key=user_key,
                )
            else:
                renderer = None
                result = _wait_run(
                    run,
                    timeout_s=float(timeout_s),
                    session=session,
                    user_key=user_key,
                )
            final_text = _finalize_run_result(result, session=session)
            if include_process_in_final and renderer is not None:
                process_md = renderer.process_summary_markdown()
                if process_md:
                    final_text = append_process_summary(final_text, process_md)
            last_error = None
            break
        except TaskInterrupted:
            interrupted = True
            keep_agent_open = False
            safe_cancel_run(active_run)
            if use_pool and pool is not None and user_key:
                pool.invalidate(user_key)
            raise
        except Exception as exc:
            last_error = exc
            safe_cancel_run(active_run)
            if use_pool and pool is not None and user_key:
                pool.invalidate(user_key)
                keep_agent_open = False
            retries_left = max_attempts - attempt - 1
            if retries_left > 0 and is_retryable_agent_error(exc):
                if _should_reset_bridge_for_retry(exc):
                    reset_sdk_bridge()
                logger.warning(
                    "Agent 运行失败，自动重试 %s/%s: %s",
                    attempt + 1,
                    AGENT_RUN_MAX_RETRIES,
                    exc,
                )
                time.sleep(min(0.5 * (attempt + 1), 2.0))
                continue
            raise RuntimeError(
                _format_agent_run_failure(exc, retries=AGENT_RUN_MAX_RETRIES if attempt > 0 else 0)
            ) from exc
        finally:
            should_close = agent is not None and (interrupted or not keep_agent_open)
            if should_close:
                safe_cancel_run(active_run)
                try:
                    agent.close()
                except Exception:  # noqa: BLE001
                    pass

    if final_text is not None:
        return final_text

    if last_error is not None:
        raise RuntimeError(
            _format_agent_run_failure(last_error, retries=AGENT_RUN_MAX_RETRIES)
        ) from last_error

    raise RuntimeError("Agent 未返回结果")


def run_agent_prompt_streaming(
    prompt: str,
    *,
    on_render: Callable[[str], None],
    image_paths: Sequence[str | Path] | None = None,
    links: Sequence[str] | None = None,
    cwd: str | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    model: str = DEFAULT_MODEL,
    use_gateway_rules: bool = True,
    enable_mcp: bool = True,
    session: TaskSession | None = None,
    user_key: str | None = None,
    sender_name: str | None = None,
    allow_code_modify: bool = True,
    allow_moa_registry: bool = False,
    show_thinking: bool = True,
    include_process_in_final: bool = False,
    web_stream: bool = False,
) -> str:
    """流式运行 Agent：thinking/text/tool 事件经 on_render 推送，返回最终文本。"""
    from agent_stream_card import DEFAULT_MIN_INTERVAL_S, WEB_STREAM_RENDER_INTERVAL_S

    return run_agent_prompt(
        prompt,
        image_paths=image_paths,
        links=links,
        cwd=cwd,
        timeout_s=timeout_s,
        model=model,
        use_gateway_rules=use_gateway_rules,
        enable_mcp=enable_mcp,
        session=session,
        user_key=user_key,
        sender_name=sender_name,
        allow_code_modify=allow_code_modify,
        allow_moa_registry=allow_moa_registry,
        stream=True,
        on_render=on_render,
        show_thinking=show_thinking,
        card_compact=not web_stream,
        web_stream=web_stream,
        render_min_interval_s=(
            WEB_STREAM_RENDER_INTERVAL_S if web_stream else DEFAULT_MIN_INTERVAL_S
        ),
        include_process_in_final=include_process_in_final,
    )


def truncate_for_dingtalk(text: str, max_chars: int = DINGTALK_MAX_REPLY_CHARS) -> str:
    from export_delivery import _truncate_inline
    from markdown_display import enhance_markdown_list_indent

    body = enhance_markdown_list_indent(text or "")
    return _truncate_inline(body, max_chars)


def main() -> int:
    load_env_local()
    if len(sys.argv) < 2:
        print("用法: python cursor_runner.py '<prompt>'", file=sys.stderr)
        return 2
    prompt = sys.argv[1]
    try:
        print(run_agent_prompt(prompt))
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
