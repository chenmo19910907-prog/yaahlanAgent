"""MSE 服务配置 CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .client import get_configs_by_namespace
from .env import load_local_env
from .mutate import load_context, mse_publish_config, mse_save_config
from .patch import apply_set_args, parse_config_value
from .publish import save_config_value
from .namespaces import resolve_namespace
from .paths import config_json_path, mse_dir
from .share_link import build_mse_config_share_link, format_share_link_output
from .summary import format_config_detail, format_config_list


def _load_defaults() -> dict[str, object]:
    path = config_json_path()
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    defaults = data.get("defaults")
    return defaults if isinstance(defaults, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    defaults = _load_defaults()
    parser = argparse.ArgumentParser(description="MSE 服务配置读取与修改（getConfigs / saveOrUpdate / publish）")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MSE_BASE_URL", defaults.get("base_url", "https://mse.wemomo.com")),
        help="MSE 域名",
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("MSE_REGION", defaults.get("region", "alpha")),
        help="region/corp，如 alpha",
    )
    parser.add_argument(
        "--env",
        default=os.environ.get("MSE_ENV", defaults.get("env", "alpha")),
        help="环境，如 alpha / stage",
    )
    parser.add_argument(
        "--cluster",
        default=os.environ.get("MSE_CLUSTER", defaults.get("cluster", "stage")),
        help="集群，如 stage",
    )
    parser.add_argument(
        "--app-key",
        default=os.environ.get("MSE_APP_KEY") or None,
        help="appKey（省略则用 config.json defaults.app_key）",
    )
    parser.add_argument(
        "--namespace",
        "--name-space",
        dest="name_space",
        default=os.environ.get("MSE_NAMESPACE") or None,
        help=(
            "命名空间：voga-common / voga-activity；"
            "Application 或 私有/application 表示私有应用配置（API nameSpace 为空）；"
            "省略则用 config.json defaults.name_space"
        ),
    )
    parser.add_argument(
        "--config-key",
        default="",
        help="按 configKey 精确查询；省略则列出 namespace 下全部配置",
    )
    parser.add_argument(
        "--grep",
        default="",
        help="客户端过滤 configKey 包含的子串（仅在未指定 --config-key 时生效）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="摘要模式最多展示条数（默认 20）",
    )
    parser.add_argument(
        "--output",
        choices=("summary", "json", "value"),
        default="summary",
        help="输出格式",
    )
    parser.add_argument(
        "--order",
        action="store_true",
        help="请求参数 order=true",
    )
    parser.add_argument(
        "--cookie",
        default=os.environ.get("MSE_COOKIE") or os.environ.get("MOA_COOKIE"),
        help="MSE Cookie（默认 MSE_COOKIE / MOA_COOKIE）",
    )
    parser.add_argument("--timeout-ms", type=int, default=30000, help="HTTP 超时（毫秒）")

    write = parser.add_argument_group("写入/发布")
    write.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="修改 configValue JSON 顶层字段（可重复）；与 --config-value / --config-value-file 互斥",
    )
    write.add_argument("--config-value", default="", help="直接指定新的 configValue 字符串")
    write.add_argument("--config-value-file", default="", help="从文件读取新的 configValue")
    write.add_argument(
        "--save",
        action="store_true",
        help="保存配置到 MSE（saveOrUpdateConfigModel）；与 --publish 二选一或组合",
    )
    write.add_argument(
        "--publish",
        action="store_true",
        help="保存后走发布流程（createPublishRecord → 跳过灰度 → 全量发布 → complete）",
    )
    write.add_argument(
        "--with-grey",
        action="store_true",
        help="发布时走灰度（默认跳过灰度直接全量；灰度实例选择尚未实现）",
    )
    write.add_argument(
        "--dry-run",
        action="store_true",
        help="仅展示变更 diff，不写入 MSE",
    )
    parser.add_argument(
        "--share-link",
        action="store_true",
        help="输出 MSE 控制台分享链接（可与读取配置组合）",
    )
    parser.add_argument(
        "--share-link-only",
        action="store_true",
        help="仅输出分享链接，不调用 getConfigs（无需 Cookie）",
    )
    return parser


def _resolve_new_config_value(
    *,
    current_value: str,
    active_name: str,
    set_args: list[str],
    config_value: str,
    config_value_file: str,
) -> tuple[str, list[str]]:
    if config_value and (set_args or config_value_file):
        raise RuntimeError("--config-value 不能与 --set / --config-value-file 同时使用")
    if config_value_file:
        with open(config_value_file, "r", encoding="utf-8") as f:
            config_value = f.read()
    if config_value:
        return config_value.strip(), ["configValue: <整段替换>"]

    if not set_args:
        raise RuntimeError("写入/发布须指定 --set、--config-value 或 --config-value-file")

    parsed = parse_config_value(current_value)
    if not isinstance(parsed, dict):
        raise RuntimeError("仅支持对 JSON object 类型的 configValue 使用 --set")
    updated, changes = apply_set_args(parsed, set_args)
    if active_name == "json":
        return json.dumps(updated, ensure_ascii=False, indent=4), changes
    return json.dumps(updated, ensure_ascii=False), changes


def _set_args_to_dict(set_args: list[str]) -> dict[str, object]:
    from .patch import parse_scalar

    out: dict[str, object] = {}
    for item in set_args:
        text = item.strip()
        if "=" not in text:
            raise RuntimeError(f"--set 格式错误，应为 key=value：{item!r}")
        key, raw_value = text.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeError(f"--set 缺少 key：{item!r}")
        out[key] = parse_scalar(raw_value)
    return out


def _run_write_flow(args: argparse.Namespace) -> int:
    if not args.config_key:
        print("写入/发布须指定 --config-key", file=sys.stderr)
        return 2

    if not args.set and not args.config_value and not args.config_value_file:
        raise RuntimeError("写入/发布须指定 --set、--config-value 或 --config-value-file")

    ctx = load_context(
        base_url=str(args.base_url),
        region=str(args.region),
        env=str(args.env),
        cluster=str(args.cluster),
        app_key=_effective_app_key(args),
        cookie=str(args.cookie),
        timeout_s=max(int(args.timeout_ms), 1000) / 1000.0,
    )
    api_namespace, display_namespace = resolve_namespace(_effective_name_space(args))

    if args.set and not args.config_value and not args.config_value_file:
        result = mse_save_config(
            str(args.config_key),
            _set_args_to_dict(list(args.set or [])),
            name_space=_effective_name_space(args),
            dry_run=bool(args.dry_run),
            ctx=ctx,
        )
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or result.get("code") or "保存失败"))
        changes = list(result.get("changes") or [])
        config_id = result.get("config_id")
        new_value = str(result.get("after") or "")

        if args.dry_run:
            print(f"**{args.config_key}**（namespace={display_namespace}）dry-run")
            for line in changes:
                print(f"- {line}")
            print("")
            print("改前：")
            print(str(result.get("before") or "")[:2000])
            print("")
            print("改后：")
            print(new_value[:2000])
            return 0

        print(f"已保存 **{args.config_key}**（id={config_id}）")
        for line in changes:
            print(f"- {line}")
    else:
        items = get_configs_by_namespace(
            base_url=ctx.base_url,
            cookie=ctx.cookie,
            region=ctx.region,
            env=ctx.env,
            cluster=ctx.cluster,
            app_key=ctx.app_key,
            name_space=api_namespace,
            config_key=str(args.config_key),
            timeout_s=ctx.timeout_s,
        )
        if not items:
            print(f"未找到 configKey={args.config_key}", file=sys.stderr)
            return 1
        item = items[0]
        config_id = item.get("id")
        if config_id is None:
            print("配置缺少 id，无法写入", file=sys.stderr)
            return 1
        current_value = str(item.get("configValue") or "")
        active_name = str(item.get("activeName") or "json")
        new_value, changes = _resolve_new_config_value(
            current_value=current_value,
            active_name=active_name,
            set_args=list(args.set or []),
            config_value=str(args.config_value or ""),
            config_value_file=str(args.config_value_file or ""),
        )
        if args.dry_run:
            print(f"**{args.config_key}**（namespace={display_namespace}）dry-run")
            for line in changes:
                print(f"- {line}")
            print("")
            print("改前：")
            print(current_value[:2000])
            print("")
            print("改后：")
            print(new_value[:2000])
            return 0
        save_config_value(
            base_url=ctx.base_url,
            cookie=ctx.cookie,
            region=ctx.region,
            env=ctx.env,
            cluster=ctx.cluster,
            app_key=ctx.app_key,
            config_id=int(config_id),
            config_value=new_value,
            timeout_s=ctx.timeout_s,
        )
        print(f"已保存 **{args.config_key}**（id={config_id}）")
        for line in changes:
            print(f"- {line}")

    if args.publish:
        if args.with_grey:
            raise RuntimeError("灰度发布尚未实现，请省略 --with-grey")
        pub = mse_publish_config(
            str(args.config_key),
            name_space=_effective_name_space(args),
            confirm_publish=True,
            config_id=int(config_id) if config_id is not None else None,
            config_value=new_value,
            ctx=ctx,
        )
        if not pub.get("ok"):
            raise RuntimeError(str(pub.get("error") or pub.get("code") or "发布失败"))
        print(f"已发布全量（recordId={pub.get('publish_record_id')}，skipGrey=True）")
    return 0


def _effective_app_key(args: argparse.Namespace) -> str:
    if args.app_key:
        return str(args.app_key).strip()
    defaults = _load_defaults()
    return str(defaults.get("app_key") or "momo.bpm.biz.gameplatform.overseas-voga-mts-vas").strip()


def _effective_name_space(args: argparse.Namespace) -> str:
    if args.name_space:
        return str(args.name_space).strip()
    defaults = _load_defaults()
    return str(defaults.get("name_space") or "voga-common").strip()


def _share_link_app_key(args: argparse.Namespace) -> str:
    return str(args.app_key or "").strip()


def _share_link_name_space(args: argparse.Namespace) -> str:
    return str(args.name_space or "").strip()


def _print_share_link(args: argparse.Namespace) -> int:
    config_key = str(args.config_key or "").strip()
    if not config_key:
        print("分享链接须指定 --config-key", file=sys.stderr)
        return 2
    try:
        print(
            format_share_link_output(
                config_key,
                app_key=_share_link_app_key(args),
                name_space=_share_link_name_space(args),
            )
        )
    except ValueError as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    base_dir = mse_dir()
    load_local_env(base_dir)
    args = build_parser().parse_args()

    if args.share_link_only:
        return _print_share_link(args)

    cookie = (args.cookie or "").strip()
    if not cookie:
        print(
            "缺少 Cookie：请设置 MSE_COOKIE 或 MOA/.env.local 中的 MOA_COOKIE",
            file=sys.stderr,
        )
        return 2

    wants_write = bool(args.save or args.publish or args.dry_run or args.set or args.config_value or args.config_value_file)
    if wants_write:
        if args.publish and not args.save:
            args.save = True
        if not args.save and not args.dry_run:
            print("写入须指定 --save 或 --publish（预览用 --dry-run）", file=sys.stderr)
            return 2
        try:
            return _run_write_flow(args)
        except RuntimeError as exc:
            print(f"执行失败: {exc}", file=sys.stderr)
            return 1

    api_namespace, display_namespace = resolve_namespace(_effective_name_space(args))

    try:
        items = get_configs_by_namespace(
            base_url=str(args.base_url),
            cookie=cookie,
            region=str(args.region),
            env=str(args.env),
            cluster=str(args.cluster),
            app_key=_effective_app_key(args),
            name_space=api_namespace,
            config_key=str(args.config_key or "").strip(),
            order=bool(args.order),
            timeout_s=max(int(args.timeout_ms), 1000) / 1000.0,
        )
    except RuntimeError as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        return 1

    grep = str(args.grep or "").strip()
    if grep and not args.config_key:
        items = [item for item in items if grep.lower() in str(item.get("configKey") or "").lower()]

    if args.output == "json":
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0

    if args.config_key:
        if not items:
            print(f"未找到 configKey={args.config_key}", file=sys.stderr)
            return 1
        item = items[0]
        if args.output == "value":
            print(str(item.get("configValue") or ""))
            return 0
        detail = format_config_detail(item)
        if args.share_link:
            try:
                link = build_mse_config_share_link(
                    str(args.config_key),
                    app_key=str(item.get("appKey") or _share_link_app_key(args) or _effective_app_key(args)),
                    name_space=str(args.name_space or item.get("nameSpace") or "Application"),
                    corp=str(args.region or ""),
                    env=str(args.cluster or ""),
                )
                detail = f"{detail}\n\n**分享链接**\n\n{link}"
            except ValueError as exc:
                detail = f"{detail}\n\n分享链接生成失败：{exc}"
        print(detail)
        return 0

    if args.output == "value":
        print("value 输出需指定 --config-key", file=sys.stderr)
        return 2

    print(
        format_config_list(
            items,
            limit=int(args.limit),
            name_space=api_namespace,
            display_namespace=display_namespace,
            app_key=_effective_app_key(args),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
