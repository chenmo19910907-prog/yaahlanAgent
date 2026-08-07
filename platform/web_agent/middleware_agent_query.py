#!/usr/bin/env python3
"""查询 MDP Agent（默认 http://172.18.50.12:8080），供 Web Agent 勾选外部 Agent 后调用。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from env_loader import load_env_local  # noqa: E402
from external_agent_progress import (  # noqa: E402
    clear_external_agent_progress,
    report_external_agent_error,
    report_external_agent_querying,
    resolve_user_key,
)
from run_child_processes import run_child_guard  # noqa: E402

DEFAULT_BASE_URL = "http://172.18.50.12:8080"
BASE_URL_ENV_KEYS = ("MIDDLEWARE_AGENT_URL", "MDP_MIDDLEWARE_AGENT_URL")
AGENT_ID = "mdp_middleware"
AGENT_LABEL = "MDP Agent"
TASK_HANDOFF_RE = re.compile(r"_task_handoff:(\{.*?\})_", re.DOTALL)
THINKING_RE = re.compile(r"_thinking:\{.*?\}_\s*", re.DOTALL)


def _clean_reply(text: str) -> str:
    return THINKING_RE.sub("", text or "").strip()


def resolve_base_url(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip().rstrip("/")
    load_env_local()
    for key in BASE_URL_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value.rstrip("/")
    return DEFAULT_BASE_URL


def _parse_ndjson_events(raw: str) -> list[dict]:
    events: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(evt, dict):
            events.append(evt)
    return events


def _extract_task_id(reply: str) -> str | None:
    match = TASK_HANDOFF_RE.search(reply or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    task_id = str(payload.get("task_id") or "").strip()
    return task_id or None


def _poll_task_result(
    base_url: str,
    task_id: str,
    *,
    timeout_s: int,
    poll_interval_s: float = 2.0,
) -> tuple[str, str | None]:
    url = f"{base_url}/agent-tasks/{task_id}"
    deadline = time.monotonic() + max(10, timeout_s)
    last_status = ""
    while time.monotonic() < deadline:
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"MDP Agent 任务查询 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"MDP Agent 任务查询失败: {exc.reason}") from exc

        status = str(data.get("status") or "").strip()
        last_status = status or last_status
        if status == "done":
            result = str(data.get("result") or "").strip()
            if result:
                return result, task_id
            return f"任务 `{task_id}` 已完成，但未返回 result 字段。", task_id
        if status == "failed":
            error = str(data.get("error") or data.get("result") or "未知错误").strip()
            raise RuntimeError(f"MDP Agent 任务失败 `{task_id}`: {error}")
        if status == "awaiting_approval":
            pending = str(data.get("pending_approval") or "").strip()
            hint = pending or "需在MDP Agent Web 界面授权后继续"
            return (
                f"MDP Agent 任务 `{task_id}` 等待人工授权，无法自动完成。\n"
                f"请打开 {base_url} 处理授权后重试。\n"
                f"详情：{hint}",
                task_id,
            )
        time.sleep(poll_interval_s)

    raise RuntimeError(
        f"MDP Agent 任务 `{task_id}` 超时（{timeout_s}s），最后状态={last_status or 'unknown'}"
    )


def _collect_chat_result(events: list[dict], session_id: str | None) -> tuple[str, str | None]:
    reply_parts: list[str] = []
    reply = ""
    conv_id = session_id
    for evt in events:
        evt_type = evt.get("type")
        if evt_type == "reply_delta":
            delta = str(evt.get("delta") or evt.get("text") or "")
            if delta:
                reply_parts.append(delta)
        elif evt_type == "done":
            reply = str(evt.get("reply") or reply)
            conv_id = str(evt.get("session_id") or conv_id or "") or conv_id
        elif not reply and evt.get("reply"):
            reply = str(evt.get("reply"))
        if evt.get("session_id"):
            conv_id = str(evt.get("session_id") or conv_id or "") or conv_id

    if reply_parts and not reply:
        reply = "".join(reply_parts)
    return reply.strip(), conv_id


def query_middleware_agent(
    message: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    session_id: str | None = None,
    poll_task_timeout_s: int = 180,
    chat_timeout_s: int = 120,
) -> tuple[str, str | None, str | None]:
    body = json.dumps(
        {
            "message": message,
            "session_id": session_id,
            "stream": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    chat_url = f"{base_url.rstrip('/')}/chat"
    req = urllib.request.Request(
        chat_url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "*/*"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=max(10, chat_timeout_s)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"MDP Agent HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"MDP Agent 请求失败: {exc.reason}") from exc

    events = _parse_ndjson_events(raw)
    if not events:
        try:
            single = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("MDP Agent 返回内容无法解析") from exc
        events = [single] if isinstance(single, dict) else []

    reply, conv_id = _collect_chat_result(events, session_id)
    if not reply:
        raise RuntimeError("MDP Agent 未返回 reply 内容")

    task_id = _extract_task_id(reply)
    reply = _clean_reply(reply)
    if task_id:
        final, _ = _poll_task_result(
            base_url,
            task_id,
            timeout_s=poll_task_timeout_s,
        )
        return _clean_reply(final.strip()), conv_id, task_id
    return reply, conv_id, None


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 MDP Agent")
    parser.add_argument("--message", required=True, help="提问内容")
    parser.add_argument("--user-key", default=None, help="Web Agent batch_key（默认读 WEB_AGENT_BATCH_KEY）")
    parser.add_argument("--session-id", default=None, help="续聊 session_id")
    parser.add_argument("--base-url", default=None, help="MDP Agent 根地址（默认读 .env.local）")
    parser.add_argument("--poll-timeout", type=int, default=180, help="后台任务轮询超时秒数")
    parser.add_argument("--timeout", type=int, default=120, help="/chat 请求超时秒数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url)
    user_key = resolve_user_key(args.user_key)
    with run_child_guard(user_key):
        if user_key:
            report_external_agent_querying(
                user_key,
                agent_id=AGENT_ID,
                agent_label=AGENT_LABEL,
                message=args.message.strip(),
            )
        try:
            answer, session_id, task_id = query_middleware_agent(
                args.message.strip(),
                base_url=base_url,
                session_id=args.session_id,
                poll_task_timeout_s=max(30, int(args.poll_timeout)),
                chat_timeout_s=max(10, int(args.timeout)),
            )
        except RuntimeError as exc:
            if user_key:
                report_external_agent_error(
                    user_key,
                    agent_id=AGENT_ID,
                    agent_label=AGENT_LABEL,
                    error=str(exc),
                )
            raise
        else:
            if user_key:
                clear_external_agent_progress(user_key)
    if args.json:
        print(
            json.dumps(
                {"answer": answer, "session_id": session_id, "task_id": task_id},
                ensure_ascii=False,
            )
        )
    else:
        print(answer)
        if session_id:
            print(f"\n[session_id={session_id}]", file=sys.stderr)
        if task_id:
            print(f"[task_id={task_id}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
