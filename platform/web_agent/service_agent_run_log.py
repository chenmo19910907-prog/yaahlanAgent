"""本轮 Web run 内服务端 Agent 问答落盘，供最终回复附问答概述。"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent / "data" / "service_agent_run_log"
QUESTION_MAX_CHARS = 240
ANSWER_SUMMARY_MAX_CHARS = 360
ANSWER_RAW_MAX_CHARS = 2400
MAX_ENTRIES = 20
VALID_REPLY_MODES = frozenset({"concise", "standard", "detailed"})
SUMMARY_TITLE_RE = re.compile(r"^##\s+.+\s+问答概述\s*$", re.MULTILINE)
COMBINED_QA_LINE_RE = re.compile(
    r"^(\*\*)?(?P<num>\d+)\.\s*(?:\*\*)?\s*问(?:\*\*)?[：:]\s*(?P<q>.+?)\s+(?:\*\*)?答(?:\*\*)?[：:]\s*(?P<a>.+?)(\*\*)?\s*$"
)
OLD_QA_QUESTION_LINE_RE = re.compile(r"^\*\*(?P<num>\d+)\.\s*问\*\*[：:]\s*(?P<q>.+?)\s*$")
OLD_QA_ANSWER_LINE_RE = re.compile(r"^\*\*答\*\*[：:]\s*(?P<a>.+?)\s*$")
SPLIT_QA_QUESTION_LINE_RE = re.compile(
    r"^(?P<num>\d+)\.\s*\*\*问\*\*[：:]\s*(?P<q>.+?)\s*$"
)
SPLIT_QA_ANSWER_LINE_RE = re.compile(
    r"^\s*\*\*答\*\*[：:]\s*(?P<a>.+?)\s*$"
)


@dataclass(frozen=True)
class ServiceAgentExchange:
    question: str
    answer_summary: str
    agent_label: str = "服务端 Agent"
    status: str = "completed"
    answer_raw: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "question": self.question,
            "answer_summary": self.answer_summary,
            "agent_label": self.agent_label,
            "status": self.status,
            "answer_raw": self.answer_raw or self.answer_summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceAgentExchange:
        answer_summary = str(data.get("answer_summary") or "")
        answer_raw = str(data.get("answer_raw") or answer_summary)
        return cls(
            question=str(data.get("question") or ""),
            answer_summary=answer_summary,
            agent_label=str(data.get("agent_label") or "服务端 Agent"),
            status=str(data.get("status") or "completed"),
            answer_raw=answer_raw,
        )


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}.json"


def _log_path(user_key: str) -> Path:
    return LOG_DIR / _safe_filename(user_key)


def _normalize_line(text: str) -> str:
    return " ".join((text or "").split())


def _truncate_raw(text: str, *, limit: int) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if len(raw) <= limit:
        return raw
    return raw[: limit - 1] + "…"


def _truncate(text: str, *, limit: int) -> str:
    line = _normalize_line(text)
    if not line:
        return ""
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def _normalize_reply_mode(mode: str | None) -> str:
    value = str(mode or "").strip()
    return value if value in VALID_REPLY_MODES else "standard"


def _summary_limits(mode: str | None) -> tuple[int, int, int]:
    """返回 (question_limit, answer_limit, max_paragraphs)。"""
    normalized = _normalize_reply_mode(mode)
    if normalized == "concise":
        return 100, 72, 1
    if normalized == "detailed":
        return QUESTION_MAX_CHARS, 720, 3
    return QUESTION_MAX_CHARS, ANSWER_SUMMARY_MAX_CHARS, 1


def _summarize_answer(
    answer: str,
    *,
    error: str = "",
    mode: str | None = "standard",
) -> str:
    question_limit, answer_limit, max_paragraphs = _summary_limits(mode)
    del question_limit
    if error.strip():
        return _truncate(f"查询失败：{error.strip()}", limit=answer_limit)
    raw = (answer or "").strip()
    if not raw:
        return "（无回答）"
    blocks = [block.strip() for block in raw.split("\n\n") if block.strip()]
    chunks: list[str] = []
    for block in blocks:
        if len(chunks) >= max_paragraphs:
            break
        content_lines: list[str] = []
        for line in block.splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            content_lines.append(text.lstrip("-*> ").strip())
        if content_lines:
            chunks.append(" ".join(content_lines))
    if chunks:
        return _truncate(" ".join(chunks), limit=answer_limit)
    return _truncate(raw, limit=answer_limit)


def append_service_agent_exchange(
    user_key: str,
    *,
    question: str,
    answer: str = "",
    agent_label: str = "服务端 Agent",
    error: str = "",
) -> None:
    key = (user_key or "").strip()
    q = _truncate(question, limit=QUESTION_MAX_CHARS)
    if not key or not q:
        return
    answer_raw = _truncate_raw(answer, limit=ANSWER_RAW_MAX_CHARS) if not error.strip() else ""
    entry = ServiceAgentExchange(
        question=q,
        answer_summary=_summarize_answer(answer, error=error, mode="standard"),
        answer_raw=answer_raw,
        agent_label=(agent_label or "服务端 Agent").strip() or "服务端 Agent",
        status="failed" if error.strip() else "completed",
    )
    rows = [item.as_dict() for item in list_service_agent_exchanges(key)]
    rows.append(entry.as_dict())
    if len(rows) > MAX_ENTRIES:
        rows = rows[-MAX_ENTRIES:]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _log_path(key).write_text(
        json.dumps({"user_key": key, "entries": rows, "updated_at": time.time()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_service_agent_exchanges(user_key: str) -> list[ServiceAgentExchange]:
    key = (user_key or "").strip()
    if not key:
        return []
    path = _log_path(key)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out: list[ServiceAgentExchange] = []
    for item in data.get("entries") or []:
        if isinstance(item, dict):
            out.append(ServiceAgentExchange.from_dict(item))
    return out


def body_has_service_agent_summary(text: str) -> bool:
    return bool(SUMMARY_TITLE_RE.search(text or ""))


def dedupe_service_agent_summary_sections(text: str) -> str:
    """正文已含问答概述时保留首段，去掉后续重复块。"""
    raw = (text or "").rstrip()
    matches = list(SUMMARY_TITLE_RE.finditer(raw))
    if len(matches) <= 1:
        return normalize_qa_summary_format(raw)
    head = raw[: matches[1].start()].rstrip()
    while head.endswith("---"):
        head = head[: -len("---")].rstrip()
    return normalize_qa_summary_format(head)


def _format_qa_pair(index: int, question: str, answer: str) -> list[str]:
    """问/答各一段，避免 Markdown 有序列表内换行被 HTML 折叠成同一行。"""
    q = _normalize_line(question)
    a = _normalize_line(answer)
    return [f"**{index}. 问**：{q}", "", f"**答**：{a}"]


def normalize_qa_summary_format(text: str) -> str:
    """问答概述内：合并行拆成问/答两段，并统一为「**N. 问** / 空行 / **答**」。"""
    raw = (text or "").rstrip()
    if not raw or not SUMMARY_TITLE_RE.search(raw):
        return raw
    out: list[str] = []
    pending_q: tuple[int, str] | None = None
    for line in raw.splitlines():
        if not line.strip():
            if pending_q is None:
                out.append(line)
            continue
        combined = COMBINED_QA_LINE_RE.match(line)
        if combined:
            if pending_q is not None:
                out.extend(_format_qa_pair(pending_q[0], pending_q[1], "（无回答）"))
                pending_q = None
            out.extend(
                _format_qa_pair(
                    int(combined.group("num")),
                    combined.group("q"),
                    combined.group("a"),
                )
            )
            continue
        split_q = SPLIT_QA_QUESTION_LINE_RE.match(line)
        if split_q:
            if pending_q is not None:
                out.extend(_format_qa_pair(pending_q[0], pending_q[1], "（无回答）"))
            pending_q = (int(split_q.group("num")), split_q.group("q").strip())
            continue
        split_a = SPLIT_QA_ANSWER_LINE_RE.match(line)
        if split_a and pending_q is not None:
            out.extend(_format_qa_pair(pending_q[0], pending_q[1], split_a.group("a").strip()))
            pending_q = None
            continue
        old_q = OLD_QA_QUESTION_LINE_RE.match(line)
        if old_q:
            if pending_q is not None:
                out.extend(_format_qa_pair(pending_q[0], pending_q[1], "（无回答）"))
            pending_q = (int(old_q.group("num")), old_q.group("q").strip())
            continue
        old_a = OLD_QA_ANSWER_LINE_RE.match(line)
        if old_a and pending_q is not None:
            out.extend(_format_qa_pair(pending_q[0], pending_q[1], old_a.group("a").strip()))
            pending_q = None
            continue
        if pending_q is not None:
            out.extend(_format_qa_pair(pending_q[0], pending_q[1], "（无回答）"))
            pending_q = None
        out.append(line)
    if pending_q is not None:
        out.extend(_format_qa_pair(pending_q[0], pending_q[1], "（无回答）"))
    return "\n".join(out).strip()


def build_service_agent_summary(user_key: str, *, reply_mode: str | None = "standard") -> str:
    entries = list_service_agent_exchanges(user_key)
    if not entries:
        return ""
    question_limit, _, _ = _summary_limits(reply_mode)
    labels = {item.agent_label for item in entries if item.agent_label}
    title = "服务端 Agent 问答概述"
    if len(labels) == 1:
        title = f"{next(iter(labels))} 问答概述"
    lines = [f"## {title}", ""]
    for index, item in enumerate(entries, start=1):
        question = _truncate(item.question, limit=question_limit)
        if item.status == "failed":
            err = item.answer_summary.removeprefix("查询失败：")
            answer = _summarize_answer("", error=err, mode=reply_mode)
        else:
            answer = _summarize_answer(item.answer_raw or item.answer_summary, mode=reply_mode)
        lines.extend(_format_qa_pair(index, question, answer))
        if index < len(entries):
            lines.append("")
    return "\n".join(lines).strip()


def append_service_agent_summary_to_reply(
    body: str,
    user_key: str,
    *,
    reply_mode: str | None = "standard",
) -> str:
    summary = build_service_agent_summary(user_key, reply_mode=reply_mode)
    text = dedupe_service_agent_summary_sections(body)
    if not summary:
        return normalize_qa_summary_format(text)
    if body_has_service_agent_summary(text):
        return normalize_qa_summary_format(text)
    if summary in text:
        return normalize_qa_summary_format(text)
    if text:
        return normalize_qa_summary_format(f"{text}\n\n---\n\n{summary}")
    return summary


def clear_service_agent_run_log(user_key: str) -> None:
    key = (user_key or "").strip()
    if not key:
        return
    try:
        _log_path(key).unlink(missing_ok=True)
    except OSError:
        pass
