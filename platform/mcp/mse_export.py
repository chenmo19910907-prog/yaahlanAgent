"""MSE 配置导出到钉钉表格 — MCP tool 与 CLI 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATEWAY_DIR = _REPO_ROOT / "platform" / "dingtalk_gateway"
if str(_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(_GATEWAY_DIR))

from family_monster_lottery_to_workbook import (  # noqa: E402
    sync_family_monster_lottery_to_workbook,
)
from family_monster_mse_to_workbook import (  # noqa: E402
    DEFAULT_WORKBOOK,
    sync_family_monster_to_workbook,
)

FAMILY_MONSTER_CONFIG_KEY = "activityConfig.FamilyMonster"
_EXPORT_KINDS = frozenset({"config", "lottery", "both"})


def mse_export_to_workbook(
    *,
    config_key: str,
    export_kind: str = "config",
    namespace: str = "voga-common",
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
    workbook: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """将 MSE 配置同步到钉钉表格。

    export_kind: config | lottery | both
    """
    kind = (export_kind or "config").strip().lower()
    if kind not in _EXPORT_KINDS:
        return {
            "ok": False,
            "error": f"export_kind 须为 config / lottery / both，收到: {export_kind!r}",
        }

    key = config_key.strip()
    if key != FAMILY_MONSTER_CONFIG_KEY:
        return {
            "ok": False,
            "error": f"暂仅支持 {FAMILY_MONSTER_CONFIG_KEY}，收到: {key!r}",
        }

    target_workbook = (workbook or DEFAULT_WORKBOOK).strip()
    common = {
        "namespace": namespace,
        "config_key": key,
        "cluster": cluster,
        "env": env,
        "region": region,
        "dry_run": dry_run,
        "workbook": target_workbook,
    }
    out: dict[str, Any] = {"ok": True, "configKey": key, "exportKind": kind, **common}

    try:
        if kind in ("config", "both"):
            out["configSheet"] = sync_family_monster_to_workbook(
                namespace=namespace,
                config_key=key,
                cluster=cluster,
                env=env,
                region=region,
                workbook_url=target_workbook,
                dry_run=dry_run,
            )

        if kind in ("lottery", "both"):
            out["lotterySheet"] = sync_family_monster_lottery_to_workbook(
                workbook=target_workbook,
                namespace=namespace,
                config_key=key,
                cluster=cluster,
                env=env,
                region=region,
                dry_run=dry_run,
            )
    except Exception as exc:
        return {"ok": False, "error": str(exc), **common}

    if not dry_run:
        for sheet_key in ("configSheet", "lotterySheet"):
            sheet = out.get(sheet_key)
            if isinstance(sheet, dict) and sheet.get("workbookUrl"):
                out["workbookUrl"] = sheet["workbookUrl"]

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="MSE 配置导出到钉钉表格")
    parser.add_argument("--config-key", default=FAMILY_MONSTER_CONFIG_KEY)
    parser.add_argument(
        "--export-kind",
        choices=sorted(_EXPORT_KINDS),
        default="config",
        help="config=怪兽挑战配置；lottery=奖池配置；both=两者",
    )
    parser.add_argument("--namespace", default="voga-common")
    parser.add_argument("--cluster", default="alpha")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--workbook", default="", help="钉钉表 URL，省略用默认")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = mse_export_to_workbook(
        config_key=args.config_key,
        export_kind=args.export_kind,
        namespace=args.namespace,
        cluster=args.cluster,
        env=args.env,
        region=args.region,
        workbook=args.workbook.strip() or None,
        dry_run=args.dry_run,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
