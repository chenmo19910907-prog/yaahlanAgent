"""将脚本/Agent 原始输出转为钉钉群自然语言消息。"""

from __future__ import annotations

import json
import re

from natural_language import (
    naturalize_agent_reply,
    naturalize_catalog,
    naturalize_export,
    naturalize_moa_check,
    naturalize_report,
    naturalize_vip_failure,
    naturalize_vip_success,
)
from moa_registry_guard import is_explicit_moa_check_command, looks_like_moa_registry_intent
from export_delivery import TRUNCATE_GUIDE
from route_patterns import (
    CATALOG_OPEN_RE,
    EXPORT_FILE_RE,
    REPORT_URL_RE,
    REPORT_VERSION_RE,
    VIP_UPGRADE_RE,
)

BUSINESS_FAIL_RE = re.compile(r"业务返回失败: ec=(\d+), em=(.+)")
MOA_OUTER_FAIL_RE = re.compile(r"MOA 返回失败: ec=(\d+), em=(.+)")
EXEC_FAIL_RE = re.compile(r"执行失败:\s*(.+)", re.S)

DINGTALK_REPLY_MAX_CHARS = 3800


def _is_html_blob(text: str) -> bool:
    lower = text.lower()
    return "<!doctype html>" in lower or "<html" in lower or "Aegis SSO" in text


def _looks_raw_dump(text: str) -> bool:
    stripped = text.strip()
    if _is_html_blob(stripped):
        return True
    if "返回不是合法 JSON" in stripped:
        return True
    if stripped.startswith("{") and len(stripped) > 1200:
        return True
    if "HTTP Request:" in stripped or "请求信息:" in stripped:
        return True
    return False


