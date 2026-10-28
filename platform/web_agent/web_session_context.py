"""Web 会话上下文：过长会话轮换 Cursor Agent，避免 ResumeAgent 卡死在思考阶段。"""

from __future__ import annotations

import re

from web_session_store import ChatMessage, get_session_store

# 超过阈值则新建 Cursor Agent（不再 Resume 整段历史）
ROTATE_MESSAGE_COUNT = 80
ROTATE_MESSAGE_BYTES = 120_000
CONTEXT_SNIPPET_MESSAGES = 8
CONTEXT_SNIPPET_CHARS = 2_400

_PK_HINT_RE = re.compile(
    r"PK提款机|pk[\s-]?atm|跨房\s*PK|来一场.{0,8}PK|pk-atm-test|"
    r"总\s*PK|提款机|pk_atm",
    re.I,
)

_PK_SESSION_RE = re.compile(
    r"pkId|pk_atm_(test|dingtalk)|双方总\s*PK|验收通过.*PK|"
    r"pk_atm_dingtalk_sheet2",
    re.I,
)

_FAMILY_MONSTER_SHEET_RE = re.compile(
    r"怪兽挑战|family.?monster|FamilyMonster|奖池配置",
    re.I,
)

_PROP_BACKPACK_ISSUE_RE = re.compile(
    r"下发.{0,8}道具|道具.{0,8}下发|离线下发|addPropTask|propTaskIssue|"
    r"下发到背包|背包.{0,6}道具",
    re.I,
)

_PROP_BACKPACK_SESSION_RE = re.compile(
    r"addPropTaskV2|propTaskIssueAdmin|Later 工单|auditStatus|"
    r"下发至背包|propPackageValidDays",
    re.I,
)

_REWARD_VERIFY_RE = re.compile(
    r"奖励下发验证|奖励.*验收|发奖前|发奖后|资产快照|展示.*物品|记录.*物品",
    re.I,
)

_REWARD_VERIFY_SESSION_RE = re.compile(
    r"web_reward_verify\.py|full-inventory|奖励下发验证",
    re.I,
)

# 短追问 / 指代型消息：Resume 失败或无轮换摘要时易答非所问
_VAGUE_FOLLOWUP_RE = re.compile(
    r"(这个|那个|上面|前文|刚才|之前|继续|再.{0,16}|"
    r"为什么|能不能|可以吗|能.{0,8}吗|有没有|"
    r"优化一下|搞错|梳理|分析一下|做成工作流|"
    r"详细|再说说|然后呢|接着|一下吧)",
    re.I,
)
_EXPLICIT_TASK_RE = re.compile(
    r"https?://|\d{6,}|online_execute|moa_execute|workflow_execute|"
    r"admin_execute|tunnel_execute|userId|user\s*id|手机号",
    re.I,
)


def session_message_stats(session_id: str) -> tuple[int, int]:
    """返回 (消息条数, 消息 JSON 估算字节)。"""
    sid = (session_id or "").strip()
    if not sid:
        return 0, 0
    store = get_session_store()
    meta = store.get_session(sid)
    if meta is None:
        return 0, 0
    count = int(meta.message_count or 0)
    total_bytes = store.messages_file_size(sid)
    return count, total_bytes


def should_rotate_cursor_agent(session_id: str) -> bool:
    count, total_bytes = session_message_stats(session_id)
    if count >= ROTATE_MESSAGE_COUNT:
        return True
    if count >= 40 and total_bytes >= ROTATE_MESSAGE_BYTES:
        return True
    return False


