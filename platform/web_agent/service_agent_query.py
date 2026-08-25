#!/usr/bin/env python3
"""查询 Yaahlan 服务 Agent（Open API），供工具 Agent 在 settings 启用后调用。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    report_external_agent_multi_querying,
    report_external_agent_querying,
    resolve_user_key,
)
from service_agent_task_store import (  # noqa: E402
    ServiceAgentTaskRecord,
    get_task,
    list_active_tasks,
    list_tasks,
    register_task,
    update_task,
)
from service_agent_run_log import append_service_agent_exchange  # noqa: E402
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
DEFAULT_TIMEOUT_S = 600


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
) -> tuple[str, str | None]:
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
    conv_id = str(data.get("conversation_id") or "").strip() or None
    return task_id, conv_id


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
    user_key: str | None = None,
    conversation_id: str | None = None,
    audience_role: str = "tech",
    task_type: str = "business_analysis",
    runtime: str = "cursor_cli",
    target_environment: str = DEFAULT_TARGET_ENVIRONMENT,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    request_id: str | None = None,
    use_webhook: bool | None = None,
    callback_url: str | None = None,
) -> tuple[str, str | None]:
    env = resolve_target_environment(target_environment)
    conv_id = (conversation_id or "").strip() or None
    outbound_message = (message or "").strip()
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
        task_id, submit_conv_id = _submit_task(
            base_url,
            token=token,
            message=outbound_message,
            request_id=req_id,
            conversation_id=conv_id,
            audience_role=audience_role,
            task_type=task_type,
            runtime=runtime,
            target_environment=env,
            timeout_s=min(60, timeout_s),
            callback_url=webhook_url if webhook_on else None,
        )
    except RuntimeError as exc:
        if webhook_on and "INVALID_CALLBACK_URL" in str(exc):
            task_id, submit_conv_id = _submit_task(
                base_url,
                token=token,
                message=outbound_message,
                request_id=req_id,
                conversation_id=conv_id,
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
    if submit_conv_id:
        conv_id = submit_conv_id
    if webhook_on:
        answer, result_conv_id = _wait_webhook_then_query(
            base_url,
            token=token,
            task_id=task_id,
            timeout_s=timeout_s,
        )
    else:
        answer, result_conv_id = _poll_task_result(
            base_url,
            token=token,
            task_id=task_id,
            timeout_s=timeout_s,
        )
    return answer, result_conv_id or conv_id


def _sync_tasks_progress(user_key: str) -> None:
    """按在途 task 刷新 Web 进度条（支持并行）。"""
    active = list_active_tasks(user_key)
    if not active:
        return
    started = min(item.submitted_at or item.updated_at or time.time() for item in active)
    report_external_agent_multi_querying(
        user_key,
        agent_label=AGENT_LABEL,
        details=[item.message_preview or item.task_id for item in active],
        started_at=started,
    )


def submit_service_agent_async(
    message: str,
    *,
    token: str,
    base_url: str = DEFAULT_BASE_URL,
    user_key: str,
    conversation_id: str | None = None,
    audience_role: str = "tech",
    task_type: str = "business_analysis",
    runtime: str = "cursor_cli",
    target_environment: str = DEFAULT_TARGET_ENVIRONMENT,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    request_id: str | None = None,
    use_webhook: bool | None = None,
    callback_url: str | None = None,
) -> tuple[str, str | None]:
    """提交任务后立即返回 task_id，后台进程轮询终态。"""
    env = resolve_target_environment(target_environment)
    conv_id = (conversation_id or "").strip() or None
    outbound_message = (message or "").strip()
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
        task_id, submit_conv_id = _submit_task(
            base_url,
            token=token,
            message=outbound_message,
            request_id=req_id,
            conversation_id=conv_id,
            audience_role=audience_role,
            task_type=task_type,
            runtime=runtime,
            target_environment=env,
            timeout_s=min(60, timeout_s),
            callback_url=webhook_url if webhook_on else None,
        )
    except RuntimeError as exc:
        if webhook_on and "INVALID_CALLBACK_URL" in str(exc):
            task_id, submit_conv_id = _submit_task(
                base_url,
                token=token,
                message=outbound_message,
                request_id=req_id,
                conversation_id=conv_id,
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
    if submit_conv_id:
        conv_id = submit_conv_id
    register_task(
        user_key,
        task_id=task_id,
        agent_id=AGENT_ID,
        agent_label=AGENT_LABEL,
        message=message.strip(),
        conversation_id=conv_id or "",
    )
    _sync_tasks_progress(user_key)
    _spawn_background_poller(
        task_id=task_id,
        user_key=user_key,
        token=token,
        base_url=base_url,
        timeout_s=timeout_s,
        use_webhook=webhook_on,
        target_environment=env,
        message=message,
    )
    return task_id, conv_id


def _spawn_background_poller(
    *,
    task_id: str,
    user_key: str,
    token: str,
    base_url: str,
    timeout_s: int,
    use_webhook: bool,
    target_environment: str = DEFAULT_TARGET_ENVIRONMENT,
    message: str = "",
) -> None:
    script = str(Path(__file__).resolve())
    cmd = [
        sys.executable,
        script,
        "--poll-background",
        "--task-id",
        task_id,
        "--user-key",
        user_key,
        "--base-url",
        base_url,
        "--timeout",
        str(max(10, int(timeout_s))),
        "--target-environment",
        resolve_target_environment(target_environment),
    ]
    question = (message or "").strip()
    if question:
        cmd.extend(["--message", question])
    if use_webhook:
        cmd.append("--use-webhook")
    else:
        cmd.append("--no-webhook")
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def poll_task_background(
    *,
    task_id: str,
    user_key: str,
    token: str,
    base_url: str,
    timeout_s: int,
    use_webhook: bool | None = None,
    target_environment: str = DEFAULT_TARGET_ENVIRONMENT,
    message: str = "",
) -> int:
    """后台轮询单 task 至终态并落库。"""
    key = (user_key or "").strip()
    tid = (task_id or "").strip()
    with run_child_guard(key):
        update_task(key, tid, status="running")
        _sync_tasks_progress(key)
        try:
            if use_webhook:
                answer, conv_id = _wait_webhook_then_query(
                    base_url,
                    token=token,
                    task_id=tid,
                    timeout_s=timeout_s,
                )
            else:
                answer, conv_id = _poll_task_result(
                    base_url,
                    token=token,
                    task_id=tid,
                    timeout_s=timeout_s,
                )
        except RuntimeError as exc:
            record = get_task(key, tid)
            question = message or (record.message_preview if record else tid)
            update_task(key, tid, status="failed", error=str(exc))
            append_service_agent_exchange(
                key,
                question=question,
                error=str(exc),
                agent_label=AGENT_LABEL,
            )
            if not list_active_tasks(key):
                report_external_agent_error(
                    key,
                    agent_id=AGENT_ID,
                    agent_label=AGENT_LABEL,
                    error=str(exc),
                )
            else:
                _sync_tasks_progress(key)
            return 1
        update_task(
            key,
            tid,
            status="completed",
            result=answer,
            conversation_id=conv_id or "",
        )
        record = get_task(key, tid)
        append_service_agent_exchange(
            key,
            question=message or (record.message_preview if record else ""),
            answer=answer,
            agent_label=AGENT_LABEL,
        )
        if list_active_tasks(key):
            _sync_tasks_progress(key)
        else:
            clear_external_agent_progress(key)
    return 0


def wait_service_agent_task(
    *,
    user_key: str,
    task_id: str,
    timeout_s: int = 0,
) -> ServiceAgentTaskRecord:
    tid = (task_id or "").strip()
    deadline = time.monotonic() + max(0, timeout_s) if timeout_s > 0 else None
    while True:
        record = get_task(user_key, tid)
        if record is None:
            raise RuntimeError(f"未找到 task `{tid}`")
        if record.status in TERMINAL_STATUSES:
            if record.status == "completed":
                if not record.result:
                    raise RuntimeError(f"任务 `{tid}` 已完成但 result 为空")
                return record
            err = record.error or f"任务 `{tid}` 状态={record.status}"
            raise RuntimeError(err)
        if deadline is not None and time.monotonic() >= deadline:
            raise RuntimeError(f"等待 task `{tid}` 超时（{timeout_s}s），当前状态={record.status}")
        time.sleep(1.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="查询 Yaahlan 服务 Agent（Open API）")
    parser.add_argument("--message", default=None, help="提问内容")
    parser.add_argument("--user-key", default=None, help="Web Agent batch_key（默认读 WEB_AGENT_BATCH_KEY）")
    parser.add_argument("--conversation-id", default=None, help="续聊 conversation_id（须显式传入）")
    parser.add_argument("--task-id", default=None, help="异步 task_id（配合 --wait 取结果）")
    parser.add_argument(
        "--async",
        dest="async_submit",
        action="store_true",
        help="仅 submit，后台轮询；可并行开启多个 task",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="等待 --task-id 终态（读本地 task store，非阻塞轮询由后台进程负责）",
    )
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="列出当前 user_key 下全部异步 task",
    )
    parser.add_argument(
        "--poll-background",
        action="store_true",
        help=argparse.SUPPRESS,
    )
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
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_S,
        help=f"超时秒数（含轮询/Webhook 等待，默认 {DEFAULT_TIMEOUT_S}）",
    )
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
    parser.add_argument("--json", action="store_true", help="输出 JSON（含 conversation_id / task_id）")
    args = parser.parse_args()

    token = resolve_token(args.token)
    base_url = resolve_base_url(args.base_url or args.api_url)
    target_environment = resolve_target_environment(args.target_environment)
    user_key = resolve_user_key(args.user_key)

    use_webhook: bool | None = None
    if args.use_webhook:
        use_webhook = True
    elif args.no_webhook:
        use_webhook = False

    if args.poll_background:
        if not args.task_id or not user_key:
            raise SystemExit("--poll-background 需要 --task-id 与 user_key")
        return poll_task_background(
            task_id=args.task_id.strip(),
            user_key=user_key,
            token=token,
            base_url=base_url,
            timeout_s=max(10, int(args.timeout)),
            use_webhook=use_webhook,
            target_environment=target_environment,
            message=(args.message or "").strip(),
        )

    if args.list_tasks:
        rows = list_tasks(user_key) if user_key else []
        payload = [item.as_dict() for item in rows]
        if args.json:
            print(json.dumps({"tasks": payload}, ensure_ascii=False))
        else:
            for item in rows:
                print(f"{item.task_id}\t{item.status}\t{item.message_preview}")
        return 0

    if args.task_id:
        if not user_key:
            raise SystemExit("--task-id 需要 user_key（Web Agent 会自动注入 WEB_AGENT_BATCH_KEY）")
        if args.wait:
            record = wait_service_agent_task(
                user_key=user_key,
                task_id=args.task_id.strip(),
                timeout_s=max(0, int(args.timeout)),
            )
        else:
            record = get_task(user_key, args.task_id.strip())
            if record is None:
                raise SystemExit(f"未找到 task `{args.task_id}`")
        if args.json:
            print(json.dumps(record.as_dict(), ensure_ascii=False))
        elif record.status == "completed":
            print(record.result)
            if record.conversation_id:
                print(f"\n[conversation_id={record.conversation_id}]", file=sys.stderr)
        else:
            print(json.dumps(record.as_dict(), ensure_ascii=False))
        return 0

    message = (args.message or "").strip()
    if not message:
        raise SystemExit("需要 --message，或使用 --task-id / --list-tasks")

    if args.async_submit:
        if not user_key:
            raise SystemExit("--async 需要 user_key（Web Agent 会自动注入 WEB_AGENT_BATCH_KEY）")
        task_id, conv_id = submit_service_agent_async(
            message,
            token=token,
            base_url=base_url,
            user_key=user_key,
            conversation_id=args.conversation_id,
            target_environment=target_environment,
            timeout_s=max(10, int(args.timeout)),
            use_webhook=use_webhook,
            callback_url=args.callback_url,
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "task_id": task_id,
                        "status": "pending",
                        "conversation_id": conv_id,
                        "target_environment": target_environment,
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"task_id={task_id}")
        return 0

    with run_child_guard(user_key):
        if user_key:
            report_external_agent_querying(
                user_key,
                agent_id=AGENT_ID,
                agent_label=AGENT_LABEL,
                message=message,
            )
        try:
            answer, conv_id = query_service_agent(
                message,
                token=token,
                base_url=base_url,
                user_key=user_key,
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
                append_service_agent_exchange(
                    user_key,
                    question=message,
                    error=str(exc),
                    agent_label=AGENT_LABEL,
                )
            raise
        else:
            if user_key:
                clear_external_agent_progress(user_key)
                append_service_agent_exchange(
                    user_key,
                    question=message,
                    answer=answer,
                    agent_label=AGENT_LABEL,
                )
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
