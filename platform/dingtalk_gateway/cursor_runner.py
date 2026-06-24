"""Cursor SDK 单次 Agent 调用封装（无人值守 + MCP + 仓库规则）。"""

from __future__ import annotations

import concurrent.futures
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions, SDKImage, UserMessage
from cursor_sdk.errors import NetworkError

from bridge_manager import is_transient_sdk_error, reset_sdk_bridge
from user_agent_pool import get_user_agent_pool

from env_loader import GATEWAY_DIR, load_env_local, require_env
from gateway_prompt import batch_progress_instruction, build_gateway_prompt
from mcp_config import build_stdio_mcp_servers, inject_scripts_path
from task_session import TaskInterrupted, TaskSession, safe_cancel_run

REPO_ROOT = GATEWAY_DIR.parent.parent
EXECUTOR_CONFIG = GATEWAY_DIR / "config" / "executor.local.json"
DEFAULT_MODEL = "composer-2.5"
DEFAULT_TIMEOUT_S = 600
DINGTALK_MAX_REPLY_CHARS = 3800


def repo_cwd() -> str:
    load_env_local()
    if EXECUTOR_CONFIG.is_file():
        data = json.loads(EXECUTOR_CONFIG.read_text(encoding="utf-8"))
        root = data.get("repo_root")
        if isinstance(root, str) and root.strip():
            return root.strip()
    return str(REPO_ROOT)


def _build_prompt_text(
    text: str,
    *,
    image_count: int,
    links: list[str],
    use_gateway_rules: bool,
    is_new_session: bool,
    allow_code_modify: bool = True,
    batch_progress_key: str = "",
) -> str:
    link_list = [str(link).strip() for link in links if str(link).strip()]
    if use_gateway_rules and is_new_session:
        return build_gateway_prompt(
            text,
            image_count=image_count,
            links=link_list or None,
            allow_code_modify=allow_code_modify,
            batch_progress_key=batch_progress_key,
        )
    if use_gateway_rules:
        extras: list[str] = []
        if not allow_code_modify:
            extras.append(
                "【只读模式】当前用户无代码修改权限：禁止改动仓库源代码与网关逻辑；"
                "仅允许查询脚本、导出与 temporary_testcase/ 用例写入。"
            )
        batch_note = batch_progress_instruction(batch_progress_key)
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
            body = "\n\n".join([body, *extras]) if body else "\n\n".join(extras)
        return f"用户消息（钉钉群 @，延续当前 Agent 对话）：\n{body}"
    return text


def _wait_run(run, *, timeout_s: float, session: TaskSession | None):
    """带超时与中断检查的 run.wait()；中断时不阻塞等待 run 自然结束。"""
    if timeout_s <= 0:
        return run.wait()

    deadline = time.monotonic() + timeout_s
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = pool.submit(run.wait)
    try:
        while True:
            if session:
                session.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
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
    keep_agent_open = False
    is_new_session = not use_pool
    active_run = None

    for attempt in range(2):
        agent = None
        keep_agent_open = False
        active_run = None
        try:
            if use_pool and pool is not None:
                agent, is_new_session = pool.acquire(
                    user_key,
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
                agent = Agent.create(
                    AgentOptions(
                        api_key=api_key,
                        model=model,
                        local=local_opts,
                        mcp_servers=mcp_servers or None,
                    ),
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
            result = _wait_run(run, timeout_s=float(timeout_s), session=session)
            last_error = None
            break
        except TaskInterrupted:
            interrupted = True
            keep_agent_open = False
            safe_cancel_run(active_run)
            if use_pool and pool is not None and user_key:
                pool.invalidate(user_key)
            raise
        except (CursorAgentError, NetworkError) as exc:
            last_error = exc
            safe_cancel_run(active_run)
            if use_pool and pool is not None and user_key:
                pool.invalidate(user_key)
                keep_agent_open = False
            if attempt == 0 and is_transient_sdk_error(exc):
                reset_sdk_bridge()
                continue
            raise RuntimeError(f"Agent 启动失败: {exc.message if hasattr(exc, 'message') else exc}") from exc
        finally:
            should_close = agent is not None and (interrupted or not keep_agent_open)
            if should_close:
                safe_cancel_run(active_run)
                try:
                    agent.close()
                except Exception:  # noqa: BLE001
                    pass

    if last_error is not None:
        raise RuntimeError(
            f"Agent 启动失败: {last_error.message if hasattr(last_error, 'message') else last_error}"
        ) from last_error

    if result is None:
        raise RuntimeError("Agent 未返回结果")

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


def truncate_for_dingtalk(text: str, max_chars: int = DINGTALK_MAX_REPLY_CHARS) -> str:
    from export_delivery import _truncate_inline

    return _truncate_inline(text, max_chars)


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
