"""加载 projects/<id>/project.json，供 Web Agent / 钉钉网关 / catalog 共用。"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PLATFORM_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PLATFORM_DIR.parent
PROJECTS_DIR = REPO_ROOT / "projects"
DEFAULT_PROJECT_ID = "yaahlan"
LEGACY_SOURCES = PLATFORM_DIR / "config" / "sources.json"


def get_repo_root() -> Path:
    return REPO_ROOT


def get_project_id() -> str:
    raw = os.environ.get("AGENT_PROJECT") or os.environ.get("PROJECT") or DEFAULT_PROJECT_ID
    value = str(raw).strip()
    if not value:
        return DEFAULT_PROJECT_ID
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
        raise ValueError(f"非法 AGENT_PROJECT: {value!r}")
    return value


def project_dir(project_id: str | None = None) -> Path:
    pid = project_id or get_project_id()
    return PROJECTS_DIR / pid


def project_path(project_id: str | None = None) -> Path:
    path = project_dir(project_id) / "project.json"
    if not path.is_file():
        known = sorted(p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()) if PROJECTS_DIR.is_dir() else []
        raise FileNotFoundError(
            f"未找到项目配置: {path}（AGENT_PROJECT={project_id or get_project_id()}；"
            f"已知项目: {', '.join(known) or '无'}）"
        )
    return path


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 JSON object")
    return data


def resolve_path(relative: str, *, base: Path | None = None) -> Path:
    rel = str(relative or "").strip()
    if not rel:
        raise ValueError("路径不能为空")
    path = Path(rel)
    if path.is_absolute():
        return path
    root = base or REPO_ROOT
    # 保留项目内 symlink 逻辑路径（如 projects/example/moa/templates），不跟随到 MOA/templates
    return (root / path).absolute()


@lru_cache(maxsize=8)
def get_project_config(project_id: str | None = None) -> dict[str, Any]:
    pid = project_id or get_project_id()
    cfg = _read_json(project_path(pid))
    cfg.setdefault("id", pid)
    return cfg


def _agent_cfg() -> dict[str, Any]:
    agent = get_project_config().get("agent")
    return agent if isinstance(agent, dict) else {}


def _paths_cfg() -> dict[str, Any]:
    paths = get_project_config().get("paths")
    return paths if isinstance(paths, dict) else {}


def _prompts_cfg() -> dict[str, Any]:
    prompts = get_project_config().get("prompts")
    return prompts if isinstance(prompts, dict) else {}


def web_agent_title() -> str:
    return str(_agent_cfg().get("title") or "智能工具 Agent")


def web_agent_subtitle() -> str:
    return str(
        _agent_cfg().get("subtitle")
        or "MOA/Admin 查数 · Tunnel 抓包 · 用例生成"
    )


def web_agent_name() -> str:
    return str(_agent_cfg().get("webAgentName") or f"{web_agent_title()} Web Agent")


def gateway_agent_name() -> str:
    return str(_agent_cfg().get("gatewayAgentName") or f"{web_agent_title()} 网关 Agent")


def gateway_lifecycle_prefix() -> str:
    return str(_agent_cfg().get("gatewayLifecyclePrefix") or web_agent_title())


def catalog_export_basename() -> str:
    return str(_agent_cfg().get("catalogExportBasename") or "智能工具平台")


def catalog_title() -> str:
    return str(_agent_cfg().get("catalogTitle") or f"{web_agent_title()} 工具平台")


def http_user_agent() -> str:
    return str(_agent_cfg().get("httpUserAgent") or "AgentPlatform/1.0")


def web_login_phrase() -> str:
    return str(_agent_cfg().get("webLoginPhrase") or "请求访问智能工具 Agent")


def web_login_match_parts() -> tuple[str, ...]:
    raw = _agent_cfg().get("webLoginMatchParts")
    if isinstance(raw, list) and raw:
        parts = tuple(str(x).strip() for x in raw if str(x).strip())
        if parts:
            return parts
    return tuple(web_login_phrase().split())


@lru_cache(maxsize=8)
def web_login_pattern(*, project_id: str | None = None) -> re.Pattern[str]:
    if project_id:
        agent = get_project_config(project_id).get("agent")
        agent_dict = agent if isinstance(agent, dict) else {}
        custom = str(agent_dict.get("webLoginPattern") or "").strip()
        if custom:
            return re.compile(custom, re.I)
        parts = agent_dict.get("webLoginMatchParts")
        if isinstance(parts, list) and parts:
            tokens = [str(x).strip() for x in parts if str(x).strip()]
        else:
            tokens = str(agent_dict.get("webLoginPhrase") or "请求访问智能工具 Agent").split()
    else:
        agent_dict = _agent_cfg()
        custom = str(agent_dict.get("webLoginPattern") or "").strip()
        if custom:
            return re.compile(custom, re.I)
        tokens = list(web_login_match_parts())
    body = r"\s*".join(re.escape(token) for token in tokens)
    return re.compile(rf"^\s*{body}\s*$", re.I)


def sources_path() -> Path:
    rel = str(_paths_cfg().get("sources") or "").strip()
    if rel:
        path = resolve_path(rel)
        if path.is_file():
            return path
    if LEGACY_SOURCES.is_file():
        return LEGACY_SOURCES
    raise FileNotFoundError("未找到 sources.json（请在 project.json paths.sources 或 platform/config/sources.json 配置）")


def test_devices_path() -> Path:
    rel = str(_paths_cfg().get("testDevices") or "testcase-kb/test_devices.json").strip()
    return resolve_path(rel)


def _app_cfg() -> dict[str, Any]:
    app = get_project_config().get("app")
    return app if isinstance(app, dict) else {}


def _tunnel_cfg() -> dict[str, Any]:
    tunnel = get_project_config().get("tunnel")
    return tunnel if isinstance(tunnel, dict) else {}


def path_key(key: str, default_relative: str) -> Path:
    """读取 paths.{key}，不存在则用仓库内 default_relative。"""
    rel = str(_paths_cfg().get(key) or default_relative).strip()
    return resolve_path(rel)


def admin_config_path() -> Path:
    return path_key("adminConfig", "Admin/config.json")


def online_config_path() -> Path:
    return path_key("onlineConfig", "online/config.json")


def moa_thresholds_path() -> Path:
    return path_key("moaThresholds", "MOA/config/thresholds.json")


def moa_templates_dir() -> Path:
    return path_key("moaTemplates", "MOA/templates")


def moa_runtime_yaml_path() -> Path:
    return path_key("moaRuntimeYaml", "MOA/config/moa.yaml")


def moa_registry_path() -> Path:
    return path_key("moaRegistry", "MOA/config/registry.json")


def mse_config_path() -> Path:
    return path_key("mseConfig", "MSE/config.json")


def risk_config_path() -> Path:
    return path_key("riskConfig", "Risk/config.json")


def gift_cp_love_config_path() -> Path:
    return path_key("giftCpLoveConfig", "Gift/config/cp_love_gift.json")


def adb_scripts_root() -> Path:
    return path_key("adbScriptsRoot", "adb/录制脚本")


def adb_autotest_root() -> Path:
    return path_key("adbAutotestRoot", "adb/自动化用例")


def app_android_package() -> str:
    return str(_app_cfg().get("androidPackage") or "com.immomo.biz.yaahlan")


def app_android_activity() -> str:
    return str(_app_cfg().get("androidActivity") or ".personalityIcon4")


def app_android_launch_mode() -> str:
    return str(_app_cfg().get("androidLaunchMode") or "launcher")


def app_android_launch_wait_ms() -> int:
    raw = _app_cfg().get("androidLaunchWaitMs")
    try:
        return int(raw) if raw is not None else 4000
    except (TypeError, ValueError):
        return 4000


def app_android_splash_ad_max_ms() -> int:
    raw = _app_cfg().get("androidSplashAdMaxMs")
    try:
        return int(raw) if raw is not None else 8000
    except (TypeError, ValueError):
        return 8000


def app_android_splash_ad_script_id() -> str:
    return str(_app_cfg().get("androidSplashAdScriptId") or "dismiss-splash-ad")


def dingtalk_kb_config_path() -> Path:
    return path_key("dingtalkKb", "DingTalk/config/kb.json")


def dingtalk_folders_config_path() -> Path:
    return path_key("dingtalkFolders", "DingTalk/config/folders.json")


def testcase_kb_root() -> Path:
    return path_key("testcaseKbRoot", "testcase-kb")


def prd_kb_root() -> Path:
    return path_key("prdKbRoot", "prd-kb")


def bug_kb_root() -> Path:
    return path_key("bugKbRoot", "bug-kb")


def online_test_accounts_path() -> Path:
    return path_key("onlineTestAccounts", "testcase-kb/online_test_accounts.json")


def temporary_testcase_dir() -> Path:
    return path_key("temporaryTestcase", "temporary_testcase")


def app_id() -> int:
    raw = _app_cfg().get("appId", 2005)
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"project.app.appId 无效: {raw!r}") from exc


def app_cmdb_appkey() -> str:
    return str(_app_cfg().get("cmdbAppKey") or "momo.ibt.yaahlan.service.yaahlan-web")


def app_cmdb_corp() -> str:
    return str(_app_cfg().get("cmdbCorp") or "alpha")


def app_cmdb_env() -> str:
    return str(_app_cfg().get("cmdbEnv") or "stage")


def cmdb_instances_url() -> str:
    return (
        "http://cmdb.momo.com/open/hubble-app-instances/"
        f"?appkey={app_cmdb_appkey()}&corp={app_cmdb_corp()}&env={app_cmdb_env()}"
    )


def tunnel_mock_base_url() -> str:
    return str(_tunnel_cfg().get("mockBaseUrl") or "http://gw-api-alpha.yaahlan.fun").rstrip("/")


def tunnel_default_g_appid() -> str:
    return str(_tunnel_cfg().get("defaultGAppid") or "All")


def tunnel_default_g_env() -> str:
    return str(_tunnel_cfg().get("defaultGEnv") or "alpha")


def gift_defaults_path() -> Path:
    rel = str(_paths_cfg().get("giftDefaults") or "platform/dingtalk_gateway/config/gift_defaults.json").strip()
    return resolve_path(rel)


def gift_cp_love_rule_line() -> str | None:
    line = _prompts_cfg().get("giftCpLoveRule")
    if line is None:
        return None
    text = str(line).strip()
    return text or None


def _api_cfg() -> dict[str, Any]:
    api = get_project_config().get("api")
    return api if isinstance(api, dict) else {}


def api_stage_gateway_base() -> str:
    return str(
        _api_cfg().get("stageGatewayBase") or "https://melon-gateway-alpha-stage.immomo.com"
    ).rstrip("/")


def api_http_prefix() -> str:
    return str(_api_cfg().get("httpPrefix") or "/yaahlan").rstrip("/") or "/yaahlan"


def api_moa_service_prefix() -> str:
    return str(_api_cfg().get("moaServicePrefix") or "/service/yaahlan").rstrip("/")


def api_moa_trick_service_prefix() -> str:
    return str(_api_cfg().get("moaTrickServicePrefix") or "/service/yaahlan-trick").rstrip("/")


def api_family_pk_h5_path() -> str:
    return str(
        _api_cfg().get("familyPkH5Path")
        or "/yaahlan-fe/yaahlan-family-pk/index.html?_bid=1006677&_ui=256"
    )


def app_java_area_enum_fqcn() -> str:
    return str(
        _app_cfg().get("javaAreaEnumFqcn")
        or "com.immomo.yaahlan.business.utils.enums.AreaEnum"
    )


def api_endpoint(key: str, default: str = "") -> str:
    endpoints = _api_cfg().get("endpoints")
    if isinstance(endpoints, dict):
        raw = endpoints.get(key)
        if raw is not None:
            text = str(raw).strip()
            if text:
                return text
    return default


def stage_gateway_url(endpoint_key: str, default_path: str) -> str:
    path = api_endpoint(endpoint_key, default_path)
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{api_stage_gateway_base()}{path}"


def moa_generative_root() -> Path:
    return path_key("moaGenerativeRoot", "MOA-generative")


def workflow_root() -> Path:
    return path_key("workflowRoot", "workflow")


def load_sources() -> dict[str, Any]:
    return _read_json(sources_path())


def list_projects() -> list[str]:
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in PROJECTS_DIR.iterdir()
        if p.is_dir() and (p / "project.json").is_file() and not p.name.startswith("_")
    )
