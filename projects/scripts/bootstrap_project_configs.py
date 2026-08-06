#!/usr/bin/env python3
"""从仓库默认配置 bootstrap projects/<id>/ 自有 config / 知识库目录。

用法:
  python3 projects/scripts/bootstrap_project_configs.py example
  python3 projects/scripts/bootstrap_project_configs.py myapp --from yaahlan
  python3 projects/scripts/bootstrap_project_configs.py myapp --copy-registry
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLATFORM = REPO / "platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))

DEFAULT_COPIES: list[tuple[str, str]] = [
    ("Admin/config.json", "config/admin.json"),
    ("online/config.json", "config/online.json"),
    ("MOA/config/thresholds.json", "config/moa-thresholds.json"),
    ("MOA/config/moa.yaml", "config/moa.yaml"),
    ("MSE/config.json", "config/mse.json"),
    ("Risk/config.json", "config/risk.json"),
    ("Gift/config/cp_love_gift.json", "config/cp_love_gift.json"),
    ("DingTalk/config/kb.json", "config/dingtalk-kb.json"),
    ("DingTalk/config/folders.json", "config/dingtalk-folders.json"),
]

REGISTRY_COPIES: list[tuple[str, str]] = [
    ("MOA/config/registry.json", "moa/config/registry.json"),
    ("Admin/config/registry.json", "config/admin-registry.json"),
    ("MSE/config/registry.json", "config/mse-registry.json"),
    ("Gift/config/registry.json", "config/gift-registry.json"),
    ("Risk/config/registry.json", "config/risk-registry.json"),
    ("Tunnel/config/registry.json", "config/tunnel-registry.json"),
    ("online/config/registry.json", "config/online-registry.json"),
    ("DingTalk/config/registry.json", "config/dingtalk-registry.json"),
]

PATH_KEYS_AFTER_BOOTSTRAP = {
    "adminConfig": "config/admin.json",
    "adminRegistry": "config/admin-registry.json",
    "onlineConfig": "config/online.json",
    "onlineRegistry": "config/online-registry.json",
    "moaThresholds": "config/moa-thresholds.json",
    "moaRuntimeYaml": "config/moa.yaml",
    "moaRegistry": "moa/config/registry.json",
    "mseConfig": "config/mse.json",
    "mseRegistry": "config/mse-registry.json",
    "riskConfig": "config/risk.json",
    "riskRegistry": "config/risk-registry.json",
    "giftCpLoveConfig": "config/cp_love_gift.json",
    "giftRegistry": "config/gift-registry.json",
    "tunnelRegistry": "config/tunnel-registry.json",
    "dingtalkKb": "config/dingtalk-kb.json",
    "dingtalkFolders": "config/dingtalk-folders.json",
    "dingtalkRegistry": "config/dingtalk-registry.json",
    "moaTemplates": "moa/templates",
    "testcaseKbRoot": "knowledge/testcase-kb",
    "prdKbRoot": "knowledge/prd-kb",
    "bugKbRoot": "knowledge/bug-kb",
    "onlineTestAccounts": "knowledge/online_test_accounts.json",
    "testDevices": "knowledge/test_devices.json",
    "moaGenerativeRoot": "moa-generative",
    "workflowRoot": "workflow",
    "adbScriptsRoot": "adb/scripts",
    "adbAutotestRoot": "adb/autotest",
}


def _copy_file(src_rel: str, dst: Path) -> None:
    src = REPO / src_rel
    if not src.is_file():
        raise FileNotFoundError(f"缺少源文件: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  copy {src_rel} -> {dst.relative_to(REPO)}")


def os_relpath(target: Path, start: Path) -> str:
    import os

    return os.path.relpath(str(target.resolve()), str(start.resolve()))


def _ensure_dir_symlink(link: Path, target: Path, *, label: str) -> None:
    if link.is_symlink():
        print(f"  skip {label} (symlink exists)")
        return
    if link.is_dir() and any(link.iterdir()):
        print(f"  skip {label} (非空目录)")
        return
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    rel = Path(os_relpath(target, link.parent))
    link.symlink_to(rel, target_is_directory=True)
    print(f"  symlink {label} -> {rel}")


def _ensure_module_registries(project_dir: Path, *, force_copy: bool = False) -> None:
    for src_rel, dst_rel in REGISTRY_COPIES:
        dst = project_dir / dst_rel
        if dst.is_file() and not force_copy:
            print(f"  skip {dst_rel} (已存在)")
            continue
        _copy_file(src_rel, dst)


def _ensure_knowledge_dirs(project_dir: Path) -> None:
    kb = project_dir / "knowledge"
    for name in ("testcase-kb", "prd-kb", "bug-kb"):
        (kb / name).mkdir(parents=True, exist_ok=True)
    devices = kb / "test_devices.json"
    if not devices.is_file():
        template = REPO / "projects/_template/knowledge/test_devices.json"
        if template.is_file():
            shutil.copy2(template, devices)
        else:
            devices.write_text("[]\n", encoding="utf-8")
    accounts = kb / "online_test_accounts.json"
    if not accounts.is_file():
        accounts.write_text("{}\n", encoding="utf-8")
    print(f"  knowledge/ 就绪")


def _patch_project_json(project_dir: Path, project_id: str) -> None:
    path = project_dir / "project.json"
    if not path.is_file():
        raise FileNotFoundError(f"缺少 {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    paths = data.setdefault("paths", {})
    prefix = f"projects/{project_id}/"
    for key, rel in PATH_KEYS_AFTER_BOOTSTRAP.items():
        paths[key] = prefix + rel
    paths.setdefault("sources", f"{prefix}sources.json")
    paths.setdefault("bookmarks", f"{prefix}bookmarks.json")
    paths.setdefault("temporaryTestcase", f"{prefix}temporary_testcase")
    paths.setdefault("giftDefaults", "platform/dingtalk_gateway/config/gift_defaults.json")
    data["paths"] = paths
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  更新 {path.relative_to(REPO)}")


def _patch_sources_json(project_dir: Path, project_id: str) -> None:
    path = project_dir / "sources.json"
    if not path.is_file():
        print(f"  skip sources.json (不存在)")
        return
    project_json = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    display = str(project_json.get("displayName") or project_id).strip()
    agent = project_json.get("agent") if isinstance(project_json.get("agent"), dict) else {}
    catalog_title_text = str(agent.get("catalogTitle") or "").strip()

    data = json.loads(path.read_text(encoding="utf-8"))
    modules = data.get("modules")
    if not isinstance(modules, list):
        return
    for mod in modules:
        if not isinstance(mod, dict):
            continue
        mid = str(mod.get("id") or "").strip()
        if mid == "admin" and display:
            mod["label"] = f"{display}后台"
            mod["subtitle"] = f"{display} 测试后台"
    data["modules"] = modules
    if catalog_title_text:
        data["catalog_title_hint"] = catalog_title_text
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  更新 {path.relative_to(REPO)} (modules 品牌)")


def bootstrap(
    project_id: str,
    *,
    from_project: str = "yaahlan",
    link_shared: bool = True,
    copy_registry: bool = False,
) -> None:
    project_dir = REPO / "projects" / project_id
    if not project_dir.is_dir():
        raise FileNotFoundError(f"项目目录不存在: {project_dir}")
    print(f"bootstrap projects/{project_id} (from {from_project})")
    for src_rel, dst_rel in DEFAULT_COPIES:
        _copy_file(src_rel, project_dir / dst_rel)
    if link_shared:
        _ensure_dir_symlink(project_dir / "moa" / "templates", REPO / "MOA" / "templates", label="moa/templates")
        _ensure_dir_symlink(project_dir / "workflow", REPO / "workflow", label="workflow")
        _ensure_dir_symlink(
            project_dir / "moa-generative",
            REPO / "MOA-generative",
            label="moa-generative",
        )
        _ensure_dir_symlink(
            project_dir / "adb" / "scripts",
            REPO / "adb" / "录制脚本",
            label="adb/scripts",
        )
        _ensure_dir_symlink(
            project_dir / "adb" / "autotest",
            REPO / "adb" / "自动化用例",
            label="adb/autotest",
        )
    _ensure_module_registries(project_dir, force_copy=copy_registry)
    _ensure_knowledge_dirs(project_dir)
    (project_dir / "temporary_testcase").mkdir(exist_ok=True)
    _patch_project_json(project_dir, project_id)
    _patch_sources_json(project_dir, project_id)
    print("done")


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap projects/<id> 自有 config 与知识库")
    ap.add_argument("project_id", help="如 example / myapp")
    ap.add_argument("--from", dest="from_project", default="yaahlan")
    ap.add_argument(
        "--no-link-shared",
        action="store_true",
        help="不 symlink moa/templates、workflow、moa-generative（需自行准备目录）",
    )
    ap.add_argument(
        "--copy-registry",
        action="store_true",
        help="强制覆盖 projects/<id>/ 下全部 module registry.json",
    )
    args = ap.parse_args()
    try:
        bootstrap(
            args.project_id,
            from_project=args.from_project,
            link_shared=not args.no_link_shared,
            copy_registry=args.copy_registry,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
