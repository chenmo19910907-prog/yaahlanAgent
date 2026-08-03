#!/usr/bin/env python3
"""将 preview.html 中的演示 mock UI（UI_COPY / MOA_RECORD_COPY / demoHtml 等）同步到 Web_Agent_Keynote.html。

MOA 录制演示文案与模式自 moa_record_panel.js + chat.html 抽取，保证与真实 Web Agent UI 一致。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
WEB_AGENT = BASE.parent
PREVIEW = BASE / "preview.html"
KEYNOTE = BASE / "Web_Agent_Keynote.html"
MOA_PANEL = WEB_AGENT / "moa_record_panel.js"
CHAT_HTML = WEB_AGENT / "chat.html"


def _between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start))
    return text[i:j]


def _sub_once(text: str, pattern: str, repl: str, label: str) -> str:
    new_text, n = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)
    if n != 1:
        raise SystemExit(f"{label} 替换失败 ({n})")
    return new_text


def _js_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _extract_moa_modes(panel_text: str) -> list[dict[str, str]]:
    modes: list[dict[str, str]] = []
    for match in re.finditer(
        r"\{\s*id:\s*'([^']+)',\s*label:\s*'([^']+)',\s*desc:\s*'([^']+)'",
        panel_text,
    ):
        modes.append({"id": match.group(1), "label": match.group(2), "desc": match.group(3)})
    if len(modes) != 4:
        raise SystemExit(f"MOA 模式解析异常，期望 4 项，得到 {len(modes)}")
    return modes


def _extract_server_code_mode(panel_text: str) -> dict[str, str]:
    block = re.search(r"id:\s*'server_code'[\s\S]*?buildPrompt\(data\)", panel_text)
    if not block:
        raise SystemExit("未找到 server_code 模式定义")
    text = block.group(0)
    label = re.search(r"label:\s*'([^']+)'", text)
    desc = re.search(r"desc:\s*'([^']+)'", text)
    field_label = re.search(r"id:\s*'operation'[\s\S]*?label:\s*'([^']+)'", text)
    placeholder = re.search(r"id:\s*'operation'[\s\S]*?placeholder:\s*'([^']+)'", text)
    if not all([label, desc, field_label, placeholder]):
        raise SystemExit("server_code 模式字段解析不完整")
    demo_value = placeholder.group(1)
    if demo_value.startswith("如："):
        demo_value = demo_value[2:]
    return {
        "label": label.group(1),
        "desc": desc.group(1),
        "fieldLabel": field_label.group(1),
        "fieldPlaceholder": placeholder.group(1),
        "demoValue": demo_value,
    }


def _extract_modal_copy(chat_text: str) -> dict[str, str]:
    title = re.search(r'id="moa-record-title">([^<]+)<', chat_text)
    subtitle = re.search(
        r'class="moa-record-head"[\s\S]*?<p>([^<]+)</p>',
        chat_text,
    )
    submit = re.search(r'id="btn-moa-record-submit"[^>]*>([^<]+)<', chat_text)
    search = re.search(
        r'class="catalog-search"[^>]*placeholder="([^"]+)"',
        chat_text,
    )
    if not all([title, subtitle, submit, search]):
        raise SystemExit("chat.html MOA 录制 UI 文案解析不完整")
    return {
        "title": title.group(1).strip(),
        "subtitle": subtitle.group(1).strip(),
        "submit": submit.group(1).strip(),
        "catalogSearch": search.group(1).strip(),
    }


def build_moa_record_copy_block() -> str:
    panel_text = MOA_PANEL.read_text(encoding="utf-8")
    chat_text = CHAT_HTML.read_text(encoding="utf-8")
    modal = _extract_modal_copy(chat_text)
    modes = _extract_moa_modes(panel_text)
    server_code = _extract_server_code_mode(panel_text)

    mode_lines = ",\n".join(
        "      { id: "
        + _js_str(m["id"])
        + ", label: "
        + _js_str(m["label"])
        + ", desc: "
        + _js_str(m["desc"])
        + " }"
        for m in modes
    )
    sc = server_code
    return (
        "  var MOA_RECORD_COPY = {\n"
        f"    title: {_js_str(modal['title'])},\n"
        f"    subtitle: {_js_str(modal['subtitle'])},\n"
        f"    submit: {_js_str(modal['submit'])},\n"
        f"    catalogSearch: {_js_str(modal['catalogSearch'])},\n"
        "    modes: [\n"
        f"{mode_lines}\n"
        "    ],\n"
        "    serverCode: {\n"
        f"      label: {_js_str(sc['label'])},\n"
        f"      desc: {_js_str(sc['desc'])},\n"
        f"      fieldLabel: {_js_str(sc['fieldLabel'])},\n"
        f"      fieldPlaceholder: {_js_str(sc['fieldPlaceholder'])},\n"
        f"      demoValue: {_js_str(sc['demoValue'])}\n"
        "    }\n"
        "  };\n"
    )


def _inject_moa_record_copy(text: str, block: str) -> str:
    if "var MOA_RECORD_COPY = {" not in text:
        return text.replace("  var ICON = {", block + "  var ICON = {", 1)
    return _sub_once(
        text,
        r"  var MOA_RECORD_COPY = \{.*?(?=  var ICON = \{)",
        block,
        "MOA_RECORD_COPY",
    )


def sync() -> None:
    moa_copy_block = build_moa_record_copy_block()
    preview = PREVIEW.read_text(encoding="utf-8")
    preview = _inject_moa_record_copy(preview, moa_copy_block)
    PREVIEW.write_text(preview, encoding="utf-8")

    keynote = KEYNOTE.read_text(encoding="utf-8")

    ui_block = _between(preview, "  var UI_COPY = {", "  function countSteps(scene) {")
    moa_block = _between(preview, "  var MOA_RECORD_COPY = {", "  var ICON = {")
    demo_block = _between(preview, "  function demoHtml(id) {", "  function radialCenterHtml() {")
    waiting_block = (
        _between(
            preview,
            "    var typing = demo.querySelector('.mock-msg-wrap.typing",
            "    if (!cursor || !typing) return;\n",
        )
        + "    if (!cursor || !typing) return;\n"
    )

    chrome_css = _between(
        preview,
        "  .mock-chrome { display: flex;",
        "  .radial-title { position: absolute;",
    )
    layout_css = _between(preview, "  .mock-layout-session-title {", "  .mock-motion-sub {")
    app_hbtn_css = _between(preview, "  .mock-app-hbtn {\n    display: inline-flex;", "  .mock-app-chat {")
    cat_hbtn_css = _between(preview, "  .mock-cat-hbtn {\n    display: inline-flex;", "  .mock-cat-hbtn.is-accent {")
    mr_css = _between(preview, "  .mock-mr-body {", "  .mock-bm-body {")
    bm_sub_css = "  .mock-bm-empty-sub { font-size: 0.4rem; color: rgba(164, 173, 189, 0.55); max-width: 88%; line-height: 1.35; margin-top: 2px; }\n"

    if "var UI_COPY = {" in keynote:
        keynote = _sub_once(
            keynote,
            r"  var UI_COPY = \{.*?(?=  function countSteps\(scene\) \{)",
            ui_block,
            "UI_COPY",
        )
    else:
        keynote = keynote.replace("  function countSteps(scene) {", ui_block + "  function countSteps(scene) {", 1)

    if "var MOA_RECORD_COPY = {" in keynote:
        keynote = _sub_once(
            keynote,
            r"  var MOA_RECORD_COPY = \{.*?(?=  var ICON = \{)",
            moa_block,
            "MOA_RECORD_COPY",
        )
    else:
        keynote = keynote.replace("  var ICON = {", moa_block + "  var ICON = {", 1)

    keynote = _sub_once(
        keynote,
        r"  function demoHtml\(id\) \{.*?(?=  function radialCenterHtml\(\) \{)",
        demo_block,
        "demoHtml",
    )

    keynote = _sub_once(
        keynote,
        r"    var typing = demo\.querySelector\('\.mock-msg.*?    if \(!cursor \|\| !typing\) return;\n",
        waiting_block,
        "waiting demo selectors",
    )

    keynote = _sub_once(
        keynote,
        r"  \.mock-chrome \{ display: flex;.*?(?=  \.radial-title \{ position: absolute;)",
        chrome_css,
        "mock-chrome CSS",
    )

    if ".mock-layout-session-title {" in keynote:
        keynote = _sub_once(
            keynote,
            r"  \.mock-layout-session-title \{.*?(?=  \.mock-motion-sub \{)",
            layout_css,
            "layout CSS",
        )
    else:
        keynote = keynote.replace("  .mock-motion-sub {", layout_css + "  .mock-motion-sub {", 1)

    keynote = _sub_once(
        keynote,
        r"  \.mock-app-hbtn \{.*?(?=  \.mock-app-chat \{)",
        app_hbtn_css,
        "mock-app-hbtn CSS",
    )
    keynote = _sub_once(
        keynote,
        r"  \.mock-cat-hbtn \{.*?(?=  \.mock-cat-hbtn\.is-accent \{)",
        cat_hbtn_css,
        "mock-cat-hbtn CSS",
    )

    if ".mock-mr-body {" in keynote:
        keynote = _sub_once(
            keynote,
            r"  \.mock-mr-body \{.*?(?=  \.mock-bm-body \{)",
            mr_css,
            "mock-mr CSS",
        )
    else:
        keynote = keynote.replace("  .mock-bm-body {", mr_css + "  .mock-bm-body {", 1)

    if ".mock-bm-empty-sub {" not in keynote:
        keynote = keynote.replace(
            "  .mock-bm-empty-title { font-size: 0.52rem; font-weight: 650; color: rgba(242, 245, 250, 0.88); }\n",
            "  .mock-bm-empty-title { font-size: 0.52rem; font-weight: 650; color: rgba(242, 245, 250, 0.88); }\n"
            + bm_sub_css,
            1,
        )

    agent_preview_css = _between(preview, "  #content.agent-preview {", "  .mock-sb-body { display: flex;")
    if "#content.agent-preview {" in keynote:
        keynote = _sub_once(
            keynote,
            r"  #content\.agent-preview \{.*?(?=  \.mock-sb-body \{ display: flex;)",
            agent_preview_css,
            "agent-preview CSS",
        )
    else:
        keynote = keynote.replace(
            "  .mock-sb-body { display: flex;",
            agent_preview_css + "  .mock-sb-body { display: flex;",
            1,
        )

    build_ap = _between(preview, "  function mockApHeaderBtn(label, icon, active) {", "  function demoHtml(id) {")
    if "function mockApHeaderBtn" in keynote:
        keynote = _sub_once(
            keynote,
            r"  function mockApHeaderBtn\(label, icon, active\) \{.*?(?=  function demoHtml\(id\) \{)",
            build_ap,
            "buildAgentPreviewHtml",
        )
    elif "function buildAgentPreviewHtml" in keynote:
        keynote = _sub_once(
            keynote,
            r"  function buildAgentPreviewHtml\(\) \{.*?(?=  function demoHtml\(id\) \{)",
            build_ap,
            "buildAgentPreviewHtml",
        )
    else:
        keynote = keynote.replace("  function demoHtml(id) {", build_ap + "  function demoHtml(id) {", 1)

    render_ap = _between(preview, "  function applyAgentPreviewView(root, viewId) {", "  function renderLines(s) {")
    if "function applyAgentPreviewView" in keynote:
        keynote = _sub_once(
            keynote,
            r"  function applyAgentPreviewView\(root, viewId\) \{.*?(?=  function renderLines\(s\) \{)",
            render_ap,
            "renderAgentPreview JS",
        )
    else:
        keynote = keynote.replace("  function renderLines(s) {", render_ap + "  function renderLines(s) {", 1)

    if "var agentPreviewTimer" not in keynote:
        keynote = keynote.replace(
            "  var usageGrowthTimer = null;",
            "  var usageGrowthTimer = null;\n  var agentPreviewTimer = null;",
            1,
        )

    count_steps = _between(preview, "  function countSteps(scene) {", "  function esc(s) {")
    keynote = _sub_once(
        keynote,
        r"  function countSteps\(scene\) \{.*?(?=  function esc\(s\) \{)",
        count_steps,
        "countSteps",
    )

    scene_nav = _between(preview, "  function sceneNavLabel(s, i) {", "  function renderNav() {")
    keynote = _sub_once(
        keynote,
        r"  function sceneNavLabel\(s, i\) \{.*?(?=  function renderNav\(\) \{)",
        scene_nav,
        "sceneNavLabel",
    )

    is_step = _between(preview, "  function isStepScene(s) {", "  function layoutContentScale() {")
    keynote = _sub_once(
        keynote,
        r"  function isStepScene\(s\) \{.*?(?=  function layoutContentScale\(\) \{)",
        is_step,
        "isStepScene",
    )

    layout_scale = _between(preview, "  function layoutContentScale() {", "  function scheduleContentScale() {")
    keynote = _sub_once(
        keynote,
        r"  function layoutContentScale\(\) \{.*?(?=  function scheduleContentScale\(\) \{)",
        layout_scale,
        "layoutContentScale",
    )

    render_fn = _between(preview, "  function render() {", "  function nextStep() {")
    keynote = _sub_once(
        keynote,
        r"  function render\(\) \{.*?(?=  function nextStep\(\) \{)",
        render_fn,
        "render",
    )

    KEYNOTE.write_text(keynote, encoding="utf-8")
    print(f"synced demo UI (+ MOA_RECORD_COPY from real UI) → {KEYNOTE.name}")


if __name__ == "__main__":
    sync()
