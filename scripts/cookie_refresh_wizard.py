#!/usr/bin/env python3
"""半自动 Cookie 更新向导：打开登录页 → 引导复制 → 校验并写入配置。"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from credential_probe import (  # noqa: E402
    probe_dingtalk_doc_cookie,
    probe_moa_cookie,
    probe_tunnel_cookie,
    validate_dingtalk_doc_cookie_format,
)

_DINGTALK_SYNC = SCRIPTS / ".dingtalk_cookie_sync.py"
_MOA_ENV = ROOT / "MOA" / ".env.local"
_MOA_ENV_EXAMPLE = ROOT / "MOA" / ".env.example"


@dataclass(frozen=True)
class Target:
    key: str
    label: str
    login_url: str
    copy_hint: str
    after_save: str
    validate: Callable[[str], list[str]]
    probe: Callable[[], tuple[bool, str]]
    save: Callable[[str], None]


def _normalize_cookie(cookie: str) -> str:
    return " ".join((cookie or "").split())


def _open_browser(url: str, *, no_open: bool) -> None:
    if no_open:
        print(f"（未打开浏览器）请手动访问: {url}")
        return
    if webbrowser.open(url):
        print(f"已打开浏览器: {url}")
    else:
        print(f"未能自动打开浏览器，请手动访问: {url}")


def _read_clipboard() -> str:
    if sys.platform != "darwin":
        return ""
    try:
        proc = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _upsert_env_file(path: Path, updates: dict[str, str]) -> None:
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    remaining = dict(updates)
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out.append(f"{key}={remaining.pop(key)}\n")
                continue
        out.append(raw if raw.endswith("\n") else raw + "\n")

    for key, value in remaining.items():
        out.append(f"{key}={value}\n")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(out), encoding="utf-8")


def _load_dingtalk_sync_module():
    spec = importlib.util.spec_from_file_location("dingtalk_cookie_sync", _DINGTALK_SYNC)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {_DINGTALK_SYNC}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _save_dingtalk_cookie(cookie: str) -> None:
    sync = _load_dingtalk_sync_module()
    sync._sync_to_all(cookie, dry_run=False)


def _save_moa_cookie(cookie: str) -> None:
    if not _MOA_ENV.is_file() and _MOA_ENV_EXAMPLE.is_file():
        _MOA_ENV.write_text(_MOA_ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"已从模板创建 {_MOA_ENV}")
    _upsert_env_file(_MOA_ENV, {"MOA_COOKIE": _normalize_cookie(cookie)})
    print(f"已更新 {_MOA_ENV} 中的 MOA_COOKIE")
    print("Tunnel 默认复用 MOA_COOKIE，一般无需单独配置 Tunnel/.env.local")


def _validate_moa_cookie_format(cookie: str) -> list[str]:
    text = _normalize_cookie(cookie)
    issues: list[str] = []
    if not text:
        issues.append("Cookie 为空")
        return issues
    markers = ("JSESSIONID=", "auth_cookie=", "tunnel_login_session=")
    if not any(marker in text for marker in markers):
        issues.append("缺少 JSESSIONID / auth_cookie / tunnel_login_session，可能复制不完整")
    if len(text) < 40:
        issues.append("Cookie 过短，可能复制不完整")
    return issues


def _build_targets() -> dict[str, Target]:
    return {
        "dingtalk": Target(
            key="dingtalk",
            label="钉钉文档",
            login_url="https://alidocs.dingtalk.com",
            copy_hint=(
                "1. 在已登录的 alidocs 页面按 F12 打开开发者工具\n"
                "2. 切到 Network，刷新页面\n"
                "3. 任选一条 alidocs 请求 → Headers → Request Headers\n"
                "4. 复制整行 Cookie（需含 doc_atoken、XSRF-TOKEN）\n"
                "5. 回到终端：若已复制到剪贴板，直接按 Enter；否则粘贴后按 Enter"
            ),
            after_save=(
                "已写入 ~/.dingtalk_doc_cookie 与 .cursor/.mcp.secrets.json\n"
                "请在 Cursor 执行 Reload Window（Cmd+Shift+P → Developer: Reload Window）"
            ),
            validate=validate_dingtalk_doc_cookie_format,
            probe=lambda: probe_dingtalk_doc_cookie(),
            save=_save_dingtalk_cookie,
        ),
        "moa": Target(
            key="moa",
            label="MOA 测试环境",
            login_url="https://mse.wemomo.com",
            copy_hint=(
                "1. 在 MSE 页面按 F12 → Network\n"
                "2. 打开任意 MOA 测试请求（apirest/httpproxy/moa/test）\n"
                "3. 复制 Request Headers 里的完整 Cookie\n"
                "4. 回到终端：若已复制到剪贴板，直接按 Enter；否则粘贴后按 Enter"
            ),
            after_save=f"已写入 {_MOA_ENV}",
            validate=_validate_moa_cookie_format,
            probe=probe_moa_cookie,
            save=_save_moa_cookie,
        ),
        "tunnel": Target(
            key="tunnel",
            label="Tunnel 抓包（复用 MOA Cookie）",
            login_url="https://tunnel.wemomo.com",
            copy_hint=(
                "1. 在 Tunnel 页面按 F12 → Network\n"
                "2. 任选 /api/requests 请求 → 复制完整 Cookie\n"
                "3. 需包含 tunnel_login_session（通常与 MSE Cookie 相同）\n"
                "4. 回到终端：若已复制到剪贴板，直接按 Enter；否则粘贴后按 Enter"
            ),
            after_save=f"已写入 {_MOA_ENV}（Tunnel 复用 MOA_COOKIE）",
            validate=_validate_moa_cookie_format,
            probe=probe_tunnel_cookie,
            save=_save_moa_cookie,
        ),
    }


def _read_cookie_interactive(*, use_clipboard: bool) -> str:
    if use_clipboard:
        clip = _read_clipboard()
        if clip and len(clip) > 20:
            preview = clip[:72] + ("…" if len(clip) > 72 else "")
            print(f"\n检测到剪贴板内容（{len(clip)} 字符）: {preview}")
            answer = input("使用剪贴板内容？[Y/n] ").strip().lower()
            if answer in ("", "y", "yes"):
                return clip

    print("\n请粘贴 Cookie（单行），粘贴后按 Enter，空行结束：")
    first = sys.stdin.readline()
    if not first:
        return ""
    text = first.rstrip("\n")
    if not text.strip():
        return ""
    return text


def _run_target(
    target: Target,
    *,
    cookie: str | None,
    no_open: bool,
    use_clipboard: bool,
    skip_probe: bool,
) -> int:
    print(f"\n=== {target.label} Cookie 更新 ===")

    if not skip_probe:
        ok, msg = target.probe()
        mark = "有效" if ok else "失效或未配置"
        print(f"当前状态: {mark} — {msg}")

    if cookie:
        raw = _normalize_cookie(cookie)
    else:
        _open_browser(target.login_url, no_open=no_open)
        print("\n请按以下步骤复制 Cookie：")
        print(target.copy_hint)
        try:
            input("\n登录并复制完成后，按 Enter 继续… ")
        except EOFError:
            print("未检测到交互输入", file=sys.stderr)
            return 1
        raw = _normalize_cookie(_read_cookie_interactive(use_clipboard=use_clipboard))

    if not raw:
        print("未获得 Cookie", file=sys.stderr)
        return 1

    issues = target.validate(raw)
    for issue in issues:
        print(f"格式检查: {issue}")
    if issues:
        answer = input("格式检查有警告，仍要保存？[y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            return 1

    target.save(raw)

    if skip_probe:
        print(target.after_save)
        return 0

    ok, msg = target.probe()
    print(f"{'保存并验证通过' if ok else '已保存但在线验证失败'}: {msg}")
    if ok:
        print(target.after_save)
        return 0
    return 3


def main(argv: list[str] | None = None) -> int:
    targets = _build_targets()
    parser = argparse.ArgumentParser(
        description="半自动 Cookie 更新：打开登录页 → 引导复制 → 校验写入",
    )
    parser.add_argument(
        "target",
        nargs="?",
        choices=[*targets.keys(), "all"],
        default="dingtalk",
        help="要更新的凭证（默认 dingtalk）",
    )
    parser.add_argument("--set", metavar="COOKIE", help="直接写入 Cookie，跳过交互")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument(
        "--no-clipboard",
        action="store_true",
        help="不尝试从 macOS 剪贴板读取",
    )
    parser.add_argument("--skip-probe", action="store_true", help="跳过保存前后的在线探活")
    args = parser.parse_args(argv)

    use_clipboard = not args.no_clipboard
    selected = list(targets.keys()) if args.target == "all" else [args.target]

    exit_code = 0
    for key in selected:
        rc = _run_target(
            targets[key],
            cookie=args.set,
            no_open=args.no_open,
            use_clipboard=use_clipboard and not args.set,
            skip_probe=args.skip_probe,
        )
        exit_code = max(exit_code, rc)
        if args.set and len(selected) > 1 and key != selected[-1]:
            print("\n--- 继续下一项 ---\n")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
