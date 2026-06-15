"""加载与校验自动化用例（按需求文件夹）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..recorded_scripts import load_test_accounts
from .paths import (
    AUTOTEST_ROOT,
    CATALOG_PATH,
    LEGACY_CASES_DIR,
    LEGACY_REGISTRY_DIR,
    P0_CATALOG_PATH,
    requirement_cases_dir,
    requirement_catalog_path,
    requirement_dir,
    requirement_registry_path,
)


class AutotestCaseError(ValueError):
    """自动化用例格式或引用错误。"""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise AutotestCaseError(f"无法读取 {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise AutotestCaseError(f"JSON 非法 {path}: {e}") from e
    if not isinstance(data, dict):
        raise AutotestCaseError(f"用例须为 object: {path}")
    return data


def _root_catalog_raw() -> dict[str, Any]:
    if CATALOG_PATH.is_file():
        return _read_json(CATALOG_PATH)
    if P0_CATALOG_PATH.is_file():
        return _read_json(P0_CATALOG_PATH)
    return {"version": 1, "requirements": [], "suites": []}


def list_requirement_entries() -> list[dict[str, Any]]:
    raw = _root_catalog_raw()
    requirements = raw.get("requirements")
    if isinstance(requirements, list) and requirements:
        return [r for r in requirements if isinstance(r, dict)]
    # 无 requirements 时扫描子目录（含 catalog.json）
    out: list[dict[str, Any]] = []
    if not AUTOTEST_ROOT.is_dir():
        return out
    for child in sorted(AUTOTEST_ROOT.iterdir()):
        if not child.is_dir() or child.name in ("reports", "templates"):
            continue
        sub_catalog = child / "catalog.json"
        if not sub_catalog.is_file():
            continue
        sub = _read_json(sub_catalog)
        out.append(
            {
                "id": sub.get("requirementId") or f"req-{child.name}",
                "folder": child.name,
                "name": sub.get("name") or child.name,
                "module": sub.get("module"),
                "registry": sub.get("registry") or (
                    "registry.json" if (child / "registry.json").is_file() else None
                ),
                **{
                    k: sub[k]
                    for k in ("prdRef", "manualCaseUrl", "manualCaseSheet", "prdLocal")
                    if k in sub
                },
            }
        )
    return out


_REQUIREMENT_ID_ALIASES: dict[str, str] = {
    "req-动态-发布视频": "req-动态支持视频发布",
}


def normalize_requirement_id(requirement_id: str) -> str:
    rid = requirement_id.strip()
    return _REQUIREMENT_ID_ALIASES.get(rid, rid)


def folder_for_requirement(requirement_id: str) -> str | None:
    rid = normalize_requirement_id(requirement_id)
    for req in list_requirement_entries():
        if str(req.get("id") or "").strip() == rid:
            folder = str(req.get("folder") or "").strip()
            return folder or None
    return None


def iter_cases_dirs() -> list[Path]:
    dirs: list[Path] = []
    seen: set[str] = set()
    if LEGACY_CASES_DIR.is_dir():
        key = str(LEGACY_CASES_DIR.resolve())
        dirs.append(LEGACY_CASES_DIR)
        seen.add(key)
    for req in list_requirement_entries():
        folder = str(req.get("folder") or "").strip()
        if not folder:
            continue
        cases_dir = requirement_cases_dir(folder)
        key = str(cases_dir.resolve())
        if cases_dir.is_dir() and key not in seen:
            dirs.append(cases_dir)
            seen.add(key)
    return dirs


def case_file_for_id(case_id: str) -> Path:
    safe = case_id.strip()
    if not safe:
        raise AutotestCaseError("case id 不能为空")
    for cases_dir in iter_cases_dirs():
        path = cases_dir / f"{safe}.json"
        if path.is_file():
            return path
    searched = "、".join(str(d.relative_to(AUTOTEST_ROOT)) for d in iter_cases_dirs())
    raise AutotestCaseError(f"用例文件不存在: {safe}.json（已查: {searched or '无'}）")


def folder_for_case_id(case_id: str) -> str | None:
    path = case_file_for_id(case_id)
    try:
        rel = path.parent.relative_to(AUTOTEST_ROOT)
        if len(rel.parts) >= 2 and rel.parts[1] == "cases":
            return rel.parts[0]
    except ValueError:
        pass
    return None


def resolve_account(case: dict[str, Any]) -> dict[str, Any]:
    raw = case.get("account")
    if not isinstance(raw, dict):
        raise AutotestCaseError("用例缺少 account 对象")
    alias = str(raw.get("alias") or "").strip()
    if not alias:
        raise AutotestCaseError("account.alias 不能为空")

    accounts = load_test_accounts()
    entry = accounts.get(alias)
    if not isinstance(entry, dict):
        known = "、".join(sorted(accounts.keys())) or "（无）"
        raise AutotestCaseError(f"未知账号别名 {alias!r}，可选: {known}")

    resolved = {
        "alias": alias,
        "role": entry.get("role"),
        "countryCode": entry.get("countryCode"),
        "phone": str(entry.get("phone", "")),
        "verifyCode": entry.get("verifyCode"),
        "userId": str(entry.get("userId", "")),
        "description": raw.get("description") or entry.get("role"),
        "precondition": raw.get("precondition"),
    }
    return resolved


def load_case(case_id: str) -> dict[str, Any]:
    data = _read_json(case_file_for_id(case_id))
    if str(data.get("id", "")).strip() != case_id.strip():
        raise AutotestCaseError(f"用例 id 与文件名不一致: {case_id}")
    data["_resolvedAccount"] = resolve_account(data)
    folder = folder_for_case_id(case_id)
    if folder:
        data["_requirementFolder"] = folder
    return data


def load_catalog() -> dict[str, Any]:
    raw = _root_catalog_raw()
    suites: list[dict[str, Any]] = []
    root_suites = raw.get("suites")
    if isinstance(root_suites, list):
        suites.extend(s for s in root_suites if isinstance(s, dict))

    for req in list_requirement_entries():
        folder = str(req.get("folder") or "").strip()
        if not folder:
            continue
        sub_path = requirement_catalog_path(folder)
        if not sub_path.is_file():
            continue
        sub = _read_json(sub_path)
        sub_suites = sub.get("suites")
        if isinstance(sub_suites, list):
            suites.extend(s for s in sub_suites if isinstance(s, dict))

    merged = dict(raw)
    merged["suites"] = suites
    if "requirements" not in merged:
        merged["requirements"] = list_requirement_entries()
    return merged


def _parse_priority_filter(priority: str | None) -> set[str] | None:
    if not priority:
        return None
    parts = {p.strip().upper() for p in priority.split(",") if p.strip()}
    return parts or None


def _suite_matches_filters(
    suite: dict[str, Any],
    *,
    requirement_id: str | None,
    priority_filter: set[str] | None,
) -> bool:
    if requirement_id:
        req = str(suite.get("requirementId") or "").strip()
        if normalize_requirement_id(req) != normalize_requirement_id(requirement_id):
            return False
    if priority_filter:
        suite_priority = str(suite.get("priority") or "P0").strip().upper()
        if suite_priority not in priority_filter:
            return False
    return True


def list_suites(*, requirement_id: str | None = None, priority: str | None = None) -> list[dict[str, Any]]:
    catalog = load_catalog()
    suites = catalog.get("suites")
    if not isinstance(suites, list):
        return []
    priority_filter = _parse_priority_filter(priority)
    out: list[dict[str, Any]] = []
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        if not _suite_matches_filters(
            suite,
            requirement_id=requirement_id,
            priority_filter=priority_filter,
        ):
            continue
        out.append(suite)
    return out


def list_case_ids(
    *,
    suite_id: str | None = None,
    requirement_id: str | None = None,
    priority: str | None = None,
) -> list[str]:
    catalog = load_catalog()
    suites = catalog.get("suites")
    priority_filter = _parse_priority_filter(priority)

    if suite_id:
        if not isinstance(suites, list):
            raise AutotestCaseError(f"未知 suite: {suite_id}")
        for suite in suites:
            if not isinstance(suite, dict):
                continue
            if str(suite.get("id", "")).strip() != suite_id.strip():
                continue
            cases = suite.get("cases")
            if isinstance(cases, list):
                return [str(c).strip() for c in cases if str(c).strip()]
        raise AutotestCaseError(f"未知 suite: {suite_id}")

    ids: list[str] = []
    seen: set[str] = set()
    if isinstance(suites, list):
        for suite in suites:
            if not isinstance(suite, dict):
                continue
            if not _suite_matches_filters(
                suite,
                requirement_id=requirement_id,
                priority_filter=priority_filter,
            ):
                continue
            cases = suite.get("cases")
            if not isinstance(cases, list):
                continue
            for case_id in cases:
                cid = str(case_id).strip()
                if cid and cid not in seen:
                    seen.add(cid)
                    ids.append(cid)
    if ids:
        return ids

    all_ids: list[str] = []
    for cases_dir in iter_cases_dirs():
        for path in sorted(cases_dir.glob("*.json")):
            cid = path.stem
            if cid not in seen:
                seen.add(cid)
                all_ids.append(cid)
    return all_ids


def list_suites_summary(
    *,
    requirement_id: str | None = None,
    priority: str | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for suite in list_suites(requirement_id=requirement_id, priority=priority):
        case_ids = suite.get("cases")
        if not isinstance(case_ids, list):
            case_ids = []
        out.append(
            {
                "id": suite.get("id"),
                "name": suite.get("name"),
                "module": suite.get("module"),
                "priority": suite.get("priority", "P0"),
                "requirementId": suite.get("requirementId"),
                "caseCount": len(case_ids),
                "cases": case_ids,
            }
        )
    return out


def find_requirement_entry(requirement_id: str) -> dict[str, Any] | None:
    rid = normalize_requirement_id(requirement_id)
    for req in list_requirement_entries():
        if normalize_requirement_id(str(req.get("id") or "")) == rid:
            return req
    return None


def list_requirements_summary() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for req in list_requirement_entries():
        req_id = str(req.get("id") or "").strip()
        folder = str(req.get("folder") or "").strip()
        suites = list_suites_summary(requirement_id=req_id or None)
        case_ids: list[str] = []
        for suite in suites:
            for cid in suite.get("cases") or []:
                if cid not in case_ids:
                    case_ids.append(cid)
        out.append(
            {
                "id": req_id,
                "folder": folder,
                "name": req.get("name"),
                "module": req.get("module"),
                "prdRef": req.get("prdRef"),
                "manualCaseUrl": req.get("manualCaseUrl"),
                "registry": req.get("registry"),
                "suiteCount": len(suites),
                "autoCaseCount": len(case_ids),
                "cases": case_ids,
                "suites": [s.get("id") for s in suites],
            }
        )
    return out


def load_registry(requirement_id: str) -> dict[str, Any]:
    requirement_id = normalize_requirement_id(requirement_id)
    folder = folder_for_requirement(requirement_id)
    if folder:
        reg_path = requirement_registry_path(folder)
        if reg_path.is_file():
            return _read_json(reg_path)

    catalog = load_catalog()
    requirements = catalog.get("requirements")
    registry_rel: str | None = None
    if isinstance(requirements, list):
        for req in requirements:
            if not isinstance(req, dict):
                continue
            if normalize_requirement_id(str(req.get("id") or "")) == normalize_requirement_id(
                requirement_id
            ):
                registry_rel = str(req.get("registry") or "").strip() or None
                if folder and registry_rel:
                    path = requirement_dir(folder) / registry_rel
                    if path.is_file():
                        return _read_json(path)
                break

    if LEGACY_REGISTRY_DIR.is_dir():
        short = requirement_id.removeprefix("req-").replace("-", "")
        for path in LEGACY_REGISTRY_DIR.glob("*.json"):
            if short in path.stem.replace("-", ""):
                return _read_json(path)

    raise AutotestCaseError(f"未找到需求 registry: {requirement_id}")
