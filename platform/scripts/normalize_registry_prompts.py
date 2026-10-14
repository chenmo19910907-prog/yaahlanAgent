#!/usr/bin/env python3
"""补全工具台 prompt 的 <key|label> 占位符，去掉「这台/这一」等无主体表述与写死示例。"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "platform"))
from project.loader import load_sources  # noqa: E402

# item_id -> 替换后的 prompts（整组覆盖；同 id 跨模块时用 PROMPTS_BY_NAME）
PROMPTS_BY_ID: dict[str, list[str]] = {
    "query_device_current_account": [
        "查设备<device|设备名或资产编号或mmuidv3>当前登录账号",
    ],
    "query_family": [
        "查询家族<familyId|家族ID>信息",
        "查家族<familyName|家族名称>详情",
    ],
    "add_guild_member": [
        "用户<userId|userId>加入公会<tradeId|公会ID>",
    ],
    "query_guild": [
        "查询公会长<userId|userId>的公会信息",
        "查公会<tradeUnion|公会名称>详情",
        "公会 ID <tradeId|公会ID> 有多少主播",
    ],
    "delete_im_task": [
        "删除 IM 配置任务<taskId|任务ID>",
        "清理 IM 任务 id 大于<id|任务ID>",
    ],
    "update_app_store_review_version": [
        "设置 iOS 审核版本<iosVersion|iOS版本> Android版本号<androidVersionCode|版本号>",
    ],
    "big_r_verify_smoke": [
        "大R后台冒烟验收 userId=<userId|userId>",
    ],
    "big_r_import_data": [
        "导入大R测试数据<startDate|开始日期>到<endDate|结束日期>",
    ],
    "room_owner_absence_downgrade_real": [
        "模拟房间<roomId|roomId>房主<ownerId|房主userId>未回房真实降级",
    ],
    "room_owner_absence_downgrade_keep_level": [
        "房间<roomId|roomId>房主<ownerId|房主userId>不升等级触发活跃度下降",
    ],
    "room_level_page_prompt_query": [
        "房间<roomId|roomId>房主<ownerId|房主userId>查询等级页衰减弹窗",
    ],
    "room_level_page_prompt_mock": [
        "Mock 房间<roomId|roomId>房主<ownerId|房主userId>等级页衰减弹窗",
    ],
    "room_member_lv_level_upgrade": [
        "房间<roomId|roomId>用户<userId|userId>升到成员等级<level|等级>当前经验<currentExp|当前陪伴值>",
    ],
    "vip_level_upgrade": [
        "把用户<userId|userId>升级到 VIP<level|等级>",
    ],
    "vip_try_dispatch": [
        "给用户<userId|userId>下发<durationSeconds|秒数>VIP<level|等级>体验卡",
    ],
    "noble_level_upgrade": [
        "用户<userId|userId>升级到贵族 lv<level|等级>当前经验<currentExp|当前消费值>",
    ],
    "family_fund_tier_cache_clear": [
        "清除家族<familyId|familyId>基金档位缓存 周<weekMonday|周一yyyy-MM-dd>",
    ],
    "family_fund_reward_dispatch_clear": [
        "清除家族基金本周奖励下发记录 周<weekMonday|周一yyyy-MM-dd>",
    ],
    "family_fund_contrib_add": [
        "给家族<familyId|familyId>在<weekMonday|周一yyyy-MM-dd>周期增加<contrib|贡献值>基金贡献值",
    ],
    "family_member_fund_contrib_add": [
        "成员<userId|userId>在家族<familyId|familyId>增加<contrib|贡献值>基金贡献值 周<weekMonday|周一yyyy-MM-dd>",
    ],
    "user_area_change": [
        "修改用户<userId|userId>大区为<area|大区>",
    ],
    "gift_panel_backpack_view": [
        "查看用户<userId|userId>在房间<roomId|roomId>礼物面板背包",
    ],
    "gift_panel_backpack_gifts": [
        "查看背包礼物 userId=<userId|userId> roomId=<roomId|roomId>",
    ],
    "anniversary_egg_mystery_count": [
        "查询砸金蛋神秘保底次数 userId=<userId|userId> roomId=<roomId|roomId>",
    ],
    "anniversary_egg_smash_record": [
        "用户<userId|userId>砸金蛋<smashCount|次数>次并写钉钉表",
    ],
    "recharge_rebate_incr_flow": [
        "模拟充值后增加流水 userId=<userId|userId> 钻石<diamonds|数量> 日期<yyyyMMdd|yyyyMMdd>",
    ],
    "user_prop_query_own": [
        "查用户<userId|userId>资料页背景装扮 propType=<propTypeCode|道具类型>",
    ],
    "family_kick_member": [
        "家族<familyId|familyId>长<operatorId|族长userId>踢出成员<remoteId|成员userId>",
    ],
    "family_pk_member_contrib_list": [
        "家族PK成员贡献 familyId=<familyId|familyId> date=<date|日期> userId=<userId|userId>",
    ],
    "family_pk_request_page": [
        "getFamilyPkPage userId=<userId|userId> date=<date|日期>",
    ],
    "family_pk_query_receive_daily_rank_2": [
        "查询<date|日期>家族收礼日榜 top<limit|条数>",
    ],
    "family_delete": [
        "删除家族<familyId|familyId> 操作人<userId|userId>",
    ],
    "feed_publish_comment": [
        "用户<userId|userId>帖子评论 feedId=<feedId|feedId> 内容<content|内容>",
    ],
    "feed_gift_send": [
        "用户<userId|userId>给帖子<feedId|feedId>用户<toUserId|收礼userId>送礼物<giftId|礼物ID>",
    ],
    "im_send_p2p_message": [
        "用户<fromUid|发送方>给<toUid|接收方>发私聊<text|消息内容>",
    ],
    "feed_publish": [
        "用户<userId|userId>发动态<text|内容>",
    ],
    "reward_dispatch_block_check": [
        "奖励未下发拦截排查 userId=<userId|userId> ruleId=<ruleId|规则ID> scene=<scene|场景>",
    ],
    "reward_dispatch_risk_precheck": [
        "奖励下发风控预检 userId=<userId|userId> ruleId=<ruleId|规则ID> scene=<scene|场景>",
    ],
    "reward_verify_diff": [
        "用户<userId|userId>奖励验收发奖前后求差",
    ],
    "reward_verify_compare": [
        "用户<userId|userId>奖励验收对照期望配置",
    ],
    "user_contact_cs_send_message": [
        "批量<fromUid|用户>联系客服<csUserId|客服userId>发消息<text|内容>",
    ],
    "room_send_channel_message": [
        "用户<userId|userId>在房间<roomId|roomId>发公屏<text|消息内容>",
    ],
    "room_send_channel_image": [
        "用户<userId|userId>在房间<roomId|roomId>发公屏图片 url=<url|图片URL>",
    ],
    "p2p_gift_send_2": [
        "用户<senderUserId|送礼方>批量私聊送礼给<receiverUserId|收礼方> giftId=<giftId|礼物ID> count=<count|数量>",
    ],
    "package_gift_send": [
        "给用户<userId|userId>下发背包礼物 fromUserId=<fromUserId|发放方>",
    ],
    "pk_rank_query": [
        "PK榜数值查询 周<YYYYMMDD或本周|yyyyMMdd或本周>",
    ],
    "moa_generative_diamond_history": [
        "查询用户<userId|userId>钻石记录 pageSize=<pageSize|页大小> lastId=<lastId|游标>",
    ],
    "moa_generative_workflow_run": [
        "【推荐·工作流】抓包 body 文件<bodyFile|抓包 body.json> 生成并执行 MOA 服务<serviceUrl|MOA ServiceUrl> 方法<method|方法名>",
    ],
    "moa_generative_run_script": [
        "【一键脚本】抓包 body 文件<bodyFile|抓包 body.json> 生成并执行 MOA 服务<serviceUrl|MOA ServiceUrl> 方法<method|方法名>",
    ],
    "moa_generative_build_only": [
        "【仅生成 payload】抓包 body 文件<bodyFile|抓包 body.json> 只生成 MOA 请求 JSON（不调用）服务<serviceUrl|MOA ServiceUrl> 方法<method|方法名>",
    ],
    "folder_lookup": [
        "在目录按关键词<关键词|关键词>查找用例表链接",
    ],
    "kb_sync_workbook": [
        "同步钉钉用例表<表格URL|表格链接>到知识库",
    ],
    "prd_sync_document": [
        "同步需求文档<PRD文档URL|文档链接>到知识库",
    ],
    "excel_mark_p0": [
        "用例表<表格URL|表格链接>预期结果列标 P0",
    ],
    "publish_family_monster_from_workbook": [
        "家族怪兽表格<workbookUrl|钉钉表格链接>改参发布",
    ],
    "update_config_set": [
        "MSE 改参保存 voga-common <configKey|配置Key> 设<key|字段>=<value|值>",
    ],
    "update_config_publish": [
        "MSE 改参上线 voga-common <configKey|配置Key> 设<key|字段>=<value|值>",
    ],
    "update_config_dry_run": [
        "dry-run MSE 改参 <configKey|配置Key> 设<key|字段>=<value|值>",
    ],
    "stage_gift_chatroom": [
        "Stage 用户<sender|userId>在房间<roomId|roomId>给<receivers|userId>送礼物<giftId|礼物ID>数量<num|数量>",
    ],
    "stage_gift_private": [
        "Stage 用户<sender|userId>私聊给<receiver|userId>送礼物<giftId|礼物ID>数量<num|数量>",
    ],
    "stage_gift_group": [
        "Stage 用户<sender|userId>在群组<groupId|群组ID>给<receivers|userId>送礼物<giftId|礼物ID>数量<num|数量>",
    ],
    "stage_gift_room_all": [
        "Stage 用户<sender|userId>在房间<roomId|roomId>全房送礼物<giftId|礼物ID>数量<num|数量>",
    ],
    "stage_gift_probe": [
        "Stage 探测用户<sender|userId>在房间<roomId|roomId>给<receivers|userId>送礼物<giftId|礼物ID>所需 CMDB/MOA",
    ],
    "stage_gift_dry_run": [
        "Stage 预演送礼（不 POST）用户<sender|userId>在房间<roomId|roomId>给<receivers|userId>送礼物<giftId|礼物ID>",
    ],
    "release_test_device": [
        "给测试机<deviceName|设备名>资产<assetId|资产编号>加白",
    ],
    "release_online_login_device": [
        "线上环境解除<phone|手机号>最近登录手机的风控 userId=<userId|userId>",
    ],
    "request_detail": [
        "tunnel 详情 requestId=<requestId|请求ID> userId=<userId|userId>",
    ],
    "tunnel_capture_run": [
        "抓包验收<captureId|场景> userId=<userId|userId>",
    ],
    "mock_param_set": [
        "tunnel mock 用户<userId|userId> 接口<keyword|uri> 字段<fieldPath|JSON路径> 改为<value|值>",
        "mock CP 爱意宝箱倒计时 userId=<userId|userId> keyword=<keyword|uri> 字段<fieldPath|路径> 值<value|秒数>",
    ],
    "mock_param_list": [
        "查看用户<userId|userId> tunnel mock 接口<keyword|uri> 字段",
    ],
    "mock_case_list": [
        "tunnel mock list userId=<userId|userId> keyword=<keyword|uri>",
    ],
    "mock_case_stop": [
        "关闭用户<userId|userId> tunnel mock keyword=<keyword|uri>",
    ],
    "online_user_prop_query_own": [
        "线上环境用户<userId|userId>资料页背景装扮 propType=<propTypeCode|道具类型>",
    ],
}

# 按 name 匹配（同 id 跨模块或 id 兜底）
PROMPTS_BY_NAME: dict[str, list[str]] = {
    "用户-批量互关结好友": [
        "从用户列表给<userId|目标用户>批量结好友<count|数量>个",
    ],
    "用户-批量互关好友（用户列表）": [
        "从创新中台拉<count|数量>人和<userId|目标用户>互关好友",
    ],
    "奖励验收-前后快照求差": [
        "奖励验收求差 before=<beforeFile|发奖前快照> after=<afterFile|发奖后快照> out=<outFile|diff.json>",
    ],
    "奖励验收-前后快照对比": [
        "奖励验收对比 before=<beforeFile|发奖前> after=<afterFile|发奖后> expected=<expectedFile|期望JSON>",
    ],
    "3周年砸金蛋-造数并记录": [
        "用户<userId|userId>砸金蛋<smashCount|次数>次并写钉钉表",
    ],
    "奖励验收-发奖前后求差": [
        "用户<userId|userId>奖励验收发奖前后求差",
    ],
    "奖励验收-对照期望配置": [
        "用户<userId|userId>奖励验收对照期望配置",
    ],
}

HARDCODE_PROMPT_RE = re.compile(
    r"133111\d+|100\d{6}|价值19|下发1天VIP|大区为 MENA|phone-start|3966|批量发招呼消息$|批量打招呼$"
)
VAGUE_PROMPT_RE = re.compile(r"这台|此设备|该设备|这一张|这一篇|某张表|查一下这个")

# param=<占位> → 中文前缀 + 占位（避免 prompt 堆 API 参数名）
PARAM_EQ_RE = re.compile(r"(\w+)=(<[^>]+>|\w+)")

KEY_NATURAL: dict[str, str] = {
    "userId": "用户",
    "sender": "用户",
    "senderUserId": "送礼方",
    "receiver": "收礼方",
    "receiver": "收礼用户",
    "receiverUserId": "收礼用户",
    "receivers": "收礼用户",
    "fromUserId": "发放方",
    "fromUid": "发送方",
    "toUid": "接收方",
    "toUserId": "收礼用户",
    "roomId": "房间",
    "groupId": "群组",
    "giftId": "礼物",
    "feedId": "帖子",
    "familyId": "家族",
    "memberUserId": "成员",
    "operatorId": "操作人",
    "remoteId": "成员",
    "ownerId": "房主",
    "reportedUserId": "被举报用户",
    "date": "日期",
    "pkDate": "PK 日期",
    "rankDate": "榜单日",
    "propType": "道具类型",
    "propTypeCode": "道具类型",
    "ruleId": "规则",
    "scene": "场景",
    "requestId": "请求",
    "keyword": "接口",
    "fieldPath": "字段",
    "value": "值",
    "pageSize": "每页",
    "lastId": "游标",
    "nameplateId": "铭牌",
    "limit": "前",
    "count": "数量",
    "rounds": "轮数",
    "inviteId": "邀请",
    "acrossRoomId": "对端房间",
    "acrossRoomPkId": "跨房 PK",
    "pkId": "PK",
    "pkMinute": "时长",
    "pkDelta": "PK 值",
    "seatCount": "席位数",
    "minute": "分钟",
    "area": "大区",
    "prizeBagId": "星礼包",
    "configKey": "配置",
    "key": "字段",
    "workbookUrl": "表格",
    "beforeFile": "发奖前快照",
    "afterFile": "发奖后快照",
    "expectedFile": "期望配置",
    "outFile": "输出文件",
    "url": "图片",
    "content": "内容",
    "text": "内容",
    "diamonds": "钻石",
    "yyyyMMdd": "日期",
    "smashCount": "次数",
    "contrib": "贡献值",
    "weekMonday": "周一",
    "tradeId": "公会",
    "score": "分数",
    "level": "等级",
    "currentExp": "经验",
    "captureId": "场景",
    "num": "数量",
    "phone": "手机号",
    "device": "设备",
    "deviceName": "设备",
    "assetId": "资产编号",
    "startDate": "开始日期",
    "endDate": "结束日期",
    "taskId": "任务",
    "id": "ID",
    "familyReceiveScore": "收礼分",
    "csUserId": "客服",
}

INTRO_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Stage dry-run 送礼"), "Stage 预演送礼"),
    (re.compile(r"^Stage 探测送礼\b"), "Stage 探测送礼"),
    (re.compile(r"\bgetFamilyPkPage\b"), "查家族 PK 活动页"),
    (re.compile(r"^tunnel mock list\b"), "查看 tunnel mock 列表"),
    (re.compile(r"^tunnel 详情\b"), "查看 tunnel 抓包详情"),
    (re.compile(r"^dry-run MSE 改参"), "MSE 改参预演"),
    (re.compile(r"^查 MSE 配置 key="), "查 MSE 配置"),
    (re.compile(r"^mock CP 爱意宝箱倒计时\b"), "Mock CP 爱意宝箱倒计时"),
    (re.compile(r"^执行抓包验收 gift_send\b"), "执行送礼抓包验收"),
]


def _wrap_placeholder(raw: str) -> str:
    s = raw.strip()
    if s.startswith("<") and s.endswith(">"):
        return s
    return f"<{s}|{s}>"


def _naturalize_param_equals(prompt: str) -> str:
    if not PARAM_EQ_RE.search(prompt):
        return prompt

    def repl(m: re.Match[str]) -> str:
        key, val = m.group(1), m.group(2)
        prefix = KEY_NATURAL.get(key)
        if prefix is None:
            return val if val.startswith("<") else _wrap_placeholder(val)
        if val.startswith("<"):
            return f"{prefix}{val}"
        return f"{prefix}{_wrap_placeholder(val)}"

    out = PARAM_EQ_RE.sub(repl, prompt)
    for pat, sub in INTRO_REPLACEMENTS:
        out = pat.sub(sub, out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def naturalize_prompt(prompt: str) -> str:
    p = prompt.strip()
    p = _naturalize_param_equals(p)
    return p


def _registry_paths() -> list[Path]:
    sources = load_sources()
    paths: list[Path] = []
    for mod in sources.get("modules", []):
        reg = mod.get("registry")
        if reg:
            paths.append(REPO / reg)
    wa = REPO / "platform/web_agent/config/registry.json"
    if wa.exists():
        paths.append(wa)
    return paths


def _dedupe_prompts(prompts: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in prompts:
        p = p.strip()
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _resolve_prompts(
    *,
    rel: str,
    iid: str,
    name: str,
    prompts: list[str],
    allow_id_map: bool,
) -> list[str]:
    if name in PROMPTS_BY_NAME:
        base = list(PROMPTS_BY_NAME[name])
    elif allow_id_map and iid in PROMPTS_BY_ID and not rel.startswith("workflow/"):
        base = list(PROMPTS_BY_ID[iid])
    else:
        base = list(prompts)
    filtered = [
        p
        for p in base
        if not HARDCODE_PROMPT_RE.search(p) and not VAGUE_PROMPT_RE.search(p)
    ]
    if not filtered:
        filtered = base
    return _dedupe_prompts([naturalize_prompt(p) for p in filtered])


def _update_prompts_on(obj: dict, *, rel: str, allow_id_map: bool) -> bool:
    prompts = obj.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        return False
    iid = str(obj.get("id", ""))
    name = str(obj.get("name", obj.get("title", "")))
    new_prompts = _resolve_prompts(
        rel=rel, iid=iid, name=name, prompts=prompts, allow_id_map=allow_id_map
    )
    if new_prompts != prompts:
        obj["prompts"] = new_prompts
        return True
    return False


def normalize_file(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = 0
    rel = str(path.relative_to(REPO))
    for item in data.get("items", []):
        if _update_prompts_on(item, rel=rel, allow_id_map=True):
            changed += 1
    for pb in data.get("playbooks", []):
        if _update_prompts_on(pb, rel=rel, allow_id_map=False):
            changed += 1
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    total = 0
    touched: list[str] = []
    for path in _registry_paths():
        n = normalize_file(path)
        if n:
            total += n
            touched.append(f"{path.relative_to(REPO)} ({n})")
    print(f"Updated {total} capabilities in {len(touched)} files")
    for line in touched:
        print(f"  {line}")
    if total:
        subprocess.run(
            [sys.executable, str(REPO / "platform/scripts/generate_catalog.py")],
            check=True,
            cwd=str(REPO),
        )
        for mod in load_sources().get("modules", []):
            reg = mod.get("registry", "")
            parts = Path(reg).parts
            if len(parts) >= 1:
                gen = REPO / parts[0] / "scripts" / "generate_index.py"
                if gen.exists():
                    subprocess.run([sys.executable, str(gen)], check=False, cwd=str(REPO))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
