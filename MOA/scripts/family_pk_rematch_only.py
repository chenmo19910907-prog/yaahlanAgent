#!/usr/bin/env python3
"""清除指定日期家族 PK 匹配并重新匹配（runFamilyPkMatchTask）。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CLEAR_TPL = _REPO / "MOA/templates/家族PK-清除匹配数据.json"
_MATCH_TPL = _REPO / "MOA/templates/家族PK-结算发奖匹配.json"


def _patch_template(path: Path, *, pk_date: str, timeout_ms: int | None = None) -> Path:
    tpl = json.loads(path.read_text(encoding="utf-8"))
    if path.name.startswith("家族PK-清除匹配数据"):
        tpl["params"][0]["value"] = {"date": pk_date}
        tpl["params"][0]["json"] = json.dumps({"date": pk_date}, ensure_ascii=False)
    else:
        tpl["params"][0]["value"] = pk_date
        tpl["params"][0]["txt"] = pk_date
        if timeout_ms is not None:
            tpl.setdefault("settings", {})["time"] = str(timeout_ms)
    out = _REPO / ".tmp" / f"family_pk_rematch_{path.stem}_{pk_date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tpl, ensure_ascii=False), encoding="utf-8")
    return out


def _run_payload(payload_path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(_REPO / "MOA/moa_execute.py"), "--payload-file", str(payload_path)],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    text = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(text[-800:])
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {"raw": text}
    return json.loads(text[start : end + 1])


def run_clear_and_rematch(*, pk_date: str, timeout_ms: int) -> dict[str, Any]:
    clear_path = _patch_template(_CLEAR_TPL, pk_date=pk_date)
    match_path = _patch_template(_MATCH_TPL, pk_date=pk_date, timeout_ms=timeout_ms)
    clear_resp = _run_payload(clear_path)
    match_resp = _run_payload(match_path)
    inner = match_resp.get("result", {}).get("result", match_resp.get("result"))
    return {
        "pkDate": pk_date,
        "timeoutMs": timeout_ms,
        "clearResponse": clear_resp,
        "matchResponse": inner,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="清除并重匹配家族 PK")
    parser.add_argument("--pk-date", required=True, help="PK/匹配日期 yyyy-MM-dd")
    parser.add_argument("--timeout-ms", type=int, default=180000, help="runFamilyPkMatchTask 超时")
    args = parser.parse_args()
    try:
        summary = run_clear_and_rematch(
            pk_date=args.pk_date.strip(),
            timeout_ms=args.timeout_ms,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