def _trim_line(text: str, limit: int = 160) -> str:
    line = " ".join((text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + "…"


def build_rotation_context_snippet(session_id: str) -> str:
    """抽取最近若干轮 user/assistant 摘要，供轮换 Agent 后带入 prompt。"""
    messages, _ = get_session_store().get_messages((session_id or "").strip(), tail=CONTEXT_SNIPPET_MESSAGES)
    if not messages:
        return ""
    tail = messages[-CONTEXT_SNIPPET_MESSAGES:]
    lines: list[str] = []
    used = 0
    for msg in tail:
        role = "用户" if msg.role == "user" else "Agent"
        line = f"- {role}：{_trim_line(msg.content)}"
        line_bytes = len(line.encode("utf-8"))
        if used + line_bytes > CONTEXT_SNIPPET_CHARS and lines:
            break
        lines.append(line)
        used += line_bytes
    return "\n".join(lines)


def build_rotation_system_note(session_id: str) -> str:
    """轮换 Agent 时追加到用户消息前的系统说明（Markdown）。"""
    if not should_rotate_cursor_agent(session_id):
        return ""
    snippet = build_rotation_context_snippet(session_id)
    parts = [
        "请**立即调用工具**执行，勿长时间只做规划。",
    ]
    if snippet:
        parts.append("近期上下文摘要：")
        parts.append(snippet)
    return "\n\n".join(parts)


def looks_like_vague_follow_up(text: str) -> bool:
    """是否短追问/指代型消息（须附带近期摘要，避免脱离会话主题）。"""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return False
    if _EXPLICIT_TASK_RE.search(t):
        return False
    if _VAGUE_FOLLOWUP_RE.search(t):
        return True
    return len(t) <= 20


def build_continue_context_note(session_id: str, message: str) -> str:
    """延续会话短追问：未达轮换阈值时也注入近期摘要。"""
    sid = (session_id or "").strip()
    if not sid or not looks_like_vague_follow_up(message):
        return ""
    if should_rotate_cursor_agent(sid):
        return ""
    snippet = build_rotation_context_snippet(sid)
    if not snippet:
        return ""
    return "\n\n".join(
        [
            "【系统】本条为短追问/指代型消息，请结合以下近期对话摘要理解用户意图。",
            "近期上下文摘要：",
            snippet,
        ]
    )


def looks_like_pk_atm_task(text: str) -> bool:
    blob = text or ""
    if _PK_HINT_RE.search(blob):
        return True
    return bool(_PK_SESSION_RE.search(blob))


def session_looks_like_pk_atm(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    messages, _ = get_session_store().get_messages(sid, tail=24)
    for msg in messages[-24:]:
        if looks_like_pk_atm_task(msg.content):
            return True
    return False


def pk_atm_prompt_hint(text: str, *, session_id: str = "") -> str | None:
    if not looks_like_pk_atm_task(text) and not session_looks_like_pk_atm(session_id):
        return None
    return (
        "**PK 提款机**：必须用 `python3 workflow/scripts/pk_atm_dingtalk_sheet2_run.py` "
        "（全流程 + **每轮自动新建钉钉 Sheet「测试结果-*」**），"
        "禁止仅用 `pk_atm_test_run.py` 而不写表；参数见 workflow/workflows/pk-atm-test.json。"
        "验收完成后回复须含 **钉钉在线表格链接**（脚本 stdout 的 workbookUrl + sheetName）。"
        "不要从零长时探索；无发钻场景请设 `--target-combined-pk` 低于 MSE 场次门槛。"
        "给定总 PK / 个人 PK 要求时，须**先算出各用户各房送礼计划**再执行，禁止边送边算。"
        "跨房 PK **随机匹配前**须确认双方账号 **App 已登录且在自己的房间内**"
        "（Admin onlineStatus=1 + Tunnel 近 5 分钟 heartbeat roomId=自己的 roomId）；"
        "未满足时说明需人工真机登录并进房（Web Agent 不支持 ADB），勿直接 MOA 盲匹配。"
        "匹配失败**最多重试 3 轮**（`--match-retries`，脚本硬上限 3），"
        "3 轮均失败则**立即终止任务**（exit 1），勿再手动循环重跑。"
        "自然结束 PK 时加 `--wait-natural-end`；手动结束则 `--closer-phone <记败方手机号>`。"
        "PK 时长走完后进入惩罚阶段（stage≥3）即可验收，不必等 stage=4。"
    )


def session_looks_like_family_monster_workbook(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    messages, _ = get_session_store().get_messages(sid, tail=24)
    for msg in messages[-24:]:
        if _FAMILY_MONSTER_SHEET_RE.search(msg.content or ""):
            return True
    return False


def session_looks_like_prop_backpack_issue(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    messages, _ = get_session_store().get_messages(sid, tail=24)
    for msg in messages[-24:]:
        if _PROP_BACKPACK_ISSUE_RE.search(msg.content or ""):
            return True
        if _PROP_BACKPACK_SESSION_RE.search(msg.content or ""):
            return True
    return False


def session_looks_like_reward_verify(session_id: str) -> bool:
    sid = (session_id or "").strip()
    if not sid:
        return False
    messages, _ = get_session_store().get_messages(sid, tail=24)
    for msg in messages[-24:]:
        if _REWARD_VERIFY_RE.search(msg.content or ""):
            return True
        if _REWARD_VERIFY_SESSION_RE.search(msg.content or ""):
            return True
    return False


def reward_verify_prompt_hint(text: str, *, session_id: str = "") -> str | None:
    blob = text or ""
    if not _REWARD_VERIFY_RE.search(blob) and not session_looks_like_reward_verify(session_id):
        return None
    sid = (session_id or "").strip() or "<session_id>"
    return (
        "**奖励下发验证（Web Agent）**：给用户做发奖前/后验收时，"
        "须用 `python3 platform/web_agent/web_reward_verify.py record "
        f"--session-id {sid} --slot baseline --user-id <userId>`（或 `--phone`）"
        "记录**全量**资产（钻石、金币、礼物背包礼/道具、装扮背包、铭牌、CP 勋章）。"
        "用户要求展示/查看资产时用 `web_reward_verify.py show --session-id "
        f"{sid} --slot baseline`，**仅输出资产概况表**（钻石/金币/背包礼物/装扮/铭牌条数），"
        "不要逐条全量清单。"
        "用户要求导出钉钉表格时用 `web_reward_verify.py export --session-id "
        f"{sid} --slot baseline`：全量明细写入在线表格，回复链接 + JSON 内 overviewMarkdown 概况表。"
        "抽奖/发奖后单轮验收：`web_reward_verify.py round --session-id "
        f"{sid} --user-id <userId>`（或工作流 web-reward-verify-round）；"
        "输出 JSON 含 markdown、diamondHistory（本轮明细）、装扮 incrementDays。"
        "baseline：`record --slot baseline` 或 web-reward-verify-baseline；"
        "导出钉钉：web-reward-verify-export。"
    )


def prop_backpack_issue_prompt_hint(text: str, *, session_id: str = "") -> str | None:
    blob = text or ""
    if not _PROP_BACKPACK_ISSUE_RE.search(blob) and not session_looks_like_prop_backpack_issue(
        session_id
    ):
        return None
    return (
        "**道具离线下发至背包（铁律）**：测试 MDP "
        "`POST …/propTaskIssueAdmin/addPropTaskV2`（`type=1` 下发至背包，"
        "`propPackageValidDays` 为背包有效天数；`useType=20`）。"
        "工单创建成功后**同轮立即**走 Later `custom_831` 审批（"
        "`GET /v3/approve-confirm` → `POST /v3/approve`），"
        "勿等用户再发「直接审批」。"
        "最后用 MOA `礼物面板-查看背包道具`（propPackageList）验收到账。"
    )


def family_monster_workbook_hint(text: str, *, session_id: str = "") -> str | None:
    blob = text or ""
    if not _FAMILY_MONSTER_SHEET_RE.search(blob) and not session_looks_like_family_monster_workbook(
        session_id
    ):
        return None
    return (
        "**家族怪兽挑战钉钉表排版（铁律）**：Sheet「怪兽挑战奖池配置」"
        "仅 **10 列**（奖池ID、奖池名称、序号、奖品类型、数量/区间、奖品ID、"
        "奖品名称、限量(limit)、权重占比、名称/备注）；"
        "**禁止**追加元数据/MSE 映射/同步时间/额外列/「道具明细」Sheet。"
        "同步脚本：`python3 platform/dingtalk_gateway/family_monster_lottery_to_workbook.py`；"
        "排版定义见 `platform/dingtalk_gateway/config/family_monster_workbook_layout.json`。"
    )
