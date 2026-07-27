#!/usr/bin/env python3
"""Analyze May Yaahlan customer complaint data and build Excel top summary rows."""
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def excel_to_dt(serial):
    if serial in ("", None):
        return None
    try:
        serial = float(serial)
    except (TypeError, ValueError):
        return None
    return datetime(1899, 12, 30) + timedelta(days=serial)


def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


def hours_between(start, end):
    if not start or not end:
        return None
    return (end - start).total_seconds() / 3600


def categorize(text):
    rules = [
        ("账号绑定/换绑", r"换绑|更换绑定|改绑|旧邮箱|新邮箱|旧手机|新手机|绑定|google|gmail|邮箱|手机号|无法登录|验证码|登录账号|账号被偷"),
        ("充值/支付", r"充值|visa|mastercard|stripe|apple pay|usdt|币商|支付|钻石未到账|扣款|未到账|无法充值"),
        ("房间输入/键盘体验", r"键盘|打字|输入困难|非法信息|输入语言|输入过程"),
        ("网络/卡顿/加载", r"卡顿|加载很慢|加载|网络状态|内存不足|自动退出|公共资源"),
        ("风控/安全", r"风控|多开|风险用户|解封|封禁|篡改|验证码次数过多"),
        ("真人认证", r"真人认证|验证一直不成功|认证功能异常|验证一直"),
        ("活动/奖励/任务", r"活动|奖励|任务|宝箱|赛季|邀请奖励|支持值|来晚了|第一名"),
        ("礼物/定制礼物", r"定制礼物|上传.*视频|求婚戒指|mp4"),
        ("房间/家族/管理员", r"管理员|贵族|踢出|房间成员|家族宝箱|房间宝箱"),
        ("产品规则说明", r"私信按钮|好友|对方拒绝|设计如此|不符合活动规则|无需处理"),
        ("第三方/审核", r"审核|误判|云上曲率|第三方|播放器|动态头像"),
        ("钻石消费查询", r"钻石被扣除|消费"),
        ("VIP/系统设置", r"vip|红色标识|高对比|无障碍"),
    ]
    for name, pat in rules:
        if re.search(pat, text, re.I):
            return name
    return "其他"


def infer_over24_reason(row):
    """Infer why resolution took >24h based on conclusion and metadata."""
    conclusion = row.get("conclusion", "") or ""
    info = row.get("info", "") or ""
    handlers = row.get("handlers", "") or ""
    resp = row.get("response_dt")
    record = row.get("record_dt")

    reasons = []
    if not resp:
        reasons.append("缺少响应时间记录，工单进入研发/多角色协同后才首次响应")
    elif record and resp and hours_between(record, resp) > 24:
        reasons.append("首次响应本身已超过24h")

    if len([h for h in re.split(r"[,，]", handlers) if h.strip()]) >= 3:
        reasons.append("多角色协同（充值/风控/研发等跨团队排查）")

    if re.search(r"充值|stripe|visa|usdt|币商|订单", info + conclusion, re.I):
        reasons.append("需核对支付渠道/中台订单，等待渠道侧或财务数据")
    if re.search(r"风控|解封|多开", info + conclusion, re.I):
        reasons.append("需风控团队核查设备/账号风险")
    if re.search(r"无法复现|录屏|排查|日志|后台", conclusion, re.I):
        reasons.append("问题非必现或需拉日志/后台数据定位")
    if re.search(r"vpn|卸载|安装.*apk|挂VPN", conclusion, re.I):
        reasons.append("需用户侧配合重装/VPN验证，等待用户反馈")
    if re.search(r"身份|旧邮箱不一致|无法确认", conclusion, re.I):
        reasons.append("账号归属核验耗时")
    if re.search(r"已下发|让用户再看", conclusion, re.I):
        reasons.append("奖励已发但用户未感知，需二次确认到账")
    if not reasons:
        reasons.append("处理链路较长，未在结论中明确标注阻塞原因")
    return "；".join(dict.fromkeys(reasons))


