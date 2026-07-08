#!/usr/bin/env python3
"""macOS「iPhone 镜像」窗口辅助操作（坐标点击 + 区域截图）。

⚠️ 限制（请务必阅读）：
- 只能操作 **iPhone Mirroring** 投屏窗口，不是 ADB/XCUITest，无 Activity / resourceId。
- 镜像窗口在 macOS 无障碍里通常只有 **1 个整块 group**，无法像 Android observe 那样读控件树。
- 点击依赖 **窗口位置 + 百分比坐标**，窗口移动/缩放后会偏；仅适合临时探索，不适合稳定回归。
- 需要给「终端 / Cursor」开启 **辅助功能** + **输入监控** 权限；截图需 **屏幕录制** 权限。
- 点击/滑动依赖 **cliclick**（`brew install cliclick`）；无 cliclick 时 CGEvent 对镜像窗口通常无效。
- 正式 iOS UI 自动化请用仓库 `midscene/` + WDA（WebDriverAgent），见 midscene/scripts/midscene-run.mjs --platform=ios。

示例：
  python3 scripts/iphone_mirror_control.py status
  python3 scripts/iphone_mirror_control.py focus
  python3 scripts/iphone_mirror_control.py capture --out .tmp/iphone_mirror.png
  python3 scripts/iphone_mirror_control.py observe
  python3 scripts/iphone_mirror_control.py aim --pct 60 32 --out .tmp/aim.png   # 移鼠标+截图核对
  python3 scripts/iphone_mirror_control.py cursor --pct 60 32                    # 仅移鼠标
  python3 scripts/iphone_mirror_control.py tap --pct 50 92    # 确认后再点
  python3 scripts/iphone_mirror_control.py swipe --from-pct 50 80 --to-pct 50 20 --steps 8
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


PROCESS_NAME = "iPhone Mirroring"
CLICLICK_CANDIDATES = (
    "/opt/homebrew/bin/cliclick",
    "/usr/local/bin/cliclick",
)


def _cliclick_path() -> str | None:
    for path in CLICLICK_CANDIDATES:
        if Path(path).is_file():
            return path
    found = subprocess.run(
        ["which", "cliclick"],
        capture_output=True,
        text=True,
        check=False,
    )
    if found.returncode == 0:
        text = (found.stdout or "").strip()
        if text:
            return text
    return None


@dataclass(frozen=True)
class MirrorWindow:
    name: str
    x: int
    y: int
    width: int
    height: int

    def center_screen(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def pct_to_screen(self, pct_x: float, pct_y: float) -> tuple[int, int]:
        px = self.x + int(round(self.width * pct_x / 100.0))
        py = self.y + int(round(self.height * pct_y / 100.0))
        return px, py


def _run_osascript(script: str) -> str:
    proc = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"osascript 退出码 {proc.returncode}")
    return (proc.stdout or "").strip()


def _is_running() -> bool:
    script = f'''
tell application "System Events"
  return (name of processes) contains "{PROCESS_NAME}"
end tell
'''
    return _run_osascript(script).lower() == "true"


def get_mirror_window() -> MirrorWindow:
    if not _is_running():
        raise RuntimeError(
            f"未找到「{PROCESS_NAME}」进程。请先在 Mac 上打开 iPhone 镜像并连接手机。"
        )
    script = f'''
tell application "System Events"
  tell process "{PROCESS_NAME}"
    if (count of windows) is 0 then
      error "镜像进程在运行，但没有可见窗口"
    end if
    set w to front window
    set {{px, py}} to position of w
    set {{ww, wh}} to size of w
    set wn to name of w
    return wn & "\\t" & px & "\\t" & py & "\\t" & ww & "\\t" & wh
  end tell
end tell
'''
    line = _run_osascript(script)
    parts = line.split("\t")
    if len(parts) != 5:
        raise RuntimeError(f"解析窗口信息失败: {line!r}")
    name, x, y, w, h = parts
    return MirrorWindow(name=name, x=int(x), y=int(y), width=int(w), height=int(h))


def focus_mirror() -> MirrorWindow:
    script = f'''
tell application "System Events"
  tell process "{PROCESS_NAME}"
    set frontmost to true
  end tell
end tell
'''
    _run_osascript(script)
    time.sleep(0.15)
    return get_mirror_window()


def _load_coregraphics():
    lib = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
    lib.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
    ]
    lib.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    lib.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    lib.CGEventPost.restype = None
    lib.CFRelease.argtypes = [ctypes.c_void_p]
    lib.CFRelease.restype = None
    return lib


def _make_point(x: float, y: float) -> ctypes.Structure:
    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    return CGPoint(x, y)


def _post_mouse(cg, event_type: int, x: int, y: int, button: int = 0) -> None:
    k_cghid_event_tap = 0
    point = _make_point(float(x), float(y))
    event = cg.CGEventCreateMouseEvent(None, event_type, ctypes.byref(point), button)
    if not event:
        raise RuntimeError("CGEventCreateMouseEvent 失败")
    try:
        cg.CGEventPost(k_cghid_event_tap, event)
    finally:
        cg.CFRelease(event)


def move_cursor(x: int, y: int) -> None:
    cli = _cliclick_path()
    if not cli:
        raise RuntimeError("移动鼠标需要 cliclick（brew install cliclick）")
    proc = subprocess.run(
        [cli, f"m:{x},{y}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"cliclick 移动鼠标失败: {err or proc.returncode}")


def read_cursor_screen() -> tuple[int, int] | None:
    cli = _cliclick_path()
    if not cli:
        return None
    proc = subprocess.run([cli, "p"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    # 输出形如 "1280,400"
    if "," not in text:
        return None
    x_str, y_str = text.split(",", 1)
    return int(x_str.strip()), int(y_str.strip())


def click_screen(x: int, y: int) -> None:
    """发送鼠标点击。iPhone 镜像须用 cliclick 才能转发触摸（CGEvent/AppleScript 无效）。"""
    cli = _cliclick_path()
    if cli:
        proc = subprocess.run(
            [cli, f"c:{x},{y}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"cliclick 点击失败: {err or proc.returncode}")
        return
    cg = _load_coregraphics()
    k_mouse_down = 1
    k_mouse_up = 2
    _post_mouse(cg, k_mouse_down, x, y)
    time.sleep(0.05)
    _post_mouse(cg, k_mouse_up, x, y)


def _desktop_bounds() -> tuple[int, int, int, int]:
    raw = _run_osascript('tell application "Finder" to get bounds of window of desktop')
    parts = [int(x.strip()) for x in raw.split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"无法解析桌面 bounds: {raw!r}")
    return parts[0], parts[1], parts[2], parts[3]


def _image_pixel_size(path: Path) -> tuple[int, int]:
    proc = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "sips 失败").strip())
    w = h = 0
    for line in (proc.stdout or "").splitlines():
        if "pixelWidth:" in line:
            w = int(line.split(":")[-1].strip())
        if "pixelHeight:" in line:
            h = int(line.split(":")[-1].strip())
    if w <= 0 or h <= 0:
        raise RuntimeError(f"无法读取图片尺寸: {path}")
    return w, h


def _mirror_crop_rect(
    pixel_w: int,
    pixel_h: int,
    window: MirrorWindow,
) -> tuple[int, int, int, int]:
    """在全屏截图像素坐标系中计算镜像窗口裁剪框 (x, y, w, h)。"""
    left, top, _, _ = _desktop_bounds()
    # 多显示器 + Retina 下 -R 常失败；全屏图裁剪时尝试多种 scale / 原点
    offsets = (
        lambda s: (int(round(window.x * s)), int(round(window.y * s))),
        lambda s: (int(round((window.x - left) * s)), int(round((window.y - top) * s))),
    )
    for scale in (2.0, 3.0, 1.5, 1.0):
        pw = int(round(window.width * scale))
        ph = int(round(window.height * scale))
        if pw <= 0 or ph <= 0:
            continue
        for origin in offsets:
            px, py = origin(scale)
            if px < 0 or py < 0:
                continue
            if px + pw <= pixel_w and py + ph <= pixel_h:
                return px, py, pw, ph
    raise RuntimeError(
        f"无法在全屏截图 ({pixel_w}x{pixel_h}) 中定位镜像窗口 "
        f"{window.width}x{window.height} @ ({window.x},{window.y})"
    )


def capture_region(window: MirrorWindow, out_path: Path, *, include_cursor: bool = False) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_full = out_path.parent / "iphone_mirror_full.png"
    cap_cmd = ["screencapture", "-x"]
    if include_cursor:
        cap_cmd.insert(1, "-C")
    cap_cmd.append(str(tmp_full))
    proc = subprocess.run(
        cap_cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"全屏截图失败（需屏幕录制权限）: {err or proc.returncode}")
    if not tmp_full.is_file() or tmp_full.stat().st_size == 0:
        raise RuntimeError(f"全屏截图文件无效: {tmp_full}")

    pixel_w, pixel_h = _image_pixel_size(tmp_full)
    px, py, pw, ph = _mirror_crop_rect(pixel_w, pixel_h, window)
    crop = subprocess.run(
        [
            "sips",
            "--cropOffset",
            str(py),
            str(px),
            "--cropToHeightWidth",
            str(ph),
            str(pw),
            str(tmp_full),
            "--out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if crop.returncode != 0:
        err = (crop.stderr or crop.stdout or "").strip()
        raise RuntimeError(f"裁剪镜像区域失败: {err}")
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError(f"截图文件无效: {out_path}")
    return out_path


def swipe_screen(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    steps: int,
    pause_ms: int,
) -> None:
    if steps < 2:
        raise ValueError("steps 须 >= 2")
    sx, sy = start
    ex, ey = end
    cli = _cliclick_path()
    if cli:
        parts = [f"dd:{sx},{sy}"]
        for i in range(1, steps):
            t = i / (steps - 1)
            x = int(round(sx + (ex - sx) * t))
            y = int(round(sy + (ey - sy) * t))
            parts.append(f"dm:{x},{y}")
            if pause_ms > 0 and i < steps - 1:
                parts.append(f"w:{pause_ms}")
        parts.append(f"du:{ex},{ey}")
        proc = subprocess.run(
            [cli, *parts],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(f"cliclick 滑动失败: {err or proc.returncode}")
        return
    cg = _load_coregraphics()
    k_mouse_down = 1
    k_mouse_up = 2
    k_mouse_dragged = 6
    _post_mouse(cg, k_mouse_down, sx, sy)
    time.sleep(0.05)
    for i in range(1, steps):
        t = i / (steps - 1)
        x = int(round(sx + (ex - sx) * t))
        y = int(round(sy + (ey - sy) * t))
        _post_mouse(cg, k_mouse_dragged, x, y)
        time.sleep(pause_ms / 1000.0)
    _post_mouse(cg, k_mouse_up, ex, ey)


def cmd_status(_: argparse.Namespace) -> int:
    if not _is_running():
        print(json.dumps({"running": False, "process": PROCESS_NAME}, ensure_ascii=False, indent=2))
        return 1
    win = get_mirror_window()
    payload = {"running": True, "process": PROCESS_NAME, "window": asdict(win)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_focus(_: argparse.Namespace) -> int:
    win = focus_mirror()
    print(json.dumps({"focused": True, "window": asdict(win)}, ensure_ascii=False, indent=2))
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    win = focus_mirror() if args.focus else get_mirror_window()
    path = capture_region(win, Path(args.out).expanduser().resolve())
    print(json.dumps({"path": str(path), "window": asdict(win)}, ensure_ascii=False, indent=2))
    return 0


def cmd_observe(args: argparse.Namespace) -> int:
    """截图 + 窗口信息，供 Agent 读图验收（无 UI 树）。"""
    win = focus_mirror()
    out = Path(args.out).expanduser().resolve()
    path = capture_region(win, out)
    payload = {
        "process": PROCESS_NAME,
        "window": asdict(win),
        "capture": str(path),
        "note": "镜像无 resourceId/Activity；先 aim 核对鼠标再 tap",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_cursor(args: argparse.Namespace) -> int:
    win = focus_mirror()
    if args.pct:
        tx, ty = win.pct_to_screen(args.pct[0], args.pct[1])
    elif args.screen:
        tx, ty = int(args.screen[0]), int(args.screen[1])
    else:
        raise ValueError("cursor 需要 --pct 或 --screen")
    move_cursor(tx, ty)
    time.sleep(0.15)
    actual = read_cursor_screen()
    payload: dict[str, object] = {
        "action": "cursor",
        "target": [tx, ty],
        "pct": list(args.pct) if args.pct else None,
        "window": asdict(win),
    }
    if actual:
        payload["actual"] = list(actual)
        payload["delta"] = [actual[0] - tx, actual[1] - ty]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_aim(args: argparse.Namespace) -> int:
    """移动鼠标到目标点并截图（含光标），用于核对是否对准控件。"""
    win = focus_mirror()
    if args.pct:
        tx, ty = win.pct_to_screen(args.pct[0], args.pct[1])
    elif args.screen:
        tx, ty = int(args.screen[0]), int(args.screen[1])
    else:
        raise ValueError("aim 需要 --pct 或 --screen")
    move_cursor(tx, ty)
    time.sleep(0.25)
    out = Path(args.out).expanduser().resolve()
    path = capture_region(win, out, include_cursor=True)
    actual = read_cursor_screen()
    payload: dict[str, object] = {
        "action": "aim",
        "target": [tx, ty],
        "pct": list(args.pct) if args.pct else None,
        "capture": str(path),
        "window": asdict(win),
        "note": "读图确认光标在输入框/按钮上，不对则调整 --pct 再 aim",
    }
    if actual:
        payload["actual"] = list(actual)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_tap(args: argparse.Namespace) -> int:
    win = focus_mirror() if args.focus else get_mirror_window()
    if args.pct:
        px, py = win.pct_to_screen(args.pct[0], args.pct[1])
    elif args.screen:
        px, py = int(args.screen[0]), int(args.screen[1])
    else:
        raise ValueError("tap 需要 --pct 或 --screen")
    if args.delay_ms > 0:
        time.sleep(args.delay_ms / 1000.0)
    click_screen(px, py)
    print(
        json.dumps(
            {"action": "tap", "screen": [px, py], "window": asdict(win)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_swipe(args: argparse.Namespace) -> int:
    win = focus_mirror() if args.focus else get_mirror_window()
    if args.from_pct and args.to_pct:
        start = win.pct_to_screen(args.from_pct[0], args.from_pct[1])
        end = win.pct_to_screen(args.to_pct[0], args.to_pct[1])
    elif args.from_screen and args.to_screen:
        start = (int(args.from_screen[0]), int(args.from_screen[1]))
        end = (int(args.to_screen[0]), int(args.to_screen[1]))
    else:
        raise ValueError("swipe 需要 --from-pct/--to-pct 或 --from-screen/--to-screen")
    swipe_screen(start, end, steps=args.steps, pause_ms=args.pause_ms)
    print(
        json.dumps(
            {
                "action": "swipe",
                "from": list(start),
                "to": list(end),
                "steps": args.steps,
                "window": asdict(win),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="macOS iPhone 镜像窗口：点击 / 滑动 / 截图")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="查询镜像进程与窗口位置")
    p_status.set_defaults(func=cmd_status)

    p_focus = sub.add_parser("focus", help="前置镜像窗口")
    p_focus.set_defaults(func=cmd_focus)

    p_cap = sub.add_parser("capture", help="截取镜像窗口区域")
    p_cap.add_argument("--out", default=".tmp/iphone_mirror.png", help="输出 PNG 路径")
    p_cap.add_argument("--focus", action="store_true", help="截图前先前置窗口")
    p_cap.set_defaults(func=cmd_capture)

    p_obs = sub.add_parser("observe", help="前置窗口 + 截图 + 输出 JSON（Agent 读图用）")
    p_obs.add_argument("--out", default=".tmp/iphone_mirror.png")
    p_obs.set_defaults(func=cmd_observe)

    p_cur = sub.add_parser("cursor", help="仅移动鼠标到目标点（不点击）")
    g0 = p_cur.add_mutually_exclusive_group(required=True)
    g0.add_argument("--pct", nargs=2, type=float, metavar=("X", "Y"))
    g0.add_argument("--screen", nargs=2, type=int, metavar=("X", "Y"))
    p_cur.set_defaults(func=cmd_cursor)

    p_aim = sub.add_parser("aim", help="移鼠标到目标点 + 带光标截图核对")
    g_aim = p_aim.add_mutually_exclusive_group(required=True)
    g_aim.add_argument("--pct", nargs=2, type=float, metavar=("X", "Y"))
    g_aim.add_argument("--screen", nargs=2, type=int, metavar=("X", "Y"))
    p_aim.add_argument("--out", default=".tmp/iphone_aim.png")
    p_aim.set_defaults(func=cmd_aim)

    p_tap = sub.add_parser("tap", help="在镜像窗口内点击")
    g = p_tap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pct", nargs=2, type=float, metavar=("X", "Y"), help="窗口内百分比 0–100")
    g.add_argument("--screen", nargs=2, type=int, metavar=("X", "Y"), help="屏幕绝对坐标")
    p_tap.add_argument("--focus", action="store_true", help="点击前先前置窗口")
    p_tap.add_argument("--delay-ms", type=int, default=0, help="点击前等待毫秒")
    p_tap.set_defaults(func=cmd_tap)

    p_sw = sub.add_parser("swipe", help="在镜像窗口内滑动（多段 click 模拟）")
    g1 = p_sw.add_mutually_exclusive_group(required=True)
    g1.add_argument("--from-pct", nargs=2, type=float, metavar=("X", "Y"))
    g1.add_argument("--from-screen", nargs=2, type=int, metavar=("X", "Y"))
    g2 = p_sw.add_mutually_exclusive_group(required=True)
    g2.add_argument("--to-pct", nargs=2, type=float, metavar=("X", "Y"))
    g2.add_argument("--to-screen", nargs=2, type=int, metavar=("X", "Y"))
    p_sw.add_argument("--steps", type=int, default=10, help="滑动分段数")
    p_sw.add_argument("--pause-ms", type=int, default=30, help="分段间隔毫秒")
    p_sw.add_argument("--focus", action="store_true")
    p_sw.set_defaults(func=cmd_swipe)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
