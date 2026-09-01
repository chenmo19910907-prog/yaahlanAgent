#!/usr/bin/env python3
"""奖励未下发通用拦截排查：风控 rule-id + 公会黑名单（可扩展更多拦截类型）。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

RISK_TEMPLATE = REPO / "MOA/templates/奖励下发-风控预检.json"
UNION_TEMPLATE = REPO / "MOA/templates/用户-查所属公会.json"
MSE_NAMESPACE = "voga-common"
MSE_BLACK_UNION_KEY = "blackUnionIdList"


def _run_json_cmd(cmd: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    merged = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode, proc.stdout or "", merged


def _parse_last_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    idx = 0
    last: dict[str, Any] | None = None
    while idx < len(text):
        start = text.find("{", idx)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(payload, dict):
            last = payload
        idx = end
    return last


def _fetch_black_union_ids() -> list[str]:
    cmd = [
        sys.executable,
        str(REPO / "MSE/mse_execute.py"),
        "--namespace",
        MSE_NAMESPACE,
        "--config-key",
        MSE_BLACK_UNION_KEY,
        "--output",
        "value",
    ]
    code, stdout, merged = _run_json_cmd(cmd)
    if code != 0:
        raise RuntimeError((merged or "读取 MSE blackUnionIdList 失败").strip())
    raw = stdout.strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"blackUnionIdList 不是合法 JSON: {raw[:200]}") from exc
    if isinstance(parsed, list):
        return [str(x).strip() for x in parsed if str(x).strip()]
    if isinstance(parsed, dict):
        items = parsed.get("list") or parsed.get("blackUnionIdList") or []
        if isinstance(items, list):
            return [str(x).strip() for x in items if str(x).strip()]
    raise RuntimeError(f"无法解析 blackUnionIdList: {raw[:200]}")


def _call_moa_template(
    template: Path,
    *,
    expr: str | None = None,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(REPO / "MOA/moa_execute.py"),
        "--payload-file",
        str(template),
    ]
    if expr is not None:
        cmd.extend(["--expr", expr])
    if extra_args:
        cmd.extend(extra_args)
    code, stdout, merged = _run_json_cmd(cmd)
    payload = _parse_last_json_object(stdout) or _parse_last_json_object(merged)
    if payload is None:
        raise RuntimeError((merged or "MOA 无 JSON 返回").strip())
    if code != 0:
        payload["_exitCode"] = code
    return payload


def _inner_from_moa(resp: dict[str, Any]) -> tuple[int, str, Any]:
    inner = resp.get("result")
    if not isinstance(inner, dict):
        return -1, "result 不是 object", None
    try:
        ec = int(inner.get("ec"))
    except (TypeError, ValueError):
        ec = -1
    em = inner.get("em")
    return ec, em if isinstance(em, str) else str(em), inner.get("result")


def _fetch_trade_union(user_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "source": "moa:userJoinedTrade",
        "tradeUnionId": None,
        "tradeUnionName": None,
        "ok": False,
        "error": None,
    }
    try:
        resp = _call_moa_template(UNION_TEMPLATE, expr=user_id)
        ec, em, result = _inner_from_moa(resp)
        if ec != 0:
            out["error"] = f"ec={ec}, em={em}"
            return out
        if isinstance(result, dict):
            out["tradeUnionId"] = result.get("tradeUnionId") or result.get("tradeId")
            out["tradeUnionName"] = result.get("tradeUnionName") or result.get("tradeUnion")
        elif result is not None:
            out["tradeUnionId"] = str(result)
        out["ok"] = True
        return out
    except RuntimeError as exc:
        out["error"] = str(exc)
        return out


def _check_trade_union_blacklist(user_id: str, black_union_ids: list[str]) -> dict[str, Any]:
    union = _fetch_trade_union(user_id)
    trade_union_id = str(union.get("tradeUnionId") or "").strip()
    blocked = bool(trade_union_id and trade_union_id in set(black_union_ids))
    return {
        "type": "trade_union_blacklist",
        "label": "公会黑名单",
        "blocked": blocked,
        "userId": user_id,
        "tradeUnionId": trade_union_id or None,
        "tradeUnionName": union.get("tradeUnionName"),
        "blackUnionIdList": black_union_ids,
        "queryOk": union.get("ok"),
        "queryError": union.get("error"),
    }


def _check_reward_risk(user_id: str, rule_id: str, scene: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": "reward_risk",
        "label": "发钻风控",
        "blocked": False,
        "userId": user_id,
        "ruleId": rule_id,
        "scene": scene,
        "control": None,
        "queryOk": False,
        "queryError": None,
    }
    try:
        resp = _call_moa_template(
            RISK_TEMPLATE,
            expr=user_id,
            extra_args=[
                "--reward-risk-rule-id",
                rule_id,
                "--reward-risk-scene",
                scene,
            ],
        )
        ec, em, result = _inner_from_moa(resp)
        if ec != 0:
            out["queryError"] = f"ec={ec}, em={em}"
            return out
        out["queryOk"] = True
        if isinstance(result, dict):
            control = result.get("control") or result.get("action")
            out["control"] = control
            out["blocked"] = str(control or "").lower() == "deny"
            out["raw"] = result
        elif isinstance(result, str):
            out["control"] = result
            out["blocked"] = result.lower() == "deny"
        return out
    except RuntimeError as exc:
        out["queryError"] = str(exc)
        return out


def check_reward_dispatch_blocks(
    user_id: str,
    *,
    rule_id: str = "221",
    scene: str = "match_pk",
    skip_risk: bool = False,
    skip_union: bool = False,
) -> dict[str, Any]:
    user_id = str(user_id).strip()
    blocks: list[dict[str, Any]] = []

    if not skip_union:
        black_union_ids = _fetch_black_union_ids()
        blocks.append(_check_trade_union_blacklist(user_id, black_union_ids))

    if not skip_risk:
        blocks.append(_check_reward_risk(user_id, rule_id, scene))

    blocked_items = [b for b in blocks if b.get("blocked")]
    summary_parts: list[str] = []
    if not blocked_items:
        pending = [b for b in blocks if not b.get("queryOk")]
        if pending:
            summary_parts.append("未发现拦截，但部分检查未成功（见 queryError）")
        else:
            summary_parts.append("未发现已知拦截（风控/公会黑名单）")
    else:
        for item in blocked_items:
            if item["type"] == "reward_risk":
                summary_parts.append(f"发钻风控拦截 ruleId={item.get('ruleId')}")
            elif item["type"] == "trade_union_blacklist":
                summary_parts.append(
                    f"公会黑名单拦截 tradeUnionId={item.get('tradeUnionId')}"
                )

    return {
        "userId": user_id,
        "ruleId": rule_id,
        "scene": scene,
        "blocked": bool(blocked_items),
        "blocks": blocks,
        "summary": "；".join(summary_parts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="奖励未下发通用拦截排查")
    parser.add_argument("--user-id", required=True, help="待排查 userId")
    parser.add_argument(
        "--rule-id",
        default="221",
        help="发钻风控 rule_id（各活动见 MSE/Application rewardRiskRuleId；默认 221）",
    )
    parser.add_argument(
        "--scene",
        default="match_pk",
        help="风控场景参数 pk_type/scene（默认 match_pk；不同活动可能不同）",
    )
    parser.add_argument("--skip-risk", action="store_true", help="跳过风控预检")
    parser.add_argument("--skip-union", action="store_true", help="跳过公会黑名单检查")
    args = parser.parse_args()

    result = check_reward_dispatch_blocks(
        args.user_id,
        rule_id=str(args.rule_id).strip(),
        scene=str(args.scene).strip(),
        skip_risk=args.skip_risk,
        skip_union=args.skip_union,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("blocked"):
        return 2
    pending = [b for b in result.get("blocks") or [] if not b.get("queryOk")]
    return 3 if pending else 0


if __name__ == "__main__":
    raise SystemExit(main())
