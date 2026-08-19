#!/usr/bin/env python3
"""查询 Yaahlan 服务 Agent（Open API），供工具 Agent 在 settings 启用后调用。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
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
from service_agent_webhook import (  # noqa: E402
    cleanup_task_wait,
    peek_webhook_notification,
    register_pending_task,
    resolve_callback_url,
    webhook_mode_enabled,
)

DEFAULT_BASE_URL = "https://ai-yaahlan.wemomo.com"
BASE_URL_ENV_KEYS = ("YAAHLAN_SERVICE_AGENT_BASE_URL", "SERVICE_AGENT_BASE_URL")
TOKEN_ENV_KEYS = ("YAAHLAN_SERVICE_AGENT_TOKEN", "SERVICE_AGENT_TOKEN")
TARGET_ENV_ENV_KEYS = ("YAAHLAN_SERVICE_AGENT_TARGET_ENV", "SERVICE_AGENT_TARGET_ENV")
VALID_TARGET_ENVIRONMENTS = frozenset({"prod", "stage"})
DEFAULT_TARGET_ENVIRONMENT = "stage"
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
AGENT_ID = "yaahlan_service"
AGENT_LABEL = "服务端 Agent"


def resolve_base_url(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        url = explicit.strip().rstrip("/")
        for suffix in ("/api/chat/stream", "/api/open/v1"):
            if url.endswith(suffix):
                url = url[: -len(suffix)].rstrip("/")
        return url
    load_env_local()
    for key in BASE_URL_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value.rstrip("/")
    return DEFAULT_BASE_URL


def resolve_target_environment(explicit: str | None = None) -> str:
    if explicit is not None:
        value = explicit.strip().lower()
        if not value:
            return DEFAULT_TARGET_ENVIRONMENT
        if value not in VALID_TARGET_ENVIRONMENTS:
            allowed = ", ".join(sorted(VALID_TARGET_ENVIRONMENTS))
            raise SystemExit(f"无效 target_environment={explicit!r}，允许值：{allowed}")
        return value
    load_env_local()
    for key in TARGET_ENV_ENV_KEYS:
        value = os.environ.get(key, "").strip().lower()
        if value:
            if value not in VALID_TARGET_ENVIRONMENTS:
                allowed = ", ".join(sorted(VALID_TARGET_ENVIRONMENTS))
                raise SystemExit(f"环境变量 {key}={value!r} 无效，允许值：{allowed}")
            return value
    return DEFAULT_TARGET_ENVIRONMENT


def resolve_token(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    load_env_local()
    for key in TOKEN_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise SystemExit(
        "未配置服务 Agent Open API Token。请在 platform/dingtalk_gateway/.env.local 设置 "
        "YAAHLAN_SERVICE_AGENT_TOKEN=yaahlan_ai_...（向管理员申请，文档见 "
        "https://ai-yaahlan.wemomo.com/open-api）"
    )


def _open_api_request(
    base_url: str,
    path: str,
    *,
    token: str,
    body: dict | None = None,
    request_id: str | None = None,
    timeout_s: int = 60,
) -> dict:
    payload = json.dumps(body or {}, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if request_id:
        headers["X-Task-Request-Id"] = request_id
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"服务 Agent HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"服务 Agent 请求失败: {exc.reason}") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"服务 Agent 返回非 JSON: {raw[:300]}") from exc
    if not isinstance(envelope, dict):
        raise RuntimeError(f"服务 Agent 返回格式异常: {raw[:300]}")
    code = str(envelope.get("code") or "").strip()
    if code and code != "OK":
        message = str(envelope.get("message") or envelope)
        raise RuntimeError(f"服务 Agent 错误 {code}: {message}")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"服务 Agent 缺少 data 字段: {raw[:300]}")
    return data


def _submit_task(
    base_url: str,
    *,
    token: str,
    message: str,
    request_id: str,
    conversation_id: str | None,
    audience_role: str,
    task_type: str,
    runtime: str,
    target_environment: str,
    timeout_s: int,
    callback_url: str | None = None,
) -> str:
    body = {
        "message": message,
        "audience_role": audience_role,
        "task_type": task_type,
        "runtime": runtime,
        "target_environment": target_environment,
        "conversation_id": conversation_id or "",
    }
    if callback_url:
        body["callback_url"] = callback_url
    data = _open_api_request(
        base_url,
        "/api/open/v1/task/submit",
        token=token,
        body=body,
        request_id=request_id,
        timeout_s=timeout_s,
    )
    task_id = str(data.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError(f"服务 Agent submit 未返回 task_id: {data}")
    return task_id


def _parse_task_query_data(task_id: str, data: dict) -> tuple[str, str | None]:
    status = str(data.get("status") or "").strip()
    if status == "completed":
        result = str(data.get("result") or "").strip()
        if not result:
            raise RuntimeError(f"服务 Agent 任务 `{task_id}` 已完成但 result 为空")
        conv_id = str(data.get("conversation_id") or "").strip() or None
        return result, conv_id
    if status == "failed":
        error = str(data.get("error_message") or data.get("error_code") or "未知错误").strip()
        raise RuntimeError(f"服务 Agent 任务 `{task_id}` 失败: {error}")
    if status == "cancelled":
        error = str(data.get("error_message") or "任务已取消").strip()
        raise RuntimeError(f"服务 Agent 任务 `{task_id}` 已取消: {error}")
    if status in TERMINAL_STATUSES:
        raise RuntimeError(f"服务 Agent 任务 `{task_id}` 终态异常: {status}")
    raise RuntimeError(f"服务 Agent 任务 `{task_id}` 尚未终态: {status or 'unknown'}")


def _fetch_task_result(
    base_url: str,
    *,
    token: str,
    task_id: str,
    timeout_s: int = 30,
) -> tuple[str, str | None]:
    data = _open_api_request(
        base_url,
        "/api/open/v1/task/query",
        token=token,
        body={"task_id": task_id},
        timeout_s=timeout_s,
    )
    return _parse_task_query_data(task_id, data)


def _poll_task_result(
    base_url: str,
    *,
    token: str,
    task_id: str,
    timeout_s: int,
) -> tuple[str, str | None]:
    deadline = time.monotonic() + max(10, timeout_s)
    poll_interval_s = 2.0
    last_status = ""
    while time.monotonic() < deadline:
        data = _open_api_request(
            base_url,
            "/api/open/v1/task/query",
            token=token,
            body={"task_id": task_id},
            timeout_s=30,
        )
        status = str(data.get("status") or "").strip()
        last_status = status or last_status
        if status in TERMINAL_STATUSES:
            return _parse_task_query_data(task_id, data)
        time.sleep(poll_interval_s)
        poll_interval_s = min(poll_interval_s * 1.5, 30.0)

    raise RuntimeError(
        f"服务 Agent 任务 `{task_id}` 超时（{timeout_s}s），最后状态={last_status or 'unknown'}"
    )


def _wait_webhook_then_query(
    base_url: str,
    *,
    token: str,
    task_id: str,
    timeout_s: int,
) -> tuple[str, str | None]:
    register_pending_task(task_id)
    try:
        deadline = time.monotonic() + max(10, timeout_s)
        poll_interval_s = 2.0
        last_status = ""
        while time.monotonic() < deadline:
            notified_status = peek_webhook_notification(task_id)
            if notified_status is not None:
                return _fetch_task_result(base_url, token=token, task_id=task_id)

            data = _open_api_request(
                base_url,
                "/api/open/v1/task/query",
                token=token,
                body={"task_id": task_id},
                timeout_s=30,
            )
            status = str(data.get("status") or "").strip()
            last_status = status or last_status
            if status in TERMINAL_STATUSES:
                return _parse_task_query_data(task_id, data)

            time.sleep(poll_interval_s)
            poll_interval_s = min(poll_interval_s * 1.5, 30.0)

        raise RuntimeError(
            f"服务 Agent 任务 `{task_id}` 超时（{timeout_s}s），最后状态={last_status or 'unknown'}"
        )
    finally:
        cleanup_task_wait(task_id)


def query_service_agent(
    message: str,
    *,
    token: str,
    base_url: str = DEFAULT_BASE_URL,
    conversation_id: str | None = None,
    audience_role: str = "tech",
    task_type: str = "business_analysis",
    runtime: str = "custom",
    target_environment: str = DEFAULT_TARGET_ENVIRONMENT,
    timeout_s: int = 120,
    request_id: str | None = None,
    use_webhook: bool | None = None,
    callback_url: str | None = None,
) -> tuple[str, str | None]:
    env = resolve_target_environment(target_environment)
    req_id = (request_id or str(uuid.uuid4())).strip()
    if token.startswith("eyJ"):
        raise RuntimeError(
            "YAAHLAN_SERVICE_AGENT_TOKEN 为 Web JWT，Open API 需 yaahlan_ai_... Token；"
            "见 https://ai-yaahlan.wemomo.com/open-api"
        )
    webhook_url = resolve_callback_url(callback_url)
    webhook_on = webhook_mode_enabled(callback_url=webhook_url, explicit=use_webhook)
    if use_webhook and not webhook_url:
        raise RuntimeError(
            "已启用 Webhook 但 callback_url 不可达。"
            "请配置 YAAHLAN_SERVICE_AGENT_WEBHOOK_URL 或运行 expose_public.py 更新公网地址。"
        )
    try:
        task_id = _submit_task(
            base_url,
            token=token,
            message=message,
            request_id=req_id,
            conversation_id=conversation_id,
            audience_role=audience_role,
            task_type=task_type,
            runtime=runtime,
            target_environment=env,
            timeout_s=min(60, timeout_s),
            callback_url=webhook_url if webhook_on else None,
        )
    except RuntimeError as exc:
        if webhook_on and "INVALID_CALLBACK_URL" in str(exc):
            task_id = _submit_task(
                base_url,
                token=token,
                message=message,
                request_id=req_id,
                conversation_id=conversation_id,
                audience_role=audience_role,
                task_type=task_type,
                runtime=runtime,
                target_environment=env,
                timeout_s=min(60, timeout_s),
                callback_url=None,
            )
            webhook_on = False
        else:
            raise
    if webhook_on:
        answer, conv_id = _wait_webhook_then_query(
            base_url,
            token=token,
            task_id=task_id,
            timeout_s=timeout_s,
        )
    else:
        answer, conv_id = _poll_task_result(
            base_url,
            token=token,
            task_id=task_id,
            timeout_s=timeout_s,
        )
    return answer, conv_id or conversation_id


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 Yaahlan 服务 Agent（Open API）")
    parser.add_argument("--message", required=True, help="提问内容")
    parser.add_argument("--user-key", default=None, help="Web Agent batch_key（默认读 WEB_AGENT_BATCH_KEY）")
    parser.add_argument("--conversation-id", default=None, help="续聊 conversation_id")
    parser.add_argument("--token", default=None, help="Open API Token yaahlan_ai_...（默认读 .env.local）")
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"服务 Agent 根地址（默认 {DEFAULT_BASE_URL}）",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="已废弃，等同 --base-url（兼容旧参数）",
    )
    parser.add_argument(
        "--target-environment",
        "--target-env",
        default=None,
        help=f"代码环境 prod/stage（默认 {DEFAULT_TARGET_ENVIRONMENT}；可设 YAAHLAN_SERVICE_AGENT_TARGET_ENV）",
    )
    parser.add_argument("--timeout", type=int, default=120, help="超时秒数（含轮询/Webhook 等待）")
    parser.add_argument(
        "--use-webhook",
        action="store_true",
        help="强制走 Webhook（须配置 Secret + 回调 URL）",
    )
    parser.add_argument(
        "--no-webhook",
        action="store_true",
        help="禁用 Webhook，仅轮询 query",
    )
    parser.add_argument(
        "--callback-url",
        default=None,
        help="Webhook 回调地址（默认读 YAAHLAN_SERVICE_AGENT_WEBHOOK_URL 或 data/public_url.txt）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（含 conversation_id）")
    args = parser.parse_args()

    token = resolve_token(args.token)
    base_url = resolve_base_url(args.base_url or args.api_url)
    target_environment = resolve_target_environment(args.target_environment)
    user_key = resolve_user_key(args.user_key)
    with run_child_guard(user_key):
        if user_key:
            report_external_agent_querying(
                user_key,
                agent_id=AGENT_ID,
                agent_label=AGENT_LABEL,
                message=args.message.strip(),
            )
        use_webhook: bool | None = None
        if args.use_webhook:
            use_webhook = True
        elif args.no_webhook:
            use_webhook = False
        try:
            answer, conv_id = query_service_agent(
                args.message.strip(),
                token=token,
                base_url=base_url,
                conversation_id=args.conversation_id,
                target_environment=target_environment,
                timeout_s=max(10, int(args.timeout)),
                use_webhook=use_webhook,
                callback_url=args.callback_url,
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
                {
                    "answer": answer,
                    "conversation_id": conv_id,
                    "target_environment": target_environment,
                },
                ensure_ascii=False,
            )
        )
    else:
        print(answer)
        if conv_id:
            print(f"\n[conversation_id={conv_id}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
