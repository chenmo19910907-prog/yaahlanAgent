#!/usr/bin/env python3
"""将 templates 子目录下的 JSON 扁平化到 templates/ 根目录。"""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

MOA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(MOA_ROOT, "templates")

# 子路径 -> 扁平文件名（避免 vip/清除信息 与 auth/清除信息 冲突）
FLATTEN_MAP: dict[str, str] = {
    "vip/增加经验值.json": "VIP-增加经验值.json",
    "vip/清除信息.json": "VIP-清除信息.json",
    "vip/下发体验卡.json": "VIP-下发体验卡.json",
    "room/经验值-backdoor.json": "房间经验值-backdoor.json",
    "room/设置等级.json": "房间-设置等级.json",
    "room/增加机器人.json": "房间-增加机器人.json",
    "room/成员陪伴值.json": "房间成员-增加陪伴值.json",
    "family/增加声望值.json": "家族-增加声望值.json",
    "family/衰减声望值.json": "家族-衰减声望值.json",
    "family/设置基金档位.json": "家族-设置基金档位.json",
    "family/增加基金贡献值.json": "家族-增加基金贡献值.json",
    "family/清除基金贡献值.json": "家族-清除基金贡献值.json",
    "family/成员基金贡献.json": "家族-成员增加基金贡献值.json",
    "diamond/查询余额.json": "钻石-查询余额.json",
    "diamond/发放.json": "钻石-发放.json",
    "gift/背包下发.json": "背包礼物-下发.json",
    "gift/定制重置上传.json": "定制礼物-重置上传次数.json",
    "gift/榜单增加活跃值.json": "定制礼物榜单-增加活跃值.json",
    "gift/榜单清除数据.json": "定制礼物榜单-清除数据.json",
    "user/修改大区.json": "用户-修改大区.json",
    "user/手机号查userId.json": "用户-按手机号查userId.json",
    "user/登录天数.json": "查询用户登录天数.json",
    "user/app语言.json": "查看用户app语言.json",
    "auth/查询记录.json": "实名认证-查询认证记录.json",
    "auth/清除信息.json": "实名认证-清除认证信息.json",
    "auth/设置过期时间.json": "实名认证-设置认证过期时间.json",
    "noble/增加月消费值.json": "贵族-增加月消费值.json",
}


def _flatten_templates() -> None:
    for rel, flat_name in FLATTEN_MAP.items():
        src = os.path.join(TEMPLATES, rel.replace("/", os.sep))
        dst = os.path.join(TEMPLATES, flat_name)
        if not os.path.exists(src):
            if os.path.exists(dst):
                continue
            raise FileNotFoundError(src)
        if os.path.abspath(src) != os.path.abspath(dst):
            if os.path.exists(dst):
                os.remove(dst)
            shutil.move(src, dst)
            print(f"flatten: {flat_name}")

    for name in os.listdir(TEMPLATES):
        path = os.path.join(TEMPLATES, name)
        if os.path.isdir(path):
            shutil.rmtree(path)
            print(f"removed dir: {name}")


def _update_registry() -> None:
    registry_file = os.path.join(MOA_ROOT, "config", "registry.json")
    with open(registry_file, encoding="utf-8") as f:
        registry: dict[str, Any] = json.load(f)

    replacements = {
        f"MOA/templates/{old}": f"MOA/templates/{new}"
        for old, new in FLATTEN_MAP.items()
    }
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


def main() -> int:
    _flatten_templates()
    _update_registry()
    print("flatten done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
