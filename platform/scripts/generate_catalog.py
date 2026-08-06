#!/usr/bin/env python3
"""合并各模块 registry，按一级功能模块生成 platform/catalog.html 能力目录。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import webbrowser
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PLATFORM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM_DIR))

from display_time import now_display_time  # noqa: E402
from project.catalog_paths import module_registry_path  # noqa: E402
from project.loader import (  # noqa: E402
    catalog_export_basename,
    catalog_title,
    get_project_id,
    load_sources,
    sources_path,
    web_agent_subtitle,
)
REPO_ROOT = PLATFORM_DIR.parent
OUT_HTML = PLATFORM_DIR / "catalog.html"
OUT_HTML_STANDALONE = PLATFORM_DIR / "catalog-standalone.html"

_CATEGORY_PREFIX_RE = re.compile(r"^([^（(]+)")


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def _category_label(category: str) -> str:
    match = _CATEGORY_PREFIX_RE.match(category.strip())
    return (match.group(1).strip() if match else category.strip()) or "未分类"


def _module_id(label: str) -> str:
    slug = re.sub(r"[\s/]+", "-", label.strip())
    slug = re.sub(r"[^\w\u4e00-\u9fff-]", "", slug, flags=re.UNICODE)
    return slug.lower() or "other"


def _parse_top_level_rules(sources: dict[str, Any]) -> list[dict[str, Any]]:
    raw = sources.get("top_level_rules")
    if not isinstance(raw, list):
        return []
    rules: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        group = str(entry.get("group", "")).strip()
        if not group:
            continue
        prefixes = [str(p).strip() for p in entry.get("prefixes", []) if str(p).strip()]
        names = [str(n).strip() for n in entry.get("names", []) if str(n).strip()]
        keywords = [str(k).strip() for k in entry.get("keywords", []) if str(k).strip()]
        rules.append({"group": group, "prefixes": prefixes, "names": names, "keywords": keywords})
    return rules


def _resolve_top_level(label: str, rules: list[dict[str, Any]]) -> str:
    for rule in rules:
        if label in rule["names"]:
            return rule["group"]
        if any(label.startswith(prefix) for prefix in rule["prefixes"]):
            return rule["group"]
        if any(keyword in label for keyword in rule["keywords"]):
            return rule["group"]
    return label


def _parse_env_check(sources: dict[str, Any]) -> dict[str, str]:
    raw = sources.get("env_check")
    if not isinstance(raw, dict):
        return {
            "label": "检查环境配置",
            "prompt": "@新手上手.md 运行环境检查",
        }
    label = str(raw.get("label", "检查环境配置")).strip() or "检查环境配置"
    prompt = str(raw.get("prompt", "@新手上手.md 运行环境检查")).strip() or "@新手上手.md 运行环境检查"
    return {"label": label, "prompt": prompt}


def _workflow_id_to_item_id(workflow_id: str) -> str:
    return workflow_id.strip().replace("-", "_")


def _catalog_include_playbooks(sources: dict[str, Any]) -> bool:
    raw = sources.get("catalog_include_playbooks")
    if isinstance(raw, bool):
        return raw
    return True


def _load_playbooks(sources: dict[str, Any]) -> list[dict[str, Any]]:
    """从 workflow registry 读取 playbooks，并关联各步工作流名称与命令。"""
    if not _catalog_include_playbooks(sources):
        return []
    modules_cfg = sources.get("modules")
    if not isinstance(modules_cfg, list):
        return []
    workflow_registry_path: Path | None = None
    for mod in modules_cfg:
        if not isinstance(mod, dict):
            continue
        if str(mod.get("id", "")).strip() == "workflow":
            rel = str(mod.get("registry", "")).strip()
            if rel:
                workflow_registry_path = REPO_ROOT / rel
            break
    if workflow_registry_path is None or not workflow_registry_path.is_file():
        return []

    registry = _read_json(workflow_registry_path)
    playbooks_raw = registry.get("playbooks")
    if not isinstance(playbooks_raw, list):
        return []

    items_raw = registry.get("items")
    items_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(items_raw, list):
        for item in items_raw:
            if isinstance(item, dict):
                item_id = str(item.get("id") or "").strip()
                if item_id:
                    items_by_id[item_id] = item

    playbooks: list[dict[str, Any]] = []
    for playbook in playbooks_raw:
        if not isinstance(playbook, dict):
            continue
        title = str(playbook.get("title") or "").strip()
        if not title:
            continue
        steps_out: list[dict[str, Any]] = []
        steps_raw = playbook.get("steps")
        if isinstance(steps_raw, list):
            for step in sorted(steps_raw, key=lambda x: int(x.get("order") or 0)):
                if not isinstance(step, dict):
                    continue
                workflow_id = str(step.get("workflowId") or "").strip()
                item = items_by_id.get(_workflow_id_to_item_id(workflow_id), {})
                operations: list[str] = []
                raw_ops = step.get("operations")
                if isinstance(raw_ops, list):
                    for op in raw_ops:
                        if isinstance(op, str) and op.strip():
                            operations.append(op.strip())
                steps_out.append(
                    {
                        "order": int(step.get("order") or 0),
                        "workflowId": workflow_id,
                        "workflowName": str(item.get("name") or workflow_id).strip(),
                        "sheet": str(step.get("sheet") or "").strip(),
                        "note": str(step.get("note") or "").strip(),
                        "operations": operations,
                        "prompts": [
                            p.strip()
                            for p in (item.get("prompts") or [])
                            if isinstance(p, str) and p.strip()
                        ],
                    }
                )
        defaults: dict[str, str] = {}
        raw_defaults = playbook.get("defaults")
        if isinstance(raw_defaults, dict):
            for key, value in raw_defaults.items():
                defaults[str(key)] = str(value)
        sheets: list[dict[str, str]] = []
        raw_sheets = playbook.get("sheets")
        if isinstance(raw_sheets, list):
            for row in raw_sheets:
                if isinstance(row, dict):
                    name = str(row.get("name") or "").strip()
                    content = str(row.get("content") or "").strip()
                    if name:
                        sheets.append({"name": name, "content": content})
        prompts: list[str] = []
        raw_prompts = playbook.get("prompts")
        if isinstance(raw_prompts, list):
            for prompt in raw_prompts:
                if isinstance(prompt, str) and prompt.strip():
                    prompts.append(prompt.strip())
        notes: list[str] = []
        raw_notes = playbook.get("notes")
        if isinstance(raw_notes, list):
            for note in raw_notes:
                if isinstance(note, str) and note.strip():
                    notes.append(note.strip())
        playbooks.append(
            {
                "id": str(playbook.get("id") or title).strip(),
                "title": title,
                "category": str(playbook.get("category") or "工作流").strip(),
                "summary": str(playbook.get("summary") or "").strip(),
                "defaults": defaults,
                "sheets": sheets,
                "steps": steps_out,
                "prompts": prompts,
                "notes": notes,
            }
        )
    return playbooks


def _load_catalog_data() -> dict[str, Any]:
    sources = load_sources()
    modules_cfg = sources.get("modules")
    if not isinstance(modules_cfg, list):
        raise ValueError("sources.json modules 必须是数组")

    top_level_rules = _parse_top_level_rules(sources)
    order_cfg = sources.get("top_level_order")
    order_index: dict[str, int] = {}
    if isinstance(order_cfg, list):
        for idx, name in enumerate(order_cfg):
            if isinstance(name, str) and name.strip():
                order_index[name.strip()] = idx

    # top_label -> category -> items
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    total_items = 0

    for mod in modules_cfg:
        if not isinstance(mod, dict):
            continue
        mod_id = str(mod.get("id", "")).strip()
        mod_label = str(mod.get("label", mod_id)).strip()
        mod_env = str(mod.get("env", "")).strip()
        registry_rel = str(mod.get("registry", "")).strip()
        registry_path = module_registry_path(mod_id, registry_rel)
        if not registry_path.is_file():
            raise FileNotFoundError(f"缺少 registry: {registry_path}")

        registry = _read_json(registry_path)
        items = registry.get("items")
        if not isinstance(items, list):
            raise ValueError(f"{registry_path} items 必须是数组")

        for item in items:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "未分类").strip()
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            raw_prompts = item.get("prompts")
            prompts: list[str] = []
            if isinstance(raw_prompts, list):
                for prompt in raw_prompts:
                    if isinstance(prompt, str) and prompt.strip():
                        prompts.append(prompt.strip())

            cat_label = _category_label(category)
            if mod_env == "online":
                top_label = "线上环境"
            else:
                top_label = _resolve_top_level(cat_label, top_level_rules)
            grouped[top_label][category].append(
                {
                    "name": name,
                    "prompts": prompts,
                    "source": mod_label,
                    "source_id": mod_id,
                    "env": mod_env,
                }
            )
            total_items += 1

    def sort_key(label: str) -> tuple[int, int, str]:
        count = sum(len(items) for items in grouped[label].values())
        rank = order_index.get(label, 10_000)
        return (rank, -count, label)

    modules: list[dict[str, Any]] = []
    for top_label in sorted(grouped.keys(), key=sort_key):
        by_cat = grouped[top_label]
        categories: list[dict[str, Any]] = []
        for cat_name in sorted(by_cat.keys()):
            cat_items = sorted(by_cat[cat_name], key=lambda x: (x.get("source", ""), x.get("name", "")))
            categories.append({"name": cat_name, "items": cat_items})
        item_count = sum(len(c["items"]) for c in categories)
        modules.append(
            {
                "id": _module_id(top_label),
                "label": top_label,
                "item_count": item_count,
                "categories": categories,
            }
        )

    bridge_cfg = sources.get("cursor_bridge")
    cursor_bridge: dict[str, Any] = {"host": "127.0.0.1", "port": 18765}
    if isinstance(bridge_cfg, dict):
        if isinstance(bridge_cfg.get("host"), str) and bridge_cfg["host"].strip():
            cursor_bridge["host"] = bridge_cfg["host"].strip()
        if isinstance(bridge_cfg.get("port"), int) and bridge_cfg["port"] > 0:
            cursor_bridge["port"] = bridge_cfg["port"]

    return {
        "generated_at": now_display_time(),
        "total_items": total_items,
        "module_count": len(modules),
        "modules": modules,
        "playbooks": _load_playbooks(sources),
        "cursor_bridge": cursor_bridge,
        "env_check": _parse_env_check(sources),
    }


def _warn_unlisted_registries(modules_cfg: list[Any], exclude: set[str]) -> None:
    configured = {
        str(mod.get("registry", "")).strip()
        for mod in modules_cfg
        if isinstance(mod, dict) and str(mod.get("registry", "")).strip()
    }
    for path in sorted(REPO_ROOT.glob("*/config/registry.json")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in configured or rel in exclude:
            continue
        print(
            f"WARN platform: {rel} 未登记到 {sources_path()}，不会出现在工具台",
            file=sys.stderr,
        )


def _catalog_exclude_registries(sources: dict[str, Any]) -> set[str]:
    raw = sources.get("catalog_exclude_registries")
    if not isinstance(raw, list):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def _prepare_catalog_data() -> dict[str, Any]:
    sources = load_sources()
    modules_cfg = sources.get("modules")
    if isinstance(modules_cfg, list):
        _warn_unlisted_registries(modules_cfg, _catalog_exclude_registries(sources))
    return _load_catalog_data()


def refresh_catalog_interactive(*, quiet: bool = False) -> int:
    """本地工作台：执行按钮 + Cursor bridge（catalog.html）。"""
    data = _prepare_catalog_data()
    OUT_HTML.write_text(_render_html(data, export_mode=False), encoding="utf-8")
    if not quiet:
        print(
            f"generated: {OUT_HTML} ({data['total_items']} items, {data['module_count']} modules)"
        )
    return 0


def refresh_catalog_standalone(*, quiet: bool = False) -> int:
    """离线/钉钉分发：复制按钮（catalog-standalone.html）。"""
    data = _prepare_catalog_data()
    OUT_HTML_STANDALONE.write_text(_render_html(data, export_mode=True), encoding="utf-8")
    if not quiet:
        print(f"generated: {OUT_HTML_STANDALONE} (standalone copy)")
    return 0


def refresh_catalog(*, quiet: bool = False) -> int:
    """registry 同步等场景：同时生成交互版与离线版。"""
    data = _prepare_catalog_data()
    OUT_HTML.write_text(_render_html(data, export_mode=False), encoding="utf-8")
    OUT_HTML_STANDALONE.write_text(_render_html(data, export_mode=True), encoding="utf-8")
    if not quiet:
        print(f"generated: {OUT_HTML} ({data['total_items']} items, {data['module_count']} modules)")
        print(f"generated: {OUT_HTML_STANDALONE} (standalone copy)")
    return 0


def _render_html(data: dict[str, Any], *, export_mode: bool = False) -> str:
    page_title = catalog_title()
    export_name = catalog_export_basename()
    header_sub = web_agent_subtitle()
    payload = json.dumps(data, ensure_ascii=False)
    payload_safe = payload.replace("</", "<\\/")
    btn_class = "prompt-copy" if export_mode else "prompt-run"
    btn_label = "复制" if export_mode else "执行"
    btn_title = "复制完整提示语" if export_mode else "填入 Cursor 输入框"
    export_link = "" if export_mode else (
        '<a class="export-btn" href="catalog-standalone.html" '
        f'download="{export_name}.html">导出到桌面</a>'
    )
    footer_text = (
        "独立离线版 · 复制按钮写入剪贴板，粘贴到 Cursor 使用"
        if export_mode
        else "由 platform/scripts/generate_catalog.py 自动生成"
    )
    prompt_composer_html = "" if export_mode else """
      <section class="prompt-composer" id="promptComposer">
        <div class="prompt-composer-head">
          <h2>输入提示语</h2>
          <button type="button" class="prompt-composer-run" id="promptComposerRun" title="填入 Cursor 输入框">执行</button>
        </div>
        <textarea class="prompt-composer-input" id="promptInput" placeholder="从演示页跳转或手动输入提示语…"></textarea>
      </section>
    """

    if export_mode:
        cursor_bridge_js = ""
        prompt_action_js = """
    function copyPromptLine(btn) {
      const line = btn.closest('.prompt-line');
      if (!line) return;
      copyToClipboard(assemblePromptLine(line)).catch(() => {});
    }
