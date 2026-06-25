#!/usr/bin/env python3
"""家族成员两两互送私信礼物（含自动补钻+消耗校验），批量进度上报。"""

from __future__ import annotations

import asyncio
import json
import random
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
USER_KEY = "cidwuF5xkEMvaZMDWWu8BtHbg==:user:32274159141215328"
LABEL = "家族互送礼物"
WORKBOOK_ID = "93NwLYZXWyg4ozlzCNanyzR4JkyEqBQm"
DOC_API = "https://api.dingtalk.com/v1.0/doc"
TOKEN_API = "http://gaia-hg.momo.com/ding/excel/token"
GIFT_POOL_PATH = Path("/tmp/gift_panel_parsed.json")
RESULT_PATH = ROOT / "platform/dingtalk_gateway/exports/family_mutual_gift_result.json"

sys.path.insert(0, str(ROOT / "scripts"))
from mcp_paths import load_mcp_env  # noqa: E402


def report(current: int, total: int, detail: str = "", result_text: str = "") -> None:
    cmd = [
        "python3",
        "platform/dingtalk_gateway/batch_progress_report.py",
        "--user-key",
        USER_KEY,
        "--current",
        str(current),
        "--total",
        str(total),
        "--label",
        LABEL,
    ]
    if detail:
        cmd.extend(["--detail", detail])
    if result_text:
        cmd.extend(["--result-text", result_text])
    subprocess.run(cmd, cwd=ROOT, check=True)


def parse_gift_output(raw: str) -> dict:
    text = (raw or "").strip()
    start = text.find("{")
    if start < 0:
        raise RuntimeError(f"送礼输出无 JSON: {text[:300]}")
    return json.loads(text[start:])


