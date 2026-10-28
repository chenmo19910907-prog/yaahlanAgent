#!/usr/bin/env python3
"""回归：任务已结束但界面仍停在「思考中」（SSE/304/落盘兜底）。"""

from __future__ import annotations

from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
CHAT_HTML = WEB_AGENT_DIR / "chat.html"


def main() -> int:
    html = CHAT_HTML.read_text(encoding="utf-8")
    required = [
        "finishRun(sessionId, runToken);",
        "await finalizeStreamingShellFromServer(sid);",
        "activeRunEtags.delete(sid);",
        'messages?tail=30`, { cache: \'no-store\' }',
        "findOrphanStreamingShell(sessionId)",
    ]
    ok = True
    for token in required:
        if token not in html:
            print(f"FAIL: chat.html 缺少 {token!r}")
            ok = False
    fn_start = html.find("async function finalizeStreamingShellFromServer")
    fn_end = html.find("\n    function ", fn_start + 1)
    fn_body = html[fn_start:fn_end] if fn_start >= 0 else ""
    if "sessionCacheAwaitingAssistantReply" in fn_body:
        print("FAIL: finalizeStreamingShellFromServer 仍因 sessionCache 跳过落盘兜底")
        ok = False
    if not ok:
        return 1
    print("[PASS] verify_stream_finalize_stuck")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
