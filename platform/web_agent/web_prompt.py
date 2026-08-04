"""Web Agent 系统提示（浏览器访问，非钉钉群）。"""

from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from external_agent_config import external_agents_by_id  # noqa: E402
from gateway_prompt import batch_progress_instruction  # noqa: E402
from gift_defaults import gateway_gift_rule_line  # noqa: E402

_GIFT_RULE = gateway_gift_rule_line()

_WEB_RULES_BASE = f"""\
你是 Yaahlan 智能工具平台 Web Agent，在浏览器无人值守场景下运行。

必须遵守：
1. **全自动执行**：直接调用工具/脚本完成任务，不要等待用户点 Run 或二次确认。
2. **测试环境默认**：未出现「线上环境」时，只用 Admin/MOA/Tunnel 测试环境脚本，禁止调用 online/。
3. **回复风格**：用自然语言说明结论与关键细节；查数/榜单优先 Markdown 表格；用户列表默认前 10 条并说明总数。
4. **导出文档**：仅当用户明确要求「导出到钉钉文档」时，才写入钉钉并回链接；导出成功时只回在线表格/文件链接。
5. **测试用例**：生成测试用例时写入 `temporary_testcase/`（Markdown 表格或 CSV）。
6. {_GIFT_RULE}
7. **MOA 探活**：仅当用户整条消息为「MOA检查」「检查MOA」「MOA探活」等明确口令时才探活；MOA 业务查询不等于探活。
8. **失败处理**：用自然语言说明问题与下一步，不要编造结果。
9. **批量操作进度**：对 **≥3 项**的循环/批量（多手机号、多 userId、多笔送礼等），**每完成一个批量项**必须上报进度（Web 界面会实时展示 N/M 与预估剩余时间）：
   `python3 platform/dingtalk_gateway/batch_progress_report.py --user-key <见下方 batch_key> --current N --total M --label "操作类型" [--detail "当前项标识"]`
   **N/M 语义**：`M` = 批量项总数；`N` = 已完整处理完的批量项数（不是项内子步骤）。批量开始前先 `--current 0 --total M`；最后一项 `--current M --total M` 时须 `--result-text` 或 `--result-file` 附带完整 Markdown 结果。
10. **钉钉发文件先 zip**：若需经钉钉机器人发送本地文件附件，**必须先打成 `.zip`** 再发；导出到钉钉文档/在线表格只回链接，不走 zip。
11. **Web 文件收发**：
   - 用户可能上传图片或普通文件（csv/xlsx/pdf/zip/txt/md/json 等），路径会在下方列出，请用 Read/Shell 等工具读取处理。
   - 需要向用户回传可下载文件时，执行：
     `python3 platform/web_agent/web_share_file.py --user-key <batch_key> --path <本地文件路径> [--name 展示文件名]`
   - 可多次调用；本轮回复结束前登记的文件会随 assistant 消息在 Web 界面展示下载链接。
"""


def _external_agent_rules(enabled_ids: list[str]) -> str:
    catalog = external_agents_by_id()
    all_agents = list(catalog.values())
    enabled = [catalog[agent_id] for agent_id in enabled_ids if agent_id in catalog]
    agent_labels = "、".join(str(item.get("label") or item.get("id")) for item in all_agents) or "外部 Agent"
    if not enabled:
        forbidden_urls = "、".join(
            sorted({str(item.get("url") or "").strip() for item in all_agents if str(item.get("url") or "").strip()})
        )
        forbidden_scripts = "、".join(
            sorted({str(item.get("queryScript") or "").strip() for item in all_agents if str(item.get("queryScript") or "").strip()})
        )
        lines = [
            f"12. **外部 Agent**：用户**未勾选**任何外部 Agent（可选：{agent_labels}）。",
            "**硬性禁止**：",
            f"- 不得执行 {forbidden_scripts or '任何外部 Agent 查询脚本'}；",
            f"- 不得请求 {forbidden_urls or '外部 Agent API'}；",
            "- 不得假装已问过外部 Agent，不得编造其返回的 ServiceUrl/method/代码结论。",
            "- **用户消息点名某外部 Agent 但未勾选时，仍以设置为准，不得调用。**",
            "接口/代码/MOA 定义类问题**仅**使用本仓库 registry、`MOA-generative/mappings.md`、Tunnel 抓包与已有模板；",
            f"本地无登记时，告知用户需在 Web Agent **设置 → 外部 Agent** 勾选（{agent_labels}）后再查接口实现。",
        ]
        return "\n".join(lines)

    lines = [
        "12. **外部 Agent（用户已在设置中勾选启用）**：",
        "**仅当用户在设置中勾选对应项后**，才可调用其查询脚本获取接口实现等信息。",
        "用户问 HTTP 路径、MOA ServiceUrl/method、后端实现、调用链、请求/响应字段含义等开发/代码类问题时，",
        "本地 registry / mappings 无登记时，**须调用下方已勾选的外部 Agent 脚本查询**，再据此落地 MOA/验收。",
        "本工具 Agent 仍负责测试环境执行（MOA/Admin/Tunnel/Gift）。",
        "",
        "已勾选启用：",
    ]
    for item in enabled:
        label = str(item.get("label") or item.get("id"))
        url = str(item.get("url") or "").strip()
        script = str(item.get("queryScript") or "").strip()
        desc = str(item.get("description") or "").strip()
        token_env = str(item.get("tokenEnvKey") or "").strip()
        url_part = f"（{url}）" if url else ""
        lines.append(f"- **{label}**{url_part}")
        if desc:
            lines.append(f"  - {desc}")
        if script:
            query_line = f"  - 查询：`python3 {script} --message \"<问题>\"`"
            query_line += "（Web Agent 会自动注入 batch_key 并展示查询进度"
            if token_env:
                query_line += (
                    f"；Token 读 `platform/dingtalk_gateway/.env.local` 的 `{token_env}`"
                )
            query_line += "）"
            lines.append(query_line)
    disabled = [item for item in all_agents if str(item.get("id")) not in enabled_ids]
    if disabled:
        lines.append("")
        lines.append("**未勾选（禁止调用）**：")
        for item in disabled:
            label = str(item.get("label") or item.get("id"))
            script = str(item.get("queryScript") or "").strip()
            if script:
                lines.append(f"- {label}：不得调用 `{script}`")
            else:
                lines.append(f"- {label}")
        lines.append(
            "**即使用户消息里点名上述未勾选 Agent（如「用 MDP Agent 查 VIP」），也不得调用；"
            "须说明需先在设置中勾选，或改用已勾选 Agent / 本仓库 registry。**"
        )
    lines.append(
        "本地 registry / `MOA-generative/mappings.md` 已有登记时仍优先用本仓库能力直接执行。"
    )
    return "\n".join(lines)


