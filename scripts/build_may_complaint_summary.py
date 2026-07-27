#!/usr/bin/env python3
"""Build May Yaahlan complaint summary rows for DingTalk Excel."""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def parse_hours(s):
    if not s or s == "":
        return None
    s = str(s).strip()
    if s == "0小时":
        return 0.0
    m = re.match(r"(?:(\d+)天)?(?:(\d+(?:\.\d+)?)小时)?", s)
    if not m:
        return None
    d = int(m.group(1) or 0)
    h = float(m.group(2) or 0)
    return d * 24 + h


def fmt_duration_hours(h):
    if h is None:
        return "-"
    days = int(h // 24)
    rem = h - days * 24
    rh = int(rem)
    mins = int(round((rem - rh) * 60))
    if days > 0:
        if rh and mins:
            return f"{days}天{rh}小时{mins}分钟"
        if rh:
            return f"{days}天{rh}小时"
        return f"{days}天"
    if rh and mins:
        return f"{rh}小时{mins}分钟"
    if rh:
        return f"{rh}小时"
    return f"{mins}分钟"


def classify_overall(info, typ, conclusion):
    text = info + " " + conclusion
    if re.search(r"充值|visa|mastercard|stripe|apple pay|usdt|币商|支付|钻石未到账|无法充值", text, re.I):
        return "充值/支付问题"
    if re.search(
        r"换绑|更换绑定|改绑|旧邮箱|新邮箱|旧手机|新手机|绑定手机|绑定邮箱|google|gmail|"
        r"登录|验证码|账号被偷|无法登录|收不到验证码|请求验证码",
        text,
        re.I,
    ):
        return "账号问题（登录/换绑）"
    if typ in ("bug", "experience bug", "第三方服务问题") or re.search(
        r"键盘|输入|卡顿|加载|语音|认证|定制礼物|上传|非法信息|自动退出|内存|播放器|审核",
        text,
        re.I,
    ):
        return "技术相关（体验/房间/其他）"
    if re.search(
        r"设计如此|规则|私信按钮|好友|宝箱.*条件|不符合活动|对方拒绝|高对比|mp4|无需处理|"
        r"没有达到|已下发|数据记录",
        text,
        re.I,
    ):
        return "产品功能疑问"
    return "无效反馈/非问题"


def classify_avg_cat(info, typ, conclusion):
    text = info + " " + conclusion
    if re.search(r"充值|visa|mastercard|stripe|apple pay|usdt|币商|支付|钻石未到账|无法充值", text, re.I):
        return "充值问题"
    if re.search(r"换绑|绑定|邮箱|手机|google|gmail|登录|验证码|账号被偷|无法登录", text, re.I):
        return "登录/注册"
    if re.search(r"活动|奖励|任务|赛季|邀请奖励|支持值|宝箱奖励|来晚了|第一名", text, re.I):
        return "活动任务问题"
    if re.search(r"礼物|定制|求婚|背包|礼包|钻石被扣除", text, re.I):
        return "礼物/背包问题"
    if re.search(r"房间|键盘|输入|卡顿|加载|语音|贵族|管理员|踢|非法信息|自动退出", text, re.I):
        return "房间/输入/体验问题"
    if typ in ("bug", "experience bug", "第三方服务问题") or re.search(r"认证|头像|vip|播放器", text, re.I):
        return "其他技术问题"
    if re.search(r"设计如此|无需处理|不符合|风控|数据记录|没有达到|已下发|done", text, re.I):
        return "非问题"
    return "其他问题"


def feature_point(info, conclusion):
    text = info + " " + conclusion
    if re.search(r"换绑|绑定.*邮箱|绑定.*手机|旧邮箱|新邮箱|google|gmail|登录|验证码|账号被偷", text, re.I):
        return "账号登录/换绑手机号/邮箱"
    if re.search(r"风控|多开|邀请奖励|无法再次领取|验证码次数|解封|风险用户", text, re.I):
        return "风控/邀请/任务限制"
    if re.search(r"充值|visa|mastercard|stripe|apple pay|usdt|币商|钻石未到账|无法充值", text, re.I):
        return "充值未到账/支付失败"
    if re.search(r"键盘|输入|打字|非法信息|输入困难|输入语言", text, re.I):
        return "房间打字/键盘输入"
    if re.search(r"卡顿|加载|网络状态|自动退出|内存|公共资源|网络有问题", text, re.I):
        return "App卡顿/加载/网络"
    if re.search(r"活动|奖励|赛季|宝箱|来晚了|支持值|第一名", text, re.I):
        return "活动奖励领取"
    if re.search(r"认证|验证一直", text, re.I):
        return "真人认证"
    if re.search(r"礼物|定制|求婚", text, re.I):
        return "礼物/定制礼物"
    if re.search(r"贵族|管理员|踢", text, re.I):
        return "房间成员/贵族列表"
    return "其他"


def overtime_reason(info, conclusion):
    text = conclusion + " " + info
    if re.search(r"stripe|visa|渠道|中台|订单|币商|google 账户|kyc|银行|OR-FGEMF", text, re.I):
        return "第三方依赖（支付渠道/银行/币商）"
    if re.search(r"安装.*apk|vpn|卸载|重装|录屏|让用户|挂VPN", text, re.I):
        return "需用户配合补充信息/操作"
    if re.search(r"bug|版本|修复|优化|接口", text, re.I):
        return "技术问题需版本迭代修复"
    if re.search(r"无法复现|非必现|难复现", text, re.I):
        return "问题难复现"
    if re.search(r"风控|核查|多账号", text, re.I):
        return "风控/规则核查耗时"
    return "跨团队协同/信息核对"


def pad(row, width=11):
    row = list(row)
    while len(row) < width:
        row.append("")
    return row[:width]


def extract_detail_rows(rows):
    """Locate detail table (header row 记录时间), merge 解决时长 if needed."""
    start = 0
    for i, r in enumerate(rows):
        if str(r[0]).strip() == "记录时间":
            start = i
            break
    detail = [[c for c in r[:11]] for r in rows[start:]]
    while len(detail[0]) < 11:
        detail[0].append("")
    dur_path = Path("temporary_testcase/_duration_col.json")
    if dur_path.exists() and (len(detail[0]) <= 10 or not detail[0][10]):
        durations = json.loads(dur_path.read_text(encoding="utf-8"))
        for i, row in enumerate(detail):
            while len(row) < 11:
                row.append("")
            if i < len(durations):
                row[10] = durations[i][0]
    return detail


def build_summary(rows):
    detail_rows = extract_detail_rows(rows)
    header = detail_rows[0]
    data = []
    for r in detail_rows[1:]:
        info = str(r[2] or "")
        typ = str(r[4] or "")
        conclusion = str(r[5] or "")
        dur = parse_hours(r[10] if len(r) > 10 else "")
        data.append(
            {
                "info": info,
                "type": typ,
                "conclusion": conclusion,
                "hours": dur,
                "overall": classify_overall(info, typ, conclusion),
                "avg_cat": classify_avg_cat(info, typ, conclusion),
                "feature": feature_point(info, conclusion),
            }
        )

    total = len(data)
    bug_count = sum(1 for d in data if d["type"] == "bug")
    overall_cnt = Counter(d["overall"] for d in data)
    avg_cat_hours = defaultdict(list)
    for d in data:
        if d["hours"] is not None:
            avg_cat_hours[d["avg_cat"]].append(d["hours"])

    all_hours = [d["hours"] for d in data if d["hours"] is not None]
    overall_avg = sum(all_hours) / len(all_hours)

    over24 = [d for d in data if d["hours"] is not None and d["hours"] > 24]
    ot_reasons = Counter(overtime_reason(d["info"], d["conclusion"]) for d in over24)
    feature_cnt = Counter(d["feature"] for d in data)

    out = []
    out.append(pad(["5月 Yaahlan 客诉反馈数据分析总结", "", ""]))
    out.append(pad(["统计周期：2026-05-01 ~ 2026-05-31", "", ""]))
    out.append(pad(["", "", ""]))

    # Section I
    out.append(pad(["一、总体数量", "", ""]))
    out.append(pad(["类型", "数量", "占比"]))
    out.append(pad(["总反馈数", total, "100%"]))
    for cat in [
        "账号问题（登录/换绑）",
        "技术相关（体验/房间/其他）",
        "充值/支付问题",
        "无效反馈/非问题",
        "产品功能疑问",
    ]:
        c = overall_cnt.get(cat, 0)
        tech_label = cat
        if cat == "技术相关（体验/房间/其他）":
            tech_label = f"技术相关（体验/房间/其他）（其中技术bug {bug_count}个）"
        out.append(pad([tech_label, c, f"{c/total*100:.0f}%"]))
    out.append(pad(["", "", ""]))

    # Section II
    out.append(pad([f"二、平均解决时长（{fmt_duration_hours(overall_avg)}）", "", ""]))
    out.append(pad(["问题分类", "平均解决时长", "数量"]))
    cat_order = [
        "充值问题",
        "房间/输入/体验问题",
        "其他技术问题",
        "其他问题",
        "礼物/背包问题",
        "活动任务问题",
        "非问题",
        "登录/注册",
    ]
    for cat in cat_order:
        hs = avg_cat_hours.get(cat, [])
        if not hs:
            continue
        out.append(pad([cat, fmt_duration_hours(sum(hs) / len(hs)), len(hs)]))
    out.append(pad(["", "", ""]))

    # Section III
    out.append(pad(["三、超时原因（>24h 归档，共{}条）".format(len(over24)), "", ""]))
    out.append(pad(["超时原因分布", "条数", ""]))
    for reason, c in ot_reasons.most_common():
        out.append(pad([reason, c, ""]))
    out.append(pad(["", "", ""]))

    # Section IV
    out.append(pad(["四、集中反馈的功能点", "", ""]))
    out.append(pad(["功能问题点", "反馈数", ""]))
    for feat, c in feature_cnt.most_common(8):
        if feat != "其他":
            out.append(pad([feat, c, ""]))
    out.append(pad(["", "", ""]))

    # Section V
    out.append(pad(["五、核心结论与建议", "", ""]))
    acct = overall_cnt.get("账号问题（登录/换绑）", 0)
    recharge = overall_cnt.get("充值/支付问题", 0)
    tech = overall_cnt.get("技术相关（体验/房间/其他）", 0)
    conclusions = (
        f"1. 账号安全是最大痛点（{acct}条，{acct/total*100:.0f}%）：公会长/主播因邮箱或手机号丢失无法自助找回，"
        f"换绑工单占比高，需强化双绑引导与换绑SOP。\n"
        f"2. 2.5.x 版本房间输入体验问题集中（键盘收起、输入困难、非法信息误判），"
        f"房间45744972多次出现，需专项回归。\n"
        f"3. 充值/支付类（{recharge}条）平均解决时长最长，主要卡在 Stripe/Visa/USDT 等第三方渠道核对与中台订单查询，"
        f"建议沉淀错误码话术与自助排查页。\n"
        f"4. 技术体验类（{tech}条，含{bug_count}个bug）：卡顿/加载/网络登录与真人认证、定制礼物等需持续优化；"
        f"超24h工单多因需用户装包/VPN或跨团队协同。\n"
        f"5. 风控相关反馈（邀请奖励、任务奖励、活动计值）建议客户端展示可读拒绝原因，降低重复客诉。"
    )
    out.append(pad([conclusions, "", ""]))
    out.append(pad(["", "", ""]))
    out.append(pad(["—— 以下为客诉反馈明细 ——", "", ""]))
    out.append(pad(["", "", ""]))

    detail = [pad(header[:11])]
    for r in detail_rows[1:]:
        detail.append(pad([r[i] if i < len(r) else "" for i in range(11)]))

    return out + detail


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("temporary_testcase/_may_sheet_raw.json")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("temporary_testcase/_may_summary_full.json")
    rows = json.loads(src.read_text(encoding="utf-8"))
    full = build_summary(rows)
    out.write_text(json.dumps(full, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary+detail rows: {len(full)}, detail starts at row {len(full)-len(rows)}")


if __name__ == "__main__":
    main()
