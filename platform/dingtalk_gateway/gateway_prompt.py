"""钉钉网关 Agent 系统提示（无人值守、导出规则）。"""

from __future__ import annotations

from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
EXPORT_CONFIG = GATEWAY_DIR / "config" / "export_folder.json"

_GATEWAY_RULES = """\
你是 Yaahlan 智能工具平台网关 Agent，在钉钉群无人值守场景下运行。

必须遵守：
1. **全自动执行**：直接调用工具/脚本完成任务，不要等待用户点 Run 或二次确认。
2. **测试环境默认**：未出现「线上环境」时，只用 Admin/MOA/Tunnel 测试环境脚本，禁止调用 online/。
3. **大结果导出**：完整表格、CSV、JSON 若超过简短摘要，说明已写入 temporary_testcase/ 或给出文件路径；网关会自动导出到钉钉文档目录并回链接。
4. **导出目录**：Agent 导出目录 nodeId 见 platform/dingtalk_gateway/config/export_folder.json。
5. **回复风格（钉钉群）**：只回复「结论 + 关键数据」；失败时写清**具体问题**与**下一步**，禁止贴原始 JSON/HTML/堆栈/exit code/长日志。
6. **失败处理**：工具失败时给出明确错误与下一步，不要编造结果。

可用能力：仓库各模块 execute 脚本、钉钉 MCP（文档/Excel）、platform 工具台 registry。
"""


def build_gateway_prompt(
    user_text: str,
    *,
    image_count: int = 0,
    links: list[str] | None = None,
) -> str:
    user = (user_text or "").strip()
    extras: list[str] = []
    if image_count > 0:
        extras.append(
            f"用户附带了 {image_count} 张图片（已随消息传入），请结合附图理解需求并作答。"
        )
    if links:
        extras.append("用户消息中的链接：\n" + "\n".join(f"- {url}" for url in links))

    body = user
    if extras:
        body = "\n\n".join([user, *extras]) if user else "\n\n".join(extras)

    return f"{_GATEWAY_RULES}\n\n---\n\n用户消息（来自钉钉群 @）：\n{body}"