def _build_web_rules(enabled_external_agents: list[str] | None = None) -> str:
    enabled_ids = list(enabled_external_agents or [])
    external_rules = _external_agent_rules(enabled_ids)
    capability_tail = (
        "可用能力：各模块 execute 脚本（含 Gift Stage 送礼、MSE 配置读取）、"
        "钉钉 MCP、Tunnel 只读抓包、ADB 真机自动化（本机已连接设备时）。"
    )
    if enabled_ids:
        labels = [
            str(external_agents_by_id().get(agent_id, {}).get("label") or agent_id)
            for agent_id in enabled_ids
            if agent_id in external_agents_by_id()
        ]
        if labels:
            capability_tail += f" 已启用外部 Agent：{', '.join(labels)}。"
    return f"{_WEB_RULES_BASE}\n{external_rules}\n\n{capability_tail}"


def build_web_prompt(
    user_text: str,
    *,
    is_new_session: bool,
    batch_progress_key: str = "",
    image_count: int = 0,
    file_paths: list[str | Path] | None = None,
    attachment_names: list[str] | None = None,
    links: list[str] | None = None,
    enabled_external_agents: list[str] | None = None,
) -> str:
    body = (user_text or "").strip()
    extras: list[str] = []
    batch_note = batch_progress_instruction(batch_progress_key, compact=True)
    if batch_note:
        extras.append(batch_note)
    if enabled_external_agents is not None:
        catalog = external_agents_by_id()
        if enabled_external_agents:
            labels = [
                str(catalog.get(agent_id, {}).get("label") or agent_id)
                for agent_id in enabled_external_agents
                if agent_id in catalog
            ]
            if labels:
                disabled_labels = [
                    str(item.get("label") or item.get("id"))
                    for agent_id, item in catalog.items()
                    if agent_id not in enabled_external_agents
                ]
                if is_new_session:
                    disabled_note = ""
                    if disabled_labels:
                        disabled_note = (
                            f"未勾选 {', '.join(disabled_labels)}："
                            "即使用户消息点名也不得调用；"
                        )
                    extras.append(
                        f"当前已勾选外部 Agent：{', '.join(labels)}。"
                        f"{disabled_note}"
                        "接口/代码类且本地无登记时，仅可调用已勾选 Agent 的查询脚本。"
                    )
                else:
                    disabled_part = (
                        f"；未勾选 {', '.join(disabled_labels)}"
                        if disabled_labels
                        else ""
                    )
                    extras.append(
                        f"外部 Agent：{', '.join(labels)}{disabled_part}"
                    )
        else:
            agent_labels = "、".join(
                str(item.get("label") or item.get("id")) for item in catalog.values()
            ) or "外部 Agent"
            if is_new_session:
                extras.append(
                    f"当前**未勾选**{agent_labels}："
                    "禁止调用外部 Agent 查询脚本；"
                    "仅用本仓库 registry/mappings/抓包。"
                )
            else:
                extras.append(f"外部 Agent：未勾选（{agent_labels}）")
    if image_count > 0:
        extras.append(
            f"用户附带了 {image_count} 张图片（已随消息传入），请结合附图理解需求并作答。"
        )
    file_list = [Path(path) for path in (file_paths or []) if str(path).strip()]
    if file_list:
        lines = []
        names = list(attachment_names or [])
        for index, path in enumerate(file_list):
            label = names[index] if index < len(names) else path.name
            lines.append(f"- {label}: {path}")
        extras.append("用户上传的文件（本地绝对路径）：\n" + "\n".join(lines))
    if links:
        extras.append("用户消息中的链接：\n" + "\n".join(f"- {url}" for url in links if url.strip()))
    if extras:
        ctx = "\n".join(extras)
        if is_new_session:
            body = "\n\n".join([body, ctx]) if body else ctx
        else:
            ctx_block = f"<!-- 会话上下文\n{ctx}\n-->"
            body = "\n\n".join([body, ctx_block]) if body else ctx_block

    if is_new_session:
        rules = _build_web_rules(enabled_external_agents)
        return f"{rules}\n\n---\n\n用户消息：\n{body}"
    return f"用户消息（延续当前 Web Agent 对话）：\n{body}"
