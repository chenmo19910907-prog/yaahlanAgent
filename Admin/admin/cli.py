"""Yaahlan Admin CLI。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse

from .activity import parse_query_lottery_list_summary
from .app_store_review import (
    parse_app_store_review_version_summary,
    parse_update_app_store_review_version_summary,
)
from .client import admin_success, http_get_json, http_post_json
from .config import defaults
from .custom_gift import (
    gateway_success,
    parse_custom_gift_list_summary,
    parse_reset_custom_gift_upload_summary,
)
from .gift import mdp_gift_success, parse_query_gift_list_summary
from .prop import mdp_prop_success, parse_query_prop_info_summary
from .custom_prop import DEFAULT_PROP_TYPE, parse_reset_custom_prop_cooldown_summary
from .custom_vehicle import parse_reset_custom_vehicle_cooldown_summary
from .customer_service import (
    parse_change_cs_taking_order_summary,
    parse_cs_role_list,
    parse_query_cs_data_summary,
    parse_save_cs_data_summary,
)
from .env import load_local_env, load_online_env
from .family import parse_add_family_member_summary, parse_query_family_summary
from .guild import (
    anchor_success,
    parse_add_guild_member_summary,
    parse_anchor_id_list,
    parse_change_guild_member_summary,
    parse_query_trade_union_summary,
    parse_remove_guild_member_summary,
)
from .cancel_user import (
    assert_cancel_user_allowed,
    parse_cancel_user_summary,
    protected_phone_range_label,
)
from .gift import mdp_gift_success as mdp_user_admin_success
from .user import (
    parse_history_user_list_by_device_summary,
    parse_user_detail_summary,
    parse_user_feed_list_summary,
    parse_user_history_device_summary,
)
from .user_list import (
    build_query_user_profile_list_body,
    parse_query_user_profile_list_summary,
    parse_user_id_list,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Yaahlan Admin 后台接口本地调用")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("ADMIN_BASE_URL"),
        help="Admin 域名，默认 ADMIN_BASE_URL",
    )
    parser.add_argument("--timeout-ms", type=int, default=10000, help="HTTP 超时（毫秒）")
    parser.add_argument(
        "--线上环境",
        dest="online_env",
        action="store_true",
        help="使用线上 Admin（config.online.json + .env.online.local）；仅当用户提示词含「线上环境」时由 Agent 调用",
    )
    parser.add_argument("--dump-body", action="store_true", help="输出最终请求 body 到 stderr")

    src = parser.add_mutually_exclusive_group(required=False)
    src.add_argument("--payload-file", help="完整请求 JSON 文件")
    src.add_argument("--payload", help="完整请求 JSON 字符串")

    parser.add_argument("--query-user-id", help="查询用户详情 userId（queryUserDetail）")
    parser.add_argument(
        "--query-user-feed-list",
        action="store_true",
        help="查询用户动态列表（queryUserFeedList；需 --query-user-id）",
    )
    parser.add_argument("--feed-list-index", type=int, help="用户动态分页 index（默认 0）")
    parser.add_argument("--feed-list-count", type=int, help="用户动态每页条数 count（默认 20）")
    parser.add_argument(
        "--query-user-history-devices",
        action="store_true",
        help="查询用户历史登录设备列表（deviceHistory/queryUserHistoryDeviceList；需 --history-device-user-id）",
    )
    parser.add_argument("--history-device-user-id", help="历史设备查询 userId（配合 --query-user-history-devices）")
    parser.add_argument(
        "--query-device-history-users",
        action="store_true",
        help="查询设备历史登录账号列表（deviceHistory/queryHistoryUserListByDeviceId；需 --history-device-mmuidv3）",
    )
    parser.add_argument("--history-device-mmuidv3", help="历史账号查询设备 mmuidv3（配合 --query-device-history-users）")
    parser.add_argument("--history-device-page", type=int, help="设备历史列表页码 page（默认 1）")
    parser.add_argument("--history-device-page-size", type=int, help="设备历史列表每页条数 pageSize（默认 20）")
    parser.add_argument(
        "--query-prop-list",
        action="store_true",
        help="查询 MDP Nova 道具配置列表（propAdmin/queryPropInfo；可按 propId、名称、类型筛选）",
    )
    parser.add_argument("--prop-app-id", type=int, help="道具查询 appId（默认 2005=Yaahlan）")
    parser.add_argument("--prop-type-code", help="道具类型 propTypeCode（如 10043 头框）")
    parser.add_argument("--prop-name", help="道具名称 propName 模糊筛选")
    parser.add_argument("--prop-id", help="道具 ID propId 精确筛选")
    parser.add_argument("--prop-obtain-way-entry-id", help="获取方式 obtainWayEntryId")
    parser.add_argument("--prop-sync-prod-status", help="同步正式环境状态 syncProdStatus")
    parser.add_argument("--prop-identifier", help="标识符 identifier")
    parser.add_argument("--prop-page-no", type=int, help="道具列表页码 pageNo（默认 1）")
    parser.add_argument("--prop-page-size", type=int, help="道具列表每页条数 pageSize（默认 20）")
    parser.add_argument(
        "--query-gift-list",
        action="store_true",
        help="查询 MDP Nova 礼物列表（giftAdmin/queryGiftList；可按 baseId、名称筛选）",
    )
    parser.add_argument("--gift-app-id", type=int, help="礼物查询 appId（默认 2005=Yaahlan）")
    parser.add_argument("--gift-base-id", help="礼物 baseId 精确筛选")
    parser.add_argument("--gift-product-name", help="礼物名称模糊筛选 productName")
    parser.add_argument("--gift-type", help="礼物类型 giftType")
    parser.add_argument("--gift-sub-type", help="礼物子类型 giftSubType")
    parser.add_argument("--gift-status", help="礼物状态 giftStatus")
    parser.add_argument("--gift-effect-cate", help="礼物特效分类 giftEffectCate")
    parser.add_argument("--gift-create-source", help="创建来源 createSource")
    parser.add_argument("--gift-page-no", type=int, help="礼物列表页码 pageNo（默认 1）")
    parser.add_argument("--gift-page-size", type=int, help="礼物列表每页条数 pageSize（默认 20）")
    parser.add_argument(
        "--query-user-list",
        action="store_true",
        help="查询 MDP Nova 用户列表（userAdmin/queryUserProfileList；同 ops-admin 用户列表页）",
    )
    parser.add_argument("--user-list-app-id", type=int, help="用户列表 appId（默认 2005=Yaahlan）")
    parser.add_argument(
        "--user-list-user-ids",
        help="用户列表 userIdList，逗号/空格分隔（对应 ops-admin「用户ID」筛选）",
    )
    parser.add_argument("--user-list-nickname", help="用户列表昵称筛选")
    parser.add_argument("--user-list-phone", help="用户列表电话筛选（配合 --user-list-area-code）")
    parser.add_argument("--user-list-area-code", help="用户列表电话区号 areaCode")
    parser.add_argument("--user-list-device-id", help="用户列表设备 ID deviceId")
    parser.add_argument("--user-list-mmuidv3", help="用户列表 mmuidv3 筛选")
    parser.add_argument("--user-list-email", help="用户列表邮箱筛选")
    parser.add_argument("--user-list-area", help="用户列表大区 area（如 MENA）")
    parser.add_argument("--user-list-ban-status", help="用户列表用户状态 banStatus")
    parser.add_argument("--user-list-gender", help="用户列表性别 gender")
    parser.add_argument("--user-list-country-code", help="用户列表 IP 国家/地区 countryCode")
    parser.add_argument("--user-list-register-type", help="用户列表注册来源 registerType")
    parser.add_argument("--user-list-page-no", type=int, help="用户列表页码 pageNo（默认 1）")
    parser.add_argument("--user-list-page-size", type=int, help="用户列表每页条数 pageSize（默认 20）")
    parser.add_argument(
        "--cancel-user",
        action="store_true",
        help="注销用户账号（userAdmin/cancelUser；不可逆，须 --cancel-user-confirm）",
    )
    parser.add_argument("--cancel-user-id", help="注销账号 userId（配合 --cancel-user）")
    parser.add_argument("--cancel-user-app-id", type=int, help="注销 appId（默认 2005=Yaahlan）")
    parser.add_argument(
        "--cancel-user-confirm",
        action="store_true",
        help="二次确认注销（必须显式传入才会调用 cancelUser）",
    )
    parser.add_argument(
        "--query-custom-gift-list",
        action="store_true",
        help="查询 VIP5 定制礼物列表（getListConfig；返回 userId ↔ giftId）",
    )
    parser.add_argument(
        "--custom-gift-user-id",
        help="定制礼物列表：按 userId 过滤（配合 --query-custom-gift-list）",
    )
    parser.add_argument(
        "--custom-gift-per-page",
        type=int,
        help="定制礼物列表 perPage（默认 config.json vip5_custom_gift_list.defaultPerPage）",
    )
    parser.add_argument(
        "--reset-custom-gift-upload",
        action="store_true",
        help="重置用户定制礼物上传次数/过期时间（resetExpireTime；需 --custom-gift-reset-user-id）",
    )
    parser.add_argument(
        "--custom-gift-reset-user-id",
        help="重置定制礼物上传的用户 ID（配合 --reset-custom-gift-upload）",
    )
    parser.add_argument(
        "--reset-custom-vehicle-cooldown",
        action="store_true",
        help="重置用户定制座驾上传冷却（resetCoolDown；需 --custom-vehicle-remote-id）",
    )
    parser.add_argument(
        "--custom-vehicle-remote-id",
        help="重置定制座驾上传冷却的用户 ID（remoteId；配合 --reset-custom-vehicle-cooldown）",
    )
    parser.add_argument(
        "--reset-custom-prop-cooldown",
        action="store_true",
        help="重置用户定制道具上传冷却（resetCoolDownProp；需 --custom-prop-remote-id）",
    )
    parser.add_argument(
        "--custom-prop-remote-id",
        help="重置定制道具上传冷却的用户 ID（remoteId；配合 --reset-custom-prop-cooldown）",
    )
    parser.add_argument(
        "--custom-prop-type",
        help="定制道具类型 propType（默认 HEADER_FRAME，即头像框）",
    )
    parser.add_argument(
        "--add-family-member",
        action="store_true",
        help="增加家族成员（addFamilyMember；需 --family-id 与 --family-user-id）",
    )
    parser.add_argument("--family-id", help="家族 ID（增加成员或查询家族）")
    parser.add_argument("--family-user-id", help="要加入家族的用户 ID（配合 --add-family-member）")
    parser.add_argument(
        "--query-family",
        action="store_true",
        help="按家族 ID 或名称查询家族信息（queryFamilyByIdAndName）",
    )
    parser.add_argument(
        "--list-all-families",
        action="store_true",
        help="查询全部家族列表（getAllFamilyList；offset/limit 分页）",
    )
    parser.add_argument("--family-name", help="家族名称（配合 --query-family，可与 --family-id 组合）")
    parser.add_argument("--family-offset", type=int, help="家族查询分页 offset（默认 0）")
    parser.add_argument("--family-limit", type=int, help="家族查询分页 limit（默认 20）")
    parser.add_argument(
        "--add-guild-member",
        action="store_true",
        help="用户加入公会（addAnchor；需 --guild-user-id 与 --trade-id 或 --trade-union）",
    )
    parser.add_argument("--trade-id", help="公会 ID（tradeId）")
    parser.add_argument("--trade-union", help="公会名称（tradeUnion；可与 tradeId 二选一）")
    parser.add_argument("--guild-user-id", help="公会操作的用户 ID（加入时为 userIds；移除时为 anchorIdList，可逗号分隔多个）")
    parser.add_argument(
        "--remove-guild-member",
        action="store_true",
        help="用户移除公会（batchDeleteAnchor；需 --guild-user-id）",
    )
    parser.add_argument(
        "--change-guild-member",
        action="store_true",
        help="用户转移公会（batchAnchorChangeTradeUnion；需 --trade-union 与 --guild-user-id）",
    )
    parser.add_argument(
        "--query-guild",
        action="store_true",
        help="查询公会信息（tradeUnionPageList；可按 --guild-leader-id / --trade-id / --trade-union）",
    )
    parser.add_argument(
        "--guild-leader-id",
        help="公会长 userId（tradeUid；配合 --query-guild）",
    )
    parser.add_argument("--guild-area", help="公会查询大区 area（默认 MENA）")
    parser.add_argument("--guild-page", type=int, help="公会查询页码 page（默认 1）")
    parser.add_argument("--guild-page-size", type=int, help="公会查询 pageSize（默认 20）")
    parser.add_argument(
        "--query-cs-data",
        action="store_true",
        help="查询客服账号列表（queryCsData；可按 userId/role/enable/area 筛选）",
    )
    parser.add_argument(
        "--save-cs-data",
        action="store_true",
        help="新增/编辑客服账号（saveCsData；需 --cs-user-id）",
    )
    parser.add_argument(
        "--change-cs-taking-order",
        action="store_true",
        help="修改客服接单状态（changeTakingOrder；需 --cs-user-id 与 --cs-taking-order）",
    )
    parser.add_argument(
        "--cs-user-id",
        help="客服 userId（--save-cs-data 必填；--query-cs-data 可选筛选）",
    )
    parser.add_argument(
        "--cs-role-list",
        help="客服身份组合，逗号分隔 role ID（默认 1=VIP客服；2 游戏；3 语音房；4 Admin；5 公会通知审核；6 公会运营）",
    )
    parser.add_argument(
        "--cs-taking-order",
        type=int,
        help="是否接单 takingOrder（--save-cs-data；默认 1 接单；0 不接单）",
    )
    parser.add_argument(
        "--cs-opt-type",
        type=int,
        help="操作类型 optType（--save-cs-data；默认 1 创建；2 编辑）",
    )
    parser.add_argument("--cs-role", type=int, help="客服角色 role（默认 0=全部）")
    parser.add_argument(
        "--cs-enable",
        type=int,
        help="启用状态 enable（默认 2=全部；0 禁用；1 启用）",
    )
    parser.add_argument("--cs-area", help="大区 area（默认空=全部）")
    parser.add_argument("--cs-page-index", type=int, help="客服查询页码 pageIndex（默认 1）")
    parser.add_argument("--cs-page-size", type=int, help="客服查询 pageSize（默认 20）")
    parser.add_argument(
        "--query-activity-lottery-list",
        action="store_true",
        help="查询活动奖池配置列表（getLotteryList；body={}；可按 --lottery-id / --lottery-name 筛选）",
    )
    parser.add_argument("--lottery-id", help="奖池 ID lotteryId（配合 --query-activity-lottery-list）")
    parser.add_argument(
        "--lottery-name",
        help="奖池名称模糊筛选（配合 --query-activity-lottery-list，如 砸金蛋、Year3）",
    )
    parser.add_argument(
        "--query-app-store-review-version",
        action="store_true",
        help="查询 App Store 审核版本（getAppStoreReviewVersion；返回 iOS 版本与 Android versionCode）",
    )
    parser.add_argument(
        "--update-app-store-review-version",
        action="store_true",
        help="设置 App Store 审核版本（updateAppStoreReviewVersion；需 --ios-version）",
    )
    parser.add_argument(
        "--ios-version",
        help="iOS 审核版本号 iosVersion（配合 --update-app-store-review-version）",
    )
    parser.add_argument(
        "--android-version-code",
        help="Android versionCode（配合 --update-app-store-review-version；可选）",
    )
    parser.add_argument(
        "--app-name",
        help="应用名 appName（审核版本查询/设置；默认 yaahlan）",
    )
    parser.add_argument(
        "--output",
        choices=["summary", "json"],
        default="summary",
        help="输出格式：summary=摘要（默认）；json=完整响应",
    )
    return parser


def _resolve_base_url(args: argparse.Namespace) -> str:
    online = bool(getattr(args, "online_env", False))
    if online:
        base_url = (
            os.environ.get("ADMIN_ONLINE_BASE_URL")
            or defaults("api", online=True).get("baseUrl")
            or ""
        ).strip().rstrip("/")
        if not base_url:
            raise ValueError("缺少线上 Admin 域名：请设置 ADMIN_ONLINE_BASE_URL 或 Admin/config.online.json")
        return base_url

    base_url = (args.base_url or defaults("api").get("baseUrl") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 Admin 域名：请传 --base-url 或设置 ADMIN_BASE_URL")
    return base_url


def _resolve_yaahlan_auth(args: argparse.Namespace) -> str:
    return "yaahlan_online" if getattr(args, "online_env", False) else "yaahlan"


def _resolve_mdp_base_url(cfg: dict[str, object]) -> str:
    base_url = (
        os.environ.get("MDP_ADMIN_BASE_URL")
        or cfg.get("baseUrl")
        or ""
    ).strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 MDP Admin 域名：请设置 MDP_ADMIN_BASE_URL 或 config.json 中 query_gift_list.baseUrl")
    return base_url


def _resolve_gateway_base_url(cfg: dict[str, object]) -> str:
    base_url = (
        os.environ.get("ADMIN_GATEWAY_BASE_URL")
        or cfg.get("baseUrl")
        or ""
    ).strip().rstrip("/")
    if not base_url:
        raise ValueError("缺少 Gateway 域名：请设置 ADMIN_GATEWAY_BASE_URL 或 config.json 中对应 baseUrl")
    return base_url


def _resolve_query_prop_info_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("query_prop_info")
    base_url = _resolve_mdp_base_url(cfg)
    path = str(cfg.get("path", "/propAdmin/queryPropInfo"))

    app_id = args.prop_app_id
    if app_id is None:
        app_id = int(cfg.get("defaultAppId", 2005))
    page_no = args.prop_page_no
    if page_no is None:
        page_no = int(cfg.get("defaultPageNo", 1))
    page_size = args.prop_page_size
    if page_size is None:
        page_size = int(cfg.get("defaultPageSize", 20))
    if page_no <= 0:
        raise ValueError("prop-page-no 必须为正整数")
    if page_size <= 0:
        raise ValueError("prop-page-size 必须为正整数")

    identifier = args.prop_identifier
    if identifier is not None and str(identifier).strip() == "":
        identifier = None

    body: dict[str, object] = {
        "appId": app_id,
        "propTypeCode": str(args.prop_type_code or "").strip(),
        "propName": str(args.prop_name or "").strip(),
        "propId": str(args.prop_id or "").strip(),
        "obtainWayEntryId": str(args.prop_obtain_way_entry_id or "").strip(),
        "syncProdStatus": str(args.prop_sync_prod_status or "").strip(),
        "identifier": identifier,
        "pageNo": page_no,
        "pageSize": page_size,
    }
    return f"{base_url}{path}", body


def _resolve_query_gift_list_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("query_gift_list")
    base_url = _resolve_mdp_base_url(cfg)
    path = str(cfg.get("path", "/giftAdmin/queryGiftList"))

    app_id = args.gift_app_id
    if app_id is None:
        app_id = int(cfg.get("defaultAppId", 2005))
    page_no = args.gift_page_no
    if page_no is None:
        page_no = int(cfg.get("defaultPageNo", 1))
    page_size = args.gift_page_size
    if page_size is None:
        page_size = int(cfg.get("defaultPageSize", 20))
    if page_no <= 0:
        raise ValueError("gift-page-no 必须为正整数")
    if page_size <= 0:
        raise ValueError("gift-page-size 必须为正整数")

    body: dict[str, object] = {
        "appId": app_id,
        "baseId": str(args.gift_base_id or "").strip(),
        "createTimeBegin": "",
        "createTimeEnd": "",
        "giftType": str(args.gift_type or "").strip(),
        "productName": str(args.gift_product_name or "").strip(),
        "giftStatus": str(args.gift_status or "").strip(),
        "giftEffectCate": str(args.gift_effect_cate or "").strip(),
        "giftSubType": str(args.gift_sub_type or "").strip(),
        "createSource": str(args.gift_create_source or "").strip(),
        "pageSize": page_size,
        "pageNo": page_no,
    }
    return f"{base_url}{path}", body


def _resolve_query_user_profile_list_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("query_user_profile_list")
    base_url = _resolve_mdp_base_url(cfg)
    path = str(cfg.get("path", "/userAdmin/queryUserProfileList"))

    app_id = args.user_list_app_id
    if app_id is None:
        app_id = int(cfg.get("defaultAppId", 2005))
    page_no = args.user_list_page_no
    if page_no is None:
        page_no = int(cfg.get("defaultPageNo", 1))
    page_size = args.user_list_page_size
    if page_size is None:
        page_size = int(cfg.get("defaultPageSize", 20))

    body = build_query_user_profile_list_body(
        app_id=app_id,
        page_no=page_no,
        page_size=page_size,
        user_ids=parse_user_id_list(args.user_list_user_ids),
        nickname=args.user_list_nickname,
        phone=args.user_list_phone,
        area_code=args.user_list_area_code,
        device_id=args.user_list_device_id,
        mmuidv3=args.user_list_mmuidv3,
        email=args.user_list_email,
        area=args.user_list_area,
        ban_status=args.user_list_ban_status,
        gender=args.user_list_gender,
        country_code=args.user_list_country_code,
        register_type=args.user_list_register_type,
    )
    return f"{base_url}{path}", body


def _fetch_user_phone_for_cancel(args: argparse.Namespace, user_id: str) -> str | None:
    base_url = _resolve_base_url(args)
    path = str(defaults("query_user_detail").get("path", "/admin/user/queryUserDetail"))
    url = f"{base_url}{path}"
    resp = http_post_json(
        url,
        {"userId": user_id},
        timeout_s=max(args.timeout_ms, 1000) / 1000.0,
        auth=_resolve_yaahlan_auth(args),
    )
    if not admin_success(resp.get("ec")):
        raise ValueError(
            f"注销前查询用户详情失败: ec={resp.get('ec')}, em={resp.get('em')}"
        )
    summary = parse_user_detail_summary(resp.get("data"))
    phone = summary.get("phone")
    return str(phone).strip() if phone is not None and str(phone).strip() else None


def _lookup_protected_user_ids_via_moa(cfg: dict[str, object]) -> set[str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    moa_entry = os.path.join(repo_root, "MOA", "moa_execute.py")
    template = os.path.join(repo_root, "MOA", "templates", "用户-按手机号查userId.json")
    if not os.path.isfile(moa_entry) or not os.path.isfile(template):
        raise ValueError("缺少 MOA 登录态查询脚本，无法校验受保护测试号段")

    min_phone = int(cfg.get("protectedPhoneMin", 13311111111))
    max_phone = int(cfg.get("protectedPhoneMax", 13311111130))
    protected: set[str] = set()
    for digits in range(min_phone, max_phone + 1):
        phone = str(digits)
        proc = subprocess.run(
            [
                sys.executable,
                moa_entry,
                "--payload-file",
                template,
                "--query-user-by-phone",
                phone,
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        if data.get("registered") and data.get("userId"):
            protected.add(str(data["userId"]).strip())
    return protected


def _assert_cancel_user_not_protected(
    args: argparse.Namespace,
    *,
    user_id: str,
    cfg: dict[str, object],
) -> None:
    phone = _fetch_user_phone_for_cancel(args, user_id)
    if phone:
        assert_cancel_user_allowed(
            user_id=user_id,
            phone=phone,
            min_phone=int(cfg.get("protectedPhoneMin", 13311111111)),
            max_phone=int(cfg.get("protectedPhoneMax", 13311111130)),
        )
        return

    protected_ids = _lookup_protected_user_ids_via_moa(cfg)
    if user_id in protected_ids:
        label = protected_phone_range_label(
            min_phone=int(cfg.get("protectedPhoneMin", 13311111111)),
            max_phone=int(cfg.get("protectedPhoneMax", 13311111130)),
        )
        raise ValueError(
            f"禁止注销：userId {user_id} 属于受保护测试号段 {label}（MOA 反查）"
        )


def _resolve_cancel_user_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("cancel_user")
    user_id = str(args.cancel_user_id or "").strip()
    if not user_id:
        raise ValueError("必须提供 --cancel-user-id")

    if not args.cancel_user_confirm:
        protected = protected_phone_range_label(
            min_phone=int(cfg.get("protectedPhoneMin", 13311111111)),
            max_phone=int(cfg.get("protectedPhoneMax", 13311111130)),
        )
        raise ValueError(
            f"注销账号为不可逆操作。请先核对 userId={user_id}，"
            f"确认不在受保护测试号段 {protected} 后追加 --cancel-user-confirm 执行。"
        )

    _assert_cancel_user_not_protected(args, user_id=user_id, cfg=cfg)

    base_url = _resolve_mdp_base_url(cfg)
    path = str(cfg.get("path", "/userAdmin/cancelUser"))
    app_id = args.cancel_user_app_id
    if app_id is None:
        app_id = int(cfg.get("defaultAppId", 2005))

    body: dict[str, object] = {
        "userId": user_id,
        "appId": app_id,
    }
    return f"{base_url}{path}", body


def _resolve_custom_gift_list_url(args: argparse.Namespace) -> str:
    cfg = defaults("vip5_custom_gift_list")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/vip5UserConfig/getListConfig"))
    per_page = args.custom_gift_per_page
    if per_page is None:
        per_page = int(cfg.get("defaultPerPage", 100))
    if per_page <= 0:
        raise ValueError("custom_gift_per_page 必须为正整数")
    query = urllib.parse.urlencode({"perPage": per_page})
    return f"{base_url}{path}?{query}"


def _load_body(args: argparse.Namespace) -> dict[str, object]:
    if args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            body = json.load(f)
    elif args.payload:
        body = json.loads(args.payload)
    else:
        body = {}

    if not isinstance(body, dict):
        raise ValueError("请求 body 必须是 JSON object")
    return body


def _resolve_query_family_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    family_id = str(args.family_id or "").strip()
    family_name = str(args.family_name or "").strip()
    if not family_id and not family_name:
        raise ValueError("查询家族时至少提供 --family-id 或 --family-name 之一")

    cfg = defaults("query_family")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/family/queryFamilyByIdAndName"))
    offset = args.family_offset
    if offset is None:
        offset = int(cfg.get("defaultOffset", 0))
    limit = args.family_limit
    if limit is None:
        limit = int(cfg.get("defaultLimit", 20))
    if offset < 0:
        raise ValueError("family_offset 不能为负数")
    if limit <= 0:
        raise ValueError("family_limit 必须为正整数")

    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "familyName": family_name,
        "familyId": family_id,
        "offset": offset,
        "limit": limit,
    }
    return url, body


def _resolve_list_all_families_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("list_all_families")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/family/getAllFamilyList"))
    offset = args.family_offset
    if offset is None:
        offset = int(cfg.get("defaultOffset", 0))
    limit = args.family_limit
    if limit is None:
        limit = int(cfg.get("defaultLimit", 20))
    if offset < 0:
        raise ValueError("family_offset 不能为负数")
    if limit <= 0:
        raise ValueError("family_limit 必须为正整数")

    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "offset": offset,
        "limit": limit,
    }
    return url, body


def _resolve_query_guild_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    trade_id = str(args.trade_id or "").strip()
    trade_name = str(args.trade_union or "").strip()
    trade_uid = str(args.guild_leader_id or "").strip()
    if not trade_id and not trade_name and not trade_uid:
        raise ValueError("查询公会时至少提供 --guild-leader-id、--trade-id 或 --trade-union 之一")

    cfg = defaults("query_guild")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/anchor/tradeUnionList/tradeUnionPageList"))
    page = args.guild_page if args.guild_page is not None else int(cfg.get("defaultPage", 1))
    page_size = args.guild_page_size if args.guild_page_size is not None else int(cfg.get("defaultPageSize", 20))
    area = str(args.guild_area or cfg.get("defaultArea") or "MENA").strip()
    if page <= 0:
        raise ValueError("guild_page 必须为正整数")
    if page_size <= 0:
        raise ValueError("guild_page_size 必须为正整数")

    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "tradeName": trade_name,
        "tradeId": trade_id,
        "tradeUid": trade_uid,
        "page": page,
        "pageSize": page_size,
        "area": area,
    }
    return url, body


def _resolve_query_cs_data_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("query_cs_data")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/customerservice/queryCsData"))
    page_index = args.cs_page_index
    if page_index is None:
        page_index = int(cfg.get("defaultPageIndex", 1))
    page_size = args.cs_page_size
    if page_size is None:
        page_size = int(cfg.get("defaultPageSize", 20))
    role = args.cs_role if args.cs_role is not None else int(cfg.get("defaultRole", 0))
    enable = args.cs_enable if args.cs_enable is not None else int(cfg.get("defaultEnable", 2))
    area = str(args.cs_area if args.cs_area is not None else cfg.get("defaultArea") or "").strip()
    if page_index <= 0:
        raise ValueError("cs_page_index 必须为正整数")
    if page_size <= 0:
        raise ValueError("cs_page_size 必须为正整数")

    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "userId": str(args.cs_user_id or "").strip(),
        "role": role,
        "enable": enable,
        "pageIndex": page_index,
        "pageSize": page_size,
        "area": area,
    }
    return url, body


def _resolve_save_cs_data_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    user_id = str(args.cs_user_id or "").strip()
    if not user_id:
        raise ValueError("save-cs-data 必须提供 --cs-user-id")

    cfg = defaults("save_cs_data")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/customerservice/saveCsData"))
    default_roles = cfg.get("defaultRoleList")
    if not isinstance(default_roles, list):
        default_roles = [1]
    role_raw = str(args.cs_role_list or ",".join(str(role) for role in default_roles)).strip()
    role_list = parse_cs_role_list(role_raw)
    enable = args.cs_enable if args.cs_enable is not None else int(cfg.get("defaultEnable", 1))
    taking_order = (
        args.cs_taking_order
        if args.cs_taking_order is not None
        else int(cfg.get("defaultTakingOrder", 1))
    )
    opt_type = args.cs_opt_type if args.cs_opt_type is not None else int(cfg.get("defaultOptType", 1))
    if enable not in (0, 1):
        raise ValueError("cs_enable 仅支持 0（禁用）或 1（启用）")
    if taking_order not in (0, 1):
        raise ValueError("cs_taking_order 仅支持 0（不接单）或 1（接单）")
    if opt_type not in (1, 2):
        raise ValueError("cs_opt_type 仅支持 1（创建）或 2（编辑）")

    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "userId": user_id,
        "roleList": role_list,
        "enable": enable,
        "takingOrder": taking_order,
        "optType": opt_type,
    }
    return url, body


def _resolve_query_activity_lottery_list_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    cfg = defaults("query_activity_lottery_list")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/activity/getLotteryList"))
    url = f"{base_url}{path}"
    return url, {}


def _resolve_change_cs_taking_order_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    user_id = str(args.cs_user_id or "").strip()
    if not user_id:
        raise ValueError("change-cs-taking-order 必须提供 --cs-user-id")
    if args.cs_taking_order is None:
        raise ValueError("change-cs-taking-order 必须提供 --cs-taking-order（0 不接单；1 接单）")
    taking_order = int(args.cs_taking_order)
    if taking_order not in (0, 1):
        raise ValueError("cs_taking_order 仅支持 0（不接单）或 1（接单）")

    cfg = defaults("change_cs_taking_order")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/customerservice/changeTakingOrder"))
    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "userId": user_id,
        "takingOrder": taking_order,
    }
    return url, body


def _resolve_app_store_app_name(args: argparse.Namespace, cfg: dict[str, object]) -> str:
    app_name = str(args.app_name or cfg.get("defaultAppName") or "yaahlan").strip()
    if not app_name:
        raise ValueError("app-name 不能为空")
    return app_name


def _resolve_query_app_store_review_version_request(
    args: argparse.Namespace,
) -> tuple[str, dict[str, str]]:
    cfg = defaults("query_app_store_review_version")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/pangu/getAppStoreReviewVersion"))
    app_name = _resolve_app_store_app_name(args, cfg)
    url = f"{base_url}{path}"
    body = {"appName": app_name}
    return url, body


def _resolve_update_app_store_review_version_request(
    args: argparse.Namespace,
) -> tuple[str, dict[str, str]]:
    ios_version = str(args.ios_version or "").strip()
    if not ios_version:
        raise ValueError("设置审核版本时必须提供 --ios-version")

    cfg = defaults("update_app_store_review_version")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/pangu/updateAppStoreReviewVersion"))
    app_name = _resolve_app_store_app_name(args, cfg)
    url = f"{base_url}{path}"
    body: dict[str, str] = {
        "appName": app_name,
        "iosVersion": ios_version,
    }
    android_version_code = str(args.android_version_code or "").strip()
    if android_version_code:
        body["androidVersionCode"] = android_version_code
    return url, body


def _resolve_add_guild_member_request(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    trade_id = str(args.trade_id or "").strip()
    trade_union = str(args.trade_union or "").strip()
    user_ids = str(args.guild_user_id or "").strip()
    if not user_ids:
        raise ValueError("必须提供 --guild-user-id")
    if not trade_id and not trade_union:
        raise ValueError("加入公会时至少提供 --trade-id 或 --trade-union 之一")

    cfg = defaults("add_guild_member")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/anchor/addAnchor/addAnchor"))
    url = f"{base_url}{path}"
    body = {
        "tradeId": trade_id,
        "tradeUnion": trade_union,
        "userIds": user_ids,
    }
    return url, body


def _resolve_remove_guild_member_request(args: argparse.Namespace) -> tuple[str, dict[str, list[str]]]:
    user_ids = str(args.guild_user_id or "").strip()
    if not user_ids:
        raise ValueError("必须提供 --guild-user-id")

    cfg = defaults("remove_guild_member")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/anchor-opt/batchDeleteAnchor"))
    url = f"{base_url}{path}"
    body = {"anchorIdList": parse_anchor_id_list(user_ids)}
    return url, body


def _resolve_change_guild_member_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    trade_union = str(args.trade_union or "").strip()
    user_ids = str(args.guild_user_id or "").strip()
    if not trade_union:
        raise ValueError("转移公会时必须提供 --trade-union")
    if not user_ids:
        raise ValueError("必须提供 --guild-user-id")

    cfg = defaults("change_guild_member")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/cms/anchor-opt/batchAnchorChangeTradeUnion"))
    url = f"{base_url}{path}"
    body: dict[str, object] = {
        "tradeUnion": trade_union,
        "userIdSet": parse_anchor_id_list(user_ids),
    }
    return url, body


def _resolve_add_family_member_request(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    family_id = str(args.family_id or "").strip()
    user_id = str(args.family_user_id or "").strip()
    if not family_id:
        raise ValueError("必须提供 --family-id")
    if not user_id:
        raise ValueError("必须提供 --family-user-id")

    cfg = defaults("add_family_member")
    base_url = _resolve_gateway_base_url(cfg)
    path = str(cfg.get("path", "/yaahlan/backend/family/addFamilyMember"))
    url = f"{base_url}{path}"
    body = {"familyId": family_id, "userId": user_id}
    return url, body


def _resolve_reset_custom_gift_upload_request(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    user_id = str(args.custom_gift_reset_user_id or "").strip()
    if not user_id:
        raise ValueError("必须提供 --custom-gift-reset-user-id")

    base_url = _resolve_base_url(args)
    path = str(defaults("reset_custom_gift_upload").get("path", "/mts/components/resetExpireTime"))
    url = f"{base_url}{path}"
    body = {"userId": user_id}
    return url, body


def _resolve_reset_custom_vehicle_cooldown_request(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    remote_id = str(args.custom_vehicle_remote_id or "").strip()
    if not remote_id:
        raise ValueError("必须提供 --custom-vehicle-remote-id")

    base_url = _resolve_base_url(args)
    path = str(defaults("reset_custom_vehicle_cooldown").get("path", "/backend/custom/resetCoolDown"))
    url = f"{base_url}{path}"
    body = {"remoteId": remote_id}
    return url, body


def _resolve_reset_custom_prop_cooldown_request(args: argparse.Namespace) -> tuple[str, dict[str, str]]:
    remote_id = str(args.custom_prop_remote_id or "").strip()
    if not remote_id:
        raise ValueError("必须提供 --custom-prop-remote-id")

    cfg = defaults("reset_custom_prop_cooldown")
    prop_type = str(args.custom_prop_type or cfg.get("defaultPropType") or DEFAULT_PROP_TYPE).strip()
    if not prop_type:
        raise ValueError("custom-prop-type 不能为空")

    base_url = _resolve_base_url(args)
    path = str(cfg.get("path", "/backend/custom/resetCoolDownProp"))
    url = f"{base_url}{path}"
    body = {"remoteId": remote_id, "propType": prop_type}
    return url, body


def _resolve_device_history_pagination(args: argparse.Namespace, cfg_key: str) -> tuple[int, int]:
    cfg = defaults(cfg_key)
    page = args.history_device_page
    if page is None:
        page = int(cfg.get("defaultPage", 1))
    page_size = args.history_device_page_size
    if page_size is None:
        page_size = int(cfg.get("defaultPageSize", 20))
    if page <= 0:
        raise ValueError("history-device-page 必须为正整数")
    if page_size <= 0:
        raise ValueError("history-device-page-size 必须为正整数")
    return page, page_size


def _resolve_query_history_user_list_by_device_request(
    args: argparse.Namespace,
) -> tuple[str, dict[str, object]]:
    mmuidv3 = str(args.history_device_mmuidv3 or "").strip()
    if not mmuidv3:
        raise ValueError("必须提供 --history-device-mmuidv3")

    page, page_size = _resolve_device_history_pagination(args, "query_history_user_list_by_device_id")
    cfg = defaults("query_history_user_list_by_device_id")
    base_url = _resolve_base_url(args)
    path = str(cfg.get("path", "/yaahlan/backend/deviceHistory/queryHistoryUserListByDeviceId"))
    url = f"{base_url}{path}"
    body = {"mmuidv3": mmuidv3, "page": page, "pageSize": page_size}
    return url, body


def _resolve_query_user_history_device_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    user_id = str(args.history_device_user_id or "").strip()
    if not user_id:
        raise ValueError("必须提供 --history-device-user-id")

    page, page_size = _resolve_device_history_pagination(args, "query_user_history_device_list")
    cfg = defaults("query_user_history_device_list")
    base_url = _resolve_base_url(args)
    path = str(cfg.get("path", "/yaahlan/backend/deviceHistory/queryUserHistoryDeviceList"))
    url = f"{base_url}{path}"
    body = {"userId": user_id, "page": page, "pageSize": page_size}
    return url, body


def _resolve_query_user_feed_list_request(args: argparse.Namespace) -> tuple[str, dict[str, object]]:
    user_id = str(args.query_user_id or "").strip()
    if not user_id:
        raise ValueError("必须提供 --query-user-id")

    cfg = defaults("query_user_feed_list")
    index = args.feed_list_index
    if index is None:
        index = int(cfg.get("defaultIndex", 0))
    count = args.feed_list_count
    if count is None:
        count = int(cfg.get("defaultCount", 20))
    if index < 0:
        raise ValueError("feed-list-index 不能为负数")
    if count <= 0:
        raise ValueError("feed-list-count 必须为正整数")

    base_url = _resolve_base_url(args)
    path = str(cfg.get("path", "/admin/user/queryUserFeedList"))
    url = f"{base_url}{path}"
    body = {"userId": user_id, "index": index, "count": count}
    return url, body


def _apply_query_user_detail(args: argparse.Namespace, body: dict[str, object]) -> tuple[str, dict[str, object]]:
    user_id = str(args.query_user_id).strip()
    if not user_id:
        raise ValueError("query_user_id 不能为空")
    online = bool(getattr(args, "online_env", False))
    path = str(
        defaults("query_user_detail", online=online).get("path", "/admin/user/queryUserDetail")
    )
    return path, {"userId": user_id}


def main() -> int:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_local_env(base_dir)

    args = build_parser().parse_args()
    if getattr(args, "online_env", False):
        load_online_env(base_dir)
    try:
        if getattr(args, "online_env", False) and args.query_user_id is None:
            raise ValueError("线上环境当前仅支持 --query-user-id（须用户提示词含「线上环境」）")
        if args.query_prop_list:
            url, body = _resolve_query_prop_info_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(
                url,
                body,
                timeout_s=max(args.timeout_ms, 1000) / 1000.0,
                auth="mdp_nova",
            )
        elif args.query_gift_list:
            url, body = _resolve_query_gift_list_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(
                url,
                body,
                timeout_s=max(args.timeout_ms, 1000) / 1000.0,
                auth="mdp_nova",
            )
        elif args.query_user_list:
            url, body = _resolve_query_user_profile_list_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(
                url,
                body,
                timeout_s=max(args.timeout_ms, 1000) / 1000.0,
                auth="mdp_nova",
            )
        elif args.cancel_user:
            url, body = _resolve_cancel_user_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(
                url,
                body,
                timeout_s=max(args.timeout_ms, 1000) / 1000.0,
                auth="mdp_nova",
            )
        elif args.query_custom_gift_list:
            url = _resolve_custom_gift_list_url(args)
            if args.dump_body:
                print(f"GET {url}", file=sys.stderr)
            resp = http_get_json(url, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.add_family_member:
            url, body = _resolve_add_family_member_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_family:
            url, body = _resolve_query_family_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.list_all_families:
            url, body = _resolve_list_all_families_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.add_guild_member:
            url, body = _resolve_add_guild_member_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.remove_guild_member:
            url, body = _resolve_remove_guild_member_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.change_guild_member:
            url, body = _resolve_change_guild_member_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_guild:
            url, body = _resolve_query_guild_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_cs_data:
            url, body = _resolve_query_cs_data_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.save_cs_data:
            url, body = _resolve_save_cs_data_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.change_cs_taking_order:
            url, body = _resolve_change_cs_taking_order_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_activity_lottery_list:
            url, body = _resolve_query_activity_lottery_list_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_app_store_review_version:
            url, body = _resolve_query_app_store_review_version_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.update_app_store_review_version:
            url, body = _resolve_update_app_store_review_version_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.reset_custom_gift_upload:
            url, body = _resolve_reset_custom_gift_upload_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.reset_custom_vehicle_cooldown:
            url, body = _resolve_reset_custom_vehicle_cooldown_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.reset_custom_prop_cooldown:
            url, body = _resolve_reset_custom_prop_cooldown_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_device_history_users:
            url, body = _resolve_query_history_user_list_by_device_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_user_history_devices:
            url, body = _resolve_query_user_history_device_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_user_feed_list:
            url, body = _resolve_query_user_feed_list_request(args)
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
        elif args.query_user_id is not None:
            base_url = _resolve_base_url(args)
            path, body = _apply_query_user_detail(args, {})
            url = f"{base_url}{path}"
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(
                url,
                body,
                timeout_s=max(args.timeout_ms, 1000) / 1000.0,
                auth=_resolve_yaahlan_auth(args),
            )
        else:
            base_url = _resolve_base_url(args)
            body = _load_body(args)
            path = str(defaults("query_user_detail").get("path", "/admin/user/queryUserDetail"))
            url = f"{base_url}{path}"
            if args.dump_body:
                print(f"POST {url}", file=sys.stderr)
                print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            resp = http_post_json(url, body, timeout_s=max(args.timeout_ms, 1000) / 1000.0)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as e:
        print(f"执行失败: {e}", file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    elif args.query_prop_list:
        if not mdp_prop_success(resp.get("ec")):
            print(f"MDP 道具后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_prop_info_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_gift_list:
        if not mdp_gift_success(resp.get("ec")):
            print(f"MDP 礼物后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_gift_list_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_user_list:
        if not mdp_user_admin_success(resp.get("ec")):
            print(f"MDP 用户后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_user_profile_list_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.cancel_user:
        if not mdp_user_admin_success(resp.get("ec")):
            print(f"MDP 用户后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_cancel_user_summary(resp, user_id=str(args.cancel_user_id).strip())
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_custom_gift_list:
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_custom_gift_list_summary(
            resp.get("data"),
            filter_user_id=args.custom_gift_user_id,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.add_family_member:
        summary = parse_add_family_member_summary(
            resp,
            family_id=str(args.family_id).strip(),
            user_id=str(args.family_user_id).strip(),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_family or args.list_all_families:
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_family_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.add_guild_member:
        summary = parse_add_guild_member_summary(
            resp,
            trade_id=str(args.trade_id or "").strip(),
            trade_union=str(args.trade_union or "").strip(),
            user_ids=str(args.guild_user_id or "").strip(),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.remove_guild_member:
        summary = parse_remove_guild_member_summary(
            resp,
            anchor_id_list=parse_anchor_id_list(str(args.guild_user_id or "").strip()),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.change_guild_member:
        summary = parse_change_guild_member_summary(
            resp,
            trade_union=str(args.trade_union or "").strip(),
            user_id_set=parse_anchor_id_list(str(args.guild_user_id or "").strip()),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_guild:
        if not anchor_success(resp):
            print(f"公会接口返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_trade_union_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_cs_data:
        if not anchor_success(resp):
            print(f"客服接口返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_cs_data_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_activity_lottery_list:
        if not anchor_success(resp):
            print(f"活动奖池接口返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_query_lottery_list_summary(
            resp.get("data"),
            lottery_id=str(args.lottery_id or "").strip() or None,
            lottery_name=str(args.lottery_name or "").strip() or None,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.save_cs_data:
        cfg = defaults("save_cs_data")
        default_roles = cfg.get("defaultRoleList")
        if not isinstance(default_roles, list):
            default_roles = [1]
        role_list = parse_cs_role_list(
            str(args.cs_role_list or ",".join(str(role) for role in default_roles)).strip()
        )
        enable = args.cs_enable if args.cs_enable is not None else int(cfg.get("defaultEnable", 1))
        taking_order = (
            args.cs_taking_order
            if args.cs_taking_order is not None
            else int(cfg.get("defaultTakingOrder", 1))
        )
        opt_type = args.cs_opt_type if args.cs_opt_type is not None else int(cfg.get("defaultOptType", 1))
        summary = parse_save_cs_data_summary(
            resp,
            user_id=str(args.cs_user_id).strip(),
            role_list=role_list,
            enable=enable,
            taking_order=taking_order,
            opt_type=opt_type,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.change_cs_taking_order:
        summary = parse_change_cs_taking_order_summary(
            resp,
            user_id=str(args.cs_user_id).strip(),
            taking_order=int(args.cs_taking_order),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_app_store_review_version:
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_app_store_review_version_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.update_app_store_review_version:
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        android_version_code = str(args.android_version_code or "").strip() or None
        summary = parse_update_app_store_review_version_summary(
            resp,
            app_name=_resolve_app_store_app_name(args, defaults("update_app_store_review_version")),
            ios_version=str(args.ios_version).strip(),
            android_version_code=android_version_code,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.reset_custom_gift_upload:
        summary = parse_reset_custom_gift_upload_summary(
            resp,
            user_id=str(args.custom_gift_reset_user_id).strip(),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.reset_custom_vehicle_cooldown:
        summary = parse_reset_custom_vehicle_cooldown_summary(
            resp,
            remote_id=str(args.custom_vehicle_remote_id).strip(),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.reset_custom_prop_cooldown:
        prop_cfg = defaults("reset_custom_prop_cooldown")
        prop_type = str(
            args.custom_prop_type or prop_cfg.get("defaultPropType") or DEFAULT_PROP_TYPE
        ).strip()
        summary = parse_reset_custom_prop_cooldown_summary(
            resp,
            remote_id=str(args.custom_prop_remote_id).strip(),
            prop_type=prop_type,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_device_history_users:
        if not admin_success(resp.get("ec")):
            print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_history_user_list_by_device_summary(resp.get("data"))
        summary["mmuidv3"] = str(args.history_device_mmuidv3).strip()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_user_history_devices:
        if not admin_success(resp.get("ec")):
            print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_user_history_device_summary(resp.get("data"))
        summary["userId"] = str(args.history_device_user_id).strip()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_user_feed_list:
        if not admin_success(resp.get("ec")):
            print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_user_feed_list_summary(resp.get("data"))
        summary["userId"] = str(args.query_user_id).strip()
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.query_user_id is not None:
        if not admin_success(resp.get("ec")):
            print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
            return 3
        summary = parse_user_detail_summary(resp.get("data"))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(resp, ensure_ascii=False, indent=2))

    if args.query_prop_list:
        if not mdp_prop_success(resp.get("ec")):
            print(f"MDP 道具后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            return 3
    elif args.query_gift_list:
        if not mdp_gift_success(resp.get("ec")):
            print(f"MDP 礼物后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            return 3
    elif args.query_user_list:
        if not mdp_user_admin_success(resp.get("ec")):
            print(f"MDP 用户后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            return 3
    elif args.cancel_user:
        if not mdp_user_admin_success(resp.get("ec")):
            print(f"MDP 用户后台返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            return 3
    elif (
        args.query_custom_gift_list
        or args.add_family_member
        or args.query_family
        or args.list_all_families
        or args.query_app_store_review_version
        or args.update_app_store_review_version
    ):
        if not gateway_success(resp.get("status")):
            print(f"Gateway 返回失败: status={resp.get('status')}, msg={resp.get('msg')}", file=sys.stderr)
            return 3
    elif args.add_guild_member or args.remove_guild_member or args.change_guild_member or args.query_guild or args.query_cs_data or args.save_cs_data or args.change_cs_taking_order or args.query_activity_lottery_list:
        if not anchor_success(resp):
            print(f"公会接口返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            return 3
    elif (
        args.reset_custom_gift_upload
        or args.reset_custom_vehicle_cooldown
        or args.reset_custom_prop_cooldown
        or args.query_device_history_users
        or args.query_user_history_devices
        or args.query_user_feed_list
        or args.query_user_id is not None
    ):
        if not admin_success(resp.get("ec")):
            print(f"Admin 返回失败: ec={resp.get('ec')}, em={resp.get('em')}", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
