import os
import shlex
import time

import pytest

# 项目根目录：以 conftest.py 所在目录为准，换机后无需改配置
_project_dir = os.path.dirname(os.path.abspath(__file__))
project_root = _project_dir
data_dir = os.path.join(project_root, "data")


def _report_enabled(config) -> bool:
    if os.environ.get("GENERATE_SALARY_REPORT", "").strip() in ("1", "true", "yes"):
        return True
    return bool(getattr(config, "_generate_salary_report", False))


def pytest_addoption(parser):
    parser.addoption(
        "--salary-report",
        action="store_true",
        default=False,
        help="执行结束后生成 Yaahlan 半月结算薪 Markdown/HTML 测试报告",
    )
    parser.addoption(
        "--guild-progress-policy",
        action="store",
        default=None,
        help="公会进步奖政策：202512（旧，默认）/ 202608（新，自20260816起）/ auto（按周期自动）。",
    )
    parser.addoption(
        "--salary-report-suite",
        action="store",
        default="",
        help="算薪报告套件：cycle（默认半月结全量）/ exempt（主播豁免专项）。",
    )


def pytest_configure(config):
    from utils.env_utils import load_env_file
    from utils.guild_progress_policy import (
        ENV_KEY,
        get_guild_progress_award_policy,
        normalize_policy,
        policy_label,
    )

    load_env_file(project_root)
    cli_policy = config.getoption("--guild-progress-policy")
    if cli_policy:
        os.environ[ENV_KEY] = normalize_policy(cli_policy)
    config._guild_progress_policy = get_guild_progress_award_policy()
    print(f"[进步奖政策] {policy_label()}")

    config._generate_salary_report = config.getoption("--salary-report")
    if not _report_enabled(config):
        return
    from utils.json_utils import JsonUtils
    from utils.salary_report import (
        DATA_SUBDIR,
        DEFAULT_CASES_JSON,
        REPORT_DIR,
        REPORT_DIR_EXEMPT,
        REPORT_TITLE,
        REPORT_TITLE_EXEMPT,
        get_collector,
    )

    cmd = " ".join(shlex.quote(x) for x in getattr(config, "invocation_params", None).args or ["pytest"])
    args = getattr(config, "invocation_params", None).args or []
    arg_str = " ".join(str(a) for a in args)
    suite = (config.getoption("--salary-report-suite") or os.environ.get("CYCLE_SALARY_SUITE", "")).strip()

    report_title = REPORT_TITLE
    report_dir = REPORT_DIR
    cases_data_label = f"data/{DATA_SUBDIR}/{DEFAULT_CASES_JSON}"

    if suite == "exempt" or "test_yaahlan_cycle_salary_exempt" in arg_str:
        from utils.cycle_salary_exempt_suite import load_suite_cases

        smoke_only = os.environ.get("CYCLE_SALARY_EXEMPT_SMOKE", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        cases, meta = load_suite_cases(smoke_only=smoke_only)
        report_title = meta.get("title") or REPORT_TITLE_EXEMPT
        report_dir = REPORT_DIR_EXEMPT
        cases_data_label = (
            f"data/{DATA_SUBDIR}/{meta.get('source_cases_json', DEFAULT_CASES_JSON)} "
            f"+ suite {meta.get('suite_json', 'yaahlan_cycle_salary_exempt_suite.json')}"
        )
    else:
        data = JsonUtils.jsonfile_to_dict(DATA_SUBDIR, DEFAULT_CASES_JSON) or {}
        cases = data.get("cases") or []

    collector = get_collector()
    collector.reset()
    collector.begin_session(
        cases,
        command=cmd,
        report_title=report_title,
        report_dir=report_dir,
        cases_data_label=cases_data_label,
    )


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if not _report_enabled(config):
        return

    from utils.env_utils import load_env_file
    from utils.salary_report import (
        get_collector,
        report_path_for_today,
        send_report_brief_to_dingtalk,
        sync_html_report,
        write_report,
    )

    load_env_file(project_root)

    collector = get_collector()
    if not collector.enabled:
        return

    duration = None
    if collector.run_start is not None:
        duration = int(time.time() - collector.run_start)

    md_path = write_report(
        report_path_for_today(project_root),
        collector.results,
        collector.cases,
        collector.executed_count,
        total_duration_seconds=duration,
        command=collector.command,
        validation_errors=collector.validation_errors,
        project_root=project_root,
    )
    html_path = sync_html_report(md_path, project_root)
    print(f"\n[报告] Markdown: {md_path}")
    if html_path:
        print(f"[报告] HTML: {html_path}")

    if collector.executed_count > 0:
        send_report_brief_to_dingtalk(
            md_path,
            collector.results,
            collector.executed_count,
            duration,
            project_root=project_root,
            html_path=html_path,
        )
    else:
        print("[钉钉] 本次无执行用例，跳过简报发送")


@pytest.fixture(scope="session")
def guild_progress_policy(pytestconfig):
    """当前公会进步奖政策：202512（旧）或 202608（新）。"""
    from utils.guild_progress_policy import get_guild_progress_award_policy

    return getattr(pytestconfig, "_guild_progress_policy", None) or get_guild_progress_award_policy()
