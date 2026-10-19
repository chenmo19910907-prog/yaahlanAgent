#!/usr/bin/env python3
"""Web Agent 消息去重：落盘 assistant 后勿重复挂载 streaming shell。"""

from __future__ import annotations

import sys
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
CHAT_HTML = WEB_AGENT_DIR / "chat.html"


def main() -> int:
    html = CHAT_HTML.read_text(encoding="utf-8")
    required = [
        "function messagesHaveAssistantSinceLastUser(msgs)",
        "function shouldAppendStreamingShell(sessionId, msgs)",
        "function findOrphanStreamingShell(sessionId)",
        "function findFinalizedTailShell(sessionId)",
        "function resolveTailMergeShell(sessionId)",
        "function tailAssistantBubbleCount(sessionId)",
        "function assistantContentAlreadyInDom(content)",
        "function mergeAssistantIntoShell(sessionId, shellEl, assistantMsg)",
        "const tailAssistants = msgsToAppend.filter(",
        "shouldAppendStreamingShell(sessionId, msgs)",
        "messagesHaveAssistantSinceLastUser(msgs)",
        "messagesHaveAssistantSinceLastUser(cachedMsgs)",
        "resolveTailMergeShell(sessionId)",
        "assistantContentAlreadyInDom(lastAssistant.content)",
        "run.shellEl = null",
        "function messagesDomMatchesSession(sessionId)",
        "messagesDomMatchesSession(sessionId)",
        "clearMessagesDomRendered()",
        "function pendingUserMatchesServerTail(pendingUser, serverMsgs)",
        "pendingUserMatchesServerTail(pendingUser, list)",
        "if (pendingUserMatchesServerTail(pendingUser, list)) return list;",
        "function appendAssistantMessageToSessionCache(sessionId, assistantMsg)",
        "function insertAssistantForUserTurnInCache(sessionId, assistantMsg, userHint)",
        "function findAssistantShellForUserContent(userText)",
        "showInterruptedReply(sessionId, undefined, {",
        "runToken: cancelRunToken",
        "function filterMessagesAlreadyInDom(msgs)",
        "filterMessagesAlreadyInDom(msgsToAppend)",
        "appendAssistantMessageToSessionCache(sessionId,",
        "const cachedForSync = sessionMessagesCache.get(sessionId)",
        "countLoadedMessageElements() !== merged.length",
        "function refreshSessionMessagesCacheFromServer(sessionId)",
        "refreshSessionMessagesCacheFromServer(sessionId)",
        "!sessionCacheAwaitingAssistantReply(sessionId)",
        "sessionCacheAwaitingAssistantReply(sessionId)",
    ]
    missing = [token for token in required if token not in html]
    if missing:
        for token in missing:
            print(f"FAIL: chat.html 缺少 {token}")
        return 1
    print("[PASS] verify_web_message_dedup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
