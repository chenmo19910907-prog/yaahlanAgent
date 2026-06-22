"""将脚本/Agent 原始输出转为钉钉群可读消息（结论 + 具体内容）。"""

from __future__ import annotations

import json
import re

VIP_UPGRADE_RE = re.compile(
    r"^(?:用户\s*)?(\d{5,})\s*(?:升级|升到|升级到)\s*VIP?\s*(\d+)\s*$",
    re.I,
)
EXPORT_FILE_RE = re.compile(
    r"^(?:导出|export)\s+(.+\.(?:csv|json|md))\s*$",
    re.I,
)
ENV_CHECK_RE = re.compile(r"^(?:环境检查|检查环境|doctor)\s*$", re.I)

BUSINESS_FAIL_RE = re.compile(r"业务返回失败: ec=(\d+), em=(.+)")
MOA_OUTER_FAIL_RE = re.compile(r"MOA 返回失败: ec=(\d+), em=(.+)")
EXEC_FAIL_RE = re.compile(r"执行失败:\s*(.+)", re.S)
DOCTOR_LINE_RE = re.compile(r"^\s*\[(OK|FAIL|WARN)\]\s+(.+)$", re.M)

DINGTALK_REPLY_MAX_CHARS = 3800
_INTERESTING_JSON_KEYS = frozenset({
    "userId",
    "vipLevel",
    "level",
    "trueLevel",
    "tryLevel",
    "value",
    "currentExp",
    "roomId",
    "phone",
    "momoid",
    "onlineStatus",
    "nick",
    "nickname",
    "result",
    "em",
    "ec",
    "remainingToNextLevel",
    "nextLevelThreshold",
})


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
        "❌ 执行失败\n"
        "问题：MOA 测试环境登录已过期（返回 Aegis 登录页，不是接口 JSON）\n"
        "处理：浏览器登录 https://mse.wemomo.com → 复制 Cookie → 更新 MOA/.env.local 的 MOA_COOKIE → "
        "执行 ./gateway_ctl.sh restart"
    )


def _parse_moa_business_error(raw: str) -> str | None:
    match = BUSINESS_FAIL_RE.search(raw) or MOA_OUTER_FAIL_RE.search(raw)
    if not match:
        return None
    ec, em = match.group(1), match.group(2).strip()
    return f"业务错误 ec={ec}：{em}" if em else f"业务错误 ec={ec}"


def _compact_json_detail(raw: str) -> str:
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        if _looks_raw_dump(stripped):
            return ""
        return stripped[:800]

    lines: list[str] = []

    def walk(node: object, prefix: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                full_key = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, (dict, list)):
                    if key in {"result", "data"} or full_key.count(".") < 2:
                        walk(value, full_key)
                elif value is not None and (
                    key in _INTERESTING_JSON_KEYS or full_key.split(".")[-1] in _INTERESTING_JSON_KEYS
                ):
                    lines.append(f"- {full_key} = {value}")
        elif isinstance(node, list) and node and len(lines) < 20:
            for index, item in enumerate(node[:5]):
                walk(item, f"{prefix}[{index}]")

    walk(obj)
    if lines:
        return "\n".join(lines[:20])
    return json.dumps(obj, ensure_ascii=False, indent=2)[:1000]


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
    action = f"用户 {user_id} 升级到 VIP{level}"

    if "缺少 Cookie" in raw or ("MOA_COOKIE" in raw and "缺少" in raw):
        return (
            f"❌ {action} 失败\n"
            "问题：未配置 MOA Cookie\n"
            "处理：填写 MOA/.env.local 中的 MOA_COOKIE"
        )
    if _is_html_blob(raw) or "返回不是合法 JSON" in raw:
        return _moa_auth_expired_message().replace("执行失败", f"{action} 失败", 1)

    business_error = _parse_moa_business_error(raw)
    if business_error:
        return f"❌ {action} 失败\n原因：{business_error}"

    if not raw.strip() or raw.strip() == "exit=0" or _moa_vip_success(raw):
        lines = [f"✅ {action} 成功"]
        detail = _compact_json_detail(raw)
        if detail:
            lines.extend(["", "接口返回：", detail])
        return _truncate("\n".join(lines))

    fail = EXEC_FAIL_RE.search(raw)
    detail = fail.group(1).strip() if fail else raw.strip()
    if _is_html_blob(detail):
        return _moa_auth_expired_message().replace("执行失败", f"{action} 失败", 1)
    return _truncate(f"❌ {action} 失败\n原因：{detail[:600]}")


