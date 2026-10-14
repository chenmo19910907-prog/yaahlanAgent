#!/usr/bin/env python3
"""批量重命名 registry / 模板中歧义 category（括号前语义化，保留括号内技术后缀）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform"))
from project.loader import load_sources  # noqa: E402

# old category -> new category（整串替换）
RENAMES: dict[str, str] = {
    # 礼物 / 背包（工具台「礼物」模块常见重复项）
    "礼物（/v2/gift/send · Stage HTTP）": "Stage HTTP私聊送礼（/v2/gift/send · Stage HTTP）",
    "礼物（mdp-nova / giftAdmin）": "Admin礼物配置（mdp-nova / giftAdmin）",
    "背包礼物": "背包礼物-工作流（MOA+Tunnel）",
    "背包礼物（voga-base-service-middle-gift-stage）": "MOA背包礼物（voga-base-service-middle-gift-stage）",
    # 动态
    "动态（feed-stage）": "动态-发布（feed-stage）",
    "动态（feed-comment-stage）": "动态-评论（feed-comment-stage）",
    "动态（feed-interact-stage）": "动态-互动（feed-interact-stage）",
    "动态（/v2/gift/send · Stage HTTP）": "动态-帖子送礼（/v2/gift/send · Stage HTTP）",
    # 客服 / 举报
    "客服（/v2/report/submit · Stage HTTP）": "Stage HTTP举报（/v2/report/submit · Stage HTTP）",
    "客服（melon-gateway / cms/customerservice）": "Admin客服（melon-gateway / cms/customerservice）",
    # 家族
    "家族": "家族-基金（workflow）",
    "家族（external/user/family-api）": "家族-API（external/user/family-api）",
    "家族（internal/user/family-moa）": "家族-MOA（internal/user/family-moa）",
    "家族（melon-gateway）": "Admin家族（melon-gateway）",
    "家族PK": "家族PK-工作流（workflow）",
    "家族PK（vas/activity/family-pk-v2-api）": "家族PK-API（vas/activity/family-pk-v2-api）",
    "家族PK（vas/internal/family-pk-moa）": "家族PK-MOA（vas/internal/family-pk-moa）",
    "家族怪兽（vas/internal/family-monster · getMonsterDetail）": "家族怪兽-详情（vas/internal/family-monster · getMonsterDetail）",
    "家族怪兽（vas/internal/family-monster）": "家族怪兽-MOA（vas/internal/family-monster）",
    "家族怪兽（yh-components/gift-panel · getGiftPanel）": "家族怪兽-礼物面板（yh-components/gift-panel · getGiftPanel）",
    # 用户 Admin
    "用户（yaahlan-admin）": "Admin用户（yaahlan-admin）",
    "用户（mdp-nova / userAdmin）": "Nova用户（mdp-nova / userAdmin）",
    "用户（mdp-nova / userAdmin + MOA）": "Nova用户+MOA（mdp-nova / userAdmin + MOA）",
    "用户资料（userProfile）": "生成式用户资料（userProfile）",
    "用户资料（voga-mts-user-profile-stage）": "MOA用户资料（voga-mts-user-profile-stage）",
    # 定制
    "定制礼物（melon-gateway）": "Admin定制礼物（melon-gateway）",
    "定制礼物（yaahlan-admin）": "Admin定制礼物详情（yaahlan-admin）",
    "定制礼物（voga-components/gateway/custom-gift-stage）": "MOA定制礼物（voga-components/gateway/custom-gift-stage）",
    # 公会
    "公会（melon-gateway / cms/anchor）": "Admin公会（melon-gateway / cms/anchor）",
    "公会（yaahlan-anchor-recruit-moa-stage）": "MOA公会招募（yaahlan-anchor-recruit-moa-stage）",
    # 支付 / 钻石
    "钻石（voga-base-service-middle-pay-stage）": "MOA钻石（voga-base-service-middle-pay-stage）",
    "钻石（wallet-api）": "生成式MOA钻石（wallet-api）",
    # PK
    "PK提款机": "PK提款机-工作流（workflow）",
    "PK提款机（room/internal/room-pk）": "MOA PK提款机（room/internal/room-pk）",
    "房间PK（room/external/room-pk-api）": "房间PK-API（room/external/room-pk-api）",
    "房间PK（room/internal/room-pk）": "房间PK-MOA（room/internal/room-pk）",
    # 活动 Admin / 生成式
    "活动（melon-gateway / cms/activity）": "Admin活动（melon-gateway / cms/activity）",
    "活动（melon-gateway / cms/backend/banner）": "Admin Banner（melon-gateway / cms/backend/banner）",
    "活动（app-task）": "生成式活动任务（app-task）",
    # 宝藏猎人
    "宝藏猎人（vas/external/treasure-hunter-stage · dispatchRankPrize）": "宝藏猎人-发榜奖（vas/external/treasure-hunter-stage · dispatchRankPrize）",
    "宝藏猎人（vas/external/treasure-hunter-stage · prizeDraw）": "宝藏猎人-抽奖（vas/external/treasure-hunter-stage · prizeDraw）",
    # 奖励验收
    "奖励验收": "奖励验收-工作流（workflow）",
    "奖励验收（通用）": "奖励验收-MOA（通用）",
}


def replace_in_obj(obj: object) -> tuple[object, int]:
    n = 0
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "category" and isinstance(v, str) and v in RENAMES:
                out[k] = RENAMES[v]
                n += 1
            elif k == "label" and isinstance(v, str) and v in RENAMES:
                out[k] = RENAMES[v]
                n += 1
            else:
                nv, c = replace_in_obj(v)
                out[k] = nv
                n += c
        return out, n
    if isinstance(obj, list):
        out_list = []
        for item in obj:
            ni, c = replace_in_obj(item)
            out_list.append(ni)
            n += c
        return out_list, n
    return obj, n


def patch_file(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    new_data, n = replace_in_obj(data)
    if n:
        path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return n


def main() -> int:
    touched_registries: set[Path] = set()
    total = 0

    sources = load_sources()
    for mod in sources.get("modules") or []:
        if not isinstance(mod, dict):
            continue
        rel = str(mod.get("registry") or "").strip()
        if not rel:
            continue
        path = REPO / rel
        if path.is_file():
            c = patch_file(path)
            if c:
                touched_registries.add(path)
                total += c
                print(f"registry {rel}: {c}")

    nav_path = REPO / "platform/web_agent/config/catalog_nav.json"
    c = patch_file(nav_path)
    if c:
        total += c
        print(f"catalog_nav.json: {c}")

    moa_tpl = REPO / "MOA/templates"
    if moa_tpl.is_dir():
        for p in sorted(moa_tpl.glob("*.json")):
            c = patch_file(p)
            if c:
                total += c
                print(f"template {p.name}: {c}")

    index_scripts = {
        "Admin/config/registry.json": REPO / "Admin/scripts/generate_index.py",
        "MOA/config/registry.json": REPO / "MOA/scripts/generate_index.py",
        "MOA-generative/config/registry.json": REPO / "MOA-generative/scripts/generate_index.py",
        "Gift/config/registry.json": REPO / "Gift/scripts/generate_index.py",
        "workflow/config/registry.json": REPO / "workflow/scripts/generate_index.py",
        "Risk/config/registry.json": REPO / "Risk/scripts/generate_index.py",
    }
    for reg, script in index_scripts.items():
        if (REPO / reg) in touched_registries and script.is_file():
            env = None
            if script.parent.name == "scripts" and "workflow" in str(script):
                import os

                env = os.environ.copy()
                env["PYTHONPATH"] = str(REPO / "platform") + (
                    os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
                )
            subprocess.run([sys.executable, str(script)], cwd=REPO, check=True, env=env)

    subprocess.run([sys.executable, str(REPO / "platform/scripts/generate_catalog.py")], cwd=REPO, check=True)
    print(f"done, {total} field(s) renamed, registries refreshed: {len(touched_registries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
