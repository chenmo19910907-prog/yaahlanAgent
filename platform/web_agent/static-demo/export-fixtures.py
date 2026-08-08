#!/usr/bin/env python3
"""导出 GitHub Pages 静态 Web Agent 演示所需的 fixtures。"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WEB_AGENT_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = WEB_AGENT_DIR.parent.parent
PLATFORM_DIR = REPO_ROOT / "platform"
SCRIPTS_DIR = PLATFORM_DIR / "scripts"
OUT_DIR = Path(__file__).resolve().parent / "fixtures"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(PLATFORM_DIR) not in sys.path:
    sys.path.insert(0, str(PLATFORM_DIR))

from generate_catalog import _load_catalog_data  # noqa: E402


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _patch_web_docs_urls(data: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(data, ensure_ascii=False))

    def patch_url(url: str) -> str:
        if url == "/keynote":
            return "../keynote/"
        if url.startswith("/keynote/"):
            return f"../keynote/{url[len('/keynote/'):]}"
        return url

    for category in out.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for item in category.get("items") or []:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                item["url"] = patch_url(item["url"])
    return out


def _build_meta(cfg: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    bookmarks = _read_json(WEB_AGENT_DIR / "config" / "bookmarks.json")
    external_agents = []
    for item in cfg.get("externalAgents") or []:
        if not isinstance(item, dict):
            continue
        external_agents.append(
            {
                "id": str(item.get("id") or ""),
                "label": str(item.get("label") or item.get("id") or ""),
                "description": str(item.get("description") or ""),
                "url": str(item.get("url") or ""),
                "defaultEnabled": bool(item.get("defaultEnabled")),
            }
        )
    return {
        "title": str(cfg.get("title") or "Yaahlan 智能工具 Agent"),
        "subtitle": str(cfg.get("subtitle") or ""),
        "projectId": "yaahlan",
        "mcp_count": 6,
        "skills_count": 12,
        "modules_count": int(catalog.get("module_count") or 0),
        "capabilities_count": int(catalog.get("total_items") or 0),
        "defaultAgentModel": str(cfg.get("defaultAgentModel") or "composer-2.5"),
        "agentModels": cfg.get("agentModels") or [],
        "externalAgents": external_agents,
        "quickPrompts": cfg.get("quickPrompts") or [],
        "quickPromptCount": int(cfg.get("quickPromptCount") or 4),
        "emptyIntro": cfg.get("emptyIntro") or {},
        "featureDemos": [
            {
                "title": "新建对话",
                "demo": "new-chat",
                "description": "空状态轮播与快捷提示",
            },
            {
                "title": "流式输出",
                "demo": "stream-output",
                "description": "思考过程与 Markdown 流式渲染",
            },
            {
                "title": "能力目录",
                "demo": "catalog-onboard",
                "description": "MOA / Tunnel / 用例生成能力一览",
            },
        ],
        "featureDemoRotateMs": int(cfg.get("featureDemoRotateMs") or 10000),
        "bookmarks": bookmarks,
        "maxImagesPerMessage": 4,
        "maxAttachmentsPerMessage": 4,
        "maxImageBytes": 5 * 1024 * 1024,
        "maxFileBytes": 10 * 1024 * 1024,
        "allowedFileExtensions": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt", ".md"],
        "authRequired": False,
        "authPublicOnly": False,
        "otpAuthEnabled": False,
        "loginPhrase": "",
        "dingtalkOAuth": {"enabled": False},
    }


def _demo_sessions() -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    now = _iso_now()
    sessions = [
        {
            "id": "demo0001stagegift",
            "title": "Stage 送礼验收",
            "auto_title": "Stage 送礼验收",
            "created_at": now,
            "updated_at": now,
            "message_count": 2,
            "relative_time": "演示",
            "source": "web",
            "web_owner": "陈墨",
            "web_owner_label": "陈墨",
            "web_owner_id": "demo-user",
            "is_mine": True,
            "can_manage_collaborators": True,
            "pinned": True,
            "pinned_at": now,
            "latest_preview": "Stage 房间送礼接口已调用成功",
        },
        {
            "id": "demo0002prdcases",
            "title": "PRD 用例生成",
            "auto_title": "PRD 用例生成",
            "created_at": now,
            "updated_at": now,
            "message_count": 2,
            "relative_time": "演示",
            "source": "web",
            "web_owner": "陈墨",
            "web_owner_label": "陈墨",
            "web_owner_id": "demo-user",
            "is_mine": True,
            "can_manage_collaborators": True,
            "latest_preview": "已生成 8 条测试用例",
        },
        {
            "id": "demo0003moalookup",
            "title": "MOA 查数演示",
            "auto_title": "MOA 查数演示",
            "created_at": now,
            "updated_at": now,
            "message_count": 2,
            "relative_time": "演示",
            "source": "web",
            "web_owner": "陈墨",
            "web_owner_label": "陈墨",
            "web_owner_id": "demo-user",
            "is_mine": True,
            "can_manage_collaborators": True,
            "latest_preview": "userId: 100465989",
        },
    ]
    messages: dict[str, list[dict[str, Any]]] = {
        "demo0001stagegift": [
            {
                "role": "user",
                "content": "Stage 房间送礼：100465989 给 100153721 送 Neon Heart（2005004592）",
                "timestamp": now,
            },
            {
                "role": "assistant",
                "content": (
                    "## Stage 送礼验收（演示数据）\n\n"
                    "已模拟调用 **Gift Stage** 接口，结果如下：\n\n"
                    "| 字段 | 值 |\n| --- | --- |\n"
                    "| 送礼方 | `100465989` |\n"
                    "| 收礼方 | `100153721` |\n"
                    "| 礼物 ID | `2005004592` (Neon Heart) |\n"
                    "| ec | `0` |\n"
                    "| em | `success` |\n\n"
                    "> 此为 GitHub Pages 静态演示，数据为假数据，不连接内网服务。"
                ),
                "timestamp": now,
            },
        ],
        "demo0002prdcases": [
            {
                "role": "user",
                "content": "解析 PRD 并生成测试用例",
                "timestamp": now,
            },
            {
                "role": "assistant",
                "content": (
                    "## 测试用例（演示数据）\n\n"
                    "1. **正常路径**：上传合法 PRD，生成用例并导出 Excel\n"
                    "2. **空文档**：提示用户补充需求描述\n"
                    "3. **大文件**：超过 10MB 时给出友好错误\n"
                    "4. **权限**：未登录用户不可同步钉钉文档\n\n"
                    "完整 MOA / 钉钉 / Excel 同步需连接内网 Web Agent 服务。"
                ),
                "timestamp": now,
            },
        ],
        "demo0003moalookup": [
            {
                "role": "user",
                "content": "MOA 查手机号 +86 13311111111 对应的 userId",
                "timestamp": now,
            },
            {
                "role": "assistant",
                "content": (
                    "## MOA 查数结果（演示数据）\n\n"
                    "- 手机号：`+86 13311111111`\n"
                    "- userId：`100465989`\n"
                    "- 昵称：`DemoUser`\n"
                    "- 环境：`stage`\n\n"
                    "内网环境将调用真实 MOA 模板查询。"
                ),
                "timestamp": now,
            },
        ],
    }
    return sessions, messages


def export_all(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    cfg = _read_json(WEB_AGENT_DIR / "config.json")
    catalog = _load_catalog_data()
    web_docs = _patch_web_docs_urls(_read_json(WEB_AGENT_DIR / "config" / "web_docs.json"))
    sessions, messages = _demo_sessions()

    bundle: dict[str, Any] = {
        "meta": _build_meta(cfg, catalog),
        "authStatus": {
            "loggedIn": True,
            "otpAuthEnabled": False,
            "loginPhrase": "",
            "dingtalkOAuth": {"enabled": False},
            "user": {
                "staffId": "demo-user",
                "displayName": "陈墨（演示）",
                "isAdmin": True,
            },
        },
        "catalog": catalog,
        "webDocs": web_docs,
        "messageBoard": {"messages": []},
        "webUsers": {
            "users": [
                {"staffId": "demo-user", "displayName": "陈墨（演示）"},
                {"staffId": "demo-peer", "displayName": "测试同学"},
            ],
            "groups": [],
            "total": 2,
        },
        "sessions": sessions,
        "messages": messages,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    for key, value in bundle.items():
        path = out_dir / f"{key}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    bundle_js = WEB_AGENT_DIR / "static-demo" / "demo-fixtures.js"
    bundle_js.write_text(
        "window.__WEB_AGENT_FIXTURES__ = "
        + json.dumps(bundle, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    return bundle


def main() -> None:
    export_all()
    print(f"fixtures 已导出: {OUT_DIR}")


if __name__ == "__main__":
    main()
