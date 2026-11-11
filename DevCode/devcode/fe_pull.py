"""按前端汇总表解析结果 clone / pull 独立 H5 仓。"""

from __future__ import annotations

import os
import subprocess
from typing import Any

from devcode.fe_repos import fe_clone_url
from devcode.paths import voga_repos_dir


def _git(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def ensure_fe_repo(
    repo_name: str,
    *,
    branch: str | None = None,
    depth: int | None = None,
) -> dict[str, Any]:
    name = (repo_name or "").strip().removesuffix(".git")
    if not name:
        raise ValueError("仓库名不能为空")
    base = voga_repos_dir()
    path = os.path.join(base, name)
    entry: dict[str, Any] = {
        "repo_name": name,
        "path": path,
        "clone_url": fe_clone_url(name),
    }

    if not os.path.isdir(os.path.join(path, ".git")):
        os.makedirs(base, exist_ok=True)
        clone_args = ["clone"]
        if depth and depth > 0:
            clone_args.extend(["--depth", str(depth)])
        clone_args.extend([entry["clone_url"], path])
        cl = _git(clone_args)
        entry["clone_stdout"] = (cl.stdout or "").strip()
        entry["clone_stderr"] = (cl.stderr or "").strip()
        if cl.returncode != 0:
            entry["ok"] = False
            entry["error"] = entry["clone_stderr"] or entry["clone_stdout"] or f"git clone exit {cl.returncode}"
            return entry

    if branch:
        co = _git(["checkout", branch], path)
        if co.returncode != 0:
            fetch = _git(["fetch", "origin", branch], path)
            entry["fetch_stderr"] = (fetch.stderr or "").strip()
            co = _git(["checkout", branch], path)
        if co.returncode != 0:
            entry["ok"] = False
            entry["error"] = (co.stderr or co.stdout or "").strip() or f"checkout {branch} failed"
            return entry

    pull = _git(["pull", "--ff-only"], path)
    entry["pull_stdout"] = (pull.stdout or "").strip()
    entry["pull_stderr"] = (pull.stderr or "").strip()
    if pull.returncode != 0:
        entry["ok"] = False
        entry["error"] = entry["pull_stderr"] or entry["pull_stdout"] or f"git pull exit {pull.returncode}"
        return entry

    rev = _git(["rev-parse", "--short", "HEAD"], path)
    br = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)
    entry["ok"] = True
    entry["head"] = (rev.stdout or "").strip() if rev.returncode == 0 else ""
    entry["branch"] = (br.stdout or "").strip() if br.returncode == 0 else ""
    return entry


def pull_fe_by_feature(
    feature: str,
    *,
    branch: str | None = None,
    pick: int = 0,
) -> dict[str, Any]:
    from devcode.fe_sheet import resolve_feature

    matches, resolve_source = resolve_feature(feature)
    if not matches:
        return {
            "ok": False,
            "error": f"汇总表未匹配功能: {feature!r}",
            "resolve_source": resolve_source,
            "matches": [],
        }
    if pick < 0 or pick >= len(matches):
        pick = 0
    chosen = matches[pick]
    repo = chosen["repo_name"]
    pull_result = ensure_fe_repo(repo, branch=branch)
    return {
        "ok": bool(pull_result.get("ok")),
        "feature_query": feature,
        "resolve_source": resolve_source,
        "matches": matches,
        "chosen": chosen,
        "pull": pull_result,
    }
