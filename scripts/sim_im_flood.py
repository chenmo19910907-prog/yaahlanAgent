#!/usr/bin/env python3
"""
模拟 A ↔ B 互发 N 条私聊消息，覆盖 TEXT / IMG / VIDEO 类型。

用法:
  python3 scripts/sim_im_flood.py \
      --uid-a 100329338 --uid-b 100261858 \
      --total 2000 \
      --concurrency 5

环境变量（同 MOA CLI）:
  MOA_COOKIE      必填，从浏览器 DevTools 粘贴
  MOA_ENTRY_URL   默认 https://mse.wemomo.com/apirest/httpproxy/moa/test
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# ── 把项目根加入 sys.path ────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Admin"))

# ── 自动加载 MOA/.env.local（确保 Origin/Referer/UA 等头正确）────────────────
def _load_moa_env() -> None:
    env_file = ROOT / "MOA" / ".env.local"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        # 已由命令行/外部 env 设置时不覆盖（允许 --cookie 参数优先）
        if key and key not in os.environ:
            os.environ[key] = val

_load_moa_env()

from MOA.moa.client import MoaClient
from MOA.moa.params import set_p2p_message_params

# ── 测试资源（从 MOA/config/test_media_assets.json 加载）────────────────────
def _load_media_assets() -> tuple[list[str], str, str]:
    """返回 (img_urls, video_url, cover_url)。"""
    cfg_path = ROOT / "MOA" / "config" / "test_media_assets.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        img_urls = [i["url"] for i in cfg.get("images", []) if i.get("url")]
        videos   = cfg.get("videos", [])
        video_url  = videos[0]["url"]       if videos else ""
        cover_url  = videos[0].get("cover_url", img_urls[0] if img_urls else "")
        return img_urls or [""], video_url, cover_url
    except Exception as e:
        print(f"[WARN] 读取 test_media_assets.json 失败: {e}，使用内置默认值", file=sys.stderr)
        return (
            ["https://s.momocdn.com/s1/u/igicbbbcg/IMG_0059.PNG"],
            "https://s.momocdn.com/s1/u/igicbbbcg/IMG_1095.MOV",
            "https://s.momocdn.com/s1/u/igicbbbcg/video_cover_20261009_174854.jpg",
        )

_IMG_URLS, _VIDEO_URL, _COVER_URL = _load_media_assets()

# 文字多样化（防 IM 去重）
_TEXTS = [
    "Hello {i}! 这是测试消息",
    "你好 {i}，压测私聊",
    "Test message {i} - AUTO",
    "消息 {i}：验证IM落库",
    "Hi {i}，IM flood test",
    "رسالة رقم {i}",   # Arabic
    "Mesaj {i}",         # Turkish
    "Сообщение {i}",     # Russian
]

ENTRY_URL = "https://mse.wemomo.com/apirest/httpproxy/moa/test"
TEMPLATE_PATH = ROOT / "MOA" / "templates" / "私聊-发送消息.json"


def _base_payload() -> dict[str, Any]:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _build_msg_payload(
    from_uid: str,
    to_uid: str,
    msg_type: str,
    idx: int,
) -> dict[str, Any]:
    payload = _base_payload()
    if msg_type == "TEXT":
        text = random.choice(_TEXTS).format(i=idx)
        set_p2p_message_params(payload, from_uid, to_uid, "TEXT", text=text)
    elif msg_type == "IMG":
        url = random.choice(_IMG_URLS)
        set_p2p_message_params(payload, from_uid, to_uid, "IMG", url=url, thumb_url=url)
    elif msg_type == "VIDEO":
        set_p2p_message_params(
            payload, from_uid, to_uid, "VIDEO",
            url=_VIDEO_URL,
            video_time=random.randint(3, 15),
            cover_url=_COVER_URL,
            wh_ratio=1.0,
        )
    return payload


def _send_one(client: MoaClient, from_uid: str, to_uid: str, msg_type: str, idx: int) -> tuple[bool, str]:
    try:
        payload = _build_msg_payload(from_uid, to_uid, msg_type, idx)
        resp = client.post(payload)
        ec = resp.get("ec")
        em = resp.get("em", "")
        ok = ec in (0, 200)
        return ok, f"[{idx:04d}] {from_uid}->{to_uid} {msg_type} ec={ec} em={em}"
    except Exception as e:  # noqa: BLE001
        return False, f"[{idx:04d}] {from_uid}->{to_uid} {msg_type} ERR: {e}"


def _plan(uid_a: str, uid_b: str, total: int) -> list[tuple[str, str, str]]:
    """
    生成消息计划：A→B 与 B→A 各占一半，消息类型按 4:3:3 (TEXT:IMG:VIDEO) 交替。
    """
    types = ["TEXT"] * 4 + ["IMG"] * 3 + ["VIDEO"] * 3  # 10 为一个周期
    plan = []
    for i in range(total):
        # A→B 奇数，B→A 偶数
        if i % 2 == 0:
            sender, receiver = uid_a, uid_b
        else:
            sender, receiver = uid_b, uid_a
        msg_type = types[i % len(types)]
        plan.append((sender, receiver, msg_type))
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="A↔B 互发私聊压测（TEXT/IMG/VIDEO）")
    parser.add_argument("--uid-a", default="100329338", help="用户 A 的 userId")
    parser.add_argument("--uid-b", default="100261858", help="用户 B 的 userId")
    parser.add_argument("--total", type=int, default=2000, help="总消息数（默认 2000）")
    parser.add_argument("--concurrency", type=int, default=5, help="并发线程数（默认 5）")
    parser.add_argument("--delay-ms", type=int, default=200, help="每批发送后的延迟（ms）")
    parser.add_argument("--entry-url", default=os.environ.get("MOA_ENTRY_URL", ENTRY_URL))
    parser.add_argument("--cookie", default=os.environ.get("MOA_COOKIE", ""))
    args = parser.parse_args()

    if not args.cookie:
        print(
            "❌ 缺少 MOA Cookie。\n"
            "   请打开 https://mse.wemomo.com 登录后，在 DevTools → Network 里复制 Cookie，\n"
            "   然后通过 --cookie 参数传入，或设置环境变量 MOA_COOKIE。",
            file=sys.stderr,
        )
        sys.exit(1)

    client = MoaClient(args.entry_url, args.cookie, timeout_ms=8000, auto_refresh=False)
    plan = _plan(args.uid_a, args.uid_b, args.total)

    # 统计
    success = 0
    failed = 0
    fail_logs: list[str] = []
    start = time.time()

    print(
        f"开始发送：uid_a={args.uid_a}, uid_b={args.uid_b}, "
        f"total={args.total}, concurrency={args.concurrency}"
    )
    type_counts: dict[str, int] = {"TEXT": 0, "IMG": 0, "VIDEO": 0}
    direction_counts: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(_send_one, client, sender, receiver, mtype, idx): idx
            for idx, (sender, receiver, mtype) in enumerate(plan)
        }
        done_count = 0
        for fut in as_completed(futures):
            ok, log = fut.result()
            done_count += 1
            if ok:
                success += 1
            else:
                failed += 1
                fail_logs.append(log)
            # 解析 type 和 direction
            idx = futures[fut]
            _, _, mtype = plan[idx]
            type_counts[mtype] = type_counts.get(mtype, 0) + (1 if ok else 0)
            # 进度
            if done_count % 100 == 0 or done_count == args.total:
                elapsed = time.time() - start
                qps = done_count / elapsed if elapsed > 0 else 0
                print(
                    f"  ▶ {done_count:4d}/{args.total}  "
                    f"✓{success} ✗{failed}  "
                    f"{qps:.1f} msg/s  elapsed={elapsed:.0f}s"
                )

    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"完成！total={args.total}, 成功={success}, 失败={failed}, 耗时={elapsed:.1f}s")
    print(f"消息类型分布：TEXT={type_counts['TEXT']}, IMG={type_counts['IMG']}, VIDEO={type_counts['VIDEO']}")
    if fail_logs:
        print(f"\n失败日志（前20条）：")
        for line in fail_logs[:20]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
