"""把结构化执行结果整理为钉钉群可读的自然语言。"""

from __future__ import annotations

import json
import re
from typing import Any

DOCTOR_LINE_RE = re.compile(r"^\s*\[(OK|FAIL|WARN|SKIP)\]\s+(.+)$", re.M)
KV_BULLET_RE = re.compile(r"^[-*]\s*(?:[\w.\[\]]+\s*)?(\w+)\s*=\s*(.+?)\s*$")

_INTERESTING_KEYS = frozenset({
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
    "remainingToNextLevel",
    "nextLevelThreshold",
})


def flatten_json_fields(raw: str) -> dict[str, Any]:
    stripped = (raw or "").strip()
    if not stripped:
        return {}
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return {}

    found: dict[str, Any] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    walk(value)
                elif key in _INTERESTING_KEYS and value is not None:
                    found[key] = value
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return found


def naturalize_vip_success(user_id: str, level: str, raw: str) -> str:
    fields = flatten_json_fields(raw)
    sentences = [f"✅ 用户 {user_id} 已成功升级到 VIP{level}。"]

    if fields.get("value") is not None:
        sentences.append(f"当前 VIP 经验值为 {fields['value']}。")

    actual_level = fields.get("trueLevel") or fields.get("level") or fields.get("vipLevel")
    if actual_level is not None:
        sentences.append(f"当前账号等级为 VIP{actual_level}。")

    if fields.get("tryLevel") is not None:
        sentences.append(f"体验卡等级为 VIP{fields['tryLevel']}。")

    if fields.get("remainingToNextLevel") is not None:
        sentences.append(f"距离下一级还差 {fields['remainingToNextLevel']} 经验。")

    if fields.get("nextLevelThreshold") is not None:
        sentences.append(f"下一级门槛经验为 {fields['nextLevelThreshold']}。")

    if len(sentences) == 1 and raw.strip() and not raw.strip().startswith("{"):
        sentences.append(raw.strip()[:300])

    return "\n".join(sentences)


def naturalize_vip_failure(user_id: str, level: str, reason: str) -> str:
    reason = reason.strip()
    if reason.startswith("业务错误"):
        return f"❌ 用户 {user_id} 升级到 VIP{level} 未成功，{reason}。"
    return f"❌ 用户 {user_id} 升级到 VIP{level} 未成功。原因：{reason}"


_CREDENTIAL_PROBE_NAMES = (
    "钉钉文档 Cookie",
    "钉钉 Excel Aegis",
    "MOA Cookie",
    "Admin Token",
    "Tunnel Cookie",
    "钉钉开放平台",
)


def _split_probe_name(detail: str) -> tuple[str, str]:
    if ": " in detail:
        name, msg = detail.split(": ", 1)
        return name.strip(), msg.strip()
    return detail.strip(), ""


def _credential_status_label(status: str, msg: str) -> str:
    if status == "SKIP":
        return "未配置"
    if status == "FAIL":
        return msg or "无效"
    if status == "WARN":
        return msg or "异常"
    return msg or "有效"


def naturalize_doctor(raw: str) -> str:
    parsed: dict[str, tuple[str, str]] = {}
    other_oks: list[str] = []
    other_fails: list[str] = []
    other_warns: list[str] = []

    for line in raw.splitlines():
        match = DOCTOR_LINE_RE.match(line)
        if not match:
            continue
        status, detail = match.group(1), match.group(2).strip()
        name, msg = _split_probe_name(detail)
        if name in _CREDENTIAL_PROBE_NAMES:
            parsed[name] = (status, msg)
            continue
        if status == "FAIL":
            other_fails.append(detail)
        elif status == "WARN":
            other_warns.append(detail)
        elif status != "SKIP":
            other_oks.append(detail)

    cred_lines: list[str] = []
    cred_fails = 0
    for name in _CREDENTIAL_PROBE_NAMES:
        if name not in parsed:
            continue
        status, msg = parsed[name]
        label = _credential_status_label(status, msg)
        if status == "FAIL":
            cred_fails += 1
            cred_lines.append(f"• {name}：❌ {label}")
        elif status == "WARN":
            cred_lines.append(f"• {name}：⚠️ {label}")
        elif status == "SKIP":
            cred_lines.append(f"• {name}：— {label}")
        else:
            cred_lines.append(f"• {name}：✅ {label}")

    if not cred_lines and not other_oks and not other_fails and not other_warns:
        return raw

    parts: list[str] = []
    has_cred = bool(cred_lines)
    all_fail = cred_fails > 0 or bool(other_fails)

    if all_fail:
        parts.append("❌ 环境检查未通过。")
    else:
        parts.append("✅ 环境检查已通过。")

    if has_cred:
        parts.append("【凭证有效性】")
        parts.extend(cred_lines)

    if other_fails:
        parts.append("以下配置项异常：" + "；".join(other_fails) + "。")
    if other_warns:
        parts.append("以下配置项需注意：" + "；".join(other_warns) + "。")
    if other_oks:
        shown = "；".join(other_oks[:8])
        suffix = " 等。" if len(other_oks) > 8 else "。"
        parts.append("【本地配置】" + shown + suffix)

    return "\n".join(parts)


