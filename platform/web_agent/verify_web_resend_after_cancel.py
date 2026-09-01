#!/usr/bin/env python3
"""Web Agent：中断后立刻重发时，旧 run 的 SSE 不应再次回填输入框。"""

from __future__ import annotations

import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
CHAT_HTML = WEB_AGENT_DIR / "chat.html"


def main() -> int:
    html = CHAT_HTML.read_text(encoding="utf-8")
    required = [
        "function makeRunToken()",
        "function isActiveRun(sessionId",
        "function disposeRunResources(run)",
        "function listenOrphanRunStream(sessionId",
        "run.draftRestored = true",
        "if (run.draftRestored) return false;",
        "restoreSentDraft(sessionId, { runToken:",
        "runToken: makeRunToken()",
        "disposeRunResources(activeRuns.get(sessionId))",
        "if (!existing || existing.runToken !== runToken || existing.cancelling)",
        "if (!run || run.runToken !== runToken) return;",
        "await attachRunStream(sessionId, run_id, { runToken })",
        "if (!isActiveRun(sessionId, { runToken, runId }))",
        "finishRun(sessionId, runToken)",
        "stopRunStreamPoll(sessionId, runToken)",
        "streamDetach({ orphan = false",
        "if (existing?.sentDraft)",
        "if (activeRuns.get(sid)?.sentDraft) return;",
        "if (priorRun && isCurrentSessionStreaming() && !priorRun.cancelling) return;",
    ]
    missing = [token for token in required if token not in html]
    if missing:
        for token in missing:
            print(f"FAIL: chat.html 缺少 {token}")
        return 1
    print("[PASS] verify_web_resend_after_cancel")
    return 0


if __name__ == "__main__":
    sys.exit(main())