def _format_doctor(raw: str) -> str:
    items: list[str] = []
    sections: list[str] = []
    for line in raw.splitlines():
        if line.startswith("==="):
            sections.append(line.strip("= ").strip())
            continue
        match = DOCTOR_LINE_RE.match(line)
        if match:
            items.append(f"[{match.group(1)}] {match.group(2).strip()}")

    if not items:
        return _truncate(raw)

    has_fail = any(item.startswith("[FAIL]") for item in items)
    header = "❌ 环境检查未通过" if has_fail else "✅ 环境检查通过"
    lines = [header, ""]
    if sections:
        lines.append("检查项：")
    lines.extend(items)
    return _truncate("\n".join(lines))


def _format_export(raw: str, prompt: str) -> str:
    match = EXPORT_FILE_RE.match(prompt.strip())
    if not match:
        return ""
    rel = match.group(1).strip()
    if "文件不存在" in raw:
        return f"❌ 导出失败\n问题：文件不存在\n路径：{rel}"
    lines = [f"✅ 已导出：{rel}"]
    url_match = re.search(r"https://alidocs\.dingtalk\.com/\S+", raw)
    if url_match:
        lines.append(f"链接：{url_match.group(0)}")
    extra = raw.strip()
    if extra and url_match:
        extra = extra.replace(url_match.group(0), "").strip()
    if extra:
        lines.extend(["", "详情：", extra[:600]])
    return _truncate("\n".join(lines))


def _clean_agent_reply(raw: str) -> str:
    lines: list[str] = []
    in_code = False
    code_buf: list[str] = []

    def flush_code() -> None:
        nonlocal code_buf
        if not code_buf:
            return
        block = "\n".join(code_buf).strip()
        if block and len(block) <= 600 and not _is_html_blob(block):
            lines.append("```")
            lines.extend(code_buf)
            lines.append("```")
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
        return "⚠️ Agent 未返回内容"

    if _is_html_blob(text) or ("返回不是合法 JSON" in text and _looks_raw_dump(text)):
        return _moa_auth_expired_message()

    business_error = _parse_moa_business_error(text)
    if business_error and _looks_raw_dump(text):
        return f"❌ 执行失败\n原因：{business_error}"

    # 保留完整结构化内容（表格、列表、步骤），不只摘「结论」段
    return _truncate(text)


def format_group_reply(
    raw: str,
    *,
    prompt: str = "",
    source: str = "agent",
) -> str:
    text = (raw or "").strip()
    if not text:
        return "⚠️ 执行完成，但没有可展示的结果"

    if text.startswith("**Yaahlan 智能工具") or text.startswith("✅ MOA") or text.startswith("❌ MOA"):
        return _truncate(text)

    normalized_prompt = (prompt or "").strip()

    if ENV_CHECK_RE.match(normalized_prompt):
        return _format_doctor(text)

    export_msg = _format_export(text, normalized_prompt)
    if export_msg:
        return export_msg

    vip_msg = _format_vip_upgrade(text, normalized_prompt)
    if vip_msg:
        return vip_msg

    if _looks_raw_dump(text) and not text.startswith("|"):
        if _is_html_blob(text):
            return _moa_auth_expired_message()
        business_error = _parse_moa_business_error(text)
        if business_error:
            detail = _compact_json_detail(text)
            body = f"❌ 执行失败\n原因：{business_error}"
            if detail:
                body += f"\n\n接口返回：\n{detail}"
            return _truncate(body)
        fail = EXEC_FAIL_RE.search(text)
        if fail:
            return _truncate(f"❌ 执行失败\n原因：{fail.group(1).strip()[:600]}")
        detail = _compact_json_detail(text)
        if detail:
            return _truncate(f"执行结果：\n{detail}")

    return _format_agent_reply(text)


def format_exception(exc: BaseException) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if _is_html_blob(message) or "返回不是合法 JSON" in message:
        return _moa_auth_expired_message()
    if "connection refused" in message.lower() or "bridge request failed" in message.lower():
        return (
            "❌ 执行失败\n"
            "问题：Cursor Agent 桥接进程未就绪（可能刚被中断任务影响）\n"
            "处理：网关会自动重试；若仍失败，请执行 ./gateway_ctl.sh restart 后再 @机器人"
        )
    business_error = _parse_moa_business_error(message)
    if business_error:
        return f"❌ 执行失败\n原因：{business_error}"
    return _truncate(f"❌ 执行失败\n原因：{message}")
