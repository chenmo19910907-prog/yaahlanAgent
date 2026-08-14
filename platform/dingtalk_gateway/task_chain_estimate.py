"""基于用户问题与处理逻辑链的任务耗时预估（与历史统计融合）。"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from env_loader import GATEWAY_DIR

CONTEXT_DIR = GATEWAY_DIR / "data" / "batch_progress"

# 单步典型耗时（秒）：MOA/Admin 调用、文件编辑、catalog 刷新等
STEP_MOA_QUERY_S = 5.0
STEP_MOA_MUTATE_S = 7.0
STEP_ADMIN_QUERY_S = 4.0
STEP_TUNNEL_QUERY_S = 8.0
STEP_GIFT_SEND_S = 6.0
STEP_REGISTRY_EDIT_S = 3.0
STEP_GENERATE_INDEX_S = 2.0
STEP_CATALOG_REGEN_S = 2.0
STEP_AGENT_REASON_S = 12.0

# 批量 label → 单项逻辑链（不含 Agent 推理开销）
BATCH_LABEL_CHAINS: dict[str, list[tuple[str, float]]] = {
    "发钻石": [("查手机号→userId", STEP_MOA_QUERY_S), ("MOA发放钻石", STEP_MOA_MUTATE_S)],
    "加钻石": [("查手机号→userId", STEP_MOA_QUERY_S), ("MOA发放钻石", STEP_MOA_MUTATE_S)],
    "加1钻石": [("查手机号→userId", STEP_MOA_QUERY_S), ("MOA发放钻石", STEP_MOA_MUTATE_S)],
    "改等级": [("查 userId", STEP_MOA_QUERY_S), ("MOA 改 VIP 等级", STEP_MOA_MUTATE_S)],
    "房间满级": [
        ("Admin 查 roomId", STEP_ADMIN_QUERY_S),
        ("MOA 查经验+补差升级", STEP_MOA_QUERY_S + STEP_MOA_MUTATE_S),
        ("MOA 验收", STEP_MOA_QUERY_S),
    ],
    "VIP": [("查 userId", STEP_MOA_QUERY_S), ("MOA VIP 操作", STEP_MOA_MUTATE_S)],
    "手机号段互关": [("batch_phone_clique 单项", STEP_MOA_MUTATE_S + 2.0)],
    "查注册": [("Admin/MOA查用户详情", STEP_ADMIN_QUERY_S)],
    "查公会": [("MOA/Admin查公会", STEP_MOA_QUERY_S)],
    "查用户": [("Admin/MOA查用户", STEP_ADMIN_QUERY_S)],
    "送礼": [("查实例与礼物", STEP_MOA_QUERY_S), ("Stage POST送礼", STEP_GIFT_SEND_S)],
    "能力分类": [
        ("改 registry/sources", STEP_REGISTRY_EDIT_S),
        ("generate_index+catalog", STEP_GENERATE_INDEX_S + STEP_CATALOG_REGEN_S),
    ],
    "实名认证拆分": [
        ("改 sources.json", STEP_REGISTRY_EDIT_S),
        ("刷新 catalog", STEP_CATALOG_REGEN_S),
    ],
    "解除风控": [("Admin查设备", STEP_ADMIN_QUERY_S), ("Risk解除+落库", STEP_MOA_MUTATE_S)],
}

LABEL_ALIASES: list[tuple[str, str]] = [
    (r"发钻|发放钻石|加钻", "发钻石"),
    (r"改等级|vip\s*\d|VIP", "VIP"),
    (r"满级\s*房间|房间.*满级|房间等级.*满级", "房间满级"),
    (r"互关|手机号段", "手机号段互关"),
    (r"查注册|注册时间", "查注册"),
    (r"分类|catalog|registry", "能力分类"),
    (r"实名认证", "实名认证拆分"),
    (r"风控|解除设备", "解除风控"),
    (r"送礼|gift", "送礼"),
]

PHONE_RE = re.compile(r"1[3-9]\d{9}")
USER_ID_RE = re.compile(r"\b\d{6,12}\b")


@dataclass(frozen=True)
class TaskChainEstimate:
    """任务处理链预估。"""

    steps: tuple[tuple[str, float], ...]
    batch_count: int = 1
    overhead_s: float = STEP_AGENT_REASON_S
    source: str = "default"

    @property
    def sec_per_cycle(self) -> float:
        return sum(sec for _, sec in self.steps)

    @property
    def total_seconds(self) -> float:
        cycles = max(1, self.batch_count)
        return self.overhead_s + self.sec_per_cycle * cycles

    @property
    def summary(self) -> str:
        if not self.steps:
            return "Agent 执行"
        step_names = "+".join(name for name, _ in self.steps)
        if self.batch_count >= 3:
            return f"{step_names} ×{self.batch_count}项"
        if len(self.steps) == 1:
            return self.steps[0][0]
        return step_names


def _safe_filename(user_key: str) -> str:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()[:24]
    return f"{digest}_context.json"


def save_batch_task_context(user_key: str, prompt: str) -> None:
    """任务开始时保存用户问题，供批量进度 ETA 引用逻辑链。"""
    key = (user_key or "").strip()
    text = (prompt or "").strip()
    if not key or not text:
        return
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTEXT_DIR / _safe_filename(key)
    path.write_text(
        json.dumps({"user_key": key, "prompt": text[:4000]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_batch_task_context(user_key: str) -> str:
    key = (user_key or "").strip()
    if not key:
        return ""
    path = CONTEXT_DIR / _safe_filename(key)
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if isinstance(data, dict):
        return str(data.get("prompt") or "").strip()
    return ""


def clear_batch_task_context(user_key: str) -> None:
    key = (user_key or "").strip()
    if not key:
        return
    path = CONTEXT_DIR / _safe_filename(key)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _count_batch_items(prompt: str) -> int:
    phones = set(PHONE_RE.findall(prompt))
    if len(phones) >= 3:
        return len(phones)
    user_ids = set(USER_ID_RE.findall(prompt))
    if len(user_ids) >= 3:
        return len(user_ids)
    m = re.search(r"(\d+)\s*[个项条]", prompt)
    if m:
        try:
            n = int(m.group(1))
            if n >= 3:
                return n
        except ValueError:
            pass
    return 1


def _resolve_batch_label(label: str, prompt: str = "") -> str:
    text = (label or "").strip()
    if text and text in BATCH_LABEL_CHAINS:
        return text
    combined = f"{text} {prompt}"
    for pattern, canonical in LABEL_ALIASES:
        if re.search(pattern, combined, re.I):
            return canonical
    return text


def _chain_from_batch_label(label: str, *, batch_count: int = 1) -> TaskChainEstimate | None:
    key = _resolve_batch_label(label)
    steps = BATCH_LABEL_CHAINS.get(key)
    if not steps:
        return None
    return TaskChainEstimate(
        steps=tuple(steps),
        batch_count=max(1, batch_count),
        overhead_s=STEP_AGENT_REASON_S * 0.5,
        source=f"batch:{key}",
    )


def analyze_task_chain(
    prompt: str,
    *,
    task_kind: str | None = None,
    batch_label: str = "",
    batch_total: int = 0,
) -> TaskChainEstimate:
    """根据问题文本与任务类型推断处理逻辑链及预估耗时。"""
    text = (prompt or "").strip()
    kind = (task_kind or "").strip()
    batch_count = batch_total if batch_total >= 3 else _count_batch_items(text)
    label_chain = _chain_from_batch_label(batch_label or text, batch_count=batch_count)
    if label_chain is not None and batch_count >= 3:
        return TaskChainEstimate(
            steps=label_chain.steps,
            batch_count=batch_count,
            overhead_s=label_chain.overhead_s,
            source=label_chain.source,
        )
    if label_chain is not None and batch_label:
        return label_chain

    if re.search(r"测试用例|生成用例|写用例", text):
        return TaskChainEstimate(
            steps=(
                ("读需求/PRD", 25.0),
                ("生成用例", 55.0),
                ("写入文件/同步", 15.0),
            ),
            batch_count=1,
            source="agent:testcase",
        )
    if re.search(r"入库|sync_registry|登记.{0,12}MOA", text, re.I):
        return TaskChainEstimate(
            steps=(
                ("写 MOA 模板", 18.0),
                ("sync_registry", 8.0),
                ("刷新使用方法", 5.0),
            ),
            source="agent:moa_registry",
        )
    if kind == "agent:gift" or re.search(r"送礼|gift", text, re.I):
        return TaskChainEstimate(
            steps=(
                ("查实例/礼物/设备", STEP_MOA_QUERY_S + 2),
                ("POST /v2/gift/send", STEP_GIFT_SEND_S),
            ),
            source="agent:gift",
        )
    if kind == "agent:tunnel" or re.search(r"抓包|tunnel", text, re.I):
        return TaskChainEstimate(
            steps=(("Tunnel 查请求列表", STEP_TUNNEL_QUERY_S),),
            source="agent:tunnel",
        )
    if kind == "agent:pk_atm" or re.search(
        r"PK提款机|pk[\s-]?atm|跨房\s*PK|pk-atm-test|来一场.{0,8}PK",
        text,
        re.I,
    ):
        return TaskChainEstimate(
            steps=(
                ("读 MSE/PK 配置", 15.0),
                ("随机匹配跨房 PK", 90.0),
                ("Stage 送礼造数", 120.0),
                ("赛况/返钻验收", 60.0),
            ),
            overhead_s=45.0,
            source="agent:pk_atm",
        )
    if kind == "agent:workflow" or re.search(r"workflow\s+run", text, re.I):
        return TaskChainEstimate(
            steps=(("解析工作流参数", 8.0), ("workflow_execute 执行", 90.0)),
            overhead_s=25.0,
            source="agent:workflow",
        )
    if re.search(r"registry|catalog|分类|generate_index", text, re.I):
        return TaskChainEstimate(
            steps=(
                ("改 registry/sources", STEP_REGISTRY_EDIT_S),
                ("generate_index", STEP_GENERATE_INDEX_S),
                ("刷新 catalog", STEP_CATALOG_REGEN_S),
            ),
            source="agent:registry",
        )
    if kind == "fast:web_agent_restart" or re.fullmatch(
        r"(?:重启|restart)\s*(?:web\s*agent|webagent|网页版\s*agent|网页\s*agent)",
        text,
        re.I,
    ):
        return TaskChainEstimate(
            steps=(("重启 Web Agent", 6.0),),
            overhead_s=0.0,
            source="fast:web_agent_restart",
        )
    if kind == "agent:moa_mutate" or re.search(
        r"发钻|加钻|改等级|vip|背包|发.{0,6}钻石|钻石",
        text,
        re.I,
    ):
        return TaskChainEstimate(
            steps=(
                ("查 userId/设备", STEP_MOA_QUERY_S),
                ("MOA 变更操作", STEP_MOA_MUTATE_S),
            ),
            batch_count=batch_count,
            overhead_s=STEP_AGENT_REASON_S * 0.6,
            source="agent:moa_mutate",
        )
    if kind == "agent:moa_query" or (
        re.search(r"MOA|mse", text, re.I)
        and re.search(r"查询|查\s*user|手机号|userId|\d{6,}", text, re.I)
    ):
        return TaskChainEstimate(
            steps=(("MOA/Admin 查询", STEP_MOA_QUERY_S),),
            overhead_s=STEP_AGENT_REASON_S * 0.5,
            source="agent:moa_query",
        )
    if kind == "agent:code_modify" or re.search(r"修改|代码|网关", text):
        return TaskChainEstimate(
            steps=(
                ("读代码/定位", 20.0),
                ("改逻辑+验证", 45.0),
            ),
            source="agent:code_modify",
        )
    if kind == "agent:query" or re.search(r"查询|查\s*user|用户\s*\d{5,}", text, re.I):
        return TaskChainEstimate(
            steps=(("Admin/MOA 查询", STEP_ADMIN_QUERY_S),),
            source="agent:query",
        )

    if label_chain is not None:
        return label_chain

    return TaskChainEstimate(
        steps=(("Agent 分析+工具调用", 35.0),),
        source=kind or "agent:general",
    )


def estimate_batch_sec_per_item(
    label: str,
    *,
    prompt: str = "",
    user_key: str = "",
) -> float | None:
    """批量操作单项耗时（逻辑链基准，不含实时融合）。"""
    ctx = prompt or read_batch_task_context(user_key)
    chain = _chain_from_batch_label(label, batch_count=_count_batch_items(ctx))
    if chain is not None:
        return chain.sec_per_cycle
    if ctx:
        chain = _chain_from_batch_label(ctx, batch_count=_count_batch_items(ctx))
        if chain is not None:
            return chain.sec_per_cycle
    return None


def blend_chain_and_history(
    chain_seconds: float | None,
    history_seconds: float | None,
    *,
    chain_weight: float = 0.55,
) -> float | None:
    """融合逻辑链预估与历史统计。"""
    if chain_seconds is not None and history_seconds is not None:
        w = max(0.0, min(1.0, chain_weight))
        return w * chain_seconds + (1.0 - w) * history_seconds
    if chain_seconds is not None:
        return chain_seconds
    return history_seconds
