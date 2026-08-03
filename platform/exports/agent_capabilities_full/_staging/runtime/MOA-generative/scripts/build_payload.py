#!/usr/bin/env python3
"""Build an executable MOA-generative payload from capture body + ServiceUrl + Method."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


_DEFAULT_META = {
    "type": "moa",
    "key": "momo.pt.toB.cosmos-server.quality-platform.codequality",
    "settings": {
        "time": 10000,
        "group": "default",
        "host": "",
        "headerType": "TXT",
    },
    "region": "alpha",
    "env": "alpha",
    "cluster": "stage",
    "server": "config",
    "momoId": "df4c6f364f9fcae3",
    "momoName": "e88aa376b29864ad",
}


def _load_body(args: argparse.Namespace) -> dict[str, Any]:
    if args.body_file:
        raw = Path(args.body_file).read_text(encoding="utf-8")
        data = json.loads(raw)
    elif args.body_json:
        data = json.loads(args.body_json)
    else:
        raise SystemExit("必须提供 --body-file 或 --body-json")
    if not isinstance(data, dict):
        raise SystemExit("body 必须是 JSON object")
    return data


def build_payload(
    *,
    url: str,
    method: str,
    body: dict[str, Any],
    timeout_ms: int = 10000,
) -> dict[str, Any]:
    header_s = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    payload = dict(_DEFAULT_META)
    payload["url"] = url.strip()
    payload["method"] = method.strip()
    payload["header"] = header_s
    payload["settings"] = dict(payload["settings"])
    payload["settings"]["time"] = int(timeout_ms)
    payload["params"] = [
        {
            "name": 0,
            "title": 0,
            "txt": "",
            "json": header_s,
            "type": "json",
            "value": body,
        }
    ]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MOA-generative: capture body + ServiceUrl + Method → moa_execute payload"
    )
    parser.add_argument("--url", required=True, help="调用链 ServiceUrl，如 /service/feed/external/feed-interact-stage")
    parser.add_argument("--method", required=True, help="MOA method，如 likeContent / signIn")
    parser.add_argument("--body-file", help="抓包 request body 的 JSON 文件")
    parser.add_argument("--body-json", help="抓包 request body 的 JSON 字符串")
    parser.add_argument("--out", required=True, help="输出 payload 路径")
    parser.add_argument("--timeout-ms", type=int, default=10000, help="settings.time（默认 10000）")
    parser.add_argument("--print", action="store_true", help="同时打印到 stdout")
    args = parser.parse_args()

    body = _load_body(args)
    payload = build_payload(
        url=args.url,
        method=args.method,
        body=body,
        timeout_ms=args.timeout_ms,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    out.write_text(text + "\n", encoding="utf-8")
    if args.print:
        print(text)
    print(f"wrote {out}", file=sys.stderr)
    print(
        f"next: python3 MOA/moa_execute.py --payload-file {out} --timeout-ms {args.timeout_ms}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
