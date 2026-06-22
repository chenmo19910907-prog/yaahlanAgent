"""Cursor SDK 单次 Agent 调用封装（无人值守 + MCP + 仓库规则）。"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions, SDKImage, UserMessage
from cursor_sdk.errors import NetworkError

from bridge_manager import is_bridge_connection_error, reset_sdk_bridge

from env_loader import GATEWAY_DIR, load_env_local, require_env
from gateway_prompt import build_gateway_prompt
from mcp_config import build_stdio_mcp_servers, inject_scripts_path
from task_session import TaskInterrupted, TaskSession

REPO_ROOT = GATEWAY_DIR.parent.parent
EXECUTOR_CONFIG = GATEWAY_DIR / "config" / "executor.local.json"
DEFAULT_MODEL = "composer-2.5"
DEFAULT_TIMEOUT_S = 600
DINGTALK_MAX_REPLY_CHARS = 4000


def repo_cwd() -> str:
    load_env_local()
    if EXECUTOR_CONFIG.is_file():
        data = json.loads(EXECUTOR_CONFIG.read_text(encoding="utf-8"))
        root = data.get("repo_root")
        if isinstance(root, str) and root.strip():
            return root.strip()
    return str(REPO_ROOT)


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
    if use_gateway_rules:
        full_prompt = build_gateway_prompt(
            text,
            image_count=len(paths),
            links=link_list or None,
        )
    else:
        full_prompt = text

    mcp_servers = build_stdio_mcp_servers() if enable_mcp else None

    local_opts = LocalAgentOptions(
        cwd=workdir,
        setting_sources=["all"],
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

    agent = None
    interrupted = False
    result = None
    last_error: Exception | None = None

    for attempt in range(2):
        agent = None
        try:
            agent = Agent.create(
                AgentOptions(
                    api_key=api_key,
                    model=model,
                    local=local_opts,
                    mcp_servers=mcp_servers or None,
                ),
            )
            run = agent.send(message)
            if session:
                session.register_run(agent, run)
                session.check_cancelled()
            result = run.wait()
            last_error = None
            break
        except TaskInterrupted:
            interrupted = True
            raise
        except (CursorAgentError, NetworkError) as exc:
            last_error = exc
            if attempt == 0 and is_bridge_connection_error(exc):
                reset_sdk_bridge()
                continue
            raise RuntimeError(f"Agent 启动失败: {exc.message if hasattr(exc, 'message') else exc}") from exc
        finally:
            skip_close = interrupted or (session is not None and session.cancel_requested())
            if agent is not None and not skip_close:
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
    return truncate_for_dingtalk(output)


def truncate_for_dingtalk(text: str, max_chars: int = DINGTALK_MAX_REPLY_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n\n…（已截断，完整结果见执行机日志）"


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
