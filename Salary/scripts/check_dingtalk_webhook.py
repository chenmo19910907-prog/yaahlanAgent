#!/usr/bin/env python3
"""
钉钉 Webhook 配置诊断（不输出 token 等敏感信息）

运行: python3 scripts/check_dingtalk_webhook.py
"""
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))
from utils.env_utils import load_env_file


def main():
    root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    env_path = os.path.join(root, ".env")
    print("=== 钉钉 Webhook 配置诊断（不输出 token）===\n")

    if not os.path.isfile(env_path):
        print("[X] .env 不存在")
        print("    请复制 .env.example 为 .env 并填入 DINGTALK_WEBHOOK 或 DINGTALK_REPORT_WEBHOOK")
        sys.exit(1)
    print("[√] .env 存在")

    load_env_file(root)
    report = (os.environ.get("DINGTALK_REPORT_WEBHOOK") or "").strip()
    common = (os.environ.get("DINGTALK_WEBHOOK") or "").strip()
    webhook = report or common
    if not webhook:
        print("[X] 未配置 DINGTALK_REPORT_WEBHOOK 与 DINGTALK_WEBHOOK")
        print("    在 .env 中设置其一，例如：DINGTALK_REPORT_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=...")
        sys.exit(1)
    print("[√] 已配置 Webhook（来源: %s）" % ("DINGTALK_REPORT_WEBHOOK" if report else "DINGTALK_WEBHOOK"))

    if not webhook.startswith("https://"):
        print("[!] Webhook 值未以 https:// 开头，可能被引号或空格破坏")
    else:
        print("[√] Webhook 格式前缀正确 (https://)")
    if "oapi.dingtalk.com" not in webhook:
        print("[!] Webhook 中未包含 oapi.dingtalk.com")
    if "access_token=" not in webhook:
        print("[!] Webhook 中未包含 access_token=")
    else:
        print("[√] URL 含 access_token 参数")

    print("\n机器人安全设置：若启用「关键词」，消息须包含「测试报告」。")
    print("若启用「加签」，请在 .env 中设置 DINGTALK_SECRET。")
    sys.exit(0)


if __name__ == "__main__":
    main()
