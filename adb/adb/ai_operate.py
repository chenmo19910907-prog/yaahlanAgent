"""首页 / 个人页(Me) / 房间：禁止固定 tap 脚本，改由 Agent 读图后操作。"""

from __future__ import annotations

from typing import Any

from .activity import get_foreground_activity
from .device import AdbError
from .recorded_scripts import _load_index, list_catalog, resolve_key
from .screenshot import capture_screenshot


def ai_operate_modules() -> frozenset[str]:
    """须 AI 读图、禁用固定脚本的 testcase-kb 模块（见 索引.json aiOperateModules）。"""
    raw = _load_index().get("aiOperateModules", [])
    return frozenset(str(m) for m in raw if m)


AI_OPERATE_MODULES = ai_operate_modules()
from .screenshot import DEFAULT_CAPTURE_MAX_EDGE as _CAPTURE_MAX_EDGE

GOAL_SPECS: dict[str, dict[str, Any]] = {
    "logout": {
        "label": "退出登录到 Login 页",
        "successHints": ["login"],
        "workflow": [
            "capture --max-edge 1170 读图，确认当前页（勿 force-stop）",
            "若在房内/搜索/WebView：BACK 或读图点返回，直到 MainActivity 底栏可见",
            "读图点 Me 底栏",
            "Me 页有弹窗：读图点 Cancel（勿 BACK）",
            "读图点设置 → Log out",
            "activity 验收 hint=login",
        ],
    },
    "enter_me": {
        "label": "进入 Me 个人页",
        "successHints": ["home"],
        "workflow": [
            "capture 读图确认底栏、当前 Tab、是否有弹窗",
            "【Game 帧·无弹窗】不要进行任何点击；需要进 Me 时仅点底栏 Me（约 tap_pct 0.90,0.956）",
            "【Game 帧·有弹窗】仅读图处理该弹窗（如 Cancel）；禁止点 Banner/游戏格/Online players/顶栏头像",
            "【Game 帧禁区】无弹窗时禁止盲点 Cancel/BACK/内容区（易误触 Banner→WebView 或他人私聊）",
            "Me 页有弹窗再读图点 Cancel（勿 BACK，home/Game 上 BACK 会弹退出 App）",
            "再 capture 确认 Me 页顶部 Profile 标题与本人头像区可见",
        ],
    },
    "enter_profile": {
        "label": "进入个人资料详情 ProfileActivity",
        "successHints": ["profile"],
        "workflow": [
            "capture 读图：确认在 Me 页且无遮挡弹窗",
            "若有弹窗读图点 Cancel（勿 BACK）",
            "仅点 Me 页顶部本人头像+昵称行（约 tap_pct 0.11,0.16）；禁止点 Viewed me 小头像、Wallet/Family 列表项",
            "activity 验收 shortName=ProfileActivity 且资料页有编辑铅笔（非 Chat/Follow 他人页）",
            "落点正确后再 macro 资料页进入编辑页 --force-script",
        ],
    },
    "enter_edit_profile": {
        "label": "资料页进入编辑 EditProfileActivity",
        "successHints": ["profile_edit"],
        "workflow": [
            "activity 须已在 ProfileActivity",
            "capture 读图点右上角编辑铅笔",
            "activity 验收 shortName 含 EditProfileActivity",
        ],
    },
    "set_standard_nickname": {
        "label": "修改昵称为 QA 标准名",
        "successHints": ["profile", "profile_edit", "home"],
        "workflow": [
            "activity 须已在 EditProfileActivity（否则 ai prepare --goal enter_profile 读图导航）",
            "macro 资料页修改昵称为标准昵称 --text <完整手机号> --force-script --no-capture",
            "Admin --query-user-id 验收 nickname（133111111XX→CXX，133111112XX→C2XX）",
            "capture 读图确认 Me/资料页展示新昵称",
        ],
    },
    "dismiss_me_popup": {
        "label": "Me 页关弹窗",
        "successHints": ["home"],
        "workflow": [
            "capture 读图",
            "若有对话框/众测/账号安全：点 Cancel 或关闭（勿 BACK）",
            "再 capture 确认弹窗已关",
        ],
    },
    "home_tab": {
        "label": "切首页底栏（Game/Room 等）",
        "successHints": ["home"],
        "workflow": [
            "capture 读图确认当前 Tab 与是否有弹窗",
            "无弹窗且已在目标 Tab：不点击，直接验收",
            "需切 Tab 时仅点底栏图标/文字（y≈0.95）；Game 帧禁止点 Banner/游戏格/Online players",
            "activity 或 capture 验收",
        ],
    },
    "enter_room": {
        "label": "进入语音房",
        "successHints": ["in_room"],
        "workflow": [
            "capture 读图：在 Room 帧或搜索页",
            "读图点搜索/房间入口，输入 roomId 后进入",
            "tunnel wait heartbeat 或 activity hint=in_room 验收",
        ],
    },
    "exit_room": {
        "label": "退出语音房",
        "successHints": ["home", "search"],
        "workflow": [
            "capture 读图确认在房内",
            "读图点退出/关闭房间",
            "若在 Search 页：读图点返回至 Room 列表",
            "activity 验收 hint=home 或 search",
        ],
    },
    "recover": {
        "label": "落点纠偏（通用）",
        "successHints": ["home", "login", "in_room"],
        "workflow": [
            "capture 读图分析当前页",
            "按目标用 tap / key BACK / 输入，逐步纠偏",
            "每步后 activity 或 capture 验收；勿 force-stop",
        ],
    },
    "login": {
        "label": "手机号登录",
        "successHints": ["home"],
        "workflow": [
            "capture 读登录页",
            "读图：勾选协议 → 手机入口 → 输入手机号 → Get SMS → 验证码",
            "tunnel wait simpleUserInfo 或 login verify；activity hint=home 验收",
        ],
    },
    "cancel_account": {
        "label": "App 内注销账号预申请（AI 读图）",
        "successHints": ["login"],
        "workflow": [
            "Me → 设置 → Account security → Delete account",
            "注销说明页等 15s → 勾选余额清空 → Delete Account",
            "温馨提示 → 确定 →「确定并退出」（blocked 则 toast 结束）",
            "activity hint=login 或 toast 账号无法注销",
        ],
    },
}


