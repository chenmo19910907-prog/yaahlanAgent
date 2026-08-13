"""Web Agent 连接/启动阶段文案（SSE phase_line）。"""

from __future__ import annotations

PHASE_WORKER_READY = "Worker 已就绪…"
PHASE_BRIDGE_INIT = "正在初始化 Bridge…"
PHASE_PROMPT_BUILD = "正在组装提示词…"
PHASE_AGENT_PREPARE = "正在准备 Agent…"
PHASE_AGENT_CREATE = "正在创建 Agent 窗口…"
PHASE_AGENT_RESUME = "正在恢复 Agent 会话…"
PHASE_MODEL_WAIT = "等待模型响应…"

# 兼容旧文案
PHASE_CONNECT_LEGACY = "正在连接 Agent…"
