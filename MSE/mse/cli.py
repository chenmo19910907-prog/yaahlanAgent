"""MSE 服务配置 CLI。"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .client import get_configs_by_namespace
from .env import load_local_env
from .namespaces import resolve_namespace
from .paths import config_json_path, mse_dir
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
    parser = argparse.ArgumentParser(description="MSE 服务配置读取（getConfigsByAppKeyAndNameSpace）")
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
    return parser


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