"""
        env_check_handler_js = """
        copyToClipboard(envCfg.prompt || '@新手上手.md 运行环境检查').catch(() => {});
"""
        click_handler_js = """
      const copyBtn = e.target.closest('.prompt-copy');
      if (copyBtn) {
        e.preventDefault();
        copyPromptLine(copyBtn);
      }
"""
        composer_init_js = ""
    else:
        cursor_bridge_js = """
    const CURSOR_PROMPT_DEEPLINK = 'cursor://anysphere.cursor-deeplink/prompt';
    const CURSOR_DEEPLINK_MAX_LEN = 8000;
    const CURSOR_BRIDGE = DATA.cursor_bridge || { host: '127.0.0.1', port: 18765 };

    function openInCursor(text) {
      const url = CURSOR_PROMPT_DEEPLINK + '?text=' + encodeURIComponent(text);
      if (url.length > CURSOR_DEEPLINK_MAX_LEN) {
        copyToClipboard(text).catch(() => {});
        return;
      }
      const a = document.createElement('a');
      a.href = url;
      a.rel = 'noopener';
      a.style.display = 'none';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }

    function sendToCursor(text) {
      const bridgeUrl = `http://${CURSOR_BRIDGE.host}:${CURSOR_BRIDGE.port}/api/cursor-prompt`;
      fetch(bridgeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      }).then(resp => {
        if (resp.ok) return;
        openInCursor(text);
      }).catch(() => openInCursor(text));
    }

    function runPromptLine(btn) {
      const line = btn.closest('.prompt-line');
      if (!line) return;
      sendToCursor(assemblePromptLine(line));
    }

    function applyIncomingPrompt() {
      const params = new URLSearchParams(window.location.search);
      const prompt = params.get('prompt');
      if (!prompt) return;
      const input = document.getElementById('promptInput');
      if (!input) return;
      input.value = prompt;
      input.focus();
      const composer = document.getElementById('promptComposer');
      if (composer) composer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
"""
        prompt_action_js = ""
        env_check_handler_js = """
        sendToCursor(envCfg.prompt || '@新手上手.md 运行环境检查');
"""
        click_handler_js = """
      const runBtn = e.target.closest('.prompt-run');
      if (runBtn) {
        e.preventDefault();
        runPromptLine(runBtn);
      }
"""
        composer_init_js = """
    const promptInput = document.getElementById('promptInput');
    const promptComposerRun = document.getElementById('promptComposerRun');
    if (promptInput && promptComposerRun) {
      promptComposerRun.addEventListener('click', () => {
        const text = promptInput.value.trim();
        if (!text) {
          promptInput.focus();
          return;
        }
        sendToCursor(text);
      });
    }
    applyIncomingPrompt();
"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{page_title}</title>
  <style>
    :root {{
      --bg: #f4f6f9;
      --card: #fff;
      --text: #1a1f36;
      --muted: #5e6a86;
      --border: #e3e8f0;
      --accent: #2563eb;
      --accent-soft: #eff6ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC",
        "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.55;
    }}
    header {{
      background: linear-gradient(135deg, #1e3a8a, #2563eb);
      color: #fff;
      padding: 24px 20px 20px;
    }}
    header h1 {{ margin: 0 0 6px; font-size: 1.45rem; }}
    header p {{ margin: 0; opacity: 0.9; font-size: 0.92rem; }}
    .meta {{ margin-top: 10px; font-size: 0.82rem; opacity: 0.85; }}
    .layout {{
      display: grid;
      grid-template-columns: 220px 1fr;
      gap: 16px;
      max-width: 960px;
      margin: 0 auto;
      padding: 16px 16px 40px;
    }}
    @media (max-width: 720px) {{ .layout {{ grid-template-columns: 1fr; }} }}
    aside {{
      position: sticky;
      top: 12px;
      align-self: start;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      max-height: calc(100vh - 24px);
      overflow-y: auto;
    }}
    .search {{
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      margin-bottom: 10px;
      font-size: 0.9rem;
    }}
    .env-check-btn {{
      display: block; width: 100%;
      border: 1px solid var(--accent); background: var(--accent-soft);
      color: var(--accent); font-size: 0.88rem; padding: 8px 10px;
      border-radius: 8px; cursor: pointer; margin-bottom: 10px;
      text-align: center;
    }}
    .env-check-btn:hover {{ background: var(--accent); color: #fff; }}
    .export-btn {{
      display: block; width: 100%;
      border: 1px solid var(--border); background: #fff;
      color: var(--muted); font-size: 0.84rem; padding: 7px 10px;
      border-radius: 8px; margin-bottom: 10px; text-align: center;
      text-decoration: none;
    }}
    .export-btn:hover {{ border-color: var(--accent); color: var(--accent); background: var(--accent-soft); }}
    .module-nav button {{
      display: block;
      width: 100%;
      text-align: left;
      border: 0;
      background: transparent;
      padding: 6px 8px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.88rem;
    }}
    .module-nav button:hover {{ background: #f1f5f9; }}
    .module-nav button.active {{ background: var(--accent-soft); color: var(--accent); font-weight: 600; }}
    .module-nav .count {{ float: right; color: var(--muted); font-size: 0.78rem; }}
    section.module {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 18px;
      margin-bottom: 14px;
    }}
    .module-head {{
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--border);
    }}
    .module-head h2 {{ margin: 0 0 4px; font-size: 1.1rem; }}
    .module-head .sub {{ color: var(--muted); font-size: 0.85rem; }}
    .toc-title {{ margin: 0 0 10px; font-size: 0.95rem; font-weight: 600; }}
    ol.cats {{ margin: 0; padding-left: 1.25rem; }}
    ol.cats > li {{ margin-bottom: 10px; }}
    .cat-name {{ font-weight: 600; color: #334155; font-size: 0.88rem; }}
    ul.items {{ margin: 6px 0 0; padding-left: 0; list-style: none; }}
    .cap {{ margin: 4px 0; }}
    .cap-head {{
      display: flex; align-items: center; gap: 6px;
      padding: 4px 6px; border-radius: 6px;
    }}
    .cap-head.is-toggle {{ cursor: pointer; user-select: none; }}
    .cap-head.is-toggle:hover {{ background: #f8fafc; }}
    .cap-head.is-toggle[aria-expanded="true"] {{ background: var(--accent-soft); }}
    .cap-main {{ display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }}
    .cap-name {{ font-size: 0.9rem; color: #475569; }}
    .source-badge {{
      font-size: 0.72rem; color: var(--muted); background: #f1f5f9;
      padding: 1px 6px; border-radius: 4px; white-space: nowrap; flex-shrink: 0;
    }}
    .source-badge[data-env="online"] {{ background: #fef3c7; color: #92400e; }}
    .prompt-panel {{
      margin: 4px 0 6px 8px; padding: 8px 10px; background: #f8fafc;
      border: 1px solid var(--border); border-radius: 8px;
    }}
    .prompt-panel[hidden] {{ display: none; }}
    .prompt-list {{ margin: 0; }}
    .prompt-line {{
      display: flex; align-items: center; gap: 10px;
      margin: 6px 0; padding: 6px 8px; background: #fff;
      border: 1px solid var(--border); border-radius: 6px;
    }}
    .prompt-text {{
      flex: 1; font-size: 0.84rem; color: #64748b;
      line-height: 1.9; word-break: break-word; min-width: 0;
    }}
    .prompt-field {{
      display: inline-block; min-width: 3.5em; max-width: 14em;
      padding: 1px 6px; margin: 0 2px; border: 1px solid #cbd5e1;
      border-radius: 4px; font-size: 0.82rem; background: #fffbeb;
      color: var(--text); vertical-align: baseline;
    }}
    .prompt-field:focus {{
      outline: none; border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-soft); background: #fff;
    }}
    .prompt-field::placeholder {{ color: #94a3b8; font-style: italic; }}
    .prompt-run, .prompt-copy {{
      flex-shrink: 0;
      border: 1px solid var(--accent); background: var(--accent-soft);
      color: var(--accent); font-size: 0.78rem; padding: 4px 12px;
      border-radius: 6px; cursor: pointer; white-space: nowrap;
    }}
    .prompt-run:hover, .prompt-copy:hover {{ background: var(--accent); color: #fff; }}
    .empty {{ color: var(--muted); text-align: center; padding: 24px; }}
    footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding-bottom: 24px; }}
    .playbook-section {{
      background: linear-gradient(180deg, #eff6ff 0%, var(--card) 120px);
      border: 1px solid #bfdbfe;
      border-radius: 12px;
      padding: 16px 18px;
      margin-bottom: 14px;
    }}
    .playbook-head {{ margin-bottom: 12px; }}
    .playbook-head h2 {{ margin: 0 0 6px; font-size: 1.12rem; color: #1e3a8a; }}
    .playbook-summary {{ color: #334155; font-size: 0.9rem; margin: 0 0 10px; }}
    .playbook-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }}
    .playbook-tag {{
      font-size: 0.76rem; background: #dbeafe; color: #1d4ed8;
      padding: 2px 8px; border-radius: 999px;
    }}
    .playbook-defaults, .playbook-sheets {{
      font-size: 0.84rem; color: var(--muted); margin: 8px 0;
    }}
    .playbook-defaults code, .playbook-sheets code {{
      font-size: 0.8rem; background: #f1f5f9; padding: 1px 5px; border-radius: 4px;
    }}
    .playbook-steps {{ margin-top: 12px; }}
    .playbook-step {{
      border: 1px solid var(--border); border-radius: 10px;
      margin-bottom: 8px; background: #fff; overflow: hidden;
    }}
    .playbook-step-head {{
      display: flex; align-items: flex-start; gap: 10px;
      padding: 10px 12px; cursor: pointer; user-select: none;
    }}
    .playbook-step-head:hover {{ background: #f8fafc; }}
    .playbook-step-num {{
      flex-shrink: 0; width: 1.6rem; height: 1.6rem; border-radius: 50%;
      background: var(--accent); color: #fff; font-size: 0.82rem; font-weight: 700;
      display: flex; align-items: center; justify-content: center;
    }}
    .playbook-step-title {{ font-weight: 600; font-size: 0.9rem; color: #1e293b; }}
    .playbook-step-sub {{ font-size: 0.8rem; color: var(--muted); margin-top: 2px; }}
    .playbook-step-body {{
      padding: 0 12px 12px 3.1rem; border-top: 1px solid #f1f5f9;
    }}
    .playbook-step-body[hidden] {{ display: none; }}
    .playbook-step-note {{ font-size: 0.84rem; color: #475569; margin: 8px 0; }}
    .playbook-ops {{
      margin: 6px 0 0; padding-left: 1.2rem; font-size: 0.83rem; color: #334155;
    }}
    .playbook-ops li {{ margin: 4px 0; }}
    .playbook-notes {{
      margin-top: 10px; padding: 8px 10px; background: #fffbeb;
      border: 1px solid #fde68a; border-radius: 8px; font-size: 0.82rem; color: #92400e;
    }}
    .playbook-notes ul {{ margin: 4px 0 0; padding-left: 1.2rem; }}
    .prompt-composer {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px 16px 16px;
      margin-bottom: 14px;
    }}
    .prompt-composer-head {{
      display: flex; align-items: center; justify-content: space-between; gap: 10px;
      margin-bottom: 10px;
    }}
    .prompt-composer-head h2 {{
      margin: 0; font-size: 0.98rem; font-weight: 700; color: var(--text);
    }}
    .prompt-composer-run {{
      border: 0; border-radius: 8px; background: var(--accent); color: #fff;
      font-size: 0.88rem; font-weight: 700; padding: 8px 14px; cursor: pointer;
    }}
    .prompt-composer-run:hover {{ background: #1d4ed8; }}
    .prompt-composer-input {{
      width: 100%; min-height: 88px; resize: vertical;
      border: 1px solid var(--border); border-radius: 8px;
      padding: 10px 12px; font-size: 0.92rem; line-height: 1.55;
      font-family: inherit; color: var(--text); background: #fff;
    }}
    .prompt-composer-input:focus {{
      outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }}
  </style>
</head>
<body>
  <header>
    <h1>{page_title}</h1>
    <p>{header_sub}</p>
    <div class="meta" id="meta"></div>
  </header>
  <div class="layout">
    <aside>
      <button type="button" class="env-check-btn" id="envCheckBtn" title="在 Cursor 中 @新手上手.md 运行环境检查">检查环境配置</button>
      {export_link}
      <input class="search" id="search" type="search" placeholder="搜索能力名、分类、提示语…" autocomplete="off" />
      <div class="module-nav" id="moduleNav"></div>
    </aside>
    <main id="main">
      {prompt_composer_html}
      <div id="catalogBody"></div>
    </main>
  </div>
  <footer>{footer_text}</footer>
  <script id="catalog-data" type="application/json">{payload_safe}</script>
  <script>
    const DATA = JSON.parse(document.getElementById('catalog-data').textContent);
    const genAt = DATA.generated_at ? ` · ${{DATA.generated_at}} 生成` : '';
    document.getElementById('meta').textContent =
      `${{DATA.module_count}} 个一级模块 · ${{DATA.total_items}} 项能力${{genAt}}`;

    let activeModule = 'all';
    let query = '';

    function matches(item, funcLabel, catName, q) {{
      if (!q) return true;
      const prompts = (item.prompts || []).join('\\n');
      const hay = (funcLabel + '\\n' + catName + '\\n' + item.name + '\\n' +
        (item.source || '') + '\\n' + prompts).toLowerCase();
      return hay.includes(q);
    }}

    function bindPromptToggles(root) {{
      root.querySelectorAll('.cap-head.is-toggle').forEach(head => {{
        head.addEventListener('click', () => {{
          const panel = head.closest('.cap').querySelector('.prompt-panel');
          const open = head.getAttribute('aria-expanded') === 'true';
          head.setAttribute('aria-expanded', open ? 'false' : 'true');
          panel.hidden = open;
        }});
      }});
    }}

    const PROMPT_PLACEHOLDER_RE = /<([^>|]+)(?:\\|([^>]+))?>/g;

    function renderPromptLine(text) {{
      const spanParts = [];
      let last = 0;
      let m;
      const re = new RegExp(PROMPT_PLACEHOLDER_RE.source, 'g');
      while ((m = re.exec(text)) !== null) {{
        if (m.index > last) {{
          spanParts.push(escapeHtml(text.slice(last, m.index)));
        }}
        const key = m[1];
        const label = (m[2] || key).trim();
        const width = Math.min(14, Math.max(4, label.length + 1));
        spanParts.push(
          `<input type="text" class="prompt-field" data-key="${{escapeHtml(key)}}" ` +
          `placeholder="${{escapeHtml(label)}}" aria-label="${{escapeHtml(label)}}" ` +
          `style="width:${{width}}em">`
        );
        last = re.lastIndex;
      }}
      if (last < text.length) {{
        spanParts.push(escapeHtml(text.slice(last)));
      }}
      return `<div class="prompt-line">
        <button type="button" class="{btn_class}" title="{btn_title}">{btn_label}</button>
        <span class="prompt-text">${{spanParts.join('')}}</span>
      </div>`;
    }}

    function assemblePromptLine(lineEl) {{
      let result = '';
      lineEl.querySelector('.prompt-text').childNodes.forEach(node => {{
        if (node.nodeType === Node.TEXT_NODE) {{
          result += node.textContent;
        }} else if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('prompt-field')) {{
          const val = node.value.trim();
          const key = node.getAttribute('data-key') || node.placeholder;
          result += val || ('<' + key + '>');
        }}
      }});
      return result;
    }}

    function copyToClipboard(text) {{
      if (navigator.clipboard && window.isSecureContext) {{
        return navigator.clipboard.writeText(text);
      }}
      return new Promise((resolve, reject) => {{
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.cssText = 'position:fixed;top:0;left:0;width:2em;height:2em;padding:0;border:none;outline:none;box-shadow:none;background:transparent;opacity:0;';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, text.length);
        let ok = false;
        try {{
          ok = document.execCommand('copy');
        }} catch (err) {{
          document.body.removeChild(ta);
          reject(err);
          return;
        }}
        document.body.removeChild(ta);
        ok ? resolve() : reject(new Error('execCommand copy failed'));
      }});
    }}

{cursor_bridge_js}
{prompt_action_js}

    function bindPromptPanels(root) {{
      bindPromptToggles(root);
    }}

    function renderCapItem(item) {{
      const prompts = item.prompts || [];
      const hasPrompts = prompts.length > 0;
      const promptHtml = prompts.map(renderPromptLine).join('');
      const headToggle = hasPrompts ? ' is-toggle' : '';
      const headAria = hasPrompts ? ' aria-expanded="false"' : '';
      const source = item.source ? `<span class="source-badge" data-env="${{escapeHtml(item.env || '')}}">${{escapeHtml(item.source)}}</span>` : '';
      return `<li class="cap">
        <div class="cap-head${{headToggle}}"${{headAria}}>
          <div class="cap-main">
            <span class="cap-name">${{escapeHtml(item.name)}}</span>
            ${{source}}
          </div>
        </div>
        <div class="prompt-panel" hidden>${{hasPrompts ? `<div class="prompt-list">${{promptHtml}}</div>` : ''}}</div>
      </li>`;
    }}

    function renderPlaybookStep(step) {{
      const ops = (step.operations || []).map(op => `<li>${{escapeHtml(op)}}</li>`).join('');
      const prompts = (step.prompts || []).map(renderPromptLine).join('');
      const wf = step.workflowId ? `<code>${{escapeHtml(step.workflowId)}}</code>` : '';
      const sheet = step.sheet ? `Sheet「${{escapeHtml(step.sheet)}}」` : '';
      return `<div class="playbook-step">
        <div class="playbook-step-head" aria-expanded="false">
          <span class="playbook-step-num">${{step.order}}</span>
          <div>
            <div class="playbook-step-title">${{escapeHtml(step.workflowName || step.workflowId || '')}}</div>
            <div class="playbook-step-sub">${{wf}} ${{sheet}}</div>
          </div>
        </div>
        <div class="playbook-step-body" hidden>
          ${{step.note ? `<div class="playbook-step-note">${{escapeHtml(step.note)}}</div>` : ''}}
          ${{ops ? `<ol class="playbook-ops">${{ops}}</ol>` : ''}}
          ${{prompts ? `<div class="prompt-list" style="margin-top:8px">${{prompts}}</div>` : ''}}
        </div>
      </div>`;
    }}

    function renderPlaybook(pb) {{
      const defaults = Object.entries(pb.defaults || {{}})
        .map(([k, v]) => `<code>${{escapeHtml(k)}}</code>=${{escapeHtml(v)}}`)
        .join(' · ');
      const sheets = (pb.sheets || [])
        .map(s => `<code>${{escapeHtml(s.name)}}</code>：${{escapeHtml(s.content)}}`)
        .join('<br>');
      const steps = (pb.steps || []).map(renderPlaybookStep).join('');
      const notes = (pb.notes || []).length
        ? `<div class="playbook-notes"><strong>注意</strong><ul>${{(pb.notes || []).map(n => `<li>${{escapeHtml(n)}}</li>`).join('')}}</ul></div>`
        : '';
      const topPrompts = (pb.prompts || []).map(renderPromptLine).join('');
      return `<section class="playbook-section" id="playbook-${{escapeHtml(pb.id)}}">
        <div class="playbook-head">
          <h2>${{escapeHtml(pb.title)}}</h2>
          <p class="playbook-summary">${{escapeHtml(pb.summary || '')}}</p>
          <div class="playbook-meta">
            <span class="playbook-tag">${{escapeHtml(pb.category || '工作流')}}</span>
            <span class="playbook-tag">${{(pb.steps || []).length}} 步</span>
          </div>
          ${{defaults ? `<div class="playbook-defaults"><strong>默认参数：</strong> ${{defaults}}</div>` : ''}}
          ${{sheets ? `<div class="playbook-sheets"><strong>钉钉 Sheet：</strong><br>${{sheets}}</div>` : ''}}
          ${{topPrompts ? `<div class="prompt-list" style="margin-top:8px">${{topPrompts}}</div>` : ''}}
        </div>
        <div class="playbook-steps">${{steps}}</div>
        ${{notes}}
      </section>`;
    }}

    function bindPlaybookToggles(root) {{
      root.querySelectorAll('.playbook-step-head').forEach(head => {{
        head.addEventListener('click', () => {{
          const body = head.nextElementSibling;
          const open = head.getAttribute('aria-expanded') === 'true';
          head.setAttribute('aria-expanded', open ? 'false' : 'true');
          if (body) body.hidden = open;
        }});
      }});
    }}

    function renderPlaybooks(container) {{
      const playbooks = DATA.playbooks || [];
      if (!playbooks.length) return;
      if (activeModule !== 'all' && activeModule !== '工作流') return;
      const wrap = document.createElement('div');
      wrap.innerHTML = playbooks.map(renderPlaybook).join('');
      while (wrap.firstChild) container.appendChild(wrap.firstChild);
      bindPlaybookToggles(container);
      bindPromptPanels(container);
    }}

    function render() {{
      const q = query.trim().toLowerCase();
      const main = document.getElementById('catalogBody');
      if (!main) return;
      main.innerHTML = '';
      let any = false;

      renderPlaybooks(main);
      if ((DATA.playbooks || []).length && (activeModule === 'all' || activeModule === '工作流')) {{
        any = true;
      }}

      for (const mod of DATA.modules) {{
        if (activeModule !== 'all' && mod.id !== activeModule) continue;

        let catsHtml = '';
        let visibleCount = 0;
        let catIdx = 0;
        for (const cat of mod.categories) {{
          const filtered = cat.items.filter(it => matches(it, mod.label, cat.name, q));
          if (!filtered.length) continue;
          catIdx += 1;
          visibleCount += filtered.length;
          const items = filtered.map(renderCapItem).join('');
          catsHtml += `<li><span class="cat-name">${{catIdx}}) ${{escapeHtml(cat.name)}}</span><ul class="items">${{items}}</ul></li>`;
        }}
        if (!visibleCount) continue;
        any = true;

        const section = document.createElement('section');
        section.className = 'module';
        section.id = 'mod-' + mod.id;
        section.innerHTML = `
          <div class="module-head">
            <h2>${{escapeHtml(mod.label)}}</h2>
            <div class="sub">${{visibleCount}} 项能力</div>
          </div>
          <div class="toc-title">分类</div>
          <ol class="cats">${{catsHtml}}</ol>`;
        main.appendChild(section);
      }}

      if (!any) {{
        main.innerHTML = '<div class="empty">没有匹配的能力</div>';
      }} else {{
        bindPromptPanels(main);
      }}
    }}

    function escapeHtml(s) {{
      return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }}

    function renderNav() {{
      const nav = document.getElementById('moduleNav');
      const playbookCount = (DATA.playbooks || []).length;
      const buttons = [
        `<button type="button" data-id="all" class="${{activeModule === 'all' ? 'active' : ''}}">全部<span class="count">${{DATA.total_items}}</span></button>`
      ];
      if (playbookCount > 0) {{
        buttons.push(
          `<button type="button" data-id="工作流" class="${{activeModule === '工作流' ? 'active' : ''}}">工作流 Playbook<span class="count">${{playbookCount}}</span></button>`
        );
      }}
      for (const mod of DATA.modules) {{
        if (mod.id === '工作流' && playbookCount > 0) continue;
        buttons.push(
          `<button type="button" data-id="${{mod.id}}" class="${{activeModule === mod.id ? 'active' : ''}}">${{escapeHtml(mod.label)}}<span class="count">${{mod.item_count}}</span></button>`
        );
      }}
      nav.innerHTML = buttons.join('');
      nav.querySelectorAll('button').forEach(btn => {{
        btn.addEventListener('click', () => {{
          activeModule = btn.dataset.id;
          renderNav();
          render();
          if (activeModule !== 'all') {{
            const el = document.getElementById('mod-' + activeModule);
            if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }}
        }});
      }});
    }}

    document.getElementById('search').addEventListener('input', e => {{
      query = e.target.value;
      render();
    }});

    const envCheckBtn = document.getElementById('envCheckBtn');
    if (envCheckBtn) {{
      const envCfg = DATA.env_check || {{}};
      if (envCfg.label) envCheckBtn.textContent = envCfg.label;
      envCheckBtn.addEventListener('click', () => {{
{env_check_handler_js}
      }});
    }}

    document.addEventListener('click', e => {{
{click_handler_js}
    }});

    renderNav();
    render();
{composer_init_js}
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="生成工具平台能力目录网页")
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="生成后不自动打开浏览器（默认生成后打开）",
    )
    args = parser.parse_args()

    refresh_catalog_interactive(quiet=False)

    if not args.no_open:
        server_script = PLATFORM_DIR / "scripts" / "catalog_server.py"
        try:
            subprocess.run(
                [sys.executable, str(server_script), "--ensure"],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            bridge = load_sources().get("cursor_bridge") or {"host": "127.0.0.1", "port": 18765}
            url = f"http://{bridge['host']}:{bridge['port']}/catalog.html"
        except (subprocess.CalledProcessError, RuntimeError, KeyError):
            url = OUT_HTML.as_uri()
        if webbrowser.open(url):
            print(f"opened: {url}")
        else:
            print(f"catalog: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
