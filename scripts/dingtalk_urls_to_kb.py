#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从钉钉 Excel URL 摄入 testcase-kb 知识库。

默认导入工作簿内【全部 Sheet】。仅当显式传入 --sheet 时才导入单个 Sheet。
项目规则见 .cursor/rules/kb-import-all-sheets.mdc
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import re
import sys
from pathlib import Path
from typing import Any, List

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
KB_ROOT = ROOT / "testcase-kb"
EXCEL_SERVER = (
    ROOT
    / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/server_read.py"
)

# 复用 xlsx_kb_sync 的解析与写入逻辑
sys.path.insert(0, str(SCRIPTS))
from xlsx_kb_sync import (  # noqa: E402
    CaseRow,
    build_module_body,
    ensure_doc,
    iter_cases_from_matrix,
    normalize_text,
    optimize_doc,
    replace_or_insert_module_section,
)

EXTRA_KB_FILES = {
    "cp_relation": "CP好友关系.md",
}

KB_FILES = {
    "room": "房间.md",
    "gift": "礼物.md",
    "family": "家族.md",
    "theme_room": "主题房.md",
    "moments": "动态.md",
    "message": "消息.md",
    "face_auth": "人脸认证.md",
    "auth_login": "注册登录.md",
    "customer_service": "客服.md",
    "super_admin": "超管.md",
    "agency": "公会.md",
    "coin": "币商.md",
    "game": "游戏.md",
    "rank_activity": "榜单与活动.md",
    **EXTRA_KB_FILES,
}

SKIP_MODULE_PREFIX = (
    "设计人",
    "开发",
    "产品",
    "測試",
    "测试工具",
    "用例总计",
    "翻译",
    "镜像",
    "关联场景考虑",
    "新老版本交互",
    "老版本历史功能回测",
    "定时任务",
    "失败与回滚",
    "各场景case完善检查",
    "幂等",
    "弱网",
    "性能",
    "兼容性",
)


