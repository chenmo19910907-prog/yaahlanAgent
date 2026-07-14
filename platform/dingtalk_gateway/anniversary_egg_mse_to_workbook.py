#!/usr/bin/env python3
"""3周年砸金蛋 MSE 配置 activityConfig.Year3Anniversary → 钉钉 Sheet「金蛋活动配置」。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GATEWAY_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATEWAY_DIR.parents[1]
_EXCEL_VENV = (
    REPO_ROOT / ".cursor/skills/testcase-to-excel/mcp_dingtalk_excel/venv/bin/python3.13"
)

if (
    __name__ == "__main__"
    and _EXCEL_VENV.is_file()
    and Path(sys.executable).resolve() != _EXCEL_VENV.resolve()
):
    os.execv(str(_EXCEL_VENV), [str(_EXCEL_VENV), str(Path(__file__).resolve()), *sys.argv[1:]])

if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from alidocs_excel_export import _excel_env, _get_token_and_operator  # noqa: E402
from family_pk_tab_to_workbook import _ensure_sheet, _string_rows, _write_sheet_replace  # noqa: E402
from mse_sync_to_workbook import _sheet_cell  # noqa: E402
from mse_workbook_utils import node_id  # noqa: E402

import httpx  # noqa: E402

DEFAULT_WORKBOOK = (
    "https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7wodldC4ow9vLPVGXn6lpz"
)
DEFAULT_SHEET = "金蛋活动配置"
DEFAULT_CONFIG_KEY = "activityConfig.Year3Anniversary"
DEFAULT_NAMESPACE = "Application"

# gradeBonus / 装扮 itemType 约定（结合 frame/vehicle/ownerBg 配置）
ITEM_TYPE_LABEL = {
    1: "头像框",
    2: "头像框/装扮",
    3: "座驾",
    4: "房主背景",
    5: "房间背景加成",
}


def _lookup_gift_names(gift_ids: list[str]) -> dict[str, dict[str, Any]]:
    """尽量查礼物名/价格；失败不阻断写表。"""
    out: dict[str, dict[str, Any]] = {}
    if not gift_ids:
        return out
    try:
        sys.path.insert(0, str(REPO_ROOT / "Gift"))
        from gift.send_stage import query_gift  # noqa: E402
    except Exception:
        return out
    for gid in gift_ids:
        try:
            meta = query_gift(str(gid), lang="en")
            out[str(gid)] = {
                "name": meta.get("productName") or "",
                "price": meta.get("price"),
            }
        except Exception:
            continue
    return out


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _pct(weight: int | float, total: int | float) -> str:
    if not total:
        return ""
    return f"{100.0 * float(weight) / float(total):.2f}%"


def fetch_year3_mse_config(
    *,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """返回 (parsed_config, mse_meta)。"""
    cmd = [
        "python3",
        str(REPO_ROOT / "MSE/mse_execute.py"),
        "--namespace",
        namespace,
        "--config-key",
        config_key,
        "--cluster",
        cluster,
        "--env",
        env,
        "--region",
        region,
        "--output",
        "json",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "MSE 读取失败").strip())
    data = json.loads(proc.stdout)
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"未找到配置 {namespace}/{config_key}")
    item = data[0]
    if not isinstance(item, dict):
        raise RuntimeError("MSE 返回格式异常")
    raw_value = item.get("configValue")
    if isinstance(raw_value, str):
        parsed = json.loads(raw_value)
    elif isinstance(raw_value, dict):
        parsed = raw_value
    else:
        raise RuntimeError("configValue 不是 JSON 对象")
    if not isinstance(parsed, dict):
        raise RuntimeError("configValue 解析后不是对象")
    meta = {
        "nameSpace": item.get("nameSpace") if item.get("nameSpace") not in (None, "") else "Application（私有）",
        "configKey": item.get("configKey") or config_key,
        "configDesc": item.get("configDesc") or "",
        "modified": item.get("modified") or "",
        "appKey": item.get("appKey") or "",
        "region": region,
        "env": env,
        "cluster": cluster,
    }
    return parsed, meta


def build_analysis_rows(
    cfg: dict[str, Any],
    *,
    meta: dict[str, Any],
) -> list[list[Any]]:
    synced = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows: list[list[Any]] = [
        [
            "3周年砸金蛋 · MSE 活动配置分析",
            "",
            "",
            "",
            f"同步时间 {synced}",
        ],
        ["区块", "参数/项", "值", "补充", "说明"],
    ]

    def kv(section: str, key: str, value: Any, extra: Any = "", note: str = "") -> None:
        rows.append([section, key, _cell(value), _cell(extra), note])

    def blank() -> None:
        rows.append(["", "", "", "", ""])

    # 元数据
    for key, note in (
        ("nameSpace", "MSE 命名空间（抓包 nameSpace 为空=私有 Application）"),
        ("configKey", "配置键"),
        ("appKey", "appKey"),
        ("region", "region/corp"),
        ("env", "env"),
        ("cluster", "cluster"),
        ("modified", "MSE 修改时间"),
        ("configDesc", "配置说明"),
    ):
        kv("元数据", key, meta.get(key, ""), "", note)

    blank()
    kv("基础", "dataVersion", cfg.get("dataVersion"), "", "配置版本")
    kv("基础", "startTime", cfg.get("startTime"), "", "活动开始")
    kv("基础", "endTime", cfg.get("endTime"), "", "活动结束")
    kv("基础", "dailyFreeChances", cfg.get("dailyFreeChances"), "", "每日免费砸蛋次数")
    kv(
        "基础",
        "diamondPerChance",
        cfg.get("diamondPerChance"),
        "",
        "获次规则：自己送给自己（giftIds 内礼物）每累计 500 钻可增加 1 次砸蛋机会（非砸蛋消耗）",
    )
    kv(
        "基础",
        "maxSmashPerClick",
        cfg.get("maxSmashPerClick"),
        "",
        "单次点击最多砸几个（剩余>此值按此值；≤则砸完）",
    )
    kv(
        "基础",
        "eggExpire",
        cfg.get("eggExpire"),
        "",
        "金蛋相关过期参数（单位以服务端为准，当前配置值）",
    )
    kv("基础", "enableRiskControl", cfg.get("enableRiskControl"), "", "是否开启风控")
    gift_ids = cfg.get("giftIds") or []
    kv(
        "基础",
        "giftIds",
        gift_ids,
        "",
        "可增加砸蛋次数的礼物；自己送自己，按 diamondPerChance 折算次数",
    )
    # 展开 giftIds 名称（能查到则写；查不到仍保留 ID）
    gift_name_map = _lookup_gift_names(
        [str(x) for x in gift_ids] if isinstance(gift_ids, list) else []
    )
    if isinstance(gift_ids, list):
        for idx, gid in enumerate(gift_ids):
            gid_s = str(gid)
            info = gift_name_map.get(gid_s) or {}
            name = info.get("name") or ""
            price = info.get("price")
            kv(
                "获次礼物 giftIds",
                f"[{idx}] {gid_s}",
                name or gid_s,
                f"price={price}" if price is not None else "",
                "自己送给自己可增加砸蛋次数（每 diamondPerChance 钻 +1 次）",
            )
    kv("基础", "whiteUsers", cfg.get("whiteUsers"), "", "白名单用户")
    kv("基础", "storeLotteryId", cfg.get("storeLotteryId"), "", "商城抽奖 ID")
    kv("基础", "smashRankBagId", cfg.get("smashRankBagId"), "", "砸蛋榜 bag")
    kv("基础", "revenueRankBagId", cfg.get("revenueRankBagId"), "", "营收榜 bag")
    kv("基础", "gotoStr", cfg.get("gotoStr"), "", "活动 H5 跳转")

    blank()
    pool = cfg.get("eggPoolConfig") or {}
    if isinstance(pool, dict):
        for key, note in (
            ("freeLotteryId", "免费次数奖池"),
            ("lv1LotteryId", "LV1 金蛋奖池"),
            ("lv2LotteryId", "LV2 金蛋奖池"),
            ("lv3LotteryId", "LV3 金蛋奖池"),
            ("voucherLotteryId", "券/凭证奖池"),
            ("mysteryLotteryId", "神秘奖励奖池（钻石特殊奖等）"),
        ):
            kv("奖池 lotteryId", key, pool.get(key), "", note)
        rows.append(
            [
                "奖池 lotteryId",
                "备注",
                "",
                "",
                "头像框下发天数不在本配置；一般在对应 lottery 奖品配置里。smashEgg 返回 TOOL 也无天数字段。",
            ]
        )

    blank()
    mystery = cfg.get("mysteryConfig") or {}
    if isinstance(mystery, dict):
        u_mod = mystery.get("userGuaranteeMod")
        room_mod = mystery.get("roomGuaranteeMod")
        plat_mod = mystery.get("platformGuaranteeMod")
        kv(
            "神秘奖励保底",
            "userGuaranteeMod",
            u_mod,
            "",
            "用户维度：每砸 N 次保底触发神秘奖",
        )
        kv(
            "神秘奖励保底",
            "roomGuaranteeMod",
            room_mod,
            "",
            "房间维度保底模数",
        )
        kv(
            "神秘奖励保底",
            "platformGuaranteeMod",
            plat_mod,
            "",
            "平台维度保底模数",
        )
        kv(
            "神秘奖励保底",
            "bubbleThreshold",
            mystery.get("bubbleThreshold"),
            "",
            "气泡展示门槛",
        )
        blank()
        # 落表理论计算说明（砸金蛋测试记录 Sheet）
        egg_icon = cfg.get("eggIconConfig") or {}
        lv1 = (egg_icon.get("1") or {}) if isinstance(egg_icon, dict) else {}
        lv2 = (egg_icon.get("2") or {}) if isinstance(egg_icon, dict) else {}
        t1 = int(lv1.get("upgradeThreshold") or 100) if isinstance(lv1, dict) else 100
        t2 = int(lv2.get("upgradeThreshold") or 200) if isinstance(lv2, dict) else 200
        kv(
            "落表理论计算",
            "砸蛋时金蛋等级",
            f"房间累计门槛 LV1→2={t1}，LV2→3={t2}；过期仅 LV2/LV3={lv2.get('expireSeconds')}/{(egg_icon.get('3') or {}).get('expireSeconds') if isinstance(egg_icon.get('3'), dict) else ''}（LV1 无过期）",
            f"空闲≥expireSeconds 按「记录写入时间」掉级（忽略 LV1 时间配置）",
            "按房间状态机：upgradeThreshold 升级；LV2/LV3 空闲过期掉级；接口 smashCount 为当前等级内计数",
        )
        kv(
            "落表理论计算",
            "神秘奖励",
            f"用户每{u_mod}次 / 房间每{room_mod}次 / 平台每{plat_mod}次",
            "同颗蛋多保底：用户>房间>平台，未消耗顺延下一颗；本砸仍剩余则顺延到下一次砸蛋预期；一次砸 N 蛋最多 N 次保底；多保底钻石合并为一段",
            "逐颗模拟越过保底倍数 →「理论触发」+「顺延下次」；有实发神秘即通过（不按奖品段数计次）",
        )
        kv(
            "落表理论计算",
            "验收结论",
            "①神秘奖励是否符合预期；②金蛋等级档次礼物是否符合预期；③砸蛋次数与房/用/平累加",
            "应触发保底须有实发（钻石可合并）；非保底不得有实发/理论触发；有砸次则档次奖励非空且非奖池预览",
            "写入 Sheet「砸金蛋测试记录」的「验收结论」列",
        )

    blank()
    egg_icon = cfg.get("eggIconConfig") or {}
    if isinstance(egg_icon, dict):
        for lv in sorted(egg_icon.keys(), key=lambda x: int(str(x) or 0)):
            info = egg_icon.get(lv) or {}
            if not isinstance(info, dict):
                continue
            expire_sec = info.get("expireSeconds")
            expire_note = ""
            try:
                expire_note = f"{int(expire_sec) // 60} 分钟" if expire_sec is not None else ""
            except (TypeError, ValueError):
                expire_note = ""
            kv(
                "金蛋等级",
                f"LV{lv}.upgradeThreshold",
                info.get("upgradeThreshold"),
                "",
                "升到下一档所需房间砸蛋次数增量门槛",
            )
            kv(
                "金蛋等级",
                f"LV{lv}.expireSeconds",
                expire_sec,
                expire_note,
                "本等级停留/回退相关过期秒数",
            )
            kv("金蛋等级", f"LV{lv}.eggIcon", info.get("eggIcon"), "", "金蛋图标")

    blank()
    for item in cfg.get("gradeBonusConfigs") or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("itemType")
        grade = item.get("grade")
        type_label = ITEM_TYPE_LABEL.get(int(item_type), f"类型{item_type}") if str(item_type).isdigit() or isinstance(item_type, int) else str(item_type)
        tiers = item.get("triggerTiers") or []
        total_w = 0
        for t in tiers:
            if isinstance(t, dict):
                try:
                    total_w += int(t.get("weight") or 0)
                except (TypeError, ValueError):
                    pass
        for t in tiers:
            if not isinstance(t, dict):
                continue
            w = t.get("weight")
            try:
                w_i = int(w or 0)
            except (TypeError, ValueError):
                w_i = 0
            kv(
                "档次加成权重",
                f"itemType={item_type}({type_label}) grade={grade}",
                f"rewardRate={t.get('rewardRate')}",
                f"weight={w} ({_pct(w_i, total_w)})",
                "触发倍率/档位权重（非头像框天数）",
            )

    blank()
    frame = cfg.get("frameConfig") or {}
    if isinstance(frame, dict):
        kv("头像框 frameConfig", "animationUrl", frame.get("animationUrl"), "", "钻石框动画")
        for it in frame.get("items") or []:
            if not isinstance(it, dict):
                continue
            kv(
                "头像框 frameConfig",
                f"itemId={it.get('itemId')}",
                f"itemType={it.get('itemType')} grade={it.get('grade')}",
                f"exclusiveGift={it.get('exclusiveGift')}",
                "无 days/expire 字段；天数需查装扮/lottery 配置",
            )

    blank()
    vehicle = cfg.get("vehicleConfig") or {}
    if isinstance(vehicle, dict):
        for key, note in (
            ("dailyPlatformLimit", "平台日限"),
            ("cooldownMinutes", "冷却分钟"),
            ("maxHitUsers", "最大命中用户数"),
            ("minDiamondRoomNotice", "房间通知最低钻石"),
        ):
            kv("座驾 vehicleConfig", key, vehicle.get(key), "", note)
        for it in vehicle.get("items") or []:
            if not isinstance(it, dict):
                continue
            kv(
                "座驾 vehicleConfig",
                f"itemId={it.get('itemId')}",
                f"itemType={it.get('itemType')} grade={it.get('grade')}",
                f"scatterLotteryId={it.get('scatterLotteryId')}",
                "座驾道具",
            )

    blank()
    owner = cfg.get("ownerBgConfig") or {}
    if isinstance(owner, dict):
        kv("房主背景 ownerBgConfig", "dailyLimit", owner.get("dailyLimit"), "", "日限")
        for it in owner.get("items") or []:
            if not isinstance(it, dict):
                continue
            kv(
                "房主背景 ownerBgConfig",
                f"itemId={it.get('itemId')}",
                f"itemType={it.get('itemType')} grade={it.get('grade')}",
                "",
                "房主背景道具",
            )

    blank()
    for idx, room in enumerate(cfg.get("roomBgPropConfigList") or []):
        if not isinstance(room, dict):
            continue
        kv(
            "房间背景倍率",
            f"[{idx}] itemId={room.get('itemId')} grade={room.get('grade')}",
            room.get("roomBgPropIdList"),
            "",
            "房间背景道具 ID 列表",
        )
        for m in room.get("singleMultipliers") or []:
            if isinstance(m, dict):
                kv(
                    "房间背景倍率",
                    f"[{idx}] single ×{m.get('multiplier')}",
                    m.get("probability"),
                    "",
                    "单次砸蛋倍率权重/概率配置",
                )
        for m in room.get("batchMultipliers") or []:
            if isinstance(m, dict):
                kv(
                    "房间背景倍率",
                    f"[{idx}] batch ×{m.get('multiplier')}",
                    m.get("probability"),
                    "",
                    "批量砸蛋倍率权重/概率配置",
                )

    blank()
    prize = cfg.get("prizeConfig") or {}
    if isinstance(prize, dict):
        kv("发奖 prizeConfig", "source", prize.get("source"), "", "")
        kv("发奖 prizeConfig", "desc", prize.get("desc"), "", "")
        pkg = prize.get("prizePackageConfig") or {}
        dia = prize.get("prizeDiamondConfig") or {}
        if isinstance(pkg, dict):
            kv("发奖 prizeConfig", "prizePackageConfig", pkg, "", "礼包发奖")
        if isinstance(dia, dict):
            kv("发奖 prizeConfig", "prizeDiamondConfig", dia, "", "钻石发奖")

    blank()
    for section, key in (
        ("广播 smashBroadcastConfig", "smashBroadcastConfig"),
        ("广播 mysteryBroadcastConfig", "mysteryBroadcastConfig"),
        ("广播 upgradeBroadcastConfig", "upgradeBroadcastConfig"),
    ):
        conf = cfg.get(key) or {}
        if isinstance(conf, dict):
            for ck, cv in conf.items():
                kv(section, ck, cv, "", "")

    blank()
    rows.append(
        [
            "完整 JSON",
            "configValue",
            json.dumps(cfg, ensure_ascii=False),
            "",
            "原始 configValue（一行，便于对照）",
        ]
    )
    return rows


async def write_config_sheet_async(
    workbook_url_or_id: str,
    rows: list[list[Any]],
    *,
    sheet_name: str = DEFAULT_SHEET,
) -> str:
    workbook_id = node_id(workbook_url_or_id)
    url = f"https://alidocs.dingtalk.com/i/nodes/{workbook_id}"
    env = _excel_env()
    token, operator = await _get_token_and_operator(env)
    async with httpx.AsyncClient(timeout=120) as client:
        await _ensure_sheet(
            token=token,
            operator=operator,
            workbook_id=workbook_id,
            sheet_name=sheet_name,
            client=client,
        )
    await _write_sheet_replace(
        token=token,
        operator=operator,
        workbook_id=workbook_id,
        sheet_name=sheet_name,
        rows=_string_rows([[_sheet_cell(c) for c in r] for r in rows]),
    )
    return url


def sync_year3_mse_to_workbook(
    *,
    workbook: str = DEFAULT_WORKBOOK,
    sheet_name: str = DEFAULT_SHEET,
    namespace: str = DEFAULT_NAMESPACE,
    config_key: str = DEFAULT_CONFIG_KEY,
    cluster: str = "alpha",
    env: str = "alpha",
    region: str = "alpha",
    dry_run: bool = False,
) -> dict[str, Any]:
    cfg, meta = fetch_year3_mse_config(
        namespace=namespace,
        config_key=config_key,
        cluster=cluster,
        env=env,
        region=region,
    )
    rows = build_analysis_rows(cfg, meta=meta)
    out: dict[str, Any] = {
        "sheetName": sheet_name,
        "rowCount": len(rows),
        "meta": meta,
        "highlights": {
            "startTime": cfg.get("startTime"),
            "endTime": cfg.get("endTime"),
            "dailyFreeChances": cfg.get("dailyFreeChances"),
            "diamondPerChance": cfg.get("diamondPerChance"),
            "giftIds": cfg.get("giftIds"),
            "giftChanceRule": "自己送自己 giftIds 礼物，每 diamondPerChance 钻 +1 砸蛋次数",
            "maxSmashPerClick": cfg.get("maxSmashPerClick"),
            "eggPoolConfig": cfg.get("eggPoolConfig"),
            "mysteryConfig": cfg.get("mysteryConfig"),
            "eggIconConfig": {
                str(lv): {
                    "upgradeThreshold": (info or {}).get("upgradeThreshold"),
                    "expireSeconds": (info or {}).get("expireSeconds"),
                }
                for lv, info in (cfg.get("eggIconConfig") or {}).items()
                if isinstance(info, dict)
            },
            "frameConfigHasDays": False,
            "frameNote": "frameConfig.items 无天数；天数需查 lottery/装扮配置",
        },
    }
    if dry_run:
        out["rowsPreview"] = rows[:30]
        return out
    url = asyncio.run(
        write_config_sheet_async(workbook, rows, sheet_name=sheet_name)
    )
    out["workbookUrl"] = url
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="3周年金蛋 MSE 配置写入钉钉表")
    parser.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet-name", default=DEFAULT_SHEET)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--cluster", default="alpha")
    parser.add_argument("--env", default="alpha")
    parser.add_argument("--region", default="alpha")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = sync_year3_mse_to_workbook(
        workbook=args.workbook,
        sheet_name=args.sheet_name,
        namespace=args.namespace,
        config_key=args.config_key,
        cluster=args.cluster,
        env=args.env,
        region=args.region,
        dry_run=args.dry_run,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 — CLI 边界打印
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