def _truncate(text: str, max_chars: int = DINGTALK_REPLY_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    budget = max_chars - len(TRUNCATE_GUIDE) - 2
    if budget < 200:
        return text[: max_chars - 24] + "\n\n…（部分内容已截断）"
    return text[:budget].rstrip() + "\n\n" + TRUNCATE_GUIDE


def _moa_auth_expired_message() -> str:
    return (
        "❌ 任务执行失败。"
        "原因是 MOA 测试环境登录已过期，接口返回了登录页而不是业务数据。"
        "请先在浏览器登录 https://mse.wemomo.com ，更新 MOA/.env.local 中的 MOA_COOKIE，"
        "然后执行 ./gateway_ctl.sh restart 后重试。"
    )


def _parse_moa_business_error(raw: str) -> str | None:
    match = BUSINESS_FAIL_RE.search(raw) or MOA_OUTER_FAIL_RE.search(raw)
    if not match:
        return None
    ec, em = match.group(1), match.group(2).strip()
    return f"业务返回 ec={ec}，错误信息为「{em}」" if em else f"业务返回 ec={ec}"


def _moa_vip_success(raw: str) -> bool:
    if '"ec": 0' in raw or '"ec": 200' in raw or '"ec":0' in raw:
        return True
    try:
        obj = json.loads(raw.strip())
        if isinstance(obj, dict) and obj.get("ec") in (0, 200, "0", "200"):
            return True
    except json.JSONDecodeError:
        pass
    return "addVipValue" in raw and "失败" not in raw


def _format_vip_upgrade(raw: str, prompt: str) -> str:
    match = VIP_UPGRADE_RE.match(prompt.strip())
    if not match:
        return ""
    user_id, level = match.group(1), match.group(2)

    if "缺少 Cookie" in raw or ("MOA_COOKIE" in raw and "缺少" in raw):
        return (
            f"❌ 用户 {user_id} 升级到 VIP{level} 未成功。"
            "原因是未配置 MOA Cookie，请在 MOA/.env.local 中补充后重试。"
        )
    if _is_html_blob(raw) or "返回不是合法 JSON" in raw:
        return _moa_auth_expired_message()

    business_error = _parse_moa_business_error(raw)
    if business_error:
        return naturalize_vip_failure(user_id, level, business_error)

    if not raw.strip() or raw.strip() == "exit=0" or _moa_vip_success(raw):
        return naturalize_vip_success(user_id, level, raw)

    fail = EXEC_FAIL_RE.search(raw)
    detail = fail.group(1).strip() if fail else raw.strip()[:600]
    if _is_html_blob(detail):
        return _moa_auth_expired_message()
    return naturalize_vip_failure(user_id, level, detail)


def _format_catalog(raw: str, prompt: str) -> str:
    if not (
        CATALOG_OPEN_RE.match(prompt.strip())
        or raw.strip().startswith("[OK] 工具平台离线版已生成")
    ):
        return ""
    return _truncate(naturalize_catalog(raw))


def _format_report(raw: str, prompt: str) -> str:
    if not (
        REPORT_VERSION_RE.match(prompt.strip())
        or REPORT_URL_RE.match(prompt.strip())
        or raw.strip().startswith("[OK]")
        or raw.strip().startswith("[FAIL]")
    ):
        return ""
    return _truncate(naturalize_report(raw))


def _format_export(raw: str, prompt: str) -> str:
    match = EXPORT_FILE_RE.match(prompt.strip())
    if not match:
        return ""
    rel = match.group(1).strip()
    if "文件不存在" in raw:
        return f"❌ 导出失败，文件不存在：{rel}。"
    url_match = re.search(r"https://alidocs\.dingtalk\.com/\S+", raw)
    url = url_match.group(0) if url_match else None
    return _truncate(naturalize_export(rel, raw, url))


def _preserve_markdown_clean(raw: str) -> str:
    """流式卡片：保留 Markdown 结构，仅剔除调试/脏数据行。"""
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("请求信息:") or "HTTP Request:" in line:
            continue
        if _is_html_blob(line):
            continue
        if stripped.startswith("[OK]") or stripped.startswith("[FAIL]"):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _clean_agent_reply(raw: str) -> str:
    lines: list[str] = []
    in_code = False
    code_buf: list[str] = []

    def flush_code() -> None:
        nonlocal code_buf
        if not code_buf:
            return
        block = "\n".join(code_buf).strip()
        if block and len(block) <= 400 and not _is_html_blob(block):
            lines.append("补充信息：" + block.replace("\n", "；") + "。")
        code_buf = []

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                in_code = False
                flush_code()
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        if stripped.startswith("请求信息:") or "HTTP Request:" in line:
            continue
        if _is_html_blob(line):
            continue
        lines.append(line.rstrip())

    if in_code:
        flush_code()
    return "\n".join(lines).strip()


def _format_agent_reply(raw: str) -> str:
    text = _clean_agent_reply(raw)
    if not text:
        return "⚠️ 任务已完成，但没有返回可展示的内容。"

    if _is_html_blob(text) or ("返回不是合法 JSON" in text and _looks_raw_dump(text)):
        return _moa_auth_expired_message()

    business_error = _parse_moa_business_error(text)
    if business_error and _looks_raw_dump(text):
        return f"❌ 任务执行失败，{business_error}。"

    return _truncate(naturalize_agent_reply(text))


def format_group_reply(
    raw: str,
    *,
    prompt: str = "",
    source: str = "agent",
    preserve_markdown: bool = False,
) -> str:
    text = (raw or "").strip()
    if not text:
        return "⚠️ 任务已完成，但没有返回可展示的内容。"

    if text.startswith("**Yaahlan 智能工具"):
        return _truncate(text)

    if text.startswith("✅ MOA") or text.startswith("❌ MOA"):
        if looks_like_moa_registry_intent(normalized_prompt) and not is_explicit_moa_check_command(
            normalized_prompt
        ):
            return _truncate(
                "⚠️ 本次应完成 MOA 入库，但返回了探活结果。"
                "请重新 @机器人 发送入库需求；网关不会把含「入库」的 MOA 任务当作 MOA检查。"
            )
        ok = text.startswith("✅")
        detail = text.split("，", 1)[-1].strip() if "，" in text else text[2:].strip()
        return _truncate(naturalize_moa_check(ok, detail))

    normalized_prompt = (prompt or "").strip()

    export_msg = _format_export(text, normalized_prompt)
    if export_msg:
        return export_msg

    catalog_msg = _format_catalog(text, normalized_prompt)
    if catalog_msg:
        return catalog_msg

    report_msg = _format_report(text, normalized_prompt)
    if report_msg:
        return report_msg

    vip_msg = _format_vip_upgrade(text, normalized_prompt)
    if vip_msg:
        return vip_msg

    if _looks_raw_dump(text) and not text.startswith("|"):
        if _is_html_blob(text):
            return _moa_auth_expired_message()
        business_error = _parse_moa_business_error(text)
        if business_error:
            return _truncate(f"❌ 任务执行失败，{business_error}。")
        fail = EXEC_FAIL_RE.search(text)
        if fail:
            return _truncate(f"❌ 任务执行失败。原因：{fail.group(1).strip()[:500]}")

    if preserve_markdown:
        cleaned = _preserve_markdown_clean(text)
        if not cleaned:
            return "⚠️ 任务已完成，但没有返回可展示的内容。"
        if _is_html_blob(cleaned) or ("返回不是合法 JSON" in cleaned and _looks_raw_dump(cleaned)):
            return _moa_auth_expired_message()
        business_error = _parse_moa_business_error(cleaned)
        if business_error and _looks_raw_dump(cleaned):
            return _truncate(f"❌ 任务执行失败，{business_error}。")
        return _truncate(cleaned)

    return _format_agent_reply(text)


def format_exception(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lower = message.lower()
    if _is_html_blob(message) or "返回不是合法 JSON" in message:
        return _moa_auth_expired_message()
    if "connection refused" in lower or "bridge request failed" in lower:
        return (
            "❌ 任务执行失败。"
            "原因是 Cursor Agent 桥接进程暂时不可用，可能刚被中断任务影响。"
            "请发「重新执行」重试；仍失败请执行 ./gateway_ctl.sh health 或 restart。"
        )
    if "internal error" in lower or "internal:" in lower:
        return (
            "❌ 任务执行失败，Agent 服务暂不可用。\n"
            "请发「重新执行」重试；仍失败请执行 ./gateway_ctl.sh health 或 restart。"
        )
    if "执行超时" in message or "timeout" in lower:
        return (
            "❌ 任务执行超时（已超过允许时长）。\n"
            "请发「重新执行」重试，或拆成更小的子任务。"
        )
    if "agent 未返回" in lower:
        return "❌ Agent 未返回结果，请发「重新执行」重试。"
    business_error = _parse_moa_business_error(message)
    if business_error:
        return f"❌ 任务执行失败，{business_error}。"
    return _truncate(f"❌ 任务执行失败。原因：{message}")
