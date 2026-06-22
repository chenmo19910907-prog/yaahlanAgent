"""把结构化执行结果整理为钉钉群可读的自然语言。"""

from __future__ import annotations

import json
import re
from typing import Any

DOCTOR_LINE_RE = re.compile(r"^\s*\[(OK|FAIL|WARN)\]\s+(.+)$", re.M)
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


def naturalize_doctor(raw: str) -> str:
    oks: list[str] = []
    fails: list[str] = []
    warns: list[str] = []

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
            oks.append(detail)

    if not oks and not fails and not warns:
        return raw

    parts: list[str] = []
    if fails:
        parts.append("❌ 环境检查未通过。")
        parts.append("以下项目异常：" + "；".join(fails) + "。")
    else:
        parts.append("✅ 环境检查已通过。")

    if oks:
        shown = "；".join(oks[:12])
        suffix = " 等。" if len(oks) > 12 else "。"
        parts.append("以下项目正常：" + shown + suffix)

    if warns:
        parts.append("以下项目需注意：" + "；".join(warns) + "。")

    return "\n".join(parts)


def naturalize_export(rel: str, raw: str, url: str | None) -> str:
    if url:
        return f"✅ 已将 {rel} 导出到钉钉文档，点击链接查看：{url}"
    extra = raw.strip()
    if extra:
        return f"✅ 文件 {rel} 已处理完成。{extra[:200]}"
    return f"✅ 文件 {rel} 已处理完成。"


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
