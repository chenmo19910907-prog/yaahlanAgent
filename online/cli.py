"""线上环境统一 CLI（Admin / MOA / Tunnel）。"""

from __future__ import annotations

import argparse
import subprocess
import sys

from env import ensure_online_env
from paths import repo_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="线上环境统一入口（Admin / MOA / Tunnel）；用户提示词须含「线上环境」",
    )
    sub = parser.add_subparsers(dest="service", required=True)
    sub.add_parser("admin", help="线上 Admin（queryUserDetail 等）")
    sub.add_parser("moa", help="线上 MOA（手机号查 userId 等）")
    sub.add_parser("tunnel", help="线上 Tunnel 抓包（g_env=overseas）")
    return parser


def _run(module: str, remainder: list[str]) -> int:
    root = repo_root()
    executables = {
        "admin": root / "Admin" / "admin_execute.py",
        "moa": root / "MOA" / "moa_execute.py",
        "tunnel": root / "Tunnel" / "tunnel_execute.py",
    }
    entry = executables[module]
    if not entry.is_file():
        print(f"ERROR: 缺少入口 {entry}", file=sys.stderr)
        return 2

    cmd = ["python3", str(entry), "--线上环境", *remainder]
    proc = subprocess.run(cmd, cwd=str(root))
    return int(proc.returncode)


def main(argv: list[str] | None = None) -> int:
    ensure_online_env()
    parser = build_parser()
    args, remainder = parser.parse_known_args(argv)
    if not args.service:
        parser.print_help()
        return 2
    return _run(args.service, remainder)


if __name__ == "__main__":
    raise SystemExit(main())
