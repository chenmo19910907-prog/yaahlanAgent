"""将脚本/Agent 原始输出转为钉钉群可读的「结论 + 具体问题」。"""

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


def _is_html_blob(text: str) -> bool:
    lower = text.lower()
    return "<!doctype html>" in lower or "<html" in lower or "Aegis SSO" in text


def _looks_raw_dump(text: str) -> bool:
    stripped = text.strip()
    if _is_html_blob(stripped):
        return True
    if "返回不是合法 JSON" in stripped:
        return True
    if stripped.startswith("{") and len(stripped) > 280:
        return True
    if "HTTP Request:" in stripped or "请求信息:" in stripped:
        return True
    return False


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


def _moa_vip_success(raw: str, user_id: str, level: str) -> bool:
    if '"ec": 0' in raw or '"ec": 200' in raw or '"ec":0' in raw:
        return True
    try:
        obj = json.loads(raw.strip())
        if isinstance(obj, dict):
            ec = obj.get("ec")
            if ec in (0, 200, "0", "200"):
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

    if "缺少 Cookie" in raw or "MOA_COOKIE" in raw and "缺少" in raw:
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

    if not raw.strip() or raw.strip() == "exit=0":
        return f"✅ {action} 成功"

    if _moa_vip_success(raw, user_id, level):
        return f"✅ {action} 成功"

    fail = EXEC_FAIL_RE.search(raw)
    detail = fail.group(1).strip() if fail else raw.strip()[:200]
    if _is_html_blob(detail):
        return _moa_auth_expired_message().replace("执行失败", f"{action} 失败", 1)
    return f"❌ {action} 失败\n原因：{detail[:300]}"


def _format_doctor(raw: str) -> str:
    fails: list[str] = []
    warns: list[str] = []
    oks = 0
    for line in raw.splitlines():
        match = DOCTOR_LINE_RE.match(line)
        if not match:
            continue
        status, detail = match.group(1), match.group(2).strip()
        if status == "FAIL":
            fails.append(detail)
        elif status == "WARN":
            warns.append(detail)
        else:
            oks += 1

    if fails:
        lines = ["❌ 环境检查未通过", "问题："]
        lines.extend(f"- {item}" for item in fails[:6])
        if warns:
            lines.append("提示：")
            lines.extend(f"- {item}" for item in warns[:4])
        lines.append(f"（其余 {oks} 项正常）")
        return "\n".join(lines)

    if warns:
        return "⚠️ 环境检查通过，但有提示\n" + "\n".join(f"- {w}" for w in warns[:6])
    return f"✅ 环境检查通过（{oks} 项正常）"


def _format_export(raw: str, prompt: str) -> str:
    match = EXPORT_FILE_RE.match(prompt.strip())
    if not match:
        return ""
    rel = match.group(1).strip()
    if "文件不存在" in raw:
        return f"❌ 导出失败\n问题：文件不存在\n路径：{rel}"
    if "https://alidocs.dingtalk.com" in raw:
        url = re.search(r"https://alidocs\.dingtalk\.com/\S+", raw)
        link = url.group(0) if url else raw.strip()
        return f"✅ 已导出 {rel}\n链接：{link}"
    if "失败" in raw or "FAIL" in raw or "error" in raw.lower():
        return f"❌ 导出 {rel} 失败\n原因：{raw.strip()[:300]}"
    return f"✅ 已导出 {rel}\n{raw.strip()[:200]}"


def _summarize_agent_reply(raw: str) -> str:
    text = raw.strip()
    if not text:
        return "⚠️ Agent 未返回内容"

    if _looks_raw_dump(text):
        if _is_html_blob(text) or "返回不是合法 JSON" in text:
            return _moa_auth_expired_message()
        business_error = _parse_moa_business_error(text)
        if business_error:
            return f"❌ 执行失败\n原因：{business_error}"

    for marker in ("## 结论", "**结论**", "结论：", "总结：", "### 结论"):
        idx = text.find(marker)
        if idx >= 0:
            section = text[idx:].split("\n\n", 1)[0]
            section = re.sub(r"^#+\s*", "", section)
            section = section.replace("**", "").strip()
            if len(section) > 20:
                return section[:1200]

    if len(text) <= 900 and not _looks_raw_dump(text):
        return text

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    picked: list[str] = []
    for line in lines:
        if line.startswith("```"):
            continue
        if line.startswith("请求信息:") or line.startswith("HTTP Request:"):
            continue
        if line.startswith("{") and line.endswith("}"):
            continue
        picked.append(line)
        if len("\n".join(picked)) > 700 or len(picked) >= 8:
            break
    if picked:
        body = "\n".join(picked)
        return body[:1200] + ("\n…（详细日志见执行机）" if len(text) > len(body) else "")

    return text[:800] + "\n…（已截断，详细见执行机日志）"


def format_group_reply(
    raw: str,
    *,
    prompt: str = "",
    source: str = "agent",
) -> str:
    """把原始执行输出整理成群消息。"""
    text = (raw or "").strip()
    if not text:
        return "⚠️ 执行完成，但没有可展示的结果"

    if text.startswith("**Yaahlan 智能工具") or text.startswith("✅ MOA") or text.startswith("❌ MOA"):
        return text[:3800]

    normalized_prompt = (prompt or "").strip()

    if ENV_CHECK_RE.match(normalized_prompt):
        return _format_doctor(text)

    export_msg = _format_export(text, normalized_prompt)
    if export_msg:
        return export_msg

    vip_msg = _format_vip_upgrade(text, normalized_prompt)
    if vip_msg:
        return vip_msg

    if source == "agent":
        return _summarize_agent_reply(text)

    if _looks_raw_dump(text):
        if _is_html_blob(text):
            return _moa_auth_expired_message()
        business_error = _parse_moa_business_error(text)
        if business_error:
            return f"❌ 执行失败\n原因：{business_error}"
        fail = EXEC_FAIL_RE.search(text)
        if fail:
            return f"❌ 执行失败\n原因：{fail.group(1).strip()[:400]}"

    return _summarize_agent_reply(text)


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
    if len(message) > 500:
        message = message[:500] + "…"
    return f"❌ 执行失败\n原因：{message}"
