#!/usr/bin/env python3
"""意图测试 Tunnel 抓包验收（复用 adb.adb.tunnel_verify + Tunnel 客户端）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adb.adb.tunnel_capture import get_catalog_item, load_catalog  # noqa: E402
from adb.adb.tunnel_verify import (  # noqa: E402
    TunnelVerifyOptions,
    resolve_momoid,
    wait_for_tunnel,
)

_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def _expand(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return os.environ.get(key, m.group(0))

    return _ENV_PATTERN.sub(repl, value)


def _expand_list(items: list[Any] | None) -> list[str]:
    if not items:
        return []
    out: list[str] = []
    for item in items:
        text = _expand(str(item)).strip()
        if text:
            out.append(text)
    return out


def _load_midscene_env() -> None:
    env_path = ROOT / "midscene" / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
            continue
        key, val = trimmed.split("=", 1)
        key = key.strip()
        val = val.strip().split("#", 1)[0].strip()
        if key and key not in os.environ:
            os.environ[key] = val


def _merge_catalog(spec: dict[str, Any]) -> dict[str, Any]:
    catalog_id = str(spec.get("catalogId", "")).strip()
    if not catalog_id:
        return spec
    item = get_catalog_item(catalog_id, load_catalog())
    merged = dict(spec)
    if not merged.get("keyword") and item.get("keyword"):
        merged["keyword"] = item["keyword"]
    if merged.get("expectResponseEc") is None and item.get("expectEc") is not None:
        merged["expectResponseEc"] = item["expectEc"]
    if not merged.get("name") and item.get("name"):
        merged["name"] = item["name"]
    return merged


def _body_text(item: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("url", "request", "response"):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, (dict, list)):
            chunks.append(json.dumps(val, ensure_ascii=False))
        else:
            chunks.append(str(val))
    return "\n".join(chunks)


def _check_contains(item: dict[str, Any], needles: list[str], label: str) -> str | None:
    if not needles:
        return None
    hay = _body_text(item)
    for needle in needles:
        if needle not in hay:
            return f"{label} 未包含 {needle!r}"
    return None


def build_options(spec: dict[str, Any]) -> TunnelVerifyOptions:
    spec = _merge_catalog(spec)
    momoid = _expand(str(spec.get("momoid", ""))).strip()
    account = _expand(str(spec.get("account", ""))).strip()
    keyword = _expand(str(spec.get("keyword", ""))).strip()
    if not keyword:
        raise ValueError("tunnel.keyword 或 catalogId 必填")

    expect_ec = spec.get("expectResponseEc")
    response_ec: int | None
    if expect_ec is None:
        response_ec = None
    else:
        response_ec = int(expect_ec)

    return TunnelVerifyOptions(
        momoid=resolve_momoid(momoid=momoid or None, account=account or None),
        keyword=keyword,
        wait_seconds=max(1, int(spec.get("waitSeconds", 30))),
        poll_interval_ms=max(500, int(spec.get("pollIntervalMs", 2000))),
        expect_http_status=int(spec.get("expectHttpStatus", 200)),
        expect_response_ec=response_ec,
        since_buffer_seconds=max(0, int(spec.get("sinceBufferSeconds", 5))),
        g_appid=_expand(str(spec.get("gAppid", "All"))) or "All",
        g_env=_expand(str(spec.get("gEnv", "alpha"))) or "alpha",
        min_matches=max(1, int(spec.get("minMatches", 1))),
    )


def run_verify(spec: dict[str, Any], *, start_time: int | None = None) -> dict[str, Any]:
    _load_midscene_env()
    spec = dict(spec)
    if start_time is None:
        start_time = int(time.time()) - int(spec.get("sinceBufferSeconds", 5))

    options = build_options(spec)
    result = wait_for_tunnel(options, start_time=start_time)
    result["intentId"] = spec.get("intentId")
    result["catalogId"] = spec.get("catalogId")

    if not result.get("ok"):
        return result

    matches = result.get("matches") or []
    if not matches:
        result["ok"] = False
        result["error"] = "Tunnel 匹配成功但 matches 为空"
        return result

    raw_items = matches
    # wait_for_tunnel 返回 summaries；requestContains 在 summary 上检查 url + responseData
    req_needles = _expand_list(spec.get("requestContains"))
    resp_needles = _expand_list(spec.get("responseContains"))
    req_err = _check_contains(raw_items[0], req_needles, "request/response")
    if req_err:
        result["ok"] = False
        result["error"] = req_err
        return result
    resp_err = _check_contains(raw_items[0], resp_needles, "response")
    if resp_err:
        result["ok"] = False
        result["error"] = resp_err
        return result

    latest = raw_items[0]
    req_time = latest.get("time")
    req_id = latest.get("_id")
    if req_id and req_time:
        result["tunnelUrl"] = (
            f"https://tunnel.wemomo.com/request/{req_id}"
            f"?req_time={req_time}&g_appid={options.g_appid}&g_env={options.g_env}"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="意图测试 Tunnel 验收")
    parser.add_argument("--spec", required=True, help=".tunnel.json 路径")
    parser.add_argument("--start-time", type=int, default=None, help="Unix 秒，默认 now-5")
    parser.add_argument("--out", default=None, help="写入验收结果 JSON")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    result = run_verify(spec, start_time=args.start_time)

    out_path = Path(args.out) if args.out else spec_path.with_suffix(".result.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if result.get("ok"):
        print(f"[tunnel-verify] ✓ {spec.get('intentId', spec_path.stem)} keyword={result.get('keyword')}")
        if result.get("tunnelUrl"):
            print(f"[tunnel-verify]   {result['tunnelUrl']}")
        return 0

    print(f"[tunnel-verify] ✗ {spec.get('intentId', spec_path.stem)}: {result.get('error')}", file=sys.stderr)
    if result.get("recentUrls"):
        print("[tunnel-verify] 近期 URL:", file=sys.stderr)
        for url in result["recentUrls"][:5]:
            print(f"  - {url}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
