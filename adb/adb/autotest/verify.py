"""自动化用例验收点执行。"""

from __future__ import annotations

import time
from typing import Any

from ..activity import get_foreground_activity
from ..screenshot import capture_screenshot
from ..tunnel_verify import TunnelVerifyOptions, resolve_momoid, wait_for_tunnel


def _resolve_account_ref(value: str, account: dict[str, Any]) -> str:
    text = str(value or "").strip()
    if text.startswith("account."):
        key = text.split(".", 1)[1]
        return str(account.get(key, "")).strip()
    return text


def run_verify_point(
    *,
    spec: dict[str, Any],
    serial: str,
    account: dict[str, Any],
    screenshot_dir: Any,
    max_screenshots: int,
    start_time: int,
    last_screenshot: dict[str, Any] | None,
) -> dict[str, Any]:
    method = str(spec.get("method") or "").strip().lower()
    point_id = str(spec.get("id") or spec.get("name") or method)
    name = str(spec.get("name") or point_id)

    if method == "tunnel":
        alias = _resolve_account_ref(str(spec.get("account") or "account.alias"), account)
        momoid = resolve_momoid(
            momoid=str(spec.get("momoid") or "").strip() or None,
            account=alias or str(account.get("alias") or ""),
        )
        keyword = str(spec.get("keyword") or "").strip()
        if not keyword:
            raise ValueError(f"验收点 {point_id} tunnel 缺少 keyword")
        expect_ec = spec.get("expectEc")
        opts = TunnelVerifyOptions(
            momoid=momoid,
            keyword=keyword,
            wait_seconds=int(spec.get("waitSeconds") or 30),
            poll_interval_ms=int(spec.get("pollIntervalMs") or 2000),
            expect_response_ec=int(expect_ec) if expect_ec is not None else 200,
            since_buffer_seconds=int(spec.get("sinceBufferSeconds") or 5),
            g_appid=str(spec.get("gAppid") or "All"),
            g_env=str(spec.get("gEnv") or "alpha"),
            min_matches=int(spec.get("minMatches") or 1),
        )
        result = wait_for_tunnel(opts, start_time=start_time)
        ok = bool(result.get("ok"))
        return {
            "id": point_id,
            "name": name,
            "method": method,
            "ok": ok,
            "detail": result,
            "message": "抓包验收通过" if ok else str(result.get("error") or "抓包验收失败"),
        }

    if method == "activity":
        activity = get_foreground_activity(serial=serial)
        expect_hint = str(spec.get("expectHint") or "").strip()
        expect_short = str(spec.get("expectShortName") or "").strip()
        actual_hint = str(activity.get("hint") or "")
        actual_short = str(activity.get("shortName") or "")
        ok = True
        if expect_hint:
            ok = actual_hint == expect_hint
        if expect_short:
            ok = ok and actual_short == expect_short
        expect_desc = expect_short or expect_hint or "（任意）"
        actual_desc = actual_short or actual_hint or "unknown"
        return {
            "id": point_id,
            "name": name,
            "method": method,
            "ok": ok,
            "detail": activity,
            "message": (
                f"Activity 符合 {expect_desc}"
                if ok
                else f"Activity 不符：期望 {expect_desc}，实际 {actual_desc}"
            ),
        }

    if method == "screenshot":
        shot = last_screenshot
        if spec.get("captureFresh"):
            shot = capture_screenshot(
                serial=serial,
                directory=screenshot_dir,
                max_keep=max_screenshots,
            )
        ok = isinstance(shot, dict) and bool(shot.get("path"))
        required = spec.get("required", True)
        if not required and not ok:
            ok = True
        return {
            "id": point_id,
            "name": name,
            "method": method,
            "ok": ok,
            "detail": shot,
            "message": "截图已留存" if ok else "缺少截图",
        }

    if method == "sleep":
        seconds = float(spec.get("seconds") or 1)
        time.sleep(max(seconds, 0))
        return {
            "id": point_id,
            "name": name,
            "method": method,
            "ok": True,
            "detail": {"seconds": seconds},
            "message": f"等待 {seconds}s",
        }

    raise ValueError(f"未知验收方式 method={method!r}（验收点 {point_id}）")
