#!/usr/bin/env python3
"""Build generative-MOA payload from capture body, then execute via moa_execute.

Exit 0 when the MSE proxy reaches the service (business reject is OK unless --strict).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]

# Import sibling builder without packaging
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_payload import build_payload  # noqa: E402


def _load_body(body_file: str | None, body_json: str | None) -> dict[str, Any]:
    if body_file:
        data = json.loads(Path(body_file).read_text(encoding="utf-8"))
    elif body_json:
        data = json.loads(body_json)
    else:
        raise SystemExit("必须提供 --body-file 或 --body-json")
    if not isinstance(data, dict):
        raise SystemExit("body 必须是 JSON object")
    return data


def _deep_find_em(obj: Any) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("em", "msg", "message") and v is not None:
                out.append(str(v))
            out.extend(_deep_find_em(v))
    elif isinstance(obj, list):
        for x in obj:
            out.extend(_deep_find_em(x))
    return out


def _inner_business(resp: dict[str, Any]) -> dict[str, Any]:
    """Best-effort peel httpproxy wrappers to business result."""
    cur: Any = resp
    for _ in range(4):
        if not isinstance(cur, dict):
            break
        nxt = cur.get("result")
        if isinstance(nxt, dict) and (
            "ec" in nxt or "success" in nxt or "data" in nxt or "code" in nxt
        ):
            # Prefer nested business object when present
            if isinstance(nxt.get("result"), dict) and (
                "ec" in nxt["result"] or "success" in nxt["result"] or "data" in nxt["result"]
            ):
                cur = nxt["result"]
                continue
            if "ec" in nxt or "success" in nxt or "data" in nxt:
                return nxt
        if "ec" in cur or "success" in cur:
            return cur
        if isinstance(nxt, dict):
            cur = nxt
            continue
        break
    return cur if isinstance(cur, dict) else {}


def _proxy_ok(resp: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason). Fail hard on routing / method / cast errors."""
    text = json.dumps(resp, ensure_ascii=False)
    ems = " | ".join(_deep_find_em(resp))
    blow = (text + " " + ems).lower()
    if "no address found" in blow:
        return False, "No address found（ServiceUrl 无效）"
    if "method not found" in blow:
        return False, "Method not found（method 名不对）"
    if "classcastexception" in blow:
        return False, "ClassCastException（body 须 type=json 且 header 双写）"
    outer_ec = resp.get("ec")
    if outer_ec not in (None, 0, 200):
        return False, f"proxy outer ec={outer_ec} em={resp.get('em')}"
    return True, "proxy ok"


def _business_ok(inner: dict[str, Any]) -> bool:
    if not inner:
        return False
    if inner.get("success") is True:
        return True
    ec = inner.get("ec")
    if ec in (0, 200):
        return True
    code = inner.get("code")
    if code in (0, 200):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MOA-generative run: build payload from capture + execute moa_execute"
    )
    parser.add_argument("--url", required=True, help="Call-chain ServiceUrl")
    parser.add_argument("--method", required=True, help="MOA method")
    parser.add_argument("--body-file", help="Capture request body JSON file")
    parser.add_argument("--body-json", help="Capture request body JSON string")
    parser.add_argument(
        "--out",
        default=str(_REPO / ".tmp" / "generative_moa_payload.json"),
        help="Payload output path",
    )
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument(
        "--strict",
        type=int,
        default=0,
        choices=(0, 1),
        help="1=require business success (success=true or ec=200); 0=proxy reachable is enough (default)",
    )
    args = parser.parse_args()
    strict = bool(args.strict)

    body = _load_body(args.body_file, args.body_json)
    payload = build_payload(
        url=args.url,
        method=args.method,
        body=body,
        timeout_ms=args.timeout_ms,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA" / "moa_execute.py"),
            "--payload-file",
            str(out),
            "--timeout-ms",
            str(args.timeout_ms),
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=max(60, args.timeout_ms // 1000 + 30),
        check=False,
    )
    stdout = (proc.stdout or "").strip()
    summary: dict[str, Any] = {
        "ok": False,
        "mode": "strict" if strict else "proxy",
        "url": args.url,
        "method": args.method,
        "payloadPath": str(out),
        "moaReturncode": proc.returncode,
        "stderrTail": (proc.stderr or "")[-400:],
    }

    if "{" not in stdout:
        summary["error"] = "moa_execute 无 JSON 输出"
        summary["stdoutTail"] = stdout[-500:]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    try:
        resp = json.loads(stdout[stdout.find("{") :])
    except json.JSONDecodeError as exc:
        summary["error"] = f"JSON 解析失败: {exc}"
        summary["stdoutTail"] = stdout[-500:]
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    proxy_ok, reason = _proxy_ok(resp)
    inner = _inner_business(resp)
    summary["proxyOk"] = proxy_ok
    summary["proxyReason"] = reason
    summary["business"] = {
        "ec": inner.get("ec"),
        "em": inner.get("em") or inner.get("msg"),
        "success": inner.get("success"),
        "data": inner.get("data"),
    }
    summary["raw"] = resp

    if proc.returncode != 0 and not proxy_ok:
        summary["error"] = f"moa_execute exit={proc.returncode}"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    if not proxy_ok:
        summary["error"] = reason
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    biz_ok = _business_ok(inner)
    summary["businessOk"] = biz_ok
    if strict and not biz_ok:
        summary["error"] = "strict: 业务未成功"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    summary["ok"] = True
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from exc
