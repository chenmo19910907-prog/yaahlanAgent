#!/usr/bin/env python3
"""web_moa_call_log 单测：合并批量、倒序列表。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(WEB_AGENT_DIR))

from web_moa_call_log import (  # noqa: E402
    _dedupe_moa_and_agent_turn_shadow,
    _reattribute_moa_entries_in_window,
    _extract_account_hint,
    _load_entries,
    _operation_label,
    _save_entries,
    beautify_account_summary,
    compose_source_interface_display,
    format_account_summary_display,
    beautify_params_summary,
    extract_moa_call_details_from_assistant,
    extract_params_summary_from_payload,
    finalize_dingtalk_call_log,
    is_ephemeral_audit_user,
    list_moa_call_entries,
    purge_ephemeral_audit_entries,
    record_moa_call,
    record_tool_call,
    build_semantic_operation_summary,
    collapse_batch_params_summary,
    format_operation_display,
    resolve_operation_display,
)


class WebMoaCallLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "moa_call_log.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _patch_log(self):
        return patch("web_moa_call_log.LOG_PATH", self.log_path)

    def test_merge_same_run_and_operation(self) -> None:
        payload = {"url": "/service/foo", "method": "bar", "params": []}
        ok_resp = {"ec": 200, "result": {"ec": 0}}
        fail_resp = {"ec": 200, "result": {"ec": 500}}
        with self._patch_log():
            record_moa_call(
                payload=payload,
                response=ok_resp,
                run_id="run1",
                operator_staff_id="s1",
                operator_name="测试员",
            )
            record_moa_call(
                payload=payload,
                response=ok_resp,
                run_id="run1",
                operator_name="测试员",
            )
            record_moa_call(
                payload=payload,
                response=fail_resp,
                run_id="run1",
                operator_name="测试员",
            )
            payload2 = list_moa_call_entries(limit=10)
        self.assertEqual(payload2["total"], 1)
        entry = payload2["entries"][0]
        self.assertEqual(entry["callCount"], 3)
        self.assertEqual(entry["successCount"], 2)
        self.assertEqual(entry["failCount"], 1)
        self.assertIn("成功 2/3", entry["resultSummary"])

    def test_vip_params_use_semantic_names(self) -> None:
        payload = {
            "method": "addVipValue",
            "params": [
                {"title": "参数1", "name": "1", "value": "100465989", "type": "string"},
                {"title": "参数2", "name": "2", "value": "1", "type": "int"},
            ],
        }
        summary = extract_params_summary_from_payload(payload)
        self.assertIn("userId=100465989", summary)
        self.assertIn("value=1", summary)
        self.assertNotIn("1=100465989", summary)

    def test_semantic_operation_summary(self) -> None:
        self.assertEqual(
            build_semantic_operation_summary(
                "queryLoginStatusV2",
                "loginType=MOBILE，thirdUid=13311111111，areaCode=86",
            ),
            "查询手机号 13311111111 对应 userId",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "addVipValue",
                "userId=100465989，value=1",
            ),
            "用户 100465989 增加 1 VIP经验值",
        )
        self.assertEqual(
            format_operation_display(
                "用户-按手机号查userId",
                method="queryLoginStatusV2",
                params_summary="thirdUid=13311111112，areaCode=86",
            ),
            "查询手机号 13311111112 对应 userId",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "provideDiamond",
                "userId=100465989，num=100",
                account_summary="100465989 等 5 个账号",
                call_count=5,
            ),
            "100465989 等 5 个账号各发放 100 钻石",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "provideDiamond",
                "每账号 num=100（共 5 个账号，不逐一列出）",
                account_summary="100465989 等 5 个账号",
                call_count=5,
            ),
            "100465989 等 5 个账号各发放 100 钻石",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "addPackageGift",
                'userId=100465989，giftDetails=[{"baseProductId":"2005001494","productNum":1}]',
                account_summary="100465989 等 5 个账号",
                call_count=5,
            ),
            "100465989 等 5 个账号各下发 1 个背包礼物",
        )
        self.assertEqual(
            _operation_label(
                payload_file="MOA/templates/背包礼物-下发.json",
                service_url="/service/voga-base-service-middle-gift-stage",
                method="addPackageGift",
            ),
            "背包礼物-下发",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "queryUserAccount",
                "1=100486506",
                account_summary="100486506",
            ),
            "用户 100486506 查询钻石余额",
        )
        self.assertEqual(
            format_operation_display(
                "钻石-查询余额",
                method="queryUserAccount",
                params_summary="1=100465989（共 3 个账号，不逐一列出）",
                account_summary="100277713 等 3 个账号",
                call_count=3,
            ),
            "100277713 等 3 个账号 查询钻石余额",
        )
        collapsed = collapse_batch_params_summary(
            "userId=100465989，num=100；userId=100486375，num=100",
            method="provideDiamond",
            call_count=100,
            account_summary="100465989 等 100 个账号",
        )
        self.assertEqual(collapsed, "userId=100465989，num=100")
        self.assertNotIn("100486375", collapsed)
        self.assertNotIn("不逐一列出", collapsed)
        dirty = "userId=100000001（同账号查询 4 次）（同账号查询 4 次）"
        once = collapse_batch_params_summary(
            dirty,
            method="getVipInfo",
            call_count=4,
            account_summary="100000001",
        )
        self.assertEqual(once, "userId=100000001（同账号查询 4 次）")
        self.assertEqual(
            format_operation_display(
                "",
                method="getVipInfo",
                params_summary=once,
                account_summary="100000001",
                call_count=4,
            ),
            "查询用户 100000001 VIP经验值（4 次）",
        )

    def test_get_vip_info_operation_label(self) -> None:
        label = _operation_label(
            payload_file="MOA/templates/VIP-增加经验值.json",
            service_url="/service/voga-mts-user-vip-stage",
            method="getVipInfo",
        )
        self.assertEqual(label, "VIP经验值-查询当前等级经验")
        self.assertEqual(
            resolve_operation_display("VIP-增加经验值", method="getVipInfo"),
            "VIP经验值-查询当前等级经验",
        )

    def test_contribution_across_ranks_operation_shows_chinese_name(self) -> None:
        import web_moa_call_log as mod

        mod._method_operation_names_cache = None
        self.assertEqual(
            resolve_operation_display(
                "contributionAcrossRanks",
                method="contributionAcrossRanks",
            ),
            "生成式MOA-跨房PK贡献榜",
        )

    def test_generative_payload_operation_shows_chinese_name(self) -> None:
        import web_moa_call_log as mod

        mod._method_operation_names_cache = None
        label = _operation_label(
            payload_file=".tmp/getAcrossRoomPkInfo.646413e948a3.payload",
            service_url="/service/room/external/room-pk-api",
            method="getAcrossRoomPkInfo",
        )
        self.assertEqual(label, "生成式MOA-跨房PK赛况信息")
        self.assertEqual(
            resolve_operation_display(
                "getAcrossRoomPkInfo.646413e948a3.payload",
                method="getAcrossRoomPkInfo",
            ),
            "生成式MOA-跨房PK赛况信息",
        )

    def test_method_dot_service_operation_shows_semantic_chinese(self) -> None:
        self.assertEqual(
            format_operation_display(
                "intimateHomePage · intimate-api",
                method="intimateHomePage",
                params_summary="userId=100301334",
                account_summary="100301334",
            ),
            "用户 100301334 查询亲密关系主页",
        )
        self.assertEqual(
            format_operation_display(
                "testChangeCpLevel · cp-moa",
                method="testChangeCpLevel",
                params_summary="p1=100301334，p4=9",
                account_summary="100301334",
            ),
            "用户 100301334 调整 CP 等级至 9",
        )

    def test_account_hint_omits_momo_id(self) -> None:
        payload = {
            "momoId": "df4c6f364f9fcae3",
            "params": [{"name": "1", "value": "100465989"}],
        }
        self.assertEqual(_extract_account_hint(payload), "100465989")

    def test_beautify_account_strips_momo_id(self) -> None:
        self.assertEqual(
            beautify_account_summary("100465989、df4c6f364f9fcae3"),
            "100465989",
        )

    def test_beautify_account_strips_coin_count_mistaken_as_uid(self) -> None:
        self.assertEqual(
            beautify_account_summary("100166394、100277713、120000"),
            "100166394、100277713",
        )

    def test_assistant_extract_skips_narrative_table_as_params(self) -> None:
        assistant = (
            "## 结论\n\n"
            "| 身份 | 个人钱包（金币 Tab）提现 |\n"
            "|------|-------------------------|\n"
            "| **普通用户** | **应支持**（用例：「普通用户正常提现」） |\n"
            "刚查 **100166394**：`coinCount=120000`，`canCash=1`\n"
            "`/service/voga-base-service-middle-pay-stage` · `queryUserAccount`\n"
        )
        details = extract_moa_call_details_from_assistant(assistant)
        self.assertEqual(details.get("method"), "queryUserAccount")
        self.assertNotIn("身份=", details.get("paramsSummary") or "")
        self.assertNotIn("应支持", details.get("paramsSummary") or "")

    def test_account_display_includes_environment(self) -> None:
        self.assertEqual(
            format_account_summary_display("100465989", environment="test"),
            "测试 · 100465989",
        )
        self.assertEqual(
            format_account_summary_display("100465989", environment="online"),
            "线上 · 100465989",
        )

    def test_compose_source_interface_display_no_duplicate_prefix(self) -> None:
        self.assertEqual(
            compose_source_interface_display(
                "Admin",
                "Admin · POST /admin/user/queryUserDetail",
            ),
            "Admin · POST /admin/user/queryUserDetail",
        )
        self.assertEqual(
            compose_source_interface_display("风控", "风控 · release_device"),
            "风控 · release_device",
        )
        self.assertEqual(
            compose_source_interface_display("MOA", "/service/a · m"),
            "MOA · /service/a · m",
        )

    def test_beautify_legacy_numeric_keys(self) -> None:
        raw = "1=100465989，2=1"
        fixed = beautify_params_summary(raw, method="addVipValue")
        self.assertEqual(fixed, "userId=100465989，value=1")

    def test_dedupe_moa_and_agent_turn_shadow(self) -> None:
        with self._patch_log():
            entries = [
                {
                    "ts": "2026-10-10T08:24:40+00:00",
                    "accountSummary": "100247200",
                    "method": "dispatchTryVip",
                    "operationKey": "moa#/service/voga-mts-user-vip-stage#dispatchTryVip",
                    "operatorStaffId": "32274159141215328",
                    "operatorName": "陈墨",
                },
                {
                    "ts": "2026-10-10T08:24:43+00:00",
                    "accountSummary": "100247200",
                    "method": "",
                    "operationKey": "agent-turn#abc",
                    "operatorStaffId": "444015100823145286",
                    "operatorName": "孙冰川",
                },
            ]
            removed = _dedupe_moa_and_agent_turn_shadow(
                entries,
                account="100247200",
                pivot_ts="2026-10-10T08:24:43+00:00",
                prefer_staff="444015100823145286",
                prefer_name="孙冰川",
            )
            self.assertEqual(removed, 1)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["operatorName"], "孙冰川")
            self.assertEqual(entries[0]["method"], "dispatchTryVip")

    def test_finalize_dingtalk_drops_turn_when_moa_exists(self) -> None:
        with self._patch_log():
            record_tool_call(
                source="moa",
                response={"ec": 200, "result": {"ec": 0}},
                operation="用户 100247200 下发 VIP10 体验 86400 秒",
                account_summary="100247200",
                service_url="/service/voga-mts-user-vip-stage",
                method="dispatchTryVip",
                run_id="dingtalk:msgTest1",
                batch_key="cid:test:user:444015100823145286",
                operator_staff_id="32274159141215328",
                operator_name="陈墨",
            )
            finalize_dingtalk_call_log(
                run_id="dingtalk:msgTest1",
                batch_key="cid:test:user:444015100823145286",
                sender_staff_id="444015100823145286",
                sender_name="孙冰川",
                user_text="把100247200 vip等级设置为10 时长一天",
                assistant_text="**100247200** 已设置 **VIP10 体验 1 天**",
            )
            rows = _load_entries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["operatorName"], "孙冰川")
        self.assertEqual(rows[0]["method"], "dispatchTryVip")

    def test_audit_context_no_active_fallback_without_hint(self) -> None:
        import os
        from unittest.mock import patch

        from web_agent_audit_context import publish_audit_context, resolve_audit_context

        with tempfile.TemporaryDirectory() as td:
            audit = Path(td)
            active = audit / "active.json"
            by_batch = audit / "by_batch"
            patches = patch.multiple(
                "web_agent_audit_context",
                AUDIT_DIR=audit,
                ACTIVE_PATH=active,
                BY_BATCH_DIR=by_batch,
            )
            with patches:
                for key in (
                    "WEB_AGENT_RUN_ID",
                    "WEB_AGENT_BATCH_KEY",
                    "WEB_AGENT_CALLER_STAFF_ID",
                    "WEB_AGENT_CALLER_NAME",
                ):
                    os.environ.pop(key, None)
                publish_audit_context(
                    batch_key="web:other_session",
                    run_id="web:run_other",
                    operator_staff_id="01302434415723305026",
                    operator_name="孙晓东",
                    source="web",
                )
                self.assertIsNone(resolve_audit_context())

    def test_finalize_reattributes_misassigned_moa_in_window(self) -> None:
        with self._patch_log():
            record_tool_call(
                source="moa",
                response={"ec": 200, "result": {"ec": 0}},
                operation="用户 100414599 发放钻石",
                account_summary="100414599",
                service_url="/service/voga-mts-user-account-stage",
                method="provideDiamond",
                run_id="web:wrong_run",
                batch_key="web:93abf6165aac4681",
                operator_staff_id="01302434415723305026",
                operator_name="孙晓东",
                entry_ts_override="2026-10-27T09:36:50+00:00",
            )
            finalize_dingtalk_call_log(
                run_id="dingtalk:liu_cp",
                batch_key="cid:test:user:0130310828673242",
                sender_staff_id="0130310828673242",
                sender_name="刘哲",
                user_text="给100414599加钻石",
                assistant_text="**100414599** 已发放 **1 亿** 钻石",
                ts_iso="2026-10-27T09:37:00+00:00",
            )
            rows = _load_entries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["operatorName"], "刘哲")
        self.assertEqual(rows[0]["runId"], "dingtalk:liu_cp")

    def test_audit_context_resolves_without_run_env(self) -> None:
        import os
        from unittest.mock import patch

        from web_agent_audit_context import publish_audit_context, resolve_audit_context

        with tempfile.TemporaryDirectory() as td:
            audit = Path(td)
            active = audit / "active.json"
            by_batch = audit / "by_batch"
            patches = patch.multiple(
                "web_agent_audit_context",
                AUDIT_DIR=audit,
                ACTIVE_PATH=active,
                BY_BATCH_DIR=by_batch,
            )
            with patches:
                for key in (
                    "WEB_AGENT_BATCH_KEY",
                    "WEB_AGENT_CALLER_STAFF_ID",
                    "WEB_AGENT_CALLER_NAME",
                ):
                    os.environ.pop(key, None)
                os.environ["WEB_AGENT_RUN_ID"] = "dingtalk:msgAuditCtx"
                publish_audit_context(
                    batch_key="cid:test:user:auditctx",
                    run_id="dingtalk:msgAuditCtx",
                    operator_staff_id="12585516401214119",
                    operator_name="陈可",
                    source="test",
                )
                ctx = resolve_audit_context()
                self.assertIsNotNone(ctx)
                assert ctx is not None
                self.assertEqual(ctx["run_id"], "dingtalk:msgAuditCtx")
                self.assertEqual(ctx["operator_name"], "陈可")

    def test_ephemeral_probe_user_not_recorded(self) -> None:
        payload = {
            "url": "/service/voga-mts-user-vip-stage",
            "method": "getVipInfo",
            "params": [{"name": "1", "value": "100000001", "type": "string"}],
        }
        resp = {"ec": 200, "result": {"ec": 0}}
        with self._patch_log():
            record_moa_call(
                payload=payload,
                response=resp,
                run_id="probe-run",
                operator_name="测试员",
            )
            self.assertEqual(list_moa_call_entries(limit=10)["total"], 0)

    def test_purge_ephemeral_audit_entries(self) -> None:
        with self._patch_log():
            _save_entries(
                [
                    {
                        "id": "a",
                        "ts": "2026-01-01T00:00:00+00:00",
                        "accountSummary": "100000001",
                        "operation": "查询用户 100000001 VIP经验值",
                    },
                    {
                        "id": "b",
                        "ts": "2026-01-01T00:00:01+00:00",
                        "accountSummary": "100465989",
                        "operation": "用户 100465989 发放 100 钻石",
                    },
                ]
            )
            self.assertTrue(is_ephemeral_audit_user("100000001", "userId=100000001"))
            self.assertEqual(purge_ephemeral_audit_entries(), 1)
            self.assertEqual(len(_load_entries()), 1)
            self.assertEqual(_load_entries()[0]["id"], "b")

    def test_list_newest_first(self) -> None:
        payload = {"url": "/service/a", "method": "m", "params": []}
        resp = {"ec": 0}
        with self._patch_log():
            record_moa_call(
                payload=payload,
                response=resp,
                run_id="r1",
                payload_file="模板A.json",
                operator_name="测试员",
            )
            record_moa_call(
                payload={"url": "/service/b", "method": "m", "params": []},
                response=resp,
                run_id="r2",
                operator_name="测试员",
            )
            rows = list_moa_call_entries(limit=10)["entries"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["timeBj"] >= rows[1]["timeBj"] or rows[0]["ts"] >= rows[1]["ts"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
