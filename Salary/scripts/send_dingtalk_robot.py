#!/usr/bin/env python3
"""
钉钉群机器人消息发送脚本（独立脚本）

通过 Webhook 将文本或 Markdown 消息发送到钉钉群。
Webhook 可通过环境变量 DINGTALK_WEBHOOK 覆盖，避免在命令行暴露 token。

用法示例：
  python3 scripts/send_dingtalk_robot.py "Hello 钉钉"
  echo "Hello" | python3 scripts/send_dingtalk_robot.py
  python3 scripts/send_dingtalk_robot.py --markdown --title "测试报告" --file report.md
  cat report.md | python3 scripts/send_dingtalk_robot.py --markdown --title "测试报告"
"""
import argparse
import base64
import hashlib
import hmac
import os
import sys
import time
import urllib.parse

try:
    import requests
except ImportError:
    print("请安装依赖: pip install requests", file=sys.stderr)
    sys.exit(1)

DEFAULT_WEBHOOK = os.environ.get("DINGTALK_WEBHOOK", "")


def _append_sign(webhook: str, secret: str) -> str:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = timestamp + "\n" + secret
    sign = base64.b64encode(
        hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), "sha256").digest()
    ).decode("utf-8")
    sign_encoded = urllib.parse.quote(sign, safe="")
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign_encoded}"


def send_text(webhook: str, content: str) -> dict:
    body = {"msgtype": "text", "text": {"content": content}}
    return _post(webhook, body)


def send_markdown(webhook: str, title: str, text: str) -> dict:
    body = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    return _post(webhook, body)


def _dedupe_lock_path(dedupe_id: str) -> str:
    lock_dir = os.path.join(os.path.expanduser("~"), ".cache", "yaahlan_dingtalk_dedupe")
    os.makedirs(lock_dir, exist_ok=True)
    digest = hashlib.sha256(dedupe_id.encode("utf-8")).hexdigest()[:24]
    return os.path.join(lock_dir, f"{digest}.lock")


def _dedupe_ttl_seconds() -> int:
    raw = (os.environ.get("DINGTALK_BRIEF_DEDUPE_TTL") or "300").strip()
    try:
        return max(30, int(raw))
    except ValueError:
        return 300


def _is_dedupe_sent(dedupe_id: str) -> bool:
    if not dedupe_id:
        return False
    lock_path = _dedupe_lock_path(dedupe_id)
    if not os.path.isfile(lock_path):
        return False
    try:
        return time.time() - os.path.getmtime(lock_path) < _dedupe_ttl_seconds()
    except OSError:
        return False


def _mark_dedupe_sent(dedupe_id: str) -> None:
    if not dedupe_id:
        return
    lock_path = _dedupe_lock_path(dedupe_id)
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"{time.time()}\n")


def _post(webhook: str, body: dict) -> dict:
    resp = requests.post(
        webhook,
        json=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"钉钉 API 返回错误: errcode={data.get('errcode')}, errmsg={data.get('errmsg')}")
    return data


def main():
    parser = argparse.ArgumentParser(description="通过钉钉群机器人 Webhook 发送消息")
    parser.add_argument("message", nargs="?", default=None, help="文本内容（不指定则从 stdin 读取）")
    parser.add_argument("--webhook", default=DEFAULT_WEBHOOK, help="Webhook URL（默认 DINGTALK_WEBHOOK）")
    parser.add_argument("--markdown", action="store_true", help="以 Markdown 发送")
    parser.add_argument("--title", default="通知", help="Markdown 标题")
    parser.add_argument("--file", "-f", default=None, help="从文件读取内容")
    parser.add_argument(
        "--dedupe-id",
        default=None,
        help="去重标识：TTL 内相同 id 仅发送一次（由报告简报流程传入）",
    )
    args = parser.parse_args()

    webhook = (args.webhook or "").strip()
    if not webhook:
        print("错误: 未配置 Webhook。请设置 DINGTALK_WEBHOOK 或使用 --webhook。", file=sys.stderr)
        sys.exit(2)

    secret = (os.environ.get("DINGTALK_SECRET") or "").strip()
    if secret:
        webhook = _append_sign(webhook, secret)

    if args.file:
        if not os.path.isfile(args.file):
            print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
            sys.exit(2)
        with open(args.file, encoding="utf-8") as f:
            content = f.read()
    elif args.message is not None:
        content = args.message
    else:
        content = sys.stdin.read()

    content = (content or "").strip()
    if not content:
        print("错误: 消息内容为空", file=sys.stderr)
        sys.exit(2)

    dedupe_id = (args.dedupe_id or "").strip()
    if dedupe_id and _is_dedupe_sent(dedupe_id):
        print("跳过重复消息: dedupe-id 在 TTL 内已发送", file=sys.stderr)
        sys.exit(0)

    try:
        if args.markdown:
            result = send_markdown(webhook, args.title, content)
        else:
            result = send_text(webhook, content)
        if dedupe_id:
            _mark_dedupe_sent(dedupe_id)
        print("发送成功:", result.get("errmsg", "ok"))
    except requests.RequestException as e:
        print(f"请求失败: {e}", file=sys.stderr)
        sys.exit(3)
    except RuntimeError as e:
        print(f"发送失败: {e}", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
