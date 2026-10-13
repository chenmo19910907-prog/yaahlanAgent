#!/usr/bin/env python3
"""将 Markdown 覆写到钉钉 alidocs 文档（Open API overwriteContent）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402

DOC_OVERWRITE_API = (
    "https://api.dingtalk.com/v1.0/doc/suites/documents/{doc_key}/overwriteContent"
)
_NODE_RE = re.compile(r"/i/nodes/([^?/#]+)")


def _extract_node_id(url_or_id: str) -> str:
    raw = (url_or_id or "").strip()
    if not raw:
        raise SystemExit("缺少文档 URL 或 nodeId")
    m = _NODE_RE.search(raw)
    return m.group(1) if m else raw


async def overwrite_markdown(*, doc_key: str, markdown: str, operator_id: str | None = None) -> dict:
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    op = (operator_id or operator).strip()
    if not op:
        raise RuntimeError("缺少 operatorId")
    url = f"{DOC_OVERWRITE_API.format(doc_key=doc_key)}?operatorId={op}"
    payload = {"dataType": "markdown", "content": markdown}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "x-acs-dingtalk-access-token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8")
            return {"status": resp.status, "body": body}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"覆写失败 HTTP {exc.code}: {body[:800]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown 覆写钉钉文档")
    parser.add_argument("--url", help="钉钉文档 URL")
    parser.add_argument("--doc-key", help="文档 docKey / dentryUuid（32 位）")
    parser.add_argument("--markdown-file", required=True, help="本地 Markdown 文件")
    parser.add_argument("--operator-id", help="操作者 unionId（默认从 Excel token 获取）")
    args = parser.parse_args()

    doc_key = (args.doc_key or "").strip() or _extract_node_id(args.url or "")
    md_path = Path(args.markdown_file).expanduser().resolve()
    if not md_path.is_file():
        print(f"[FAIL] 文件不存在: {md_path}", file=sys.stderr)
        return 1
    content = md_path.read_text(encoding="utf-8")
    if len(content) > 50000:
        print(f"[FAIL] 内容超过 50000 字符限制: {len(content)}", file=sys.stderr)
        return 1

    try:
        result = asyncio.run(
            overwrite_markdown(
                doc_key=doc_key,
                markdown=content,
                operator_id=args.operator_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    doc_url = args.url or f"https://alidocs.dingtalk.com/i/nodes/{doc_key}"
    print(doc_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