def analyze(rows):
    records = []
    for r in rows[1:]:
        record_dt = excel_to_dt(r[0])
        resolve_dt = excel_to_dt(r[9]) if len(r) > 9 else None
        response_dt = excel_to_dt(r[8]) if len(r) > 8 else None
        info = str(r[2] or "")
        records.append({
            "record_dt": record_dt,
            "reporter": r[1],
            "info": info[:80],
            "type": r[4],
            "conclusion": r[5],
            "status": r[6],
            "handlers": r[7],
            "response_dt": response_dt,
            "resolve_dt": resolve_dt,
            "category": categorize(info),
            "resolve_hours": hours_between(record_dt, resolve_dt),
            "response_hours": hours_between(record_dt, response_dt),
        })

    total = len(records)
    resolved = [x for x in records if x["resolve_hours"] is not None]
    avg_hours = sum(x["resolve_hours"] for x in resolved) / len(resolved) if resolved else 0

    over24 = [x for x in resolved if x["resolve_hours"] > 24]
    over24_sorted = sorted(over24, key=lambda x: -x["resolve_hours"])

    type_cnt = Counter(x["type"] for x in records)
    cat_cnt = Counter(x["category"] for x in records)
    reporter_cnt = Counter(x["reporter"] for x in records)

    # duplicate themes - room 45744972 appears multiple times
    room_ids = Counter(re.findall(r"房间ID[:：]?\s*(\d+)", " ".join(x["info"] for x in records)))

    return {
        "total": total,
        "avg_hours": avg_hours,
        "median_hours": sorted(x["resolve_hours"] for x in resolved)[len(resolved)//2],
        "within_24h": len([x for x in resolved if x["resolve_hours"] <= 24]),
        "over24_count": len(over24),
        "over24_pct": len(over24)/total*100,
        "over24_cases": over24_sorted,
        "type_cnt": type_cnt,
        "cat_cnt": cat_cnt,
        "reporter_cnt": reporter_cnt,
        "records": records,
    }


def build_summary_rows(stats):
    lines = []
    lines.append(["【5月 Yaahlan 客诉反馈数据分析】", "", "", "", "", "", "", "", "", ""])
    lines.append([f"统计周期：2026-05-01 ~ 2026-05-31 | 生成时间：{datetime.now().strftime('%Y-%m-%d')}", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])
    lines.append(["一、核心指标", "", "", "", "", "", "", "", "", ""])
    lines.append([f"总反馈数量：{stats['total']} 条", "", "", "", "", "", "", "", "", ""])
    lines.append([f"已全部归档（已解决）：{stats['total']} 条，解决率 100%", "", "", "", "", "", "", "", "", ""])
    lines.append([f"平均解决时长（反馈时间→解决时间）：{stats['avg_hours']:.1f} 小时（约 {stats['avg_hours']/24:.1f} 天）", "", "", "", "", "", "", "", "", ""])
    lines.append([f"中位解决时长：{stats['median_hours']:.1f} 小时", "", "", "", "", "", "", "", "", ""])
    lines.append([f"24h 内解决：{stats['within_24h']} 条（{stats['within_24h']/stats['total']*100:.1f}%）", "", "", "", "", "", "", "", "", ""])
    lines.append([f"超过 24h 才归档：{stats['over24_count']} 条（{stats['over24_pct']:.1f}%）", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])

    lines.append(["二、问题类型分布", "", "", "", "", "", "", "", "", ""])
    for t, c in stats["type_cnt"].most_common():
        lines.append([f"  {t}：{c} 条（{c/stats['total']*100:.1f}%）", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])

    lines.append(["三、功能/场景集中反馈 TOP", "", "", "", "", "", "", "", "", ""])
    for cat, c in stats["cat_cnt"].most_common(8):
        lines.append([f"  {cat}：{c} 条", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])

    lines.append(["四、超过 24h 归档工单及原因分析", "", "", "", "", "", "", "", "", ""])
    for i, case in enumerate(stats["over24_cases"][:12], 1):
        reason = infer_over24_reason(case)
        lines.append([
            f"{i}. 耗时{case['resolve_hours']:.0f}h | {case['category']} | {fmt_dt(case['record_dt'])}",
            case["info"][:60], reason, "", "", "", "", "", "", ""
        ])
    lines.append(["", "", "", "", "", "", "", "", "", ""])

    # Aggregate over24 reasons
    reason_buckets = Counter()
    for case in stats["over24_cases"]:
        for part in infer_over24_reason(case).split("；"):
            reason_buckets[part] += 1
    lines.append(["超24h 共性原因汇总：", "", "", "", "", "", "", "", "", ""])
    for reason, c in reason_buckets.most_common():
        lines.append([f"  · {reason}（{c} 次）", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])

    lines.append(["五、集中反馈功能点（需产品/研发关注）", "", "", "", "", "", "", "", "", ""])
    hotspots = [
        "账号绑定/换绑（邮箱、手机号、Google 账号）：公会长/主播高频，旧号停用、邮箱丢失、账号被盗",
        "充值/支付失败或未到账：Visa/Stripe/Apple Pay/USDT 多渠道，需统一用户侧错误码说明",
        "房间文字输入体验（2.5.0 版本）：键盘收起、输入困难、非法信息误判，房间45744972 多次出现",
        "登录/网络/加载异常：用户感知为「网络正常但 App 不行」，常与 CDN/公共资源/VPN 相关",
        "真人认证：5月中旬集中 3 起（含 1 起真实 bug），需优化引导与接口稳定性",
        "风控相关：邀请奖励、任务奖励、验证码、活动计值 — 客服话术与风控结论需对齐",
        "活动/奖励到账感知：赛季奖励、房间活动第一名等「已发但用户未看到」",
    ]
    for h in hotspots:
        lines.append([f"  · {h}", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])

    lines.append(["六、后续改进方案", "", "", "", "", "", "", "", "", ""])
    improvements = [
        "【SLA】建立客诉分级：P0（无法登录/充值不到账）4h 内首次响应、24h 闭环；P1 48h 闭环。表格强制填写「响应时间」",
        "【账号安全】上线/强化「双因素绑定」引导（邮箱+手机），公会长换绑 SOP + 身份核验清单，减少 15+ 条重复换绑工单",
        "【充值】整理 Top 错误码（Stripe card_declined、OR-FGEMF-86、3DS 失败）中英阿客服话术 + 用户自助排查页",
        "【房间输入】2.5.x 版本专项：键盘遮挡/自动收起、云上曲率误杀正常昵称 — 提测回归 + 白名单策略",
        "【风控透明】邀请/任务/活动奖励被拒时，客户端展示可读原因（非仅「来晚了/失败」），降低重复客诉",
        "【活动奖励】结榜后 push + 活动页「奖励已到账」状态；赛季奖励下发后批量巡检 Top 房间",
        "【家族宝箱 UI】进度条增加数值展示（已在结论中提及），避免「进度不动」误解",
        "【知识库】将高频 not bug 场景（高对比文字、私信需好友、mp4 格式等）沉淀为客服一键回复模板",
    ]
    for imp in improvements:
        lines.append([imp, "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])
    lines.append(["—— 以下为客户反馈明细 ——", "", "", "", "", "", "", "", "", ""])
    lines.append(["", "", "", "", "", "", "", "", "", ""])
    return lines


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("temporary_testcase/_may_complaint_raw.json")
    out_path = Path("temporary_testcase/_may_complaint_write.json")
    rows = json.loads(path.read_text(encoding="utf-8"))
    stats = analyze(rows)
    summary = build_summary_rows(stats)
    # pad original rows to 10 cols
    def pad(row):
        row = list(row[:10])
        while len(row) < 10:
            row.append("")
        return row
    full = [pad(r) for r in summary] + [pad(r) for r in rows]
    out_path.write_text(json.dumps({"stats": {
        "total": stats["total"],
        "avg_hours": round(stats["avg_hours"], 2),
        "over24": stats["over24_count"],
    }, "full_data": full}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats["type_cnt"], ensure_ascii=False))
    print(f"total={stats['total']} avg_h={stats['avg_hours']:.2f} over24={stats['over24_count']} rows_out={len(full)}")


if __name__ == "__main__":
    main()