def _load_excel_reader():
    spec = importlib.util.spec_from_file_location("dingtalk_excel_read", EXCEL_SERVER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 Excel 读取模块: {EXCEL_SERVER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify_big_module(sheet_title: str, module_name: str, step: str, exp: str) -> str:
    text = " ".join([sheet_title, module_name, step, exp]).lower()

    def has(*keys: str) -> bool:
        return any(key.lower() in text for key in keys)

    if has("cp空间", "cp礼物", "cp解除", "cp好友"):
        return "cp_relation"
    if has("主题房", "活动主题房", "活动房推荐", "活动推荐位"):
        return "theme_room"
    if has("定制礼物", "礼物面板", "礼物榜", "背包", "盲盒", "勋章", "礼物"):
        return "gift"
    if has("家族", "公会家族"):
        return "family"
    if has("房间", "麦位", "进房", "语音房", "room"):
        return "room"
    if has("动态", "moment", "帖子", "热榜"):
        return "moments"
    if has("消息", "im", "私聊", "群聊", "聊天"):
        return "message"
    if has("人脸", "真人认证", "face", "认证"):
        return "face_auth"
    if has("登录", "注册", "注销", "账号"):
        return "auth_login"
    if has("超管", "审核后台", "工单", "设备拉黑"):
        return "super_admin"
    if has("客服", "券包", "快捷回复"):
        return "customer_service"
    if has("am", "agency", "公会", "助理", "族长"):
        return "agency"
    if has("币商", "充值", "提现", "转账", "钻石", "钱包"):
        return "coin"
    if has("游戏", "pk", "大冒险", "battle"):
        return "game"
    if has("榜", "活动", "排名", "排行", "banner"):
        return "rank_activity"
    return "room"


def parse_version_label(rows: List[List[Any]]) -> str:
    for row in rows[:6]:
        if not row:
            continue
        first = normalize_text(str(row[0] if row[0] is not None else ""))
        if first and ("版本需求" in first or re.search(r"v?\d+\.\d+\.\d+", first, re.I)):
            return first
    return "钉钉 Excel 摄入"


def should_skip_module(module_name: str) -> bool:
    name = normalize_text(module_name)
    if not name:
        return False
    return any(name.startswith(prefix) for prefix in SKIP_MODULE_PREFIX)


def process_sheet(
    *,
    url: str,
    rows: List[List[Any]],
    sheet_title: str,
    version_label: str,
) -> List[Path]:
    stitle, cases = iter_cases_from_matrix(rows, sheet_title)
    if not cases:
        return []

    grouped: dict[tuple[str, str], list[CaseRow]] = {}
    for case in cases:
        module_name = normalize_text(case.module) or "（未填功能模块）"
        if should_skip_module(module_name):
            continue
        big_key = classify_big_module(stitle, module_name, case.step, " ".join(case.expects))
        # 同一工作簿多 Sheet 时，用「Sheet·模块」避免互相覆盖
        section_module = f"{stitle}·{module_name}"
        key = (big_key, section_module)
        grouped.setdefault(key, []).append(case)

    touched: list[Path] = []
    pseudo_name = url.rstrip("/").split("/")[-1] or "dingtalk.xlsx"
    for (big_key, section_module), module_rows in grouped.items():
        out_name = KB_FILES[big_key]
        out_path = KB_ROOT / out_name
        title = out_name.replace(".md", "")
        ensure_doc(out_path, title)

        # build_module_body 的 module_name 参数用于 ##### 行标题，保留原始模块名
        display_module = section_module.split("·", 1)[-1] if "·" in section_module else section_module
        body = build_module_body(version_label, pseudo_name, stitle, display_module, module_rows)
        old = out_path.read_text(encoding="utf-8")
        merged = replace_or_insert_module_section(old, section_module, body)
        out_path.write_text(merged, encoding="utf-8")
        touched.append(out_path)

    for path in sorted(set(touched)):
        optimize_doc(path)
    return sorted(set(touched))


async def list_workbook_sheets(excel: Any, url: str) -> list[str]:
    workbook_id = excel.extract_workbook_id_from_url(url)
    aegis_key = os.environ.get("DINGTALK_AEGIS_KEY", excel.DEFAULT_AEGIS_KEY)
    aegis_secret = os.environ.get("DINGTALK_AEGIS_SECRET", excel.DEFAULT_AEGIS_SECRET)
    workid = os.environ.get("DINGTALK_WORKID", excel.DEFAULT_WORKID)

    access_token, operator_id = await excel.getTokenAndOperatorId(aegis_key, aegis_secret, workid)
    sheets = await excel.getSheetList(workbook_id, operator_id, access_token)
    names = [normalize_text(str(item.get("name") or "")) for item in sheets]
    return [name for name in names if name]


async def ingest_url(url: str, sheetname: str | None = None) -> list[tuple[str, list[Path]]]:
    excel = _load_excel_reader()
    if sheetname:
        sheet_names = [sheetname]
    else:
        sheet_names = await list_workbook_sheets(excel, url)
        if not sheet_names:
            raise RuntimeError(f"工作簿无可用 Sheet: {url}")

    results: list[tuple[str, list[Path]]] = []
    for name in sheet_names:
        rows, actual_sheet = await excel.getSheetInfo(url, sheetname=name)
        version_label = parse_version_label(rows)
        touched = process_sheet(
            url=url,
            rows=rows,
            sheet_title=actual_sheet,
            version_label=version_label,
        )
        results.append((actual_sheet, touched))
    return results


async def ingest_urls(urls: list[str], *, sheetname: str | None = None) -> None:
    all_touched: set[Path] = set()
    for url in urls:
        sheet_results = await ingest_url(url, sheetname=sheetname)
        print(f"OK {url}")
        print(f"  sheets={len(sheet_results)}")
        for sheet, touched in sheet_results:
            print(f"  - {sheet} -> {', '.join(p.name for p in touched) or '（无有效用例行）'}")
            all_touched.update(touched)
    if not all_touched:
        return

    for script_name in (
        "content_optimize_kb_docs.py",
        "kb_knowledge_style.py",
        "kb_clean_toc_titles.py",
    ):
        script = SCRIPTS / script_name
        if script.is_file():
            os.system(f"{sys.executable} {script} --root {KB_ROOT}")


def main() -> int:
    parser = argparse.ArgumentParser(description="钉钉 Excel URL → testcase-kb（默认导入全部 Sheet）")
    parser.add_argument("urls", nargs="+", help="钉钉 Excel 文档 URL")
    parser.add_argument("--sheet", help="仅导入指定 Sheet 名称（默认导入工作簿内全部 Sheet）")
    args = parser.parse_args()
    asyncio.run(ingest_urls(args.urls, sheetname=args.sheet))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
