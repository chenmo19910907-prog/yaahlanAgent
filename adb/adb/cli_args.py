"""CLI 参数解析辅助（capture / fast / rtl / popup gate）。"""

from __future__ import annotations

import argparse

from .tunnel_verify import resolve_momoid


def use_adaptation(args: argparse.Namespace) -> bool:
    return not getattr(args, "no_adapt", False)


def rtl_mode(args: argparse.Namespace) -> str:
    if getattr(args, "no_rtl", False):
        return "off"
    if getattr(args, "rtl", False):
        return "on"
    return "off"


def resolve_capture_mode(
    *,
    explicit: str | None,
    no_capture: bool,
    default: str,
    fast: bool = False,
) -> str:
    if no_capture:
        return "never"
    if fast and explicit is None:
        return "never"
    return explicit or default


def is_fast_mode(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "fast", False))


def apply_fast_tunnel_args(args: argparse.Namespace) -> None:
    """--fast：加快 Tunnel 轮询（不缩短 wait，保证抓包准确性）。"""
    if not is_fast_mode(args):
        return
    if int(getattr(args, "tunnel_poll_ms", 1500)) >= 1500:
        args.tunnel_poll_ms = 1000


def popup_gate_auto_enabled(args: argparse.Namespace) -> bool:
    return not bool(getattr(args, "no_popup_gate", False))


def optional_momoid_from_args(args: argparse.Namespace) -> str | None:
    if not getattr(args, "tunnel_momoid", None) and not getattr(
        args, "tunnel_account", None
    ):
        return None
    return resolve_momoid(
        momoid=getattr(args, "tunnel_momoid", None),
        account=getattr(args, "tunnel_account", None),
    )
