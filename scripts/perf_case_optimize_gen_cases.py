#!/usr/bin/env python3
"""从 case优化 场景表生成 autotest cases/*.json（实验套件）。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "adb/自动化用例/主版本性能case_2026Q4-case优化"
CASES_DIR = OUT / "cases"

SCENES = [
    ("01", "开跑冷启动", "macro 冷启动回首页", "auto"),
    ("02", "Game帧Online列表快滑", "do_swipe_v(30)", "auto"),
    ("03", "Game帧下拉刷新", "手势下拉占位", "partial"),
    ("04", "Game帧进出子页内存", "macro 游戏帧进入个人资料/活动中心", "auto"),
    ("05", "Game帧静置", "sleep 30", "auto"),
    ("06", "房间列表快滑", "do_swipe_v(30)", "auto"),
    ("07", "房间Hot/Mine/Egypt Tab", "macro 房间帧切换Hot/Mine/Egypt", "auto"),
    ("08", "房间子分类 Tab", "Hot/PK/Game/Chat", "partial"),
    ("09", "房间列表下拉刷新", "手势下拉占位", "partial"),
    ("10", "进退性能房", "macro 搜索进房/退出房间", "auto"),
    ("11", "Hot首卡进房浸泡", "macro 进房 + sleep 180", "auto"),
    ("12", "房内在线列表", "macro 房内打开在线用户列表", "auto"),
    ("13", "房内贵族列表", "macro NobilityTab", "auto"),
    ("14", "房内成员列表", "macro MembersTab", "auto"),
    ("15", "退房回列表静置", "macro 退出房间 + sleep", "auto"),
    ("16", "消息列表快滑", "do_swipe_v(30)", "auto"),
    ("17", "消息列表静置", "sleep 30", "auto"),
    ("18", "会话进出压测", "macro 消息帧进入家族群聊", "auto"),
    ("19", "动态Discover快滑", "macro DiscoverTab + swipe", "auto"),
    ("20", "动态Following快滑", "macro 切换动态关注tab", "auto"),
    ("21", "动态点赞刷新", "macro Discover点赞首条", "auto"),
    ("22", "动态详情评论滑", "macro 动态详情 + swipe", "auto"),
    ("23", "动态详情收礼Tab滑", "需补图 收礼Tab", "partial"),
    ("24", "动态列表静置", "sleep 30", "auto"),
    ("25", "Me首屏静置", "sleep 5", "auto"),
    ("26", "好友/关注/粉丝", "macro 好友/关注/粉丝列表", "auto"),
    ("27", "个人资料进出", "macro 我的页进入个人资料详情", "auto"),
    ("28", "Me静置", "sleep 30", "auto"),
    ("29", "五帧快切30次", "macro 切换*底栏", "auto"),
    ("30", "结束压后台", "HOME + monkey 拉回", "auto"),
]


def main() -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    dingtalk = "https://alidocs.dingtalk.com/i/nodes/vy20BglGWOekp0O0TmrNb91lJA7depqY"
    for num, title, impl, status in SCENES:
        cid = f"PERF-OPT-{num}-{title.replace('/', '_')[:20]}"
        doc = {
            "id": cid,
            "type": "performance",
            "priority": "P0",
            "caseNo": num,
            "name": title,
            "module": "性能·case优化",
            "automationStatus": status,
            "source": {
                "dingtalkWorkbook": dingtalk,
                "dingtalkSheet": "case优化",
                "runnerRef": f"scripts/perf_automation_full.sh#scene_{int(num)}",
                "automationImpl": impl,
            },
            "macroFlags": ["--no-capture", "--no-popup-gate", "--force-script"],
            "experienceExpect": "path_ok；PerfDog 人工书签 PERF-" + num,
            "perfdog": {"enabled": False, "sessionLabel": f"case优化-{num}"},
            "operations": [
                {
                    "step": 1,
                    "description": f"执行全链路脚本场景 {num}",
                    "action": "shell",
                    "command": f"PERF_ONLY={num} ./scripts/perf_automation_full.sh",
                }
            ],
        }
        path = CASES_DIR / f"{cid}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(SCENES)} cases -> {CASES_DIR}")


if __name__ == "__main__":
    main()
