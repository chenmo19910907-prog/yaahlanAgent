#!/usr/bin/env python3
"""Publish feed comment via MOA feed-comment-stage.publishComment."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_URL = "/service/feed/external/feed-comment-stage"


def _safe_json_loads(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        cleaned = "".join(ch if ord(ch) >= 32 or ch in "\n\r\t" else " " for ch in raw)
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {}


def _write_body(path: Path, *, user_id: str, feed_id: str, content: str, source: str) -> None:
    body = {
        "userId": user_id,
        "uid": user_id,
        "feedId": feed_id,
        "content": content,
        "source": source,
        "appId": "2005",
        "area": "MENA",
        "lang": "en",
        "os": "android",
        "osType": "android",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="动态帖子评论（MOA publishComment）")
    parser.add_argument("--user-id", required=True, help="评论人 userId")
    parser.add_argument("--feed-id", required=True, help="帖子 feedId，如 7070612_100461128")
    parser.add_argument("--content", required=True, help="评论内容")
    parser.add_argument(
        "--source",
        default="discover",
        help="来源场景，默认 discover（发现页）",
    )
    parser.add_argument("--timeout-ms", type=int, default=20000)
    parser.add_argument(
        "--workdir",
        default=str(_REPO / ".tmp" / "feed_comment_form"),
        help="中间 body/payload 目录",
    )
    args = parser.parse_args()

    user_id = str(args.user_id).strip()
    feed_id = str(args.feed_id).strip()
    content = str(args.content)
    if not user_id or not feed_id or not content.strip():
        print(json.dumps({"ok": False, "error": "user-id / feed-id / content 不能为空"}, ensure_ascii=False))
        return 2

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    body_path = work / "body.json"
    _write_body(body_path, user_id=user_id, feed_id=feed_id, content=content, source=args.source)

    proc = subprocess.run(
        [
            "python3",
            str(_REPO / "MOA-generative" / "scripts" / "run_generative_moa.py"),
            "--url",
            _URL,
            "--method",
            "publishComment",
            "--body-file",
            str(body_path),
            "--out",
            str(work / "payload.json"),
            "--timeout-ms",
            str(args.timeout_ms),
            "--strict",
            "1",
        ],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=max(60, args.timeout_ms // 1000 + 30),
        check=False,
    )
    summary = _safe_json_loads(proc.stdout or "")
    if not summary:
        summary = {
            "ok": False,
            "error": "run_generative_moa 无 JSON 输出",
            "returncode": proc.returncode,
            "stderrTail": (proc.stderr or "")[-400:],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    biz = summary.get("business") or {}
    data = biz.get("data") if isinstance(biz.get("data"), dict) else {}
    report = {
        "ok": bool(summary.get("ok")),
        "userId": user_id,
        "feedId": feed_id,
        "content": content,
        "commentId": data.get("commentId"),
        "ec": biz.get("ec"),
        "em": biz.get("em"),
        "payloadPath": str(work / "payload.json"),
    }
    if not summary.get("ok"):
        report["error"] = summary.get("error") or biz.get("em") or "MOA 评论失败"
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from exc
