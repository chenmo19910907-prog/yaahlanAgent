"""Tunnel 抓包常用验收目录：list / show / run。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .gift_panel_analyze import (
    analyze_gift_panel_from_tunnel,
    find_gifts_from_tunnel,
    verify_backpack_gift_from_tunnel,
)
from .popup_analyze import analyze_scene_from_tunnel
from .tunnel_verify import (
    TunnelVerifyOptions,
    fetch_latest_tunnel_match,
    resolve_momoid,
    wait_for_tunnel,
)

_PLACEHOLDER = re.compile(r"<(\w+)>")


def catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "tunnel_capture_catalog.json"


def load_catalog() -> dict[str, Any]:
    data = json.loads(catalog_path().read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("tunnel_capture_catalog.json 根节点须为 object")
    return data


def catalog_items(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cat = catalog or load_catalog()
    items = cat.get("items")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("id")]


def get_catalog_item(item_id: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    for item in catalog_items(catalog):
        if str(item.get("id")) == item_id:
            return item
    known = "、".join(str(x.get("id")) for x in catalog_items(catalog)) or "（无）"
    raise ValueError(f"未知抓包验收项 {item_id!r}，可选: {known}")


def list_catalog(*, category: str | None = None) -> dict[str, Any]:
    cat = load_catalog()
    items = catalog_items(cat)
    if category:
        key = category.strip().lower()
        items = [
            x
            for x in items
            if key in str(x.get("category", "")).lower()
            or key in str(x.get("id", "")).lower()
        ]
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        c = str(item.get("category") or "其他")
        by_cat.setdefault(c, []).append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "keyword": item.get("keyword"),
                "trigger": item.get("trigger"),
                "command": item.get("command"),
            }
        )
    return {
        "description": cat.get("description"),
        "defaults": cat.get("defaults"),
        "categoryCount": len(by_cat),
        "itemCount": len(items),
        "categories": by_cat,
    }


def show_catalog_item(item_id: str) -> dict[str, Any]:
    return get_catalog_item(item_id)


def _substitute_command(template: str, values: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in values:
            raise ValueError(f"命令模板缺少参数: {key}")
        return values[key]

    return _PLACEHOLDER.sub(repl, template)


def _build_param_values(
    item: dict[str, Any],
    *,
    momoid: str,
    since_seconds: int,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    defaults = load_catalog().get("defaults") or {}
    params = item.get("params") if isinstance(item.get("params"), dict) else {}
    values: dict[str, str] = {
        "userId": momoid,
        "momoid": momoid,
        "sinceSeconds": str(since_seconds),
        "since": str(since_seconds),
        "gEnv": str(defaults.get("gEnv", "alpha")),
        "gAppid": str(defaults.get("gAppid", "All")),
    }
    for k, v in params.items():
        values[str(k)] = str(v)
    if extra:
        for k, v in extra.items():
            if v is not None and str(v).strip() != "":
                values[str(k)] = str(v)
    return values


def _run_shell(command: str, *, cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        command,
        shell=True,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def run_catalog_item(
    item_id: str,
    *,
    momoid: str | None = None,
    account: str | None = None,
    since_seconds: int | None = None,
    extra: dict[str, str] | None = None,
    mode: str = "run",
) -> dict[str, Any]:
    """执行目录项：内置 handler 或渲染 command 后 shell。"""
    item = get_catalog_item(item_id)
    uid = resolve_momoid(momoid=momoid, account=account)
    defaults = load_catalog().get("defaults") or {}
    since = since_seconds if since_seconds is not None else int(defaults.get("sinceSeconds", 600))
    handler = str(item.get("handler") or "shell").strip()
    params = _build_param_values(item, momoid=uid, since_seconds=since, extra=extra)

    out: dict[str, Any] = {
        "id": item_id,
        "name": item.get("name"),
        "category": item.get("category"),
        "momoid": uid,
        "sinceSeconds": since,
        "handler": handler,
        "trigger": item.get("trigger"),
        "keyword": item.get("keyword"),
    }

    if mode == "dry-run":
        cmd = item.get("waitCommand") if mode == "wait" and item.get("waitCommand") else item.get("command")
        if isinstance(cmd, str) and cmd.strip():
            out["command"] = _substitute_command(cmd, params)
        out["dryRun"] = True
        return out

    if handler == "gift_panel_analyze":
        out["result"] = analyze_gift_panel_from_tunnel(
            momoid=uid, since_seconds=since, g_env=params.get("gEnv", "alpha")
        )
        out["ok"] = bool(out["result"].get("apis", {}).get("getGiftTabListV3", {}).get("found"))
        return out

    if handler == "gift_panel_find":
        price_raw = params.get("price")
        price = int(price_raw) if price_raw and str(price_raw).isdigit() else None
        out["result"] = find_gifts_from_tunnel(
            momoid=uid,
            since_seconds=since,
            price=price,
            tab_name=params.get("tabName") or None,
            name_contains=params.get("nameContains") or None,
            g_env=params.get("gEnv", "alpha"),
        )
        out["ok"] = int(out["result"].get("matchedCount") or 0) > 0
        return out

    if handler == "gift_backpack_verify":
        bid = params.get("baseProductId") or params.get("bid")
        num_raw = params.get("num") or params.get("expectRemain")
        expect = int(num_raw) if num_raw and str(num_raw).isdigit() else None
        out["result"] = verify_backpack_gift_from_tunnel(
            momoid=uid,
            base_product_id=bid,
            expected_remain=expect,
            since_seconds=since,
            g_env=params.get("gEnv", "alpha"),
        )
        if expect is not None:
            out["ok"] = bool(out["result"].get("verifyOk"))
        else:
            out["ok"] = int(out["result"].get("matchedCount") or 0) > 0
        return out

    if handler == "popup_scene":
        scene = str(item.get("scene") or "login").strip()
        out["result"] = analyze_scene_from_tunnel(
            scene=scene,
            momoid=uid,
            since_seconds=since,
            g_env=params.get("gEnv", "alpha"),
        )
        out["ok"] = bool(out["result"].get("tunnelOk"))
        return out

    if handler == "tunnel_last":
        keyword = str(item.get("keyword") or "").strip()
        expect_ec = item.get("expectEc")
        result = fetch_latest_tunnel_match(
            momoid=uid,
            keyword=keyword,
            since_seconds=since,
            g_appid=params.get("gAppid", "All"),
            g_env=params.get("gEnv", "alpha"),
        )
        out["result"] = result
        out["ok"] = bool(result.get("ok"))
        if expect_ec is not None and int(result.get("matchedCount") or 0) > 0:
            latest = result.get("latest") or {}
            out["ok"] = out["ok"] and latest.get("responseEc") == int(expect_ec)
        elif expect_ec is not None:
            out["ok"] = False
        return out

    if handler == "tunnel_wait":
        keyword = str(item.get("keyword") or "").strip()
        expect_ec = int(item.get("expectEc") or 200)
        import time

        start = int(time.time()) - max(5, since)
        opts = TunnelVerifyOptions(
            momoid=uid,
            keyword=keyword,
            wait_seconds=25,
            poll_interval_ms=1500,
            expect_response_ec=expect_ec,
            g_appid=params.get("gAppid", "All"),
            g_env=params.get("gEnv", "alpha"),
        )
        result = wait_for_tunnel(opts, start_time=start)
        out["result"] = result
        out["ok"] = bool(result.get("ok"))
        return out

    if handler == "tunnel_list":
        repo = Path(__file__).resolve().parents[2]
        cmd = _substitute_command(
            str(item.get("command") or ""),
            params,
        )
        code, stdout, stderr = _run_shell(f"{cmd} --output json", cwd=repo)
        out["exitCode"] = code
        out["stdout"] = stdout
        out["stderr"] = stderr
        out["ok"] = code == 0
        return out

    # shell：渲染 command 或 waitCommand
    template = item.get("waitCommand") if mode == "wait" and item.get("waitCommand") else item.get("command")
    if not isinstance(template, str) or not template.strip():
        raise ValueError(f"目录项 {item_id} 无 command")
    cmd = _substitute_command(template, params)
    repo = Path(__file__).resolve().parents[2]
    code, stdout, stderr = _run_shell(cmd, cwd=repo)
    out["command"] = cmd
    out["exitCode"] = code
    out["stdout"] = stdout
    out["stderr"] = stderr
    out["ok"] = code == 0
    return out


def emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Tunnel 抓包常用验收目录")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出目录项")
    p_list.add_argument("--category", help="按分类筛选")

    p_show = sub.add_parser("show", help="查看单项详情")
    p_show.add_argument("id", help="目录 id，如 gift_send")

    p_run = sub.add_parser("run", help="执行验收")
    p_run.add_argument("id", help="目录 id")
    p_run.add_argument("--momoid", help="userId")
    p_run.add_argument("--account", help="testAccounts 键名")
    p_run.add_argument("--since", type=int, default=None)
    p_run.add_argument("--dry-run", action="store_true", help="只输出将执行的命令")
    p_run.add_argument("--wait", action="store_true", help="使用 waitCommand（若有）")
    p_run.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="覆盖模板参数")

    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            emit_json(list_catalog(category=getattr(args, "category", None)))
            return 0
        if args.command == "show":
            emit_json(show_catalog_item(args.id))
            return 0
        extra: dict[str, str] = {}
        for pair in getattr(args, "set", []) or []:
            if "=" in pair:
                k, v = pair.split("=", 1)
                extra[k.strip()] = v.strip()
        out = run_catalog_item(
            args.id,
            momoid=getattr(args, "momoid", None),
            account=getattr(args, "account", None),
            since_seconds=getattr(args, "since", None),
            extra=extra or None,
            mode="dry-run" if args.dry_run else ("wait" if args.wait else "run"),
        )
        emit_json(out)
        return 0 if out.get("ok", True) and not args.dry_run else (0 if args.dry_run else 3)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
