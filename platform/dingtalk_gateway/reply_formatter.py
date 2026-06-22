"""将脚本/Agent 原始输出转为钉钉群自然语言消息。"""

from __future__ import annotations

import json
import re

from natural_language import (
    naturalize_agent_reply,
    naturalize_catalog,
    naturalize_doctor,
    naturalize_export,
    naturalize_moa_check,
    naturalize_report,
    naturalize_vip_failure,
    naturalize_vip_success,
)

VIP_UPGRADE_RE = re.compile(
    r"^(?:用户\s*)?(\d{5,})\s*(?:升级|升到|升级到)\s*VIP?\s*(\d+)\s*$",
    re.I,
)
EXPORT_FILE_RE = re.compile(
    r"^(?:导出|export)\s+(.+\.(?:csv|json|md))\s*$",
    re.I,
)
ENV_CHECK_RE = re.compile(r"^(?:环境检查|检查环境|doctor)\s*$", re.I)
REPORT_VERSION_RE = re.compile(
    r"^(?:生成\s*)?(?:v)?(\d+\.\d+\.\d+)\s*版本\s*(?:生成\s*)?测试报告\s*$",
    re.I,
)
REPORT_URL_RE = re.compile(
    r"^(?:生成\s*)?测试报告\s+(https://alidocs\.dingtalk\.com/\S+)\s*$",
    re.I,
)
CATALOG_OPEN_RE = re.compile(
    r"^(?:打开|刷新|生成)?\s*"
    r"(?:工具平台|工具工作台|工具台|输入工作台|智能工具平台|平台目录|能力目录|工作台|catalog)"
    r"\s*(?:html|HTML)?\s*$",
    re.I,
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
    return text[: max_chars - 24] + "\n\n…（部分内容已截断）"


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
) -> str:
    text = (raw or "").strip()
    if not text:
        return "⚠️ 任务已完成，但没有返回可展示的内容。"

    if text.startswith("**Yaahlan 智能工具"):
        return _truncate(text)

    if text.startswith("✅ MOA") or text.startswith("❌ MOA"):
        ok = text.startswith("✅")
        detail = text.split("，", 1)[-1].strip() if "，" in text else text[2:].strip()
        return _truncate(naturalize_moa_check(ok, detail))

    normalized_prompt = (prompt or "").strip()

    if ENV_CHECK_RE.match(normalized_prompt):
        return _truncate(naturalize_doctor(text))

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

    return _format_agent_reply(text)


def format_exception(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if _is_html_blob(message) or "返回不是合法 JSON" in message:
        return _moa_auth_expired_message()
    if "connection refused" in message.lower() or "bridge request failed" in message.lower():
        return (
            "❌ 任务执行失败。"
            "原因是 Cursor Agent 桥接进程暂时不可用，可能刚被中断任务影响。"
            "网关会自动重试；若仍失败，请执行 ./gateway_ctl.sh restart 后再 @机器人。"
        )
    business_error = _parse_moa_business_error(message)
    if business_error:
        return f"❌ 任务执行失败，{business_error}。"
    return _truncate(f"❌ 任务执行失败。原因：{message}")
