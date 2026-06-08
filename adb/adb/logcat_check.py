"""ADB logcat 关键字轮询验收（麦位渲染、RTC、崩溃等客户端信号）。"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from typing import Any

from .apps import YAAHLAN
from .device import AdbError, run_adb

_DEFAULT_PACKAGE = YAAHLAN["package"]
_MAX_MATCH_LINE_LEN = 500
_MAX_MATCH_LINES = 10


@dataclass(frozen=True)
class LogcatCheckOptions:
    grep: str
    wait_seconds: int = 10
    poll_interval_ms: int = 1000
    tail_lines: int = 300
    clear_before: bool = False
    app_package: str | None = _DEFAULT_PACKAGE
    min_matches: int = 1
    regex: bool = False
    invert: bool = False


def resolve_app_package(*, app: str | None = None, package: str | None = None) -> str | None:
    if package and str(package).strip():
        return str(package).strip()
    if app is None or not str(app).strip():
        return _DEFAULT_PACKAGE
    key = str(app).strip().lower()
    if key in ("none", "all", "off", "false", "0"):
        return None
    if key in ("yaahlan", "yaha"):
        from .apps import YAHA

        return YAAHLAN["package"] if key == "yaahlan" else YAHA["package"]
    return str(app).strip()


def clear_logcat_buffer(*, serial: str) -> dict[str, Any]:
    run_adb(["logcat", "-c"], serial=serial, check=True)
    return {"ok": True, "cleared": True}


def _app_pid(*, serial: str, package: str) -> int | None:
    proc = run_adb(
        ["shell", "pidof", "-s", package],
        serial=serial,
        check=False,
        timeout_s=10.0,
    )
    text = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 or not text:
        return None
    try:
        return int(text.split()[0])
    except (TypeError, ValueError, IndexError):
        return None


def dump_logcat(
    *,
    serial: str,
    tail_lines: int = 300,
    app_package: str | None = _DEFAULT_PACKAGE,
) -> tuple[str, int | None]:
    tail = max(50, int(tail_lines))
    pid: int | None = None
    args: list[str] = ["logcat"]
    if app_package:
        pid = _app_pid(serial=serial, package=app_package)
        if pid is not None:
            args.append(f"--pid={pid}")
    args.extend(["-d", "-t", str(tail)])
    proc = run_adb(args, serial=serial, check=True, timeout_s=20.0)
    text = proc.stdout.decode("utf-8", errors="replace")
    return text, pid


def _compile_pattern(pattern: str, *, regex: bool) -> re.Pattern[str]:
    if regex:
        return re.compile(pattern)
    return re.compile(re.escape(pattern), re.IGNORECASE)


def grep_log_lines(
    text: str,
    pattern: str,
    *,
    regex: bool = False,
    invert: bool = False,
) -> list[str]:
    if not pattern.strip():
        return []
    compiled = _compile_pattern(pattern, regex=regex)
    lines = text.splitlines()
    if invert:
        return [line for line in lines if not compiled.search(line)]
    return [line for line in lines if compiled.search(line)]


def _trim_line(line: str) -> str:
    line = line.strip()
    if len(line) <= _MAX_MATCH_LINE_LEN:
        return line
    return line[: _MAX_MATCH_LINE_LEN - 3] + "..."


def _summarize_matches(lines: list[str]) -> list[str]:
    return [_trim_line(line) for line in lines[:_MAX_MATCH_LINES]]


def parse_logcat_check_spec(spec: Any) -> LogcatCheckOptions | None:
    if spec is None:
        return None
    if isinstance(spec, str):
        grep = spec.strip()
        if not grep:
            return None
        return LogcatCheckOptions(grep=grep)
    if not isinstance(spec, dict):
        return None

    grep = str(spec.get("grep") or spec.get("pattern") or "").strip()
    if not grep:
        return None

    app_raw = spec.get("appPackage", spec.get("package", spec.get("app")))
    app_package = resolve_app_package(
        app=str(app_raw) if app_raw is not None else None,
        package=str(spec["package"]).strip() if spec.get("package") else None,
    )
    if spec.get("noAppFilter") is True or spec.get("appFilter") is False:
        app_package = None

    return LogcatCheckOptions(
        grep=grep,
        wait_seconds=max(1, int(spec.get("waitSeconds", spec.get("wait", 10)))),
        poll_interval_ms=max(300, int(spec.get("pollIntervalMs", spec.get("poll_ms", 1000)))),
        tail_lines=max(50, int(spec.get("tailLines", spec.get("tail", 300)))),
        clear_before=bool(spec.get("clearBefore", spec.get("clear_first", False))),
        app_package=app_package,
        min_matches=max(1, int(spec.get("minMatches", 1))),
        regex=bool(spec.get("regex", False)),
        invert=bool(spec.get("invert", False)),
    )


def logcat_options_from_args(
    args: Any,
    *,
    script_spec: dict[str, Any] | None = None,
) -> LogcatCheckOptions | None:
    grep = getattr(args, "logcat_grep", None)
    if grep and str(grep).strip():
        app_package = _DEFAULT_PACKAGE
        if getattr(args, "logcat_no_app_filter", False):
            app_package = None
        return LogcatCheckOptions(
            grep=str(grep).strip(),
            wait_seconds=max(1, int(getattr(args, "logcat_wait", 10))),
            poll_interval_ms=max(300, int(getattr(args, "logcat_poll_ms", 1000))),
            tail_lines=max(50, int(getattr(args, "logcat_tail", 300))),
            clear_before=bool(getattr(args, "logcat_clear_first", False)),
            app_package=app_package,
            min_matches=max(1, int(getattr(args, "logcat_min_matches", 1))),
            regex=bool(getattr(args, "logcat_regex", False)),
            invert=bool(getattr(args, "logcat_invert", False)),
        )

    if script_spec is not None:
        return parse_logcat_check_spec(script_spec.get("logcatVerify"))
    return None


def _match_ok(lines: list[str], options: LogcatCheckOptions) -> bool:
    count = len(lines)
    if options.invert:
        return count == 0
    return count >= options.min_matches


def wait_for_logcat(
    options: LogcatCheckOptions,
    *,
    serial: str,
) -> dict[str, Any]:
    cleared = False
    if options.clear_before:
        clear_logcat_buffer(serial=serial)
        cleared = True

    deadline = time.time() + options.wait_seconds
    last_error = ""
    polls = 0
    latest_lines: list[str] = []
    pid: int | None = None

    while time.time() <= deadline:
        polls += 1
        try:
            text, pid = dump_logcat(
                serial=serial,
                tail_lines=options.tail_lines,
                app_package=options.app_package,
            )
        except (AdbError, ValueError) as e:
            last_error = str(e)
            time.sleep(options.poll_interval_ms / 1000.0)
            continue

        latest_lines = grep_log_lines(
            text,
            options.grep,
            regex=options.regex,
            invert=options.invert,
        )
        if _match_ok(latest_lines, options):
            summaries = _summarize_matches(latest_lines)
            hint = (
                f"未出现 {options.grep!r} 日志，符合 invert 预期"
                if options.invert
                else f"已匹配 {len(latest_lines)} 条 logcat 行；不必读图"
            )
            return {
                "ok": True,
                "grep": options.grep,
                "invert": options.invert,
                "regex": options.regex,
                "polls": polls,
                "matchedCount": len(latest_lines),
                "matches": summaries,
                "tailLines": options.tail_lines,
                "appPackage": options.app_package,
                "pid": pid,
                "clearedBefore": cleared,
                "agentHint": hint,
            }

        time.sleep(options.poll_interval_ms / 1000.0)

    summaries = _summarize_matches(latest_lines)
    if options.invert:
        error = last_error or (
            f"等待 {options.wait_seconds}s 内仍出现 {len(latest_lines)} 条含 "
            f"{options.grep!r} 的日志"
        )
    else:
        error = last_error or (
            f"等待 {options.wait_seconds}s 内未在 logcat 最近 {options.tail_lines} 行中"
            f"匹配到 {options.grep!r}"
        )
    return {
        "ok": False,
        "grep": options.grep,
        "invert": options.invert,
        "regex": options.regex,
        "polls": polls,
        "matchedCount": len(latest_lines),
        "matches": summaries,
        "tailLines": options.tail_lines,
        "appPackage": options.app_package,
        "pid": pid,
        "clearedBefore": cleared,
        "error": error,
        "agentHint": "读 matches 与 activity；必要时 capture 读图或拉长 --logcat-wait",
    }


def fetch_latest_logcat_match(
    *,
    serial: str,
    grep: str,
    tail_lines: int = 300,
    app_package: str | None = _DEFAULT_PACKAGE,
    regex: bool = False,
    invert: bool = False,
    min_matches: int = 1,
) -> dict[str, Any]:
    try:
        text, pid = dump_logcat(
            serial=serial,
            tail_lines=tail_lines,
            app_package=app_package,
        )
    except (AdbError, ValueError) as e:
        return {
            "ok": False,
            "grep": grep,
            "tailLines": tail_lines,
            "appPackage": app_package,
            "error": str(e),
        }

    lines = grep_log_lines(text, grep, regex=regex, invert=invert)
    summaries = _summarize_matches(lines)
    ok = _match_ok(lines, LogcatCheckOptions(
        grep=grep,
        tail_lines=tail_lines,
        app_package=app_package,
        regex=regex,
        invert=invert,
        min_matches=min_matches,
    ))
    if invert:
        error = None if ok else f"最近 {tail_lines} 行内仍出现 {len(lines)} 条含 {grep!r} 的日志"
    else:
        error = None if ok else f"最近 {tail_lines} 行内无匹配 {grep!r} 的日志"

    return {
        "ok": ok,
        "grep": grep,
        "invert": invert,
        "regex": regex,
        "tailLines": tail_lines,
        "appPackage": app_package,
        "pid": pid,
        "matchedCount": len(lines),
        "matches": summaries,
        "error": error,
        "agentHint": "客户端渲染/RTC 类验收；业务写接口仍以 tunnel 为准",
    }


def attach_logcat_verify(
    result: dict[str, Any],
    options: LogcatCheckOptions | None,
    *,
    serial: str,
) -> tuple[dict[str, Any], bool]:
    if options is None:
        return result, True
    verify = wait_for_logcat(options, serial=serial)
    result["logcatVerify"] = verify
    return result, bool(verify.get("ok"))


def add_logcat_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("logcat 校验（操作后轮询 adb logcat）")
    group.add_argument(
        "--logcat-grep",
        help="logcat 行匹配子串；加 --logcat-regex 时按正则",
    )
    group.add_argument("--logcat-wait", type=int, default=10, help="最长等待秒数（默认 10）")
    group.add_argument("--logcat-poll-ms", type=int, default=1000, help="轮询间隔毫秒")
    group.add_argument("--logcat-tail", type=int, default=300, help="每次 dump 最近行数")
    group.add_argument(
        "--logcat-clear-first",
        action="store_true",
        help="验收前先 adb logcat -c 清缓冲",
    )
    group.add_argument("--logcat-regex", action="store_true", help="grep 按正则匹配")
    group.add_argument(
        "--logcat-invert",
        action="store_true",
        help="期望不出现匹配行（如无 Exception）",
    )
    group.add_argument(
        "--logcat-no-app-filter",
        action="store_true",
        help="不按 Yaahlan 进程 pid 过滤（默认仅本 App）",
    )
    group.add_argument("--logcat-min-matches", type=int, default=1, help="至少匹配行数")