def run_gift(sender: str, receiver: str, gift_id: str) -> dict:
    proc = subprocess.run(
        [
            "python3",
            "Gift/gift_execute.py",
            "--scene",
            "private",
            "--sender",
            sender,
            "--receivers",
            receiver,
            "--gift-id",
            gift_id,
            "--num",
            "1",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    raw = proc.stdout or proc.stderr
    data = parse_gift_output(raw)
    data["_exit_code"] = proc.returncode
    return data


def gift_success(resp: dict) -> tuple[bool, str]:
    if not resp.get("ok"):
        step = resp.get("step") or "unknown"
        err = resp.get("error") or "unknown"
        return False, f"{step}: {err}"
    response = resp.get("response") or {}
    if response.get("ec") != 200:
        return False, f"post_gift: {response.get('em') or response}"
    diamond = resp.get("diamond") or {}
    after = diamond.get("after_send") or {}
    if diamond and not after.get("verified", True):
        return False, (
            f"diamond_verify: 期望 {after.get('expected')} 实际消耗 {after.get('consumed')}"
        )
    return True, "success"


async def read_pairs() -> tuple[list[dict], list[tuple[str, int]], int]:
    env = load_mcp_env("dingtalk-excel-write")
    url = (
        f"{TOKEN_API}?aegisKey={env['DINGTALK_AEGIS_KEY']}"
        f"&aegisSecret={env['DINGTALK_AEGIS_SECRET']}&workid={env['DINGTALK_WORKID']}"
    )
    async with httpx.AsyncClient(timeout=60) as client:
        token_data = (await client.get(url)).json()["data"]
        token, op = token_data["token"], token_data["operatorId"]
        sid = (
            await client.get(
                f"{DOC_API}/workbooks/{WORKBOOK_ID}/sheets?operatorId={op}",
                headers={"x-acs-dingtalk-access-token": token},
            )
        ).json()["value"][0]["id"]
        info = (
            await client.get(
                f"{DOC_API}/workbooks/{WORKBOOK_ID}/sheets/{sid}?operatorId={op}",
                headers={"x-acs-dingtalk-access-token": token},
            )
        ).json()
        max_row = int(info.get("rowCount") or 500)
        vals = (
            await client.get(
                f"{DOC_API}/workbooks/{WORKBOOK_ID}/sheets/{sid}/ranges/A1:H{max_row}?select=values&operatorId={op}",
                headers={"x-acs-dingtalk-access-token": token},
            )
        ).json().get("values") or []

    current_fid = ""
    families: dict[str, dict] = {}
    for raw in vals[1:]:
        if not any(str(cell).strip() for cell in raw):
            continue
        row = raw + [""] * (8 - len(raw))
        fid = str(row[0]).strip() or current_fid
        if str(row[0]).strip():
            current_fid = fid
        uid = str(row[5]).strip()
        if not fid or not uid or uid == "（无成员）":
            continue
        fam = families.setdefault(fid, {"name": str(row[1]).strip(), "members": []})
        if str(row[1]).strip():
            fam["name"] = str(row[1]).strip()
        if uid not in fam["members"]:
            fam["members"].append(uid)

    pairs: list[dict] = []
    odd_families: list[tuple[str, int]] = []
    for fid, info in sorted(families.items(), key=lambda item: item[0]):
        members = info["members"]
        if len(members) % 2 == 1:
            odd_families.append((fid, len(members)))
        for index in range(0, len(members) - 1, 2):
            if index + 1 < len(members):
                pairs.append(
                    {
                        "familyId": fid,
                        "familyName": info["name"],
                        "a": members[index],
                        "b": members[index + 1],
                    }
                )
    return pairs, odd_families, len(families)


def load_gift_pool() -> list[dict]:
    gifts = json.loads(GIFT_POOL_PATH.read_text(encoding="utf-8")).get("gifts") or []
    pool = [
        gift
        for gift in gifts
        if str(gift.get("price", "")).isdigit() and 100 <= int(gift["price"]) <= 100000
    ]
    if not pool:
        raise RuntimeError("礼物池为空，请先准备 /tmp/gift_panel_parsed.json")
    return pool


def build_markdown(
    pairs: list[dict],
    odd_families: list[tuple[str, int]],
    family_count: int,
    pair_results: list[dict],
    send_stats: dict,
    fail_reasons: Counter,
    topped_up_sends: int,
) -> str:
    pair_ok = sum(1 for row in pair_results if row["status"] == "成功")
    pair_fail = len(pair_results) - pair_ok
    odd_count = len(odd_families)
    unpaired_members = odd_count  # 每个奇数家族剩 1 人

    lines = [
        f"**家族互送礼物统计**（{datetime.now().strftime('%Y-%m-%d %H:%M')}）",
        "",
        "## 总体结论",
        "",
    ]
    if pair_fail == 0 and send_stats["fail"] == 0:
        lines.append(
            f"**全量可行**：{len(pair_results)} 组配对、{send_stats['total']} 笔互送全部成功。"
        )
    elif send_stats["ok"] / max(send_stats["total"], 1) >= 0.95:
        lines.append(
            f"**基本可行**：成功率 {send_stats['ok']}/{send_stats['total']} "
            f"（{send_stats['ok'] * 100 // send_stats['total']}%），"
            f"失败 {send_stats['fail']} 笔，需关注失败原因。"
        )
    else:
        lines.append(
            f"**部分失败**：成功率 {send_stats['ok']}/{send_stats['total']} "
            f"（{send_stats['ok'] * 100 // send_stats['total']}%），请排查失败账号/礼物。"
        )

    lines.extend(
        [
            "",
            "## 规模",
            "",
            f"- 表格家族数：**{family_count}**",
            f"- 可配对组数：**{len(pairs)}**（互送 **{len(pairs) * 2}** 笔）",
            f"- 奇数成员家族：**{odd_count}** 个（各剩 **1** 人无法配对，共 **{unpaired_members}** 人）",
            f"- 礼物价位：**100～100000** 钻随机",
            f"- 自动补钻：本次 **{topped_up_sends}** 笔触发了补钻",
            "",
            "## 互送结果",
            "",
            f"- 配对组成功：**{pair_ok}/{len(pair_results)}**",
            f"- 单笔送礼成功：**{send_stats['ok']}/{send_stats['total']}**",
            f"- 钻石消耗校验通过：**{send_stats['diamond_verified']}/{send_stats['total']}**",
            "",
        ]
    )

    if fail_reasons:
        lines.extend(["## 失败原因分布", ""])
        for reason, count in fail_reasons.most_common(10):
            lines.append(f"- {reason}: **{count}** 笔")
        lines.append("")

    failed_rows = [row for row in pair_results if row["status"] != "成功"]
    if failed_rows:
        lines.extend(
            [
                "## 失败明细（前 20 组）",
                "",
                "| 家族ID | 家族名称 | 成员A | 成员B | A→B | B→A | 结果 |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in failed_rows[:20]:
            name = str(row["familyName"]).replace("|", "\\|")
            lines.append(
                f"| {row['familyId']} | {name} | {row['a']} | {row['b']} | "
                f"{row['aToB']} | {row['bToA']} | {row['status']} |"
            )
        if len(failed_rows) > 20:
            lines.append("")
            lines.append(f"（另有 {len(failed_rows) - 20} 组失败，详见导出 JSON）")
    else:
        lines.extend(["## 失败明细", "", "无失败记录。"])

    return "\n".join(lines)


def main() -> int:
    pairs, odd_families, family_count = asyncio.run(read_pairs())
    pool = load_gift_pool()
    total = len(pairs)

    send_stats = {
        "total": 0,
        "ok": 0,
        "fail": 0,
        "diamond_verified": 0,
    }
    fail_reasons: Counter = Counter()
    topped_up_sends = 0
    pair_results: list[dict] = []

    report(0, total)

    for index, pair in enumerate(pairs, start=1):
        row = {
            "familyId": pair["familyId"],
            "familyName": pair["familyName"],
            "a": pair["a"],
            "b": pair["b"],
            "aToB": "",
            "bToA": "",
            "status": "成功",
        }
        for sender, receiver, key in (
            (pair["a"], pair["b"], "aToB"),
            (pair["b"], pair["a"], "bToA"),
        ):
            gift = random.choice(pool)
            send_stats["total"] += 1
            try:
                resp = run_gift(sender, receiver, str(gift["id"]))
                ok, msg = gift_success(resp)
                diamond = resp.get("diamond") or {}
                if diamond.get("topped_up"):
                    topped_up_sends += 1
                if (diamond.get("after_send") or {}).get("verified"):
                    send_stats["diamond_verified"] += 1
                elif not diamond:
                    send_stats["diamond_verified"] += 1

                if ok:
                    send_stats["ok"] += 1
                    top_note = (
                        f" 补钻{diamond['topped_up']}" if diamond.get("topped_up") else ""
                    )
                    row[key] = f"{gift['name']} {gift['price']}钻 ok{top_note}"
                else:
                    send_stats["fail"] += 1
                    row["status"] = "失败"
                    row[key] = f"{gift['name']} {gift['price']}钻 {msg}"
                    fail_reasons[msg.split(":")[0]] += 1
            except Exception as exc:  # noqa: BLE001 — 批量汇总须捕获单笔异常
                send_stats["fail"] += 1
                row["status"] = "失败"
                row[key] = f"异常: {exc}"
                fail_reasons["exception"] += 1

        pair_results.append(row)
        report(index, total, detail=f"家族 {pair['familyId']}")

        RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESULT_PATH.write_text(
            json.dumps(
                {
                    "pair_results": pair_results,
                    "send_stats": send_stats,
                    "fail_reasons": dict(fail_reasons),
                    "topped_up_sends": topped_up_sends,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    markdown = build_markdown(
        pairs,
        odd_families,
        family_count,
        pair_results,
        send_stats,
        fail_reasons,
        topped_up_sends,
    )
    report(total, total, result_text=markdown)
    print(markdown)
    return 0 if send_stats["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
