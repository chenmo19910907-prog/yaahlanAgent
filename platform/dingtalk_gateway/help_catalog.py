"""生成钉钉群「帮助」文案。"""

from __future__ import annotations

import json
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parent.parent
SOURCES = REPO_ROOT / "platform" / "config" / "sources.json"

_BUILTIN = """\
**Yaahlan 智能工具 · 群用法**

**快捷指令（不走 Agent，更快）**
• `MOA检查` — 测试环境 MOA Cookie 是否有效
• `导出 temporary_testcase/xxx.csv` — 导出到钉钉文档
• `打开工作台` / `工具平台` — 发送复制按钮版离线 HTML（zip）到本群；执行机本地请用 `python3 platform/open_catalog.py` 打开执行版
• `2.4.5版本生成测试报告` — 生成内/外网 HTML 并作为 zip 附件发到本群
• `100465989升级 VIP3` — MOA VIP 升级（示例）
• `中断操作` — 打断你当前正在执行的任务（快捷指令与 Agent 均适用）
• `重新执行` — 重跑本群上一条任务
• `帮助` — 显示本说明

**自然语言（走 Agent，每人独立 Cursor 窗口，多轮自动带上下文）**
• 查询类结果默认**直接在群里展示**；**用户列表默认前 10 条**
• 需要完整列表时说「**查看全部数据**」；需要写入文档时说「**导出到钉钉文档**」
• 生成测试用例 → 写入 `temporary_testcase/` 后**自动同步**到默认钉钉文档目录并回链接
• `@机器人 介绍一下 platform 目录`
• `@机器人 附图 + 说明` / 带 alidocs 链接

**注意**
• 默认测试环境；含「线上环境」才走 online/
• **不支持真机 ADB**（macro/observe/礼物面板 UI 等）；**送礼默认 Gift HTTP**（未说「背包送礼」不走 MOA 背包），抓包用 Tunnel 只读
• 执行中可 `中断操作`；排队时会提示前面任务数
• **批量操作**（多账号/多笔）约 **30 秒**推送一次「N/M」进度（含预估）；批量进行中不重复发「仍在执行中」心跳；完成后记录耗时供后续预估
• 普通长任务「仍在执行中」心跳含已执行时长、**当前 Agent 思考/工具进度**与预估时间（超过 3 分钟显示「3分钟以上」）
"""


def _sample_prompts_from_registry(registry_path: Path, limit: int = 6) -> list[str]:
    if not registry_path.is_file():
        return []
    try:
        data = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") or []
    samples: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompts = item.get("prompts") or []
        if prompts and isinstance(prompts[0], str):
            samples.append(prompts[0].strip())
        if len(samples) >= limit:
            break
    return samples


def build_help_message() -> str:
    lines = [_BUILTIN.strip()]
    if not SOURCES.is_file():
        return "\n".join(lines)

    try:
        sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "\n".join(lines)

    modules = sources.get("modules") or []
    moa_samples: list[str] = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        if module.get("id") != "moa":
            continue
        reg = module.get("registry")
        if isinstance(reg, str):
            moa_samples = _sample_prompts_from_registry(REPO_ROOT / reg, limit=5)
        break

    if moa_samples:
        lines.append("")
        lines.append("**MOA 能力示例（也可用自然语言描述）**")
        for sample in moa_samples:
            lines.append(f"• `{sample}`")

    lines.append("")
    lines.append("执行机本地执行版：`python3 platform/open_catalog.py`；群里发 `打开工作台` 获取复制按钮离线版")
    text = "\n".join(lines)
    if len(text) > 3800:
        return text[:3800] + "\n…（更多见工具台）"
    return text
