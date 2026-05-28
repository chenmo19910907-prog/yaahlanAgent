#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


def _load_local_env() -> None:
    """
    从仓库内的 MOA/.env.local 读取环境变量（仅本机使用，已在 .gitignore 忽略）。
    文件格式为 KEY=VALUE，每行一条；忽略空行和 # 注释。
    """
    # 以脚本所在目录为基准，避免 cwd 影响
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env.local")
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                # 不 strip v，保留 cookie 里可能的空格（如果用户复制带空格）
                if not k:
                    continue
                # 不覆盖已存在的环境变量（命令行 export 优先）
                os.environ.setdefault(k, v)
    except Exception:
        # 读取失败不应阻断主流程
        return


ROOM_LEVEL_EXP_THRESHOLDS: dict[int, int] = {
    1: 0,
    2: 200_000,
    3: 1_000_000,
    4: 4_500_000,
    5: 18_000_000,
    6: 63_000_000,
    7: 189_000_000,
}


def _build_room_exp_expr(room_id: str, exp: int) -> str:
    room_id = str(room_id).strip()
    if not room_id:
        raise ValueError("room_id 不能为空")
    if exp < 0:
        raise ValueError("exp 不能为负数")
    return f'context.getBean("roomProfileDao").addRoomActiveValue("{room_id}",{exp}D)'


def _build_room_exp_delta_for_level(level: int, current_exp: int) -> int:
    if level not in ROOM_LEVEL_EXP_THRESHOLDS:
        raise ValueError(f"不支持的房间等级: {level}，支持范围: {sorted(ROOM_LEVEL_EXP_THRESHOLDS.keys())}")
    if current_exp < 0:
        raise ValueError("current_exp 不能为负数")
    target = ROOM_LEVEL_EXP_THRESHOLDS[level]
    delta = target - current_exp
    if delta <= 0:
        raise ValueError(f"当前经验值已 >= 目标等级阈值：current_exp={current_exp}, target={target}")
    return delta


def _level_by_exp(exp: int) -> int:
    if exp < 0:
        raise ValueError("exp 不能为负数")
    # 返回满足阈值的最高等级
    level = 1
    for lv in sorted(ROOM_LEVEL_EXP_THRESHOLDS.keys()):
        if exp >= ROOM_LEVEL_EXP_THRESHOLDS[lv]:
            level = lv
    return level


def _load_payload(args: argparse.Namespace) -> Dict[str, Any]:
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif args.payload:
        payload = json.loads(args.payload)
    else:
        raise ValueError("必须提供 --payload-file 或 --payload")

    if not isinstance(payload, dict):
        raise ValueError("payload 必须是 JSON object")

    # 顶层字段对齐（与 MOA 导出的 JSON 一致）
    if args.service_url is not None:
        payload["url"] = args.service_url
    if args.moa_method is not None:
        payload["method"] = args.moa_method
    if args.region is not None:
        payload["region"] = args.region
    if args.env is not None:
        payload["env"] = args.env
    if args.cluster is not None:
        payload["cluster"] = args.cluster
    if args.server is not None:
        payload["server"] = args.server
    if args.momo_id is not None:
        payload["momoId"] = args.momo_id
    if args.momo_name is not None:
        payload["momoName"] = args.momo_name
    if args.header is not None:
        payload["header"] = args.header

    if args.host is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --host 覆盖")
        settings["host"] = args.host
    if args.moa_time is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --moa-time 覆盖")
        settings["time"] = str(args.moa_time)
    if args.group is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --group 覆盖")
        settings["group"] = args.group
    if args.header_type is not None:
        settings = payload.get("settings")
        if settings is None:
            settings = {}
            payload["settings"] = settings
        if not isinstance(settings, dict):
            raise ValueError("payload.settings 必须是 object，才能使用 --header-type 覆盖")
        settings["headerType"] = args.header_type

    expr: Optional[str] = None
    if args.expr is not None:
        expr = args.expr
    elif args.room_id is not None:
        # 查询模式：通过 addRoomActiveValue(roomId, 0D) 获取当前经验值
        if args.query_current is True:
            expr = _build_room_exp_expr(args.room_id, 0)
        # 便捷模式 1：直接指定增量 exp
        elif args.exp is not None:
            expr = _build_room_exp_expr(args.room_id, args.exp)
        # 便捷模式 2：指定目标 level，脚本根据阈值计算需要增加多少
        elif args.level is not None:
            current = args.current_exp if args.current_exp is not None else 0
            delta = _build_room_exp_delta_for_level(args.level, current_exp=current)
            expr = _build_room_exp_expr(args.room_id, delta)
        elif args.level is None and args.exp is None:
            raise ValueError("提供了 --room-id 时，必须同时提供 --exp 或 --level")
    elif args.exp is not None or args.level is not None:
        raise ValueError("使用 --exp/--level 时必须提供 --room-id")

    if expr is not None:
        params = payload.get("params")
        if not isinstance(params, list) or not params:
            raise ValueError("payload.params 必须是非空数组，才能覆盖 params[0].value/txt")
        if not isinstance(params[0], dict):
            raise ValueError("payload.params[0] 必须是 object，才能覆盖 params[0].value/txt")
        params[0]["value"] = expr
        params[0]["txt"] = expr

    return payload