def naturalize_export(rel: str, raw: str, url: str | None) -> str:
    del rel
    if url:
        return url.strip()
    extra = raw.strip()
    if extra:
        return f"导出失败：{extra[:200]}"
    return "导出失败，未能生成在线表格链接。"


def naturalize_moa_check(ok: bool, detail: str) -> str:
    detail = detail.strip()
    if ok:
        return f"✅ MOA 测试环境可用。{detail}" if detail else "✅ MOA 测试环境可用，Cookie 有效。"
    if "Cookie" in detail or "登录" in detail:
        return (
            f"❌ MOA 当前不可用：{detail}。"
            "请登录 https://mse.wemomo.com 后更新 MOA/.env.local 中的 MOA_COOKIE。"
        )
    return f"❌ MOA 当前不可用：{detail}"


def _table_to_sentences(table_lines: list[str]) -> list[str]:
    if len(table_lines) < 2:
        return []
    header = [c.strip() for c in table_lines[0].strip("|").split("|")]
    rows: list[str] = []
    for line in table_lines[2:]:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        pairs = [f"{header[i]}为{cells[i]}" for i in range(len(header)) if cells[i]]
        if pairs:
            rows.append("第" + str(len(rows) + 1) + "条：" + "，".join(pairs) + "。")
    return rows


def naturalize_agent_reply(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped

    if stripped.startswith("|") and "|" in stripped:
        lines = stripped.splitlines()
        table_lines = [ln for ln in lines if ln.strip().startswith("|")]
        prose_lines = [ln for ln in lines if not ln.strip().startswith("|") and ln.strip()]
        row_sentences = _table_to_sentences(table_lines)
        if row_sentences and len(row_sentences) <= 8:
            intro = "\n".join(prose_lines).strip()
            body = "\n".join(row_sentences)
            if intro:
                return f"{intro}\n\n{body}"
            return "查询结果如下：\n" + body

    if "接口返回：" in stripped:
        stripped = stripped.split("接口返回：", 1)[0].strip()

    converted: list[str] = []
    for line in stripped.splitlines():
        match = KV_BULLET_RE.match(line.strip())
        if match:
            key, value = match.group(1), match.group(2)
            label = _field_label(key)
            converted.append(f"{label}为 {value}。")
            continue
        if line.strip().startswith("[OK]") or line.strip().startswith("[FAIL]"):
            continue
        converted.append(line)

    if converted:
        return "\n".join(converted).strip()
    return stripped


def _field_label(key: str) -> str:
    mapping = {
        "userId": "用户 ID",
        "level": "等级",
        "trueLevel": "真实等级",
        "vipLevel": "VIP 等级",
        "value": "经验值",
        "currentExp": "当前经验",
        "roomId": "房间 ID",
        "phone": "手机号",
        "momoid": "用户 momoid",
        "onlineStatus": "在线状态",
        "nick": "昵称",
        "nickname": "昵称",
    }
    return mapping.get(key, key)


REPORT_OK_RE = re.compile(
    r"^\[OK\]\s*(?P<version>\d+\.\d+\.\d+)\s*版本测试报告已生成",
    re.M,
)


def naturalize_report(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("[OK]"):
        if text.startswith("[FAIL]"):
            detail = text.replace("[FAIL]", "", 1).strip()
            return f"❌ 测试报告生成失败。{detail}"
        return text

    version_match = REPORT_OK_RE.search(text)
    version = version_match.group("version") if version_match else ""

    lines = [
        f"✅ {version or '该'} 版本测试报告已生成，HTML 报告已作为 zip 附件发送到本群。"
        "请下载解压后用浏览器打开内网/外网 HTML 文件。",
    ]

    summary_start = False
    summary_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("本次版本共"):
            summary_start = True
        if summary_start:
            summary_lines.append(line)

    if summary_lines:
        lines.append("")
        lines.extend(summary_lines[:12])

    return "\n".join(lines)


CATALOG_OK_RE = re.compile(
    r"^\[OK\]\s*工具平台离线版已生成",
    re.M,
)


def naturalize_catalog(raw: str) -> str:
    text = (raw or "").strip()
    if not text.startswith("[OK]"):
        if text.startswith("[FAIL]"):
            detail = text.replace("[FAIL]", "", 1).strip()
            return f"❌ 工具平台导出失败。{detail}"
        return text

    lines = [
        "✅ 工具平台复制按钮版已生成，zip 附件已发到本群。",
        "请下载解压后用浏览器打开；提示语为「复制」按钮，粘贴到 Cursor 即可使用。",
        "执行机本地如需「执行」按钮版，请运行 python3 platform/open_catalog.py。",
    ]

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("共 ") and "一级模块" in stripped:
            lines.append(stripped)
            break

    extra: list[str] = []
    for line in text.splitlines():
        if "离线版提示语" in line or "粘贴到 Cursor" in line:
            extra.append(line.strip())
    if extra:
        lines.append("")
        lines.extend(extra[:2])

    return "\n".join(lines)
