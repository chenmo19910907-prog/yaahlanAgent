"""MSE 服务配置 CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .client import get_configs_by_namespace
from .env import load_local_env
from .namespaces import resolve_namespace
from .patch import apply_set_args, parse_config_value
from .paths import config_json_path, mse_dir
from .publish import publish_config_value, save_config_value
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
        default=os.environ.get(
            "MSE_APP_KEY",
            defaults.get("app_key", "momo.bpm.biz.gameplatform.overseas-voga-mts-vas"),
        ),
        help="appKey",
    )
    parser.add_argument(
        "--namespace",
        "--name-space",
        dest="name_space",
        default=os.environ.get("MSE_NAMESPACE", defaults.get("name_space", "voga-common")),
        help=(
            "命名空间：voga-common / voga-activity；"
            "Application 或 私有/application 表示私有应用配置（API nameSpace 为空）"
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


def _run_write_flow(args: argparse.Namespace) -> int:
    if not args.config_key:
        print("写入/发布须指定 --config-key", file=sys.stderr)
        return 2

    api_namespace, display_namespace = resolve_namespace(str(args.name_space))
    timeout_s = max(int(args.timeout_ms), 1000) / 1000.0

    items = get_configs_by_namespace(
        base_url=str(args.base_url),
        cookie=str(args.cookie),
        region=str(args.region),
        env=str(args.env),
        cluster=str(args.cluster),
        app_key=str(args.app_key),
        name_space=api_namespace,
        config_key=str(args.config_key),
        timeout_s=timeout_s,
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
        base_url=str(args.base_url),
        cookie=str(args.cookie),
        region=str(args.region),
        env=str(args.env),
        cluster=str(args.cluster),
        app_key=str(args.app_key),
        config_id=int(config_id),
        config_value=new_value,
        timeout_s=timeout_s,
    )
    print(f"已保存 **{args.config_key}**（id={config_id}）")
    for line in changes:
        print(f"- {line}")

    if args.publish:
        skip_grey = not bool(args.with_grey)
        record_id = publish_config_value(
            base_url=str(args.base_url),
            cookie=str(args.cookie),
            region=str(args.region),
            env=str(args.env),
            cluster=str(args.cluster),
            app_key=str(args.app_key),
            config_id=int(config_id),
            config_value=new_value,
            skip_grey=skip_grey,
            timeout_s=timeout_s,
        )
        print(f"已发布全量（recordId={record_id}，skipGrey={skip_grey}）")
    return 0


def main() -> int:
    base_dir = mse_dir()
    load_local_env(base_dir)
    args = build_parser().parse_args()

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

    api_namespace, display_namespace = resolve_namespace(str(args.name_space))

    try:
        items = get_configs_by_namespace(
            base_url=str(args.base_url),
            cookie=cookie,
            region=str(args.region),
            env=str(args.env),
            cluster=str(args.cluster),
            app_key=str(args.app_key),
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
        print(format_config_detail(item))
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
            app_key=str(args.app_key),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