def _http_post_json(url: str, cookie: str, payload: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie,
    }
    request_source = os.environ.get("MOA_REQUEST_SOURCE")
    if request_source:
        headers["request-source"] = request_source
    origin = os.environ.get("MOA_ORIGIN")
    referer = os.environ.get("MOA_REFERER")
    ua = os.environ.get("MOA_USER_AGENT")
    if origin:
        headers["Origin"] = origin
    if referer:
        headers["Referer"] = referer
    if ua:
        headers["User-Agent"] = ua

    req = urllib.request.Request(
        url=url,
        data=body,
        method="POST",
        headers=headers,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {e.code}: {raw}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"网络错误: {e}") from e

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError(f"返回不是合法 JSON: {raw[:1000]}")

    if not isinstance(obj, dict):
        raise RuntimeError("返回 JSON 不是 object")
    return obj


def _extract_ec_em_result(resp: Dict[str, Any]) -> tuple[Optional[int], Optional[str], Any]:
    ec = resp.get("ec")
    em = resp.get("em")
    result = resp.get("result")

    if isinstance(ec, bool):
        ec = int(ec)
    if ec is not None and not isinstance(ec, int):
        try:
            ec = int(ec)
        except Exception:
            ec = None
    if em is not None and not isinstance(em, str):
        em = str(em)
    return ec, em, result


def _outer_success(ec: Optional[int]) -> bool:
    # 该 httpproxy 返回外层 ec 既可能是 0，也可能是 200（ok）
    return ec in (0, 200)


def _extract_inner_result(resp: Dict[str, Any]) -> tuple[int, str, Any]:
    inner = resp.get("result")
    if not isinstance(inner, dict):
        raise RuntimeError("业务返回 result 字段不是 object")
    inner_ec = inner.get("ec")
    inner_em = inner.get("em")
    inner_result = inner.get("result")
    try:
        inner_ec_int = int(inner_ec)
    except Exception:
        raise RuntimeError(f"无法解析业务 ec: {inner_ec}")
    inner_em_str = inner_em if isinstance(inner_em, str) else str(inner_em)
    return inner_ec_int, inner_em_str, inner_result


def _parse_current_exp_from_inner(inner_result: Any) -> int:
    try:
        return int(float(inner_result))
    except Exception as e:
        raise RuntimeError(f"无法解析当前经验值: {inner_result}") from e


