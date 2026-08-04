#!/usr/bin/env python3
"""查询 Yaahlan 服务 Agent（ai-yaahlan.wemomo.com），供工具 Agent 在 settings 启用后调用。"""

from __future__ import annotations

import argparse
import json
import os
import sys
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

DEFAULT_API_URL = "https://ai-yaahlan.wemomo.com/api/chat/stream"
TOKEN_ENV_KEYS = ("YAAHLAN_SERVICE_AGENT_TOKEN", "SERVICE_AGENT_TOKEN")
AGENT_ID = "yaahlan_service"
AGENT_LABEL = "服务端 Agent"


def resolve_token(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    load_env_local()
    for key in TOKEN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise SystemExit(
        "未配置服务 Agent Token。请在 platform/dingtalk_gateway/.env.local 设置 "
        "YAAHLAN_SERVICE_AGENT_TOKEN=<JWT>"
    )


def query_service_agent(
    message: str,
    *,
    token: str,
    api_url: str = DEFAULT_API_URL,
    conversation_id: str | None = None,
    audience_role: str = "tech",
    task_type: str = "business_analysis",
    runtime: str = "custom",
    timeout_s: int = 120,
) -> tuple[str, str | None]:
    body = json.dumps(
        {
            "message": message,
            "audience_role": audience_role,
            "task_type": task_type,
            "runtime": runtime,
            "conversation_id": conversation_id,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    answer_parts: list[str] = []
    conv_id: str | None = conversation_id
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    evt = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                evt_type = evt.get("type")
                if evt_type == "conversation":
                    conv_id = str(evt.get("conversation_id") or conv_id or "") or conv_id
                elif evt_type == "answer_delta":
                    answer_parts.append(str(evt.get("text") or ""))
                elif evt_type == "error":
                    raise RuntimeError(str(evt.get("message") or evt))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"服务 Agent HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"服务 Agent 请求失败: {exc.reason}") from exc
    answer = "".join(answer_parts).strip()
    if not answer:
        raise RuntimeError("服务 Agent 未返回 answer_delta 内容")
    return answer, conv_id


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 Yaahlan 服务 Agent")
    parser.add_argument("--message", required=True, help="提问内容")
    parser.add_argument("--user-key", default=None, help="Web Agent batch_key（默认读 WEB_AGENT_BATCH_KEY）")
    parser.add_argument("--conversation-id", default=None, help="续聊 conversation_id")
    parser.add_argument("--token", default=None, help="Bearer JWT（默认读 .env.local）")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="SSE API 地址")
    parser.add_argument("--timeout", type=int, default=120, help="超时秒数")
    parser.add_argument("--json", action="store_true", help="输出 JSON（含 conversation_id）")
    args = parser.parse_args()

    token = resolve_token(args.token)
    user_key = resolve_user_key(args.user_key)
    if user_key:
        report_external_agent_querying(
            user_key,
            agent_id=AGENT_ID,
            agent_label=AGENT_LABEL,
            message=args.message.strip(),
        )
    try:
        answer, conv_id = query_service_agent(
            args.message.strip(),
            token=token,
            api_url=args.api_url.strip() or DEFAULT_API_URL,
            conversation_id=args.conversation_id,
            timeout_s=max(10, int(args.timeout)),
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
        print(json.dumps({"answer": answer, "conversation_id": conv_id}, ensure_ascii=False))
    else:
        print(answer)
        if conv_id:
            print(f"\n[conversation_id={conv_id}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
