"""对 voga-repos 下已 clone 的服务端、客户端与 yaahlan-fe H5 仓执行 git pull。"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from devcode.paths import config_dir, repos_config_path, voga_repos_dir
from devcode.repos import repo_names


def _load_repos_config() -> dict[str, Any]:
    with open(repos_config_path(), "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("repos.json 必须是 object")
    return data


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def pull_repos(*, only: str | None = None) -> dict[str, Any]:
    cfg = _load_repos_config()
    repo_names_list = repo_names()
    if only:
        if only not in repo_names_list:
            raise ValueError(f"未知仓库: {only}，可选: {', '.join(repo_names_list)}")
        repo_names_list = [only]

    base = voga_repos_dir()
    results: list[dict[str, Any]] = []
    failed = 0

    for name in repo_names_list:
        path = os.path.join(base, name)
        entry: dict[str, Any] = {"name": name, "path": path}
        if not os.path.isdir(os.path.join(path, ".git")):
            entry["ok"] = False
            entry["error"] = "不是 git 仓库（需先 clone 到 voga-repos/）"
            failed += 1
            results.append(entry)
            continue

        pull = _git(["pull", "--ff-only"], path)
        entry["pull_stdout"] = (pull.stdout or "").strip()
        entry["pull_stderr"] = (pull.stderr or "").strip()
        if pull.returncode != 0:
            entry["ok"] = False
            entry["error"] = entry["pull_stderr"] or entry["pull_stdout"] or f"git pull exit {pull.returncode}"
            failed += 1
            results.append(entry)
            continue

        rev = _git(["rev-parse", "--short", "HEAD"], path)
        branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)
        entry["ok"] = True
        entry["head"] = (rev.stdout or "").strip() if rev.returncode == 0 else ""
        entry["branch"] = (branch.stdout or "").strip() if branch.returncode == 0 else ""
        results.append(entry)

    return {
        "repos_dir": base,
        "config": os.path.join(config_dir(), "repos.json"),
        "ok": failed == 0,
        "failed": failed,
        "results": results,
    }