class AiOperateRequired(AdbError):
    """固定脚本已禁用，须 Agent 读 screenshot 后继续操作。"""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(str(payload.get("agentHint", "需要 AI 读图操作")))


def fragment_module(name: str) -> str | None:
    key = name.strip()
    if not key:
        return None
    try:
        _id, _name, _path = resolve_key(key, kind="fragment")
        lookup = {_id, _name, key}
    except ValueError:
        lookup = {key}
    for item in list_catalog():
        if item.get("kind") != "fragment":
            continue
        if str(item.get("id")) in lookup or str(item.get("name")) in lookup:
            return str(item.get("module") or "")
    return None


def is_ai_operate_fragment(name: str) -> bool:
    mod = fragment_module(name)
    return mod in ai_operate_modules() if mod else False


def goal_for_script_name(name: str, *, module: str | None = None) -> str:
    text = name.strip()
    mod = module or fragment_module(name) or ""
    pairs = (
        ("退出登录", "logout"),
        ("退出房间", "exit_room"),
        ("搜索进房", "enter_room"),
        ("切换我的", "enter_me"),
        ("关闭Me", "dismiss_me_popup"),
        ("手机号登录", "login"),
        ("冷启动登录", "login"),
        ("注销", "cancel_account"),
        ("发布", "recover"),
        ("切换动态", "recover"),
        ("切换游戏", "home_tab"),
        ("切换房间", "home_tab"),
    )
    for needle, goal in pairs:
        if needle in text:
            return goal
    return _default_goal_for_module(mod) if mod else "recover"


def assert_fragment_script_allowed(name: str, *, force_script: bool = False) -> None:
    from .script_abandon import get_script_failure_info, is_script_abandoned

    if force_script:
        return
    if is_script_abandoned(name):
        info = get_script_failure_info(name) or {}
        mod = fragment_module(name) or str(info.get("module", "?"))
        goal = goal_for_script_name(name, module=mod)
        raise AiOperateRequired(
            build_abandoned_response(
                kind="fragment",
                name=name,
                module=mod,
                goal=goal,
                failure_info=info,
            )
        )
    if not is_ai_operate_fragment(name):
        return
    mod = fragment_module(name) or "?"
    raise AiOperateRequired(
        build_blocked_response(
            kind="fragment",
            name=name,
            module=mod,
        )
    )


def build_abandoned_response(
    *,
    kind: str,
    name: str,
    module: str,
    goal: str,
    failure_info: dict[str, Any],
) -> dict[str, Any]:
    spec = GOAL_SPECS.get(goal, GOAL_SPECS["recover"])
    reason = str(
        failure_info.get("abandonReason")
        or failure_info.get("lastFailureReason")
        or "连续执行失败"
    )
    consec = failure_info.get("consecutiveFailures", max_consecutive_failures())
    base = build_blocked_response(kind=kind, name=name, module=module, goal=goal)
    base["scriptAbandoned"] = True
    base["consecutiveFailures"] = consec
    base["failureInfo"] = failure_info
    base["agentHint"] = (
        f"「{name}」已连续失败 {consec} 次，**已废弃固定脚本**（{reason}）。"
        f"改 `ai prepare --goal {goal}` 读图操作 + `tunnel wait`/`login verify` 抓包验收。"
        f"恢复脚本：`ai restore {name}` 或 macro 加 `--force-script`（仅调试）。"
    )
    base["workflow"] = spec.get("workflow", [])
    base["nextCommands"] = [
        f"python3 adb/adb_execute.py ai prepare --goal {goal}",
        "python3 adb/adb_execute.py capture --max-edge 1170",
        "python3 adb/adb_execute.py tunnel wait --keyword …",
        "python3 adb/adb_execute.py activity",
    ]
    return base