def main() -> int:
    _load_local_env()
    parser = argparse.ArgumentParser(description="在本地复现 MOA httpproxy execute 调用")
    parser.add_argument("--entry-url", default=os.environ.get("MOA_ENTRY_URL"), help="httpproxy 入口完整 URL（也可用环境变量 MOA_ENTRY_URL）")
    parser.add_argument("--cookie", default=os.environ.get("MOA_COOKIE"), help="Cookie（也可用环境变量 MOA_COOKIE）")
    parser.add_argument("--timeout-ms", type=int, default=5000, help="HTTP 超时（毫秒），默认 5000")
    parser.add_argument("--host", help='覆盖 payload.settings.host，例如 "10.247.244.119:29584"')
    parser.add_argument("--moa-time", type=int, help='覆盖 payload.settings.time（毫秒），例如 2000/5000')
    parser.add_argument("--group", help='覆盖 payload.settings.group，例如 "default"')
    parser.add_argument("--header-type", help='覆盖 payload.settings.headerType，例如 "TXT"')
    parser.add_argument("--service-url", help='覆盖 payload.url，例如 "/service/yoga-mts-room-backdoor"')
    parser.add_argument("--moa-method", help='覆盖 payload.method，例如 "execute"')
    parser.add_argument("--region", help='覆盖 payload.region，例如 "alpha"')
    parser.add_argument("--env", help='覆盖 payload.env，例如 "alpha"')
    parser.add_argument("--cluster", help='覆盖 payload.cluster，例如 "stage"')
    parser.add_argument("--server", help='覆盖 payload.server，例如 "config"')
    parser.add_argument("--momo-id", help="覆盖 payload.momoId")
    parser.add_argument("--momo-name", help="覆盖 payload.momoName")
    parser.add_argument("--header", help="覆盖 payload.header（通常为空字符串）")
    parser.add_argument("--dump-payload", action="store_true", help="把最终请求 payload（不含 cookie）输出到 stderr，便于对比 MOA")
    parser.add_argument("--origin", default=os.environ.get("MOA_ORIGIN"), help="可选：Origin（也可用环境变量 MOA_ORIGIN）")
    parser.add_argument("--referer", default=os.environ.get("MOA_REFERER"), help="可选：Referer（也可用环境变量 MOA_REFERER）")
    parser.add_argument("--user-agent", default=os.environ.get("MOA_USER_AGENT"), help="可选：User-Agent（也可用环境变量 MOA_USER_AGENT）")
    parser.add_argument("--request-source", default=os.environ.get("MOA_REQUEST_SOURCE"), help='可选：request-source（也可用环境变量 MOA_REQUEST_SOURCE），例如 "moaProxy"')

    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--payload-file", help="包含完整 payload 的 JSON 文件路径")
    src.add_argument("--payload", help="完整 payload JSON 字符串")

    parser.add_argument("--expr", help='覆盖 payload.params[0].value / txt 的表达式，例如 context.getBean("x").y(...)')
    parser.add_argument("--room-id", help='便捷参数：房间 ID（用于生成 addRoomActiveValue 表达式）')
    parser.add_argument("--exp", type=int, help="便捷参数：增加的经验值（正整数，用于生成 addRoomActiveValue 表达式）")
    parser.add_argument("--level", type=int, help="便捷参数：目标房间等级（按内置等级阈值计算需要增加的经验值）")
    parser.add_argument("--current-exp", type=int, help="便捷参数：当前房间经验值（用于配合 --level 计算增量；不传默认按 0 处理）")
    parser.add_argument("--query-current", action="store_true", help="查询当前经验值与等级（通过 addRoomActiveValue(roomId,0D)）")

    args = parser.parse_args()

    if not args.entry_url:
        print("缺少入口 URL：请传 --entry-url 或设置环境变量 MOA_ENTRY_URL", file=sys.stderr)
        return 2
    if not args.cookie:
        print("缺少 Cookie：请传 --cookie 或设置环境变量 MOA_COOKIE", file=sys.stderr)
        return 2

    try:
        # 可选请求头（不影响 payload），写入环境变量供 http 层读取
        if args.origin:
            os.environ["MOA_ORIGIN"] = args.origin
        if args.referer:
            os.environ["MOA_REFERER"] = args.referer
        if args.user_agent:
            os.environ["MOA_USER_AGENT"] = args.user_agent
        if args.request_source:
            os.environ["MOA_REQUEST_SOURCE"] = args.request_source

        # 目标等级升级：先查询当前经验值，再补差值
        if args.level is not None and args.room_id is not None and args.exp is None and not args.query_current and args.expr is None:
            # 1) query current exp via 0D
            q_args = argparse.Namespace(**vars(args))
            q_args.query_current = True
            q_args.exp = None
            q_payload = _load_payload(q_args)
            timeout_s = max(args.timeout_ms, 1) / 1000.0
            q_resp = _http_post_json(args.entry_url, args.cookie, q_payload, timeout_s=timeout_s)
            q_ec, q_em, _ = _extract_ec_em_result(q_resp)
            if not _outer_success(q_ec):
                raise RuntimeError(f"查询当前经验值失败(外层): ec={q_ec}, em={q_em}")
            inner_ec, inner_em, inner_result = _extract_inner_result(q_resp)
            if inner_ec != 0:
                raise RuntimeError(f"查询当前经验值失败(业务): ec={inner_ec}, em={inner_em}")
            current_exp = _parse_current_exp_from_inner(inner_result)
            delta = _build_room_exp_delta_for_level(args.level, current_exp=current_exp)
            print(f"已查询当前经验值: {current_exp}，目标等级: {args.level}，需要增加: {delta}", file=sys.stderr)

            # 2) execute add delta
            e_args = argparse.Namespace(**vars(args))
            e_args.current_exp = current_exp
            e_args.exp = None
            e_payload = _load_payload(e_args)
            payload = e_payload
        else:
            payload = _load_payload(args)

        # 仅输出非敏感的关键信息，便于排查（不打印 cookie）
        settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
        params0 = None
        params = payload.get("params")
        if isinstance(params, list) and params and isinstance(params[0], dict):
            params0 = params[0].get("value")
        print(
            "请求信息: "
            f'entry_url="{args.entry_url}", '
            f'service_url="{payload.get("url")}", '
            f'method="{payload.get("method")}", '
            f'host="{settings.get("host", "")}", '
            f'time="{settings.get("time", "")}", '
            f'expr="{params0 if isinstance(params0, str) else ""}"',
            file=sys.stderr,
        )
        if args.dump_payload:
            print("最终 payload（不含 cookie）:", file=sys.stderr)
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        timeout_s = max(args.timeout_ms, 1) / 1000.0
        resp = _http_post_json(args.entry_url, args.cookie, payload, timeout_s=timeout_s)
    except Exception as e:
        print(f"执行失败: {e}", file=sys.stderr)
        return 1

    print(json.dumps(resp, ensure_ascii=False, indent=2))

    ec, em, _ = _extract_ec_em_result(resp)
    if not _outer_success(ec):
        msg = em or "ec!=0"
        print(f"MOA 返回失败: ec={ec}, em={msg}", file=sys.stderr)
        return 3

    if args.query_current:
        try:
            inner_ec, inner_em, inner_result = _extract_inner_result(resp)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
        if inner_ec != 0:
            print(f"业务返回失败: ec={inner_ec}, em={inner_em}", file=sys.stderr)
            return 4
        try:
            current_exp = _parse_current_exp_from_inner(inner_result)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 4
            lv = _level_by_exp(current_exp)
            next_lv = lv + 1 if (lv + 1) in ROOM_LEVEL_EXP_THRESHOLDS else None
            next_threshold = ROOM_LEVEL_EXP_THRESHOLDS.get(next_lv) if next_lv else None
            remaining = (next_threshold - current_exp) if next_threshold is not None else None
            print(
                json.dumps(
                    {
                        "roomId": args.room_id,
                        "currentExp": current_exp,
                        "level": lv,
                        "nextLevelThreshold": next_threshold,
                        "remainingToNextLevel": remaining,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

