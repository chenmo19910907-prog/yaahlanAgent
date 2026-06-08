"""ADB 截图视觉循环 CLI。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .account_cancel import confirm_cancel_via_moa, prepare_client_cancel
from .login_or_register import enter_account
from .phone_login_status import query_phone_login_status
from .account_sweep import parse_phone_range, sweep_accounts
from .script_abandon import (
    failure_reason_from_result,
    get_script_failure_info,
    list_abandoned_scripts,
    record_script_run_outcome,
    restore_script,
)
from .ai_operate import (
    AI_OPERATE_MODULES,
    AiOperateRequired,
    GOAL_SPECS,
    assert_fragment_script_allowed,
    fragment_module,
    list_goals,
    max_consecutive_failures,
    prepare_vision_cycle,
)
from .learn_cli import add_learn_subparsers, handle_learn_command
from .vip_cli import add_vip_subparsers, handle_vip_command
from .post_login_verify import verify_and_dismiss_post_login
from .splash_verify import verify_and_recover_splash, verify_splash_landing
from .actions import clear_input_field, input_text, keyevent, swipe, tap
from .activity import get_foreground_activity
from .chain import load_steps_file, run_chain
from .device import AdbError, display_size, list_devices, require_device
from .device_calibrate import (
    calibrate_commit,
    calibrate_init,
    calibrate_set_point,
    device_info_payload,
    profile_show,
    record_reference_device,
)
from .device_profile import (
    adapt_dir,
    default_draft_path,
    list_profile_paths,
    load_profile,
)
from .macros import apply_skip_flags, list_macros, resolve_macro
from .recorded_scripts import (
    list_catalog,
    list_fragments_by_module,
    scripts_root,
)
from .screenshot import (
    DEFAULT_CAPTURE_MAX_EDGE,
    DEFAULT_MAX_SCREENSHOTS,
    capture_screenshot,
    latest_screenshot,
    png_dimensions,
    resolve_image_to_device,
    screenshot_dir,
)
from .gift_panel_analyze import analyze_gift_panel_from_tunnel, find_gifts_from_tunnel
from .popup_analyze import analyze_scene_from_tunnel, dismiss_scripts_for_analysis
from .popup_gate import ensure_popups_cleared, resolve_gate_scene
from .apps import YAAHLAN
from .logcat_check import (
    LogcatCheckOptions,
    add_logcat_arguments,
    attach_logcat_verify,
    clear_logcat_buffer,
    fetch_latest_logcat_match,
    logcat_options_from_args,
    wait_for_logcat,
)
from .tunnel_verify import (
    TunnelVerifyOptions,
    add_tunnel_arguments,
    attach_tunnel_verify,
    fetch_latest_tunnel_match,
    resolve_momoid,
    tunnel_options_from_args,
    wait_for_tunnel,
)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _attach_foreground_activity(*, serial: str, result: dict[str, object]) -> None:
    """片段执行后附带前台 Activity（~100ms），供片段间验收，免读图。"""
    try:
        result["foregroundActivity"] = get_foreground_activity(serial=serial)
    except AdbError as exc:
        result["foregroundActivity"] = {"ok": False, "error": str(exc)}


def _resolve_screenshot_path(args, shot_dir: Path) -> Path:
    custom = getattr(args, "screenshot", None)
    if custom:
        path = Path(custom)
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.is_file():
            raise AdbError(f"截图不存在: {path}")
        return path
    path = latest_screenshot(shot_dir)
    if path is None:
        raise AdbError("尚无截图，请先执行 capture")
    return path


def _capture_max_edge_from_args(args) -> int | None:
    if getattr(args, "full_res", False):
        return None
    return getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "ADB 截图视觉循环：确定路径用 chain/macro 连续操作，仅在边界 capture；"
            f"不确定时再读图。目录内仅保留最新 {DEFAULT_MAX_SCREENSHOTS} 张 PNG"
        ),
    )
    parser.add_argument("--serial", "-s", help="设备 serial（多台时必须指定）")
    parser.add_argument(
        "--screenshot-dir",
        help=f"截图目录（默认 adb/screenshots/）",
    )
    parser.add_argument(
        "--max-screenshots",
        type=int,
        default=DEFAULT_MAX_SCREENSHOTS,
        help=f"最多保留截图数量（默认 {DEFAULT_MAX_SCREENSHOTS}）",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="列出已连接设备")

    p_cap = sub.add_parser("capture", help="截屏并 prune 旧图（视觉循环第一步）")
    p_cap.add_argument(
        "--no-json",
        action="store_true",
        help="仅打印截图路径（默认输出 JSON 含宽高与保留列表）",
    )
    p_cap.add_argument(
        "--max-edge",
        type=int,
        metavar="PX",
        default=DEFAULT_CAPTURE_MAX_EDGE,
        help=(
            f"缩略图最长边像素（macOS 用 sips，默认 {DEFAULT_CAPTURE_MAX_EDGE}；"
            "JSON 含 scaleX/scaleY 供读图坐标换算）"
        ),
    )
    p_cap.add_argument(
        "--full-res",
        action="store_true",
        help="不缩略，保留设备原始分辨率（耗 token，仅校准坐标时用）",
    )

    p_coords = sub.add_parser(
        "coords",
        help="读缩略图上的像素坐标，换算为设备 tap 坐标与 tap_pct",
    )
    p_coords.add_argument("x", type=int, help="截图上的 x（读图像素）")
    p_coords.add_argument("y", type=int, help="截图上的 y（读图像素）")
    p_coords.add_argument(
        "--screenshot",
        metavar="PATH",
        help="截图路径（默认 adb/screenshots/ 最新一张）",
    )

    p_act = sub.add_parser(
        "activity",
        help="当前前台 Activity（dumpsys JSON，片段间验收用，比读图快）",
    )

    p_latest = sub.add_parser("latest", help="输出最新截图路径（若无则 exit 2）")

    p_info = sub.add_parser("info", help="设备屏幕尺寸 + 最新截图信息")

    p_tap = sub.add_parser("tap", help="点击坐标（视觉循环：读图后算出的 x y）")
    p_tap.add_argument("x", type=int)
    p_tap.add_argument("y", type=int)
    p_tap.add_argument(
        "--from-image",
        action="store_true",
        help="x/y 为读图（缩略图）像素，按截图与屏幕尺寸比例换算后再 tap",
    )
    p_tap.add_argument(
        "--screenshot",
        metavar="PATH",
        help="配合 --from-image：截图路径（默认最新一张）",
    )

    p_swipe = sub.add_parser("swipe", help="滑动")
    p_swipe.add_argument("x1", type=int)
    p_swipe.add_argument("y1", type=int)
    p_swipe.add_argument("x2", type=int)
    p_swipe.add_argument("y2", type=int)
    p_swipe.add_argument("--duration", type=int, default=300, help="毫秒")

    p_key = sub.add_parser("key", help="按键（如 4=BACK 3=HOME）")
    p_key.add_argument("code", type=int)

    p_text = sub.add_parser("text", help="输入文本")
    p_text.add_argument("content")
    p_text.add_argument(
        "--no-clear",
        action="store_true",
        help="不清空输入框直接输入（默认先清空焦点输入框）",
    )

    p_cycle = sub.add_parser(
        "cycle",
        help="一步循环：先截屏（返回路径供读图），你 tap 后再执行 capture 或单独 capture",
    )

    p_scripts = sub.add_parser(
        "scripts",
        help="列出 adb/录制脚本 片段目录",
    )

    p_macros = sub.add_parser("macros", help="列出录制片段（同 scripts 中 kind=fragment）")

    p_macro = sub.add_parser("macro", help="执行录制片段（支持中文名）")
    p_macro.add_argument("name", help="中文名或 id，如 发布纯文本动态")
    p_macro.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="KEY",
        help="跳过带 skip_key 的步骤，如 dismiss_popup_taps、dismiss_splash_ad、verify_splash_ad、login_lang",
    )
    p_macro.add_argument(
        "--text",
        help="片段参数：发布纯文本动态 的正文（纯文本，建议数字/英文）",
    )
    p_macro.add_argument(
        "--capture",
        choices=("never", "start", "end", "both"),
        help="覆盖宏内 capture 策略",
    )
    p_macro.add_argument(
        "--no-capture",
        action="store_true",
        help="等同 --capture never，全程不截图（最连贯）",
    )
    p_macro.add_argument(
        "--no-adapt",
        action="store_true",
        help="跳过设备换算（仅调试用；换机未校准时不要用）",
    )
    p_macro.add_argument(
        "--no-popup-gate",
        action="store_true",
        help="macro 结束时不自动跑首页/Me/房内弹窗截图门禁",
    )
    p_macro.add_argument(
        "--force-script",
        action="store_true",
        help="强制执行首页/Me/房间固定脚本（默认已禁用，改 AI 读图操作）",
    )
    p_macro.add_argument(
        "--rtl",
        action="store_true",
        help="阿语等 RTL 语言：原生页 tap/swipe 水平镜像 x'=1−x（WebView 除外）",
    )
    p_macro.add_argument("--no-rtl", action="store_true", help="禁用 RTL 镜像")
    add_tunnel_arguments(p_macro)
    add_logcat_arguments(p_macro)

    p_chain = sub.add_parser(
        "chain",
        help="按步骤文件连续操作（默认结束时 capture 一次）",
    )
    p_chain.add_argument(
        "steps_file",
        type=Path,
        help="JSON：{ \"capture\": \"end\", \"steps\": [...] }",
    )
    p_chain.add_argument(
        "--capture",
        choices=("never", "start", "end", "both"),
        help="覆盖文件中的 capture",
    )
    p_chain.add_argument(
        "--no-capture",
        action="store_true",
        help="等同 --capture never",
    )
    p_chain.add_argument("--no-adapt", action="store_true", help="跳过设备换算")
    p_chain.add_argument(
        "--rtl",
        action="store_true",
        help="RTL 原生页水平镜像",
    )
    p_chain.add_argument("--no-rtl", action="store_true", help="禁用 RTL 镜像")
    p_chain.add_argument(
        "--no-popup-gate",
        action="store_true",
        help="chain 结束时不自动跑弹窗截图门禁",
    )
    add_tunnel_arguments(p_chain)
    add_logcat_arguments(p_chain)

    p_device = sub.add_parser("device", help="设备型号与坐标换算（换机先校准）")
    dev_sub = p_device.add_subparsers(dest="device_command", required=True)
    dev_sub.add_parser("info", help="当前设备型号、分辨率、是否已有换算档案")

    p_dev_prof = dev_sub.add_parser("profiles", help="列出已保存的设备档案")
    p_dev_init = dev_sub.add_parser(
        "calibrate",
        help="从录制脚本提取基准点并截屏，生成校准草稿",
    )
    p_dev_init.add_argument(
        "--script",
        required=True,
        help="录制片段中文名或 id，如 发布纯文本动态",
    )
    p_dev_init.add_argument("--draft", type=Path, help="草稿 JSON 路径")
    p_dev_init.add_argument(
        "--force",
        action="store_true",
        help="已有档案时仍重新截图校准（用于操作失败后更正）",
    )

    p_dev_recal = dev_sub.add_parser(
        "recalibrate",
        help="等同 calibrate --force（更正已有机型的换算）",
    )
    p_dev_recal.add_argument("--script", required=True)
    p_dev_recal.add_argument("--draft", type=Path)

    p_dev_set = dev_sub.add_parser(
        "set",
        help="根据截图读到的像素填写某校准点的 devicePct",
    )
    p_dev_set.add_argument("--draft", type=Path, help="草稿路径（默认按 serial）")
    p_dev_set.add_argument("--note", required=True, help="与草稿 anchor.note 对应")
    p_dev_set.add_argument("--device-pct", nargs=2, type=float, metavar=("X", "Y"))
    p_dev_set.add_argument("--pixel", nargs=2, type=int, metavar=("X", "Y"))

    p_dev_commit = dev_sub.add_parser(
        "commit",
        help="根据草稿拟合换算并写入设备档案",
    )
    p_dev_commit.add_argument("--draft", type=Path)
    p_dev_commit.add_argument("--id", required=True, dest="profile_id", help="档案 id")
    p_dev_commit.add_argument("--name", required=True, help="档案中文名")
    p_dev_commit.add_argument(
        "--fix-offset",
        action="store_true",
        help="仅缩放、offset=0（校准点少时用）",
    )
    p_dev_commit.add_argument(
        "--reason",
        choices=("initial", "correction"),
        default="initial",
        help="initial=首次建档；correction=操作失败后更正",
    )

    dev_sub.add_parser(
        "record-reference",
        help="把当前手机记入基准设备.json（在录制基准机上执行一次）",
    )
    p_dev_show = dev_sub.add_parser("show", help="查看某档案详情")
    p_dev_show.add_argument("profile_id", help="档案 id")

    p_run = sub.add_parser(
        "run",
        help="自动化执行：ADB 操作 + 结束截图 + Tunnel 抓包校验（推荐 Agent 使用）",
    )
    run_src = p_run.add_mutually_exclusive_group(required=True)
    run_src.add_argument("--macro", metavar="NAME", help="执行片段")
    run_src.add_argument("--chain", type=Path, metavar="FILE", help="执行 chain JSON")
    p_run.add_argument("--text", help="片段文本参数")
    p_run.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="KEY",
        help="跳过 skip_key",
    )
    p_run.add_argument(
        "--verify",
        action="store_true",
        help="结束时强制截图（tunnel 校验时默认也会截图）",
    )
    p_run.add_argument("--no-adapt", action="store_true", help="跳过设备换算")
    p_run.add_argument(
        "--no-popup-gate",
        action="store_true",
        help="run 结束时不自动跑弹窗截图门禁",
    )
    p_run.add_argument(
        "--force-script",
        action="store_true",
        help="强制执行首页/Me/房间固定脚本（默认已禁用）",
    )
    p_run.add_argument(
        "--rtl",
        action="store_true",
        help="RTL 原生页水平镜像",
    )
    p_run.add_argument("--no-rtl", action="store_true", help="禁用 RTL 镜像")
    p_run.add_argument(
        "--popup-scene",
        choices=("login", "splash", "home", "me", "room", "mic"),
        help="操作后按场景分析 Tunnel 弹窗信号并给出处置建议",
    )
    p_run.add_argument(
        "--popup-auto-dismiss",
        action="store_true",
        help="popup 分析建议关弹窗时自动执行 dismissScripts（默认仅建议）",
    )
    p_run.add_argument("--popup-since", type=int, default=120, help="弹窗分析回溯秒数")
    add_tunnel_arguments(p_run)
    add_logcat_arguments(p_run)

    p_popup = sub.add_parser(
        "popup",
        help="结合 Tunnel 抓包分析登录/首页/Me/进房/开麦等节点的弹窗风险",
    )
    popup_sub = p_popup.add_subparsers(dest="popup_command", required=True)
    p_popup_analyze = popup_sub.add_parser(
        "analyze",
        help="分析最近抓包中的弹窗信号（可配合截图读图）",
    )
    p_popup_analyze.add_argument(
        "--scene",
        required=True,
        choices=("login", "splash", "home", "me", "room", "mic"),
        help="操作场景",
    )
    p_popup_analyze.add_argument("--momoid", help="userId")
    p_popup_analyze.add_argument("--account", help="testAccounts 键名")
    p_popup_analyze.add_argument("--since", type=int, default=120, help="回溯秒数")
    p_popup_analyze.add_argument("--g-appid", default="All")
    p_popup_analyze.add_argument("--g-env", default="alpha")
    p_popup_analyze.add_argument(
        "--capture",
        action="store_true",
        help="分析后截一张图供 Agent 读图确认 weakUiPopups",
    )
    p_popup_analyze.add_argument(
        "--auto-dismiss",
        action="store_true",
        help="存在 actionable 信号时自动执行关闭常见弹窗等脚本",
    )
    p_popup_analyze.add_argument("--no-adapt", action="store_true")

    p_popup_gate = popup_sub.add_parser(
        "gate",
        help="截图门禁：首页/Me/房内关弹窗并再截图，确认后再继续",
    )
    p_popup_gate.add_argument(
        "--scene",
        default="auto",
        choices=("auto", "home", "me", "room"),
        help="落点场景；auto 由 activity + currentTab 推断",
    )
    p_popup_gate.add_argument("--momoid", help="userId（Tunnel 辅助判断）")
    p_popup_gate.add_argument("--account", help="testAccounts 键名")
    p_popup_gate.add_argument("--since", type=int, default=120, help="Tunnel 回溯秒数")
    p_popup_gate.add_argument("--rounds", type=int, default=2, help="--dismiss 时最多轮数（保留）")
    p_popup_gate.add_argument(
        "--dismiss",
        action="store_true",
        help="读图确认有弹窗后再执行关弹窗（默认仅截图，不点任何坐标）",
    )
    p_popup_gate.add_argument("--no-adapt", action="store_true")

    add_learn_subparsers(sub)
    add_vip_subparsers(sub)

    p_tunnel = sub.add_parser(
        "tunnel",
        help="仅 Tunnel 抓包等待/查询（不操作 UI；配合手动或上轮 run 使用）",
    )
    tunnel_sub = p_tunnel.add_subparsers(dest="tunnel_command", required=True)
    p_tunnel_wait = tunnel_sub.add_parser(
        "wait",
        help="轮询直到匹配 URL 关键字或超时",
    )
    p_tunnel_wait.add_argument("--momoid", help="userId")
    p_tunnel_wait.add_argument(
        "--account",
        help="索引 testAccounts 键名，如 familyLeader",
    )
    p_tunnel_wait.add_argument("--keyword", default="", help="URL 关键字")
    p_tunnel_wait.add_argument("--since", type=int, default=300, help="回溯秒数")
    p_tunnel_wait.add_argument("--wait", type=int, default=30, dest="tunnel_wait")
    p_tunnel_wait.add_argument("--poll-ms", type=int, default=2000, dest="tunnel_poll_ms")
    p_tunnel_wait.add_argument(
        "--expect-status",
        type=int,
        default=200,
        help="HTTP status；-1 不校验",
    )
    p_tunnel_wait.add_argument("--expect-ec", type=int, dest="tunnel_expect_ec")
    p_tunnel_wait.add_argument("--g-appid", default="All", dest="tunnel_g_appid")
    p_tunnel_wait.add_argument("--g-env", default="alpha", dest="tunnel_g_env")

    p_tunnel_last = tunnel_sub.add_parser(
        "last",
        help="读取最近一条匹配 URL 的抓包（含 response.em 失败原因）",
    )
    p_tunnel_last.add_argument("--momoid", help="userId")
    p_tunnel_last.add_argument("--account", help="索引 testAccounts 键名")
    p_tunnel_last.add_argument("--keyword", required=True, help="URL 关键字，如 gift/send")
    p_tunnel_last.add_argument("--since", type=int, default=300, help="回溯秒数")
    p_tunnel_last.add_argument("--g-appid", default="All", dest="tunnel_g_appid")
    p_tunnel_last.add_argument("--g-env", default="alpha", dest="tunnel_g_env")

    p_logcat = sub.add_parser(
        "logcat",
        help="adb logcat 关键字等待/查询（客户端渲染、RTC、崩溃等）",
    )
    logcat_sub = p_logcat.add_subparsers(dest="logcat_command", required=True)
    p_logcat_clear = logcat_sub.add_parser("clear", help="清空 logcat 缓冲（adb logcat -c）")
    p_logcat_wait = logcat_sub.add_parser(
        "wait",
        help="轮询直到 logcat 出现/不出现匹配行或超时",
    )
    p_logcat_last = logcat_sub.add_parser(
        "last",
        help="读取最近 logcat 是否含匹配行",
    )
    for p in (p_logcat_wait, p_logcat_last):
        p.add_argument("--grep", required=True, help="行匹配子串或正则")
        p.add_argument("--tail", type=int, default=300, dest="logcat_tail", help="dump 最近行数")
        p.add_argument("--regex", action="store_true", dest="logcat_regex")
        p.add_argument("--invert", action="store_true", dest="logcat_invert")
        p.add_argument(
            "--no-app-filter",
            action="store_true",
            dest="logcat_no_app_filter",
            help="不按 Yaahlan pid 过滤",
        )
        p.add_argument("--min-matches", type=int, default=1, dest="logcat_min_matches")
    p_logcat_wait.add_argument("--wait", type=int, default=10, dest="logcat_wait")
    p_logcat_wait.add_argument("--poll-ms", type=int, default=1000, dest="logcat_poll_ms")
    p_logcat_wait.add_argument(
        "--clear-first",
        action="store_true",
        dest="logcat_clear_first",
        help="轮询前先 adb logcat -c",
    )

    p_gift = sub.add_parser(
        "gift",
        help="礼物面板：Tunnel 抓包解析 Tab/礼物列表（getGiftTabListV3）",
    )
    gift_sub = p_gift.add_subparsers(dest="gift_command", required=True)
    p_gift_panel = gift_sub.add_parser(
        "panel",
        help="解析礼物面板抓包",
    )
    panel_sub = p_gift_panel.add_subparsers(dest="panel_command", required=True)
    p_panel_analyze = panel_sub.add_parser("analyze", help="列出各 Tab 与礼物数量/价位")
    p_panel_find = panel_sub.add_parser("find", help="按价格/Tab/名称查找礼物")
    for p in (p_panel_analyze, p_panel_find):
        p.add_argument("--momoid", help="userId")
        p.add_argument("--account", help="testAccounts 键名")
        p.add_argument("--since", type=int, default=300, help="回溯秒数")
        p.add_argument("--g-appid", default="All")
        p.add_argument("--g-env", default="alpha")
    p_panel_find.add_argument("--price", type=int, help="钻石价格，如 99")
    p_panel_find.add_argument("--tab", dest="tab_name", help="Tab 名称子串，如 Gift / nation")
    p_panel_find.add_argument("--name", dest="name_contains", help="礼物名称子串")

    p_accounts = sub.add_parser(
        "accounts",
        help="批量账号操作（登录巡检 + 每账号 Tunnel 验收）",
    )
    accounts_sub = p_accounts.add_subparsers(dest="accounts_command", required=True)

    p_account = sub.add_parser("account", help="单账号操作")
    account_sub = p_account.add_subparsers(dest="account_command", required=True)
    p_account_cancel = account_sub.add_parser(
        "cancel",
        help="MOA 确认注销 userId（提示词「确认注销」即执行，不校验 App）",
    )
    p_account_cancel.add_argument("--user-id", required=True, help="userId / momoid")
    p_account_cancel_prepare = account_sub.add_parser(
        "cancel-prepare",
        help="AI 读图走 App 内注销预申请（与 MOA 无关）",
    )
    p_account_cancel_prepare.add_argument("--note", help="附加说明")
    p_sweep = accounts_sub.add_parser(
        "sweep",
        help="按手机号批量登录：每账号 tunnel 验登录 → 进 Me 抓包关弹窗 → tunnel 验 Me",
    )
    p_sweep.add_argument(
        "--phones",
        help="逗号分隔手机号，如 13311111111,13311111112",
    )
    p_sweep.add_argument("--from", dest="from_phone", help="范围起始手机号")
    p_sweep.add_argument("--to", dest="to_phone", help="范围结束手机号（含）")
    p_sweep.add_argument(
        "--random",
        type=int,
        metavar="N",
        help="从 --from/--to 范围随机抽 N 个账号（与 --phones 互斥时优先范围）",
    )
    p_sweep.add_argument(
        "--seed",
        type=int,
        help="随机抽样种子（调试用，默认非确定）",
    )
    p_sweep.add_argument(
        "--me",
        action="store_true",
        help="登录后再进 Me 验收关弹窗（默认仅验登录，避免批量时操作错乱）",
    )
    p_sweep.add_argument(
        "--no-me",
        action="store_true",
        help="（已废弃，默认不进 Me）",
    )
    p_sweep.add_argument(
        "--login-keyword",
        default="simpleUserInfo",
        help="登录成功抓包关键字（默认 simpleUserInfo）",
    )
    p_sweep.add_argument(
        "--me-keyword",
        default="personalHomePageUserInfo",
        help="进 Me 后抓包关键字（默认 personalHomePageUserInfo）",
    )
    p_sweep.add_argument(
        "--tunnel-wait",
        type=int,
        default=25,
        help="每步 tunnel 最长等待秒数",
    )
    p_enter = accounts_sub.add_parser(
        "enter",
        help="MOA 查手机号 userId：有 ID 登录，无 ID 注册",
    )
    p_enter.add_argument("--text", required=True, help="手机号（不含区号）")
    p_enter.add_argument(
        "--force-route",
        choices=("login", "register"),
        help="跳过 MOA，强制走登录或注册（调试用）",
    )
    p_enter.add_argument(
        "--skip-moa",
        action="store_true",
        help="跳过 MOA 查号（须配合 --force-route）",
    )
    p_status = accounts_sub.add_parser(
        "status",
        help="MOA 查手机号是否已注册 / 关联 userId",
    )
    p_status.add_argument("--text", required=True, help="手机号（不含区号）")

    p_splash = sub.add_parser(
        "splash",
        help="冷启动开屏广告验收（activity + Tunnel getOpenScreenAd/getUserConfigs）",
    )
    splash_sub = p_splash.add_subparsers(dest="splash_command", required=True)
    p_splash_verify = splash_sub.add_parser(
        "verify",
        help="验收开屏是否结束、是否误进广告 WebView",
    )
    p_splash_verify.add_argument("--momoid", help="userId（用于 Tunnel 验收）")
    p_splash_verify.add_argument("--account", help="testAccounts 键名")
    p_splash_verify.add_argument(
        "--since",
        type=int,
        default=60,
        help="回溯秒数（冷启 start_time = now - since）",
    )
    p_splash_verify.add_argument(
        "--recover",
        action="store_true",
        help="验收失败时 BACK 并重跑跳过开屏广告",
    )
    p_splash_verify.add_argument("--tunnel-wait", type=int, default=20)
    p_splash_verify.add_argument("--no-adapt", action="store_true")

    p_login = sub.add_parser(
        "login",
        help="登录后弹窗验收（签到半屏 + Tunnel sign/signInList）",
    )
    login_sub = p_login.add_subparsers(dest="login_command", required=True)
    p_login_verify = login_sub.add_parser(
        "verify",
        help="验收登录后是否卡在签到 WebView，并按抓包关弹窗",
    )
    p_login_verify.add_argument("--momoid", help="userId")
    p_login_verify.add_argument("--account", help="testAccounts 键名")
    p_login_verify.add_argument(
        "--since",
        type=int,
        default=90,
        help="登录 start_time = now - since（秒）",
    )
    p_login_verify.add_argument(
        "--force-dismiss",
        action="store_true",
        help="无视抓包强制执行登录后处理弹窗",
    )
    p_login_verify.add_argument("--no-adapt", action="store_true")

    p_ai = sub.add_parser(
        "ai",
        help="首页/个人页/房间：AI 读图操作（固定 macro 已禁用）",
    )
    ai_sub = p_ai.add_subparsers(dest="ai_command", required=True)
    p_ai_goals = ai_sub.add_parser("goals", help="列出可用 goal")
    p_ai_abandoned = ai_sub.add_parser("abandoned", help="列出已废弃的固定脚本")
    p_ai_restore = ai_sub.add_parser("restore", help="恢复脚本（清零连续失败计数）")
    p_ai_restore.add_argument("name", help="片段/组合中文名或 id")
    p_ai_failures = ai_sub.add_parser("failures", help="查看脚本失败计数")
    p_ai_failures.add_argument("name", help="片段/组合中文名或 id")
    p_ai_prepare = ai_sub.add_parser(
        "prepare",
        help="截图 + activity + 工作流，供 Agent 读图后 tap/key",
    )
    p_ai_prepare.add_argument(
        "--goal",
        required=True,
        choices=tuple(GOAL_SPECS.keys()),
        help="操作目标",
    )
    p_ai_prepare.add_argument("--note", help="附加说明写入 agentHint")

    return parser


def _use_adaptation(args: argparse.Namespace) -> bool:
    return not getattr(args, "no_adapt", False)


def _rtl_mode(args: argparse.Namespace) -> str:
    if getattr(args, "no_rtl", False):
        return "off"
    if getattr(args, "rtl", False):
        return "on"
    return "off"


def _resolve_capture_mode(
    *,
    explicit: str | None,
    no_capture: bool,
    default: str,
) -> str:
    if no_capture:
        return "never"
    return explicit or default


def _ensure_end_screenshot(
    *,
    serial: str,
    result: dict[str, object],
    shot_dir: Path,
    max_screenshots: int,
) -> None:
    if result.get("screenshot"):
        return
    cap = capture_screenshot(
        serial=serial,
        directory=shot_dir,
        max_keep=max_screenshots,
    )
    result["screenshot"] = cap


def _run_dismiss_scripts(
    *,
    serial: str,
    script_names: list[str],
    shot_dir: Path,
    max_screenshots: int,
    skip_keys: set[str],
    use_adaptation: bool,
) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for name in script_names:
        frag = resolve_macro(name)
        steps = apply_skip_flags(list(frag.get("steps", [])), skip=skip_keys)
        out = run_chain(
            serial=serial,
            steps=steps,
            capture="never",
            screenshot_dir=shot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=use_adaptation,
        )
        blocks.append(
            {
                "script": frag.get("name", name),
                "scriptId": frag.get("id", name),
                "stepsExecuted": out.get("stepsExecuted"),
            }
        )
    return blocks


def _attach_popup_analysis(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    scene: str,
    auto_dismiss: bool,
) -> None:
    momoid = resolve_momoid(
        momoid=getattr(args, "tunnel_momoid", None),
        account=getattr(args, "tunnel_account", None),
    )
    since_seconds = int(
        getattr(args, "popup_since", None) or getattr(args, "since", 120)
    )
    analysis = analyze_scene_from_tunnel(
        momoid=momoid,
        scene=scene,
        since_seconds=since_seconds,
        g_appid=str(getattr(args, "tunnel_g_appid", "All") or "All"),
        g_env=str(getattr(args, "tunnel_g_env", "alpha") or "alpha"),
    )

    dismiss_blocks: list[dict[str, object]] = []
    if auto_dismiss and analysis.get("dismissScripts"):
        dismiss_blocks = dismiss_scripts_for_analysis(
            serial=serial,
            analysis=analysis,  # type: ignore[arg-type]
            screenshot_dir=shot_dir,
            max_screenshots=max_screenshots,
            use_adaptation=_use_adaptation(args),
        )

    if analysis.get("needScreenshot") or dismiss_blocks:
        _ensure_end_screenshot(
            serial=serial,
            result=result,
            shot_dir=shot_dir,
            max_screenshots=max_screenshots,
        )

    analysis["dismissExecuted"] = dismiss_blocks
    result["popupAnalysis"] = analysis


def _finalize_with_tunnel(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    shot_dir: Path,
    max_screenshots: int,
    start_time: int,
    script_spec: dict[str, object] | None = None,
) -> int:
    tunnel_opts = tunnel_options_from_args(
        args,
        script_spec=script_spec,  # type: ignore[arg-type]
    )
    if tunnel_opts is None:
        return 0

    _ensure_end_screenshot(
        serial=serial,
        result=result,
        shot_dir=shot_dir,
        max_screenshots=max_screenshots,
    )
    merged, ok = attach_tunnel_verify(
        result,  # type: ignore[arg-type]
        tunnel_opts,
        start_time=start_time,
    )
    result.clear()
    result.update(merged)
    return 0 if ok else 3


def _finalize_with_logcat(
    *,
    args: argparse.Namespace,
    result: dict[str, object],
    serial: str,
    script_spec: dict[str, object] | None = None,
) -> int:
    logcat_opts = logcat_options_from_args(
        args,
        script_spec=script_spec,  # type: ignore[arg-type]
    )
    if logcat_opts is None:
        return 0
    merged, ok = attach_logcat_verify(
        result,  # type: ignore[arg-type]
        logcat_opts,
        serial=serial,
    )
    result.clear()
    result.update(merged)
    return 0 if ok else 3


def _logcat_exit_code(result: dict[str, object]) -> int:
    verify = result.get("logcatVerify")
    if isinstance(verify, dict) and not verify.get("ok"):
        return 3
    if result.get("logcatVerifyFailed"):
        return 3
    return 0


def _splash_verify_exit_code(result: dict[str, object]) -> int:
    splash = result.get("splashVerify")
    if isinstance(splash, dict) and not splash.get("ok"):
        return 3
    if result.get("splashVerifyFailed"):
        return 3
    return 0


def _popup_gate_exit_code(result: dict[str, object]) -> int:
    gate = result.get("popupGate")
    if isinstance(gate, dict) and (gate.get("blocked") or not gate.get("ok")):
        return 3
    if result.get("popupGateFailed"):
        return 3
    return 0


def _optional_momoid_from_args(args: argparse.Namespace) -> str | None:
    if not getattr(args, "tunnel_momoid", None) and not getattr(args, "tunnel_account", None):
        return None
    return resolve_momoid(
        momoid=getattr(args, "tunnel_momoid", None),
        account=getattr(args, "tunnel_account", None),
    )


def _popup_gate_auto_enabled(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "no_popup_gate", False))


def _track_script_outcome(
    *,
    name: str,
    kind: str,
    result: dict[str, object],
    exit_code: int,
    module: str | None = None,
    script_id: str | None = None,
) -> None:
    reason = failure_reason_from_result(result, exit_code)  # type: ignore[arg-type]
    track = record_script_run_outcome(
        name=name,
        kind=kind,
        ok=exit_code == 0,
        exit_code=exit_code,
        reason=None if exit_code == 0 else reason,
        module=module,
        script_id=script_id,
    )
    result["scriptFailureTrack"] = track
    if track.get("abandoned"):
        result["scriptAbandoned"] = True
        entry = track.get("entry")
        if isinstance(entry, dict) and entry.get("abandonReason"):
            result["agentHint"] = (
                f"{entry.get('abandonReason')}。"
                "该脚本已废弃，请 ai prepare + tunnel 抓包继续；"
                f"调试可用 ai restore {name} 或 --force-script。"
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    shot_dir = screenshot_dir(args.screenshot_dir)

    try:
        if args.command == "devices":
            devices = list_devices(ready_only=False)
            _emit(
                {
                    "devices": [
                        {"serial": d.serial, "state": d.state} for d in devices
                    ]
                }
            )
            return 0

        serial = require_device(args.serial)

        if args.command == "activity":
            _emit(get_foreground_activity(serial=serial))
            return 0

        if args.command == "capture" or args.command == "cycle":
            max_edge = _capture_max_edge_from_args(args)
            result = capture_screenshot(
                serial=serial,
                directory=shot_dir,
                max_keep=args.max_screenshots,
                max_edge=max_edge,
            )
            if args.no_json:
                print(result["path"])
            else:
                _emit(result)
            return 0

        if args.command == "coords":
            shot_path = _resolve_screenshot_path(args, shot_dir)
            dev_w, dev_h = display_size(serial)
            out = resolve_image_to_device(
                args.x,
                args.y,
                screenshot_path=shot_path,
                device_width=dev_w,
                device_height=dev_h,
            )
            _emit(out)
            return 0

        if args.command == "latest":
            path = latest_screenshot(shot_dir)
            if path is None:
                print("尚无截图，请先执行 capture", file=sys.stderr)
                return 2
            w, h = png_dimensions(path)
            _emit({"path": str(path.resolve()), "width": w, "height": h})
            return 0

        if args.command == "info":
            w, h = display_size(serial)
            path = latest_screenshot(shot_dir)
            payload: dict[str, object] = {
                "serial": serial,
                "displayWidth": w,
                "displayHeight": h,
                "screenshotDir": str(shot_dir.resolve()),
                "maxScreenshots": args.max_screenshots,
            }
            if path:
                pw, ph = png_dimensions(path)
                payload["latestScreenshot"] = {
                    "path": str(path.resolve()),
                    "width": pw,
                    "height": ph,
                }
            _emit(payload)
            return 0

        if args.command == "tap":
            tap_x, tap_y = args.x, args.y
            coord_meta: dict[str, object] | None = None
            if getattr(args, "from_image", False):
                shot_path = _resolve_screenshot_path(args, shot_dir)
                dev_w, dev_h = display_size(serial)
                coord_meta = resolve_image_to_device(
                    args.x,
                    args.y,
                    screenshot_path=shot_path,
                    device_width=dev_w,
                    device_height=dev_h,
                )
                tap_x = int(coord_meta["deviceX"])
                tap_y = int(coord_meta["deviceY"])
            tap(x=tap_x, y=tap_y, serial=serial)
            payload: dict[str, object] = {
                "action": "tap",
                "x": tap_x,
                "y": tap_y,
                "serial": serial,
            }
            if coord_meta:
                payload["fromImage"] = {
                    "imageX": coord_meta["imageX"],
                    "imageY": coord_meta["imageY"],
                    "scaleX": coord_meta["scaleX"],
                    "scaleY": coord_meta["scaleY"],
                }
            _emit(payload)
            return 0

        if args.command == "swipe":
            swipe(
                x1=args.x1,
                y1=args.y1,
                x2=args.x2,
                y2=args.y2,
                duration_ms=args.duration,
                serial=serial,
            )
            _emit(
                {
                    "action": "swipe",
                    "from": [args.x1, args.y1],
                    "to": [args.x2, args.y2],
                    "durationMs": args.duration,
                    "serial": serial,
                }
            )
            return 0

        if args.command == "key":
            keyevent(code=args.code, serial=serial)
            _emit({"action": "keyevent", "code": args.code, "serial": serial})
            return 0

        if args.command == "text":
            if not getattr(args, "no_clear", False):
                clear_input_field(serial=serial)
            input_text(text=args.content, serial=serial, clear_first=False)
            _emit({"action": "text", "serial": serial, "cleared": not getattr(args, "no_clear", False)})
            return 0

        if args.command == "scripts":
            fragments = [e for e in list_catalog() if e.get("kind") == "fragment"]
            _emit(
                {
                    "root": str(scripts_root().resolve()),
                    "fragmentModules": list(list_fragments_by_module().keys()),
                    "fragmentsByModule": list_fragments_by_module(),
                    "fragments": fragments,
                    "catalog": fragments,
                }
            )
            return 0

        if args.command == "macros":
            _emit({"macros": list_macros()})
            return 0

        if args.command == "macro":
            assert_fragment_script_allowed(
                args.name,
                force_script=bool(getattr(args, "force_script", False)),
            )
            spec = resolve_macro(args.name, text=args.text)
            tunnel_opts = tunnel_options_from_args(args, script_spec=spec)
            logcat_opts = logcat_options_from_args(args, script_spec=spec)
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=spec.get("capture", "end"),
            )
            if (tunnel_opts is not None or logcat_opts is not None) and capture == "never":
                capture = "end"
            steps = apply_skip_flags(
                list(spec.get("steps", [])),
                skip=set(args.skip),
            )
            gate_momoid: str | None = None
            try:
                gate_momoid = _optional_momoid_from_args(args)
            except ValueError:
                pass
            out = run_chain(
                serial=serial,
                steps=steps,
                capture=capture,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                use_adaptation=_use_adaptation(args),
                text=args.text,
                skip=set(args.skip),
                popup_gate_auto=_popup_gate_auto_enabled(args),
                popup_gate_momoid=gate_momoid,
                capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
                rtl_mode=_rtl_mode(args),  # type: ignore[arg-type]
            )
            out["script"] = spec.get("name", args.name)
            out["scriptId"] = spec.get("id", args.name)
            out["description"] = spec.get("description", "")
            if args.text is not None:
                out["text"] = args.text
            code = _finalize_with_tunnel(
                args=args,
                result=out,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                start_time=start_time,
                script_spec=spec,
            )
            code = max(
                code,
                _finalize_with_logcat(args=args, result=out, serial=serial, script_spec=spec),
                _splash_verify_exit_code(out),
                _popup_gate_exit_code(out),
                _logcat_exit_code(out),
            )
            _attach_foreground_activity(serial=serial, result=out)
            _track_script_outcome(
                name=str(out.get("script", args.name)),
                kind="fragment",
                result=out,
                exit_code=code,
                module=fragment_module(args.name),
                script_id=str(out.get("scriptId", "")),
            )
            _emit(out)
            return code

        if args.command == "ai":
            if args.ai_command == "goals":
                _emit({"goals": list_goals(), "blockedModules": sorted(AI_OPERATE_MODULES)})
                return 0
            if args.ai_command == "abandoned":
                _emit(
                    {
                        "abandoned": list_abandoned_scripts(),
                        "threshold": max_consecutive_failures(),
                        "stateFile": str(
                            Path(__file__).resolve().parent.parent / ".script_abandon.json"
                        ),
                    }
                )
                return 0
            if args.ai_command == "restore":
                _emit(restore_script(str(args.name)))
                return 0
            if args.ai_command == "failures":
                info = get_script_failure_info(str(args.name))
                if info is None:
                    _emit({"name": args.name, "found": False, "consecutiveFailures": 0})
                else:
                    _emit({"name": args.name, "found": True, **info})
                return 0
            if args.ai_command == "prepare":
                out = prepare_vision_cycle(
                    goal=str(args.goal),
                    serial=serial,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
                    note=getattr(args, "note", None),
                )
                _emit(out)
                return 0 if out.get("ok") else 3
            print(f"未知 ai 子命令: {args.ai_command}", file=sys.stderr)
            return 2

        if args.command == "chain":
            steps, file_capture = load_steps_file(args.steps_file)
            tunnel_opts = tunnel_options_from_args(args)
            logcat_opts = logcat_options_from_args(args)
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            capture = _resolve_capture_mode(
                explicit=args.capture,
                no_capture=args.no_capture,
                default=file_capture,
            )
            if (tunnel_opts is not None or logcat_opts is not None) and capture == "never":
                capture = "end"
            gate_momoid: str | None = None
            try:
                gate_momoid = _optional_momoid_from_args(args)
            except ValueError:
                pass
            out = run_chain(
                serial=serial,
                steps=steps,
                capture=capture,
                screenshot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                use_adaptation=_use_adaptation(args),
                popup_gate_auto=_popup_gate_auto_enabled(args),
                popup_gate_momoid=gate_momoid,
                capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
                rtl_mode=_rtl_mode(args),  # type: ignore[arg-type]
            )
            out["stepsFile"] = str(args.steps_file.resolve())
            code = _finalize_with_tunnel(
                args=args,
                result=out,
                serial=serial,
                shot_dir=shot_dir,
                max_screenshots=args.max_screenshots,
                start_time=start_time,
            )
            code = max(
                code,
                _finalize_with_logcat(args=args, result=out, serial=serial),
                _splash_verify_exit_code(out),
                _popup_gate_exit_code(out),
                _logcat_exit_code(out),
            )
            _attach_foreground_activity(serial=serial, result=out)
            _emit(out)
            return code

        if args.command == "run":
            fragment_spec: dict[str, object] | None = None
            tunnel_opts = tunnel_options_from_args(args)
            logcat_opts = logcat_options_from_args(args)
            popup_scene = getattr(args, "popup_scene", None)
            if tunnel_opts is None and not popup_scene and logcat_opts is None:
                raise ValueError(
                    "run 须指定 --tunnel-keyword、--logcat-grep 或 --popup-scene"
                )
            if popup_scene and not (
                getattr(args, "tunnel_momoid", None) or getattr(args, "tunnel_account", None)
            ):
                raise ValueError("run 使用 --popup-scene 时须同时指定 --tunnel-account 或 --tunnel-momoid")
            since_buffer = tunnel_opts.since_buffer_seconds if tunnel_opts else 5
            start_time = int(time.time()) - since_buffer
            out: dict[str, object]

            gate_momoid: str | None = None
            try:
                gate_momoid = _optional_momoid_from_args(args)
            except ValueError:
                pass
            if args.macro:
                assert_fragment_script_allowed(
                    args.macro,
                    force_script=bool(getattr(args, "force_script", False)),
                )
                spec = resolve_macro(args.macro, text=args.text)
                fragment_spec = spec
                steps = apply_skip_flags(
                    list(spec.get("steps", [])),
                    skip=set(args.skip),
                )
                out = run_chain(
                    serial=serial,
                    steps=steps,
                    capture="end",
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    use_adaptation=_use_adaptation(args),
                    text=args.text,
                    skip=set(args.skip),
                    popup_gate_auto=_popup_gate_auto_enabled(args),
                    popup_gate_momoid=gate_momoid,
                    capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
                    rtl_mode=_rtl_mode(args),  # type: ignore[arg-type]
                )
                out["runMode"] = "macro"
                out["script"] = spec.get("name", args.macro)
            else:
                steps, _file_capture = load_steps_file(args.chain)
                out = run_chain(
                    serial=serial,
                    steps=steps,
                    capture="end",
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    use_adaptation=_use_adaptation(args),
                    popup_gate_auto=_popup_gate_auto_enabled(args),
                    popup_gate_momoid=gate_momoid,
                    capture_max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
                    rtl_mode=_rtl_mode(args),  # type: ignore[arg-type]
                )
                out["runMode"] = "chain"
                out["stepsFile"] = str(args.chain.resolve())

            code = 0
            if tunnel_opts is not None:
                code = _finalize_with_tunnel(
                    args=args,
                    result=out,
                    serial=serial,
                    shot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    start_time=start_time,
                    script_spec=fragment_spec,
                )
            code = max(
                code,
                _finalize_with_logcat(
                    args=args,
                    result=out,
                    serial=serial,
                    script_spec=fragment_spec,
                ),
                _splash_verify_exit_code(out),
                _popup_gate_exit_code(out),
                _logcat_exit_code(out),
            )
            if popup_scene:
                _attach_popup_analysis(
                    args=args,
                    result=out,
                    serial=serial,
                    shot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    scene=popup_scene,
                    auto_dismiss=bool(getattr(args, "popup_auto_dismiss", False)),
                )
            _attach_foreground_activity(serial=serial, result=out)
            _emit(out)
            return code

        if args.command == "popup":
            if args.popup_command == "gate":
                momoid: str | None = None
                if getattr(args, "momoid", None) or getattr(args, "account", None):
                    momoid = resolve_momoid(
                        momoid=getattr(args, "momoid", None),
                        account=getattr(args, "account", None),
                    )
                fa = get_foreground_activity(serial=serial)
                scene = resolve_gate_scene(
                    hint=str(fa.get("hint", "")),
                    current_tab=None,
                    explicit=str(args.scene),
                )
                if scene is None:
                    raise ValueError(
                        f"无法推断 popup gate scene（hint={fa.get('hint')}），"
                        "请 --scene home|me|room"
                    )
                out = ensure_popups_cleared(
                    serial=serial,
                    scene=scene,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    momoid=momoid,
                    since_seconds=int(args.since),
                    max_rounds=int(args.rounds),
                    use_adaptation=_use_adaptation(args),
                    auto_dismiss=bool(getattr(args, "dismiss", False)),
                )
                _emit(out)
                if out.get("blocked") or not out.get("ok"):
                    return 3
                return 0
            if args.popup_command == "analyze":
                if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                    raise ValueError("popup analyze 须指定 --momoid 或 --account")
                momoid = resolve_momoid(
                    momoid=getattr(args, "momoid", None),
                    account=getattr(args, "account", None),
                )
                out: dict[str, object] = analyze_scene_from_tunnel(
                    momoid=momoid,
                    scene=args.scene,
                    since_seconds=int(args.since),
                    g_appid=str(args.g_appid),
                    g_env=str(args.g_env),
                )
                dismiss_blocks: list[dict[str, object]] = []
                if args.auto_dismiss and out.get("dismissScripts"):
                    dismiss_blocks = dismiss_scripts_for_analysis(
                        serial=serial,
                        analysis=out,  # type: ignore[arg-type]
                        screenshot_dir=shot_dir,
                        max_screenshots=args.max_screenshots,
                        use_adaptation=_use_adaptation(args),
                    )
                    out["dismissExecuted"] = dismiss_blocks
                if args.capture or out.get("needScreenshot") or dismiss_blocks:
                    cap = capture_screenshot(
                        serial=serial,
                        directory=shot_dir,
                        max_keep=args.max_screenshots,
                    )
                    out["screenshot"] = cap
                _emit(out)
                return 0
            print(f"未知 popup 子命令: {args.popup_command}", file=sys.stderr)
            return 2

        if args.command == "gift":
            if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                raise ValueError("gift panel 须指定 --momoid 或 --account")
            momoid = resolve_momoid(
                momoid=getattr(args, "momoid", None),
                account=getattr(args, "account", None),
            )
            if args.gift_command == "panel" and args.panel_command == "analyze":
                out = analyze_gift_panel_from_tunnel(
                    momoid=momoid,
                    since_seconds=int(args.since),
                    g_appid=str(args.g_appid),
                    g_env=str(args.g_env),
                )
                _emit(out)
                return 0
            if args.gift_command == "panel" and args.panel_command == "find":
                out = find_gifts_from_tunnel(
                    momoid=momoid,
                    since_seconds=int(args.since),
                    price=getattr(args, "price", None),
                    tab_name=getattr(args, "tab_name", None),
                    name_contains=getattr(args, "name_contains", None),
                    g_appid=str(args.g_appid),
                    g_env=str(args.g_env),
                )
                _emit(out)
                return 0 if out.get("matchedCount", 0) > 0 else 3
            print(f"未知 gift 子命令: {args.gift_command}", file=sys.stderr)
            return 2

        if args.command == "splash":
            if args.splash_command == "verify":
                momoid: str | None = None
                if getattr(args, "momoid", None) or getattr(args, "account", None):
                    momoid = resolve_momoid(
                        momoid=getattr(args, "momoid", None),
                        account=getattr(args, "account", None),
                    )
                start_time = int(time.time()) - max(1, int(args.since))
                if args.recover:
                    out = verify_and_recover_splash(
                        serial=serial,
                        screenshot_dir=shot_dir,
                        max_screenshots=args.max_screenshots,
                        momoid=momoid,
                        start_time=start_time,
                        recover=True,
                        tunnel_wait=int(args.tunnel_wait),
                        use_adaptation=_use_adaptation(args),
                    )
                else:
                    out = verify_splash_landing(
                        serial=serial,
                        momoid=momoid,
                        start_time=start_time,
                        tunnel_wait=int(args.tunnel_wait),
                    )
                _emit(out)
                return 0 if out.get("ok") else 3
            print(f"未知 splash 子命令: {args.splash_command}", file=sys.stderr)
            return 2

        if args.command == "login":
            if args.login_command == "verify":
                momoid: str | None = None
                if getattr(args, "momoid", None) or getattr(args, "account", None):
                    momoid = resolve_momoid(
                        momoid=getattr(args, "momoid", None),
                        account=getattr(args, "account", None),
                    )
                login_start = int(time.time()) - max(1, int(args.since))
                out = verify_and_dismiss_post_login(
                    serial=serial,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    momoid=momoid,
                    login_start=login_start,
                    use_adaptation=_use_adaptation(args),
                    force_dismiss=bool(getattr(args, "force_dismiss", False)),
                )
                _emit(out)
                return 0 if out.get("ok") else 3
            print(f"未知 login 子命令: {args.login_command}", file=sys.stderr)
            return 2

        if args.command == "account":
            if args.account_command == "cancel":
                out = confirm_cancel_via_moa(str(args.user_id))
                _emit(out)
                return 0 if out.get("ok") else 3
            if args.account_command == "cancel-prepare":
                out = prepare_client_cancel(
                    serial=serial,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    max_edge=getattr(args, "max_edge", DEFAULT_CAPTURE_MAX_EDGE),
                    note=getattr(args, "note", None),
                )
                _emit(out)
                return 0 if out.get("ok") else 3
            print(f"未知 account 子命令: {args.account_command}", file=sys.stderr)
            return 2

        if args.command == "accounts":
            if args.accounts_command == "status":
                out = query_phone_login_status(str(args.text).strip())
                _emit(out)
                return 0
            if args.accounts_command == "enter":
                if getattr(args, "skip_moa", False) and not getattr(
                    args, "force_route", None
                ):
                    print(
                        "--skip-moa 须配合 --force-route login|register",
                        file=sys.stderr,
                    )
                    return 2
                out = enter_account(
                    str(args.text).strip(),
                    serial=serial,
                    shot_dir=screenshot_dir(args.screenshot_dir),
                    max_screenshots=args.max_screenshots,
                    skip_moa_check=bool(getattr(args, "skip_moa", False)),
                    force_route=getattr(args, "force_route", None),
                )
                _emit(out)
                return 0 if out.get("ok") else 3
            if args.accounts_command == "sweep":
                phone_list = (
                    [p.strip() for p in str(args.phones or "").split(",") if p.strip()]
                    if args.phones
                    else None
                )
                phones = parse_phone_range(
                    phones=phone_list,
                    from_phone=args.from_phone,
                    to_phone=args.to_phone,
                    random_count=getattr(args, "random", None),
                    seed=getattr(args, "seed", None),
                )
                out = sweep_accounts(
                    phones,
                    serial=serial,
                    check_me=bool(getattr(args, "me", False)),
                    login_keyword=str(args.login_keyword),
                    me_keyword=str(args.me_keyword),
                    tunnel_wait=int(args.tunnel_wait),
                )
                _emit(out)
                return 0 if out.get("failed", 0) == 0 else 3
            print(f"未知 accounts 子命令: {args.accounts_command}", file=sys.stderr)
            return 2

        if args.command == "learn":
            _emit(handle_learn_command(args, serial=serial))
            return 0

        if args.command == "vip":
            vip_out = handle_vip_command(args)
            _emit(vip_out)
            return 0 if vip_out.get("ok", True) else 3

        if args.command == "logcat":
            if args.logcat_command == "clear":
                out = clear_logcat_buffer(serial=serial)
                _emit(out)
                return 0
            if args.logcat_command == "wait":
                opts = LogcatCheckOptions(
                    grep=str(args.grep),
                    wait_seconds=max(1, int(args.logcat_wait)),
                    poll_interval_ms=max(300, int(args.logcat_poll_ms)),
                    tail_lines=max(50, int(args.logcat_tail)),
                    clear_before=bool(getattr(args, "logcat_clear_first", False)),
                    app_package=None if args.logcat_no_app_filter else YAAHLAN["package"],
                    min_matches=max(1, int(args.logcat_min_matches)),
                    regex=bool(args.logcat_regex),
                    invert=bool(args.logcat_invert),
                )
                verify = wait_for_logcat(opts, serial=serial)
                _emit({"logcatVerify": verify})
                return 0 if verify.get("ok") else 3
            if args.logcat_command == "last":
                out = fetch_latest_logcat_match(
                    serial=serial,
                    grep=str(args.grep),
                    tail_lines=max(50, int(args.logcat_tail)),
                    app_package=None if args.logcat_no_app_filter else YAAHLAN["package"],
                    regex=bool(args.logcat_regex),
                    invert=bool(args.logcat_invert),
                    min_matches=max(1, int(args.logcat_min_matches)),
                )
                _emit(out)
                return 0 if out.get("ok") else 3
            print(f"未知 logcat 子命令: {args.logcat_command}", file=sys.stderr)
            return 2

        if args.command == "tunnel":
            if args.tunnel_command == "wait":
                if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                    raise ValueError("tunnel wait 须指定 --momoid 或 --account")

                raw_status = args.expect_status
                http_status: int | None = None if raw_status < 0 else int(raw_status)
                opts = TunnelVerifyOptions(
                    momoid=resolve_momoid(
                        momoid=getattr(args, "momoid", None),
                        account=getattr(args, "account", None),
                    ),
                    keyword=str(args.keyword or ""),
                    wait_seconds=max(1, int(args.tunnel_wait)),
                    poll_interval_ms=max(500, int(args.tunnel_poll_ms)),
                    expect_http_status=http_status,
                    expect_response_ec=getattr(args, "tunnel_expect_ec", None),
                    since_buffer_seconds=0,
                    g_appid=str(args.tunnel_g_appid),
                    g_env=str(args.tunnel_g_env),
                )
                start_time = int(time.time()) - max(1, int(args.since))
                verify = wait_for_tunnel(opts, start_time=start_time)
                _emit({"tunnelVerify": verify})
                return 0 if verify.get("ok") else 3
            if args.tunnel_command == "last":
                if not getattr(args, "momoid", None) and not getattr(args, "account", None):
                    raise ValueError("tunnel last 须指定 --momoid 或 --account")
                out = fetch_latest_tunnel_match(
                    momoid=resolve_momoid(
                        momoid=getattr(args, "momoid", None),
                        account=getattr(args, "account", None),
                    ),
                    keyword=str(args.keyword),
                    since_seconds=max(1, int(args.since)),
                    g_appid=str(args.tunnel_g_appid),
                    g_env=str(args.tunnel_g_env),
                )
                _emit(out)
                return 0 if out.get("ok") else 3
            print(f"未知 tunnel 子命令: {args.tunnel_command}", file=sys.stderr)
            return 2

        if args.command == "device":
            if args.device_command == "info":
                _emit(device_info_payload(serial))
                return 0
            if args.device_command == "profiles":
                items = []
                for path in list_profile_paths():
                    try:
                        p = load_profile(path)
                    except (OSError, ValueError, json.JSONDecodeError):
                        continue
                    dev = p.get("device") or {}
                    items.append(
                        {
                            "id": p.get("id"),
                            "name": p.get("name"),
                            "deviceModel": p.get("deviceModel") or dev.get("model"),
                            "width": dev.get("width"),
                            "height": dev.get("height"),
                            "path": str(path.resolve()),
                            "reusePolicy": p.get("reusePolicy"),
                            "updatedAt": p.get("updatedAt"),
                            "transform": p.get("transform"),
                        }
                    )
                _emit({"adaptDir": str(adapt_dir().resolve()), "profiles": items})
                return 0
            draft = args.draft if getattr(args, "draft", None) else default_draft_path(serial)
            if args.device_command in ("calibrate", "recalibrate"):
                force = args.device_command == "recalibrate" or getattr(
                    args, "force", False
                )
                out = calibrate_init(
                    serial=serial,
                    script_key=args.script,
                    screenshot_dir=shot_dir,
                    max_screenshots=args.max_screenshots,
                    draft_path=draft,
                    force=force,
                )
                _emit(out)
                return 0
            if args.device_command == "record-reference":
                _emit(record_reference_device(serial))
                return 0
            if args.device_command == "show":
                _emit(profile_show(args.profile_id))
                return 0
            if args.device_command == "set":
                pct = None
                if args.device_pct:
                    pct = (float(args.device_pct[0]), float(args.device_pct[1]))
                pixel = None
                if args.pixel:
                    pixel = (int(args.pixel[0]), int(args.pixel[1]))
                out = calibrate_set_point(
                    draft_path=draft,
                    note=args.note,
                    device_pct=pct,
                    pixel=pixel,
                )
                _emit(out)
                return 0
            if args.device_command == "commit":
                out = calibrate_commit(
                    draft_path=draft,
                    profile_id=args.profile_id,
                    name=args.name,
                    fix_offset=args.fix_offset,
                    reason=args.reason,
                )
                _emit(out)
                return 0
            print(f"未知 device 子命令: {args.device_command}", file=sys.stderr)
            return 2

        print(f"未知命令: {args.command}", file=sys.stderr)
        return 2

    except AiOperateRequired as e:
        _emit(e.payload)
        return 3
    except (AdbError, ValueError, RuntimeError, OSError) as e:
        print(f"错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
