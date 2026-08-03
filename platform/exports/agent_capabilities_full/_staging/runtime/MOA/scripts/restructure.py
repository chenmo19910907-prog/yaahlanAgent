#!/usr/bin/env python3
"""一次性目录重组：templates 分域、config/docs/scripts 归位。可重复执行（幂等）。"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

MOA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEMPLATE_MOVES: dict[str, str] = {
    "VIP-增加经验值.json": "vip/增加经验值.json",
    "VIP-清除信息.json": "vip/清除信息.json",
    "VIP-下发体验卡.json": "vip/下发体验卡.json",
    "房间经验值-backdoor.json": "room/经验值-backdoor.json",
    "房间-设置等级.json": "room/设置等级.json",
    "房间-增加机器人.json": "room/增加机器人.json",
    "房间成员-增加陪伴值.json": "room/成员陪伴值.json",
    "家族-增加声望值.json": "family/增加声望值.json",
    "家族-衰减声望值.json": "family/衰减声望值.json",
    "家族-设置基金档位.json": "family/设置基金档位.json",
    "家族-增加基金贡献值.json": "family/增加基金贡献值.json",
    "家族-清除基金贡献值.json": "family/清除基金贡献值.json",
    "家族-成员增加基金贡献值.json": "family/成员基金贡献.json",
    "钻石-查询余额.json": "diamond/查询余额.json",
    "钻石-发放.json": "diamond/发放.json",
    "背包礼物-下发.json": "gift/背包下发.json",
    "定制礼物-重置上传次数.json": "gift/定制重置上传.json",
    "定制礼物榜单-增加活跃值.json": "gift/榜单增加活跃值.json",
    "定制礼物榜单-清除数据.json": "gift/榜单清除数据.json",
    "用户-修改大区.json": "user/修改大区.json",
    "用户-按手机号查userId.json": "user/手机号查userId.json",
    "查询用户登录天数.json": "user/登录天数.json",
    "查看用户app语言.json": "user/app语言.json",
    "实名认证-查询认证记录.json": "auth/查询记录.json",
    "实名认证-清除认证信息.json": "auth/清除信息.json",
    "实名认证-设置认证过期时间.json": "auth/设置过期时间.json",
    "贵族-增加月消费值.json": "noble/增加月消费值.json",
}


def _move_if_exists(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.abspath(src) == os.path.abspath(dst):
        return
    if os.path.exists(dst):
        os.remove(dst)
    shutil.move(src, dst)
    print(f"moved: {os.path.relpath(dst, MOA_ROOT)}")


def _migrate_templates() -> None:
    templates_root = os.path.join(MOA_ROOT, "templates")
    for old_name, rel in TEMPLATE_MOVES.items():
        src = os.path.join(templates_root, old_name)
        dst = os.path.join(templates_root, rel)
        _move_if_exists(src, dst)


def _migrate_config() -> None:
    config_dir = os.path.join(MOA_ROOT, "config")
    os.makedirs(config_dir, exist_ok=True)
    _move_if_exists(os.path.join(MOA_ROOT, "config.json"), os.path.join(config_dir, "thresholds.json"))
    _move_if_exists(os.path.join(MOA_ROOT, "moa_registry.json"), os.path.join(config_dir, "registry.json"))


def _update_registry_paths() -> None:
    registry_file = os.path.join(MOA_ROOT, "config", "registry.json")
    if not os.path.exists(registry_file):
        return
    with open(registry_file, encoding="utf-8") as f:
        registry: dict[str, Any] = json.load(f)

    registry["generated_index_path"] = "MOA/使用方法.md"

    replacements: dict[str, str] = {
        f"MOA/templates/{old}": f"MOA/templates/{new}"
        for old, new in TEMPLATE_MOVES.items()
    }
    # 历史路径兼容
    replacements.update(
        {
            "MOA/MOA使用方法.md": "MOA/使用方法.md",
            "MOA/docs/使用方法.md": "MOA/使用方法.md",
            "MOA/moa_registry.json": "MOA/config/registry.json",
            "MOA/config.json": "MOA/config/thresholds.json",
            "MOA/generate_moa_index.py": "MOA/scripts/generate_index.py",
            "MOA/test_all_moa.py": "MOA/scripts/test_all.py",
        }
    )

    items = registry.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            cmd = item.get("command")
            if isinstance(cmd, str):
                for old, new in replacements.items():
                    cmd = cmd.replace(old, new)
                item["command"] = cmd

    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("updated: config/registry.json")


def _cleanup_legacy() -> None:
    legacy_files = [
        "MOA使用方法.md",
        "generate_moa_index.py",
        "test_all_moa.py",
        "moa_registry.json",
        "config.json",
    ]
    for name in legacy_files:
        path = os.path.join(MOA_ROOT, name)
        if os.path.isfile(path):
            os.remove(path)
            print(f"removed legacy: {name}")

    repo_root = os.path.dirname(MOA_ROOT)
    stale = os.path.join(repo_root, "MOA工具")
    if os.path.isdir(stale):
        shutil.rmtree(stale)
        print("removed stale: MOA工具/")


def main() -> int:
    _migrate_config()
    _migrate_templates()
    _update_registry_paths()
    _cleanup_legacy()
    print("restructure done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