def build_blocked_response(
    *,
    kind: str,
    name: str,
    module: str,
    goal: str | None = None,
) -> dict[str, Any]:
    goal = goal or goal_for_script_name(name, module=module)
    spec = GOAL_SPECS.get(goal, GOAL_SPECS["recover"])
    return {
        "ok": False,
        "requiresAiVision": True,
        "blockedScriptKind": kind,
        "blockedScript": name,
        "blockedModule": module,
        "goal": goal,
        "goalLabel": spec.get("label", goal),
        "workflow": spec.get("workflow", []),
        "successHints": spec.get("successHints", []),
        "agentHint": (
            f"「{name}」属 {module}，已禁用固定脚本（一步错步步错）。"
            f"请 `ai prepare --goal {goal}` → 读 screenshot → tap/key → activity 验收。"
            f"调试旧脚本须加 --force-script。"
        ),
        "nextCommands": [
            f"python3 adb/adb_execute.py ai prepare --goal {goal}",
            "python3 adb/adb_execute.py capture --max-edge 1170",
            "python3 adb/adb_execute.py tap <x> <y>",
            "python3 adb/adb_execute.py activity",
        ],
    }


def _default_goal_for_module(module: str) -> str:
    if module in {"个人主页", "家族", "充值提现转账", "特权VIP", "贵族", "财富等级", "收藏展馆", "装扮", "公会", "CP好友关系", "客服", "榜单与活动"}:
        return "enter_me"
    if module in {"房间", "房间PK", "礼物"}:
        return "enter_room"
    if module == "注册登录":
        return "login"
    if module == "动态":
        return "recover"
    if module == "游戏":
        return "home_tab"
    return "home_tab"


def max_consecutive_failures() -> int:
    from .script_abandon import max_consecutive_failures as _m

    return _m()


def prepare_vision_cycle(
    *,
    goal: str,
    serial: str,
    screenshot_dir,
    max_screenshots: int,
    max_edge: int | None = _CAPTURE_MAX_EDGE,
    note: str | None = None,
) -> dict[str, Any]:
    goal = goal.strip()
    if goal not in GOAL_SPECS:
        raise ValueError(f"未知 goal {goal!r}，可选: {', '.join(GOAL_SPECS)}")

    spec = GOAL_SPECS[goal]
    fa = get_foreground_activity(serial=serial)
    cap = capture_screenshot(
        serial=serial,
        directory=screenshot_dir,
        max_keep=max(max_screenshots, 5),
        max_edge=max_edge,
    )
    cap["capturePoint"] = f"ai_{goal}"

    hint = str(fa.get("hint", ""))
    success_hints = list(spec.get("successHints", []))
    already_ok = hint in success_hints

    agent_hint = (
        f"已达目标（hint={hint}），可继续下一段。"
        if already_ok
        else (
            f"目标：{spec.get('label', goal)}。读 screenshot 后按 workflow 逐步 tap/key；"
            f"成功 hint 应为 {success_hints}；勿 macro 固定坐标、勿 force-stop。"
        )
    )
    if note:
        agent_hint = f"{note} {agent_hint}"

    return {
        "ok": already_ok,
        "requiresAiVision": not already_ok,
        "action": "aiPrepare",
        "goal": goal,
        "goalLabel": spec.get("label", goal),
        "foregroundActivity": fa,
        "screenshot": cap,
        "workflow": spec.get("workflow", []),
        "successHints": success_hints,
        "blockedModules": sorted(ai_operate_modules()),
        "agentHint": agent_hint,
        "nextCommands": [
            "python3 adb/adb_execute.py tap <x> <y>",
            "python3 adb/adb_execute.py key 4",
            "python3 adb/adb_execute.py capture --max-edge 1170",
            "python3 adb/adb_execute.py activity",
        ],
    }


def list_goals() -> list[dict[str, str]]:
    return [
        {
            "goal": key,
            "label": str(val.get("label", key)),
            "successHints": ",".join(val.get("successHints", [])),
        }
        for key, val in GOAL_SPECS.items()
    ]
