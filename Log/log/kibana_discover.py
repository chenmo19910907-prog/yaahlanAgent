"""Kibana Discover bsearch 查询（与 Discover 搜索框短语 AND 等价）。"""

from __future__ import annotations

import base64
import json
import uuid
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import kibana_base_url, kibana_bsearch_path, kibana_index, kibana_version

TZ8 = timezone(timedelta(hours=8))


class KibanaDiscoverError(Exception):
    def __init__(self, step: str, message: str) -> None:
        self.step = step
        self.message = message
        super().__init__(f"{step}: {message}")


@dataclass
class LogHit:
    timestamp_utc: str
    line: str
    service: str
    host: str
    fields: dict[str, list[Any]]


def day_range_utc8(day: datetime) -> tuple[str, str]:
    """东八区自然日 → ES range gte/lte（UTC ISO）。"""
    if day.tzinfo is None:
        day = day.replace(tzinfo=TZ8)
    start = day.astimezone(TZ8).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start.replace(hour=23, minute=59, second=59, microsecond=999000)
    gte = start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    lte = end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return gte, lte


def hours_range_utc8(hours: float, *, now: datetime | None = None) -> tuple[str, str]:
    ref = now or datetime.now(TZ8)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=TZ8)
    gte_dt = ref - timedelta(hours=hours)
    gte = gte_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    lte = ref.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return gte, lte


def _phrase_filters(phrases: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q in phrases:
        q = q.strip()
        if not q:
            continue
        out.append({"multi_match": {"type": "phrase", "query": q, "lenient": True}})
    return out


def build_bsearch_batch(
    *,
    index: str,
    phrases: list[str],
    gte: str,
    lte: str,
    size: int,
    track_total: bool,
) -> dict[str, Any]:
    filters = _phrase_filters(phrases)
    filters.append(
        {
            "range": {
                "@timestamp": {
                    "format": "strict_date_optional_time",
                    "gte": gte,
                    "lte": lte,
                }
            }
        }
    )
    query_body = {
        "sort": [{"@timestamp": {"order": "desc", "unmapped_type": "boolean"}}],
        "fields": [
            {"field": "*", "include_unmapped": "true"},
            {"field": "@timestamp", "format": "strict_date_optional_time"},
        ],
        "size": size,
        "version": True,
        "script_fields": {},
        "stored_fields": ["*"],
        "runtime_mappings": {},
        "_source": False,
        "query": {"bool": {"must": [], "filter": filters, "should": [], "must_not": []}},
    }
    session_id = str(uuid.uuid4())
    doc_req = {
        "request": {
            "params": {"index": index, "body": {**query_body, "track_total_hits": False}},
        },
        "options": {
            "sessionId": session_id,
            "isRestore": False,
            "strategy": "ese",
            "isStored": False,
            "executionContext": {
                "type": "application",
                "name": "discover",
                "description": "fetch documents",
                "url": "/alpha-public/app/discover",
                "id": "",
            },
        },
    }
    batch = [doc_req]
    if track_total:
        total_body = {
            "size": 0,
            "script_fields": {},
            "stored_fields": ["*"],
            "runtime_mappings": {},
            "query": query_body["query"],
            "track_total_hits": True,
        }
        batch.append(
            {
                "request": {"params": {"index": index, "body": total_body}},
                "options": {
                    "sessionId": session_id,
                    "isRestore": False,
                    "strategy": "ese",
                    "isStored": False,
                    "executionContext": {
                        "type": "application",
                        "name": "discover",
                        "description": "fetch chart data and total hits",
                        "url": "/alpha-public/app/discover",
                        "id": "",
                    },
                },
            }
        )
    return {"batch": batch}


def decode_bsearch_line(line: str) -> dict[str, Any]:
    raw = zlib.decompress(base64.b64decode(line.strip()))
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise KibanaDiscoverError("decode", "bsearch 行不是 JSON object")
    return obj


def parse_bsearch_response(body: bytes) -> tuple[int | None, list[LogHit]]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        raise KibanaDiscoverError("response", "空响应体")
    lines = [ln for ln in text.split("\n") if ln.strip()]
    total: int | None = None
    hits: list[LogHit] = []
    for line in lines:
        obj = decode_bsearch_line(line)
        result = obj.get("result")
        if not isinstance(result, dict):
            continue
        raw_resp = result.get("rawResponse")
        if not isinstance(raw_resp, dict):
            continue
        hit_block = raw_resp.get("hits")
        if not isinstance(hit_block, dict):
            continue
        if raw_resp.get("aggregations") is not None or hit_block.get("total") is not None:
            t = hit_block.get("total")
            if isinstance(t, int):
                total = t
            elif isinstance(t, dict) and isinstance(t.get("value"), int):
                total = t["value"]
        for h in hit_block.get("hits") or []:
            if not isinstance(h, dict):
                continue
            fields = h.get("fields")
            if not isinstance(fields, dict):
                continue
            ts = fields.get("@timestamp", [""])[0] if fields.get("@timestamp") else ""
            line_val = fields.get("line", [""])[0] if fields.get("line") else ""
            svc = fields.get("service", [""])[0] if fields.get("service") else ""
            host = fields.get("host", [""])[0] if fields.get("host") else ""
            hits.append(
                LogHit(
                    timestamp_utc=str(ts),
                    line=str(line_val),
                    service=str(svc),
                    host=str(host),
                    fields=fields,
                )
            )
    return total, hits


def bsearch(
    *,
    phrases: list[str],
    gte: str,
    lte: str,
    index: str | None = None,
    size: int = 20,
    track_total: bool = True,
    cookie: str | None = None,
    timeout_sec: float = 120.0,
) -> tuple[int | None, list[LogHit]]:
    base = kibana_base_url()
    if not base:
        raise KibanaDiscoverError("config", "未配置 KIBANA_BASE_URL 或 Log/config.json kibanaBaseUrl")
    idx = index or kibana_index()
    url = f"{base}{kibana_bsearch_path()}?compress=true"
    payload = build_bsearch_batch(
        index=idx,
        phrases=phrases,
        gte=gte,
        lte=lte,
        size=size,
        track_total=track_total,
    )
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "kbn-version": kibana_version(),
        "Origin": base,
        "Referer": f"{base}/alpha-public/app/discover",
    }
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            status = resp.getcode()
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise KibanaDiscoverError("http", f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise KibanaDiscoverError("http", str(exc.reason)) from exc
    if status != 200:
        raise KibanaDiscoverError("http", f"HTTP {status}")
    return parse_bsearch_response(body)


def format_ts_beijing(ts_utc: str) -> str:
    if not ts_utc:
        return ""
    try:
        if ts_utc.endswith("Z"):
            dt = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(ts_utc)
        return dt.astimezone(TZ8).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts_utc
