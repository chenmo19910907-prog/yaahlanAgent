# -*- coding: utf-8 -*-
"""O.O 竞速客户端：只打第一枪，不 cancel / 不二选。"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from competition_1024.constants import DEFAULT_API_BASE


class CompetitionClient:
    def __init__(self, token: str, base_url: str = DEFAULT_API_BASE):
        self.token = token.strip()
        self.base = base_url.rstrip("/")

    def _headers(self, auth: bool) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(self, method: str, path: str, body: dict | None = None, *, auth: bool = True) -> dict[str, Any]:
        url = f"{self.base}{path}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=self._headers(auth))
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            payload = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"success": False, "http_status": e.code, "raw": payload}

    def fetch_broadcast(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/broadcast", auth=False)

    def parse(self, text: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/parse", {"text": text})

    def dispatch(self, broadcast_id: str, parse_id: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/dispatch", {"broadcast_id": broadcast_id, "parse_id": parse_id})

    def model_check(self, text: str) -> dict[str, Any]:
        return self._request("POST", "/api/v1/model/check", {"text": text})

    def pick_parse_id(self, parse_resp: dict[str, Any]) -> str | None:
        demands = parse_resp.get("demands") or []
        if not demands:
            return None
        # 服务端已带 parse_id；单输出时取第一条
        return demands[0].get("parse_id")


def run_one_shot(token: str | None = None, base_url: str | None = None) -> dict[str, Any]:
    token = token or os.environ.get("COMPETITION_1024_TOKEN", "")
    if not token:
        raise SystemExit("需要 COMPETITION_1024_TOKEN 或 --token")
    client = CompetitionClient(token, base_url or os.environ.get("COMPETITION_1024_API", DEFAULT_API_BASE))
    bc = client.fetch_broadcast()
    text = bc.get("text") or ""
    bid = bc.get("broadcast_id") or ""
    if not text:
        return {"step": "broadcast", "broadcast": bc, "action": "skip_empty"}
    pr = client.parse(text)
    if not pr.get("success", True) and pr.get("code"):
        return {"broadcast_id": bid, "parse": pr, "action": "parse_failed"}
    pid = client.pick_parse_id(pr)
    if not pid:
        return {"broadcast_id": bid, "parse": pr, "action": "no_demands"}
    t0 = time.time()
    dr = client.dispatch(bid, pid)
    return {
        "broadcast_id": bid,
        "parse_id": pid,
        "dispatch": dr,
        "elapsed_sec": round(time.time() - t0, 3),
        "action": "dispatched",
    }
