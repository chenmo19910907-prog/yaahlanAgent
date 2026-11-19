"""
DingTalk AliDocs Sheet 读写工具（供 code-testcase-review skill 调用）

用法：
    import asyncio
    from scripts.dingtalk_sheet import get_token, read_range, write_range, mark_fail

    token, op = asyncio.run(get_token())
    values = asyncio.run(read_range(token, op, WORKBOOK_ID, SHEET_ID, "A1:E300"))
    asyncio.run(write_range(token, op, WORKBOOK_ID, SHEET_ID, cases, start_row=100))
    asyncio.run(mark_fail(token, op, WORKBOOK_ID, SHEET_ID, [12, 35, 59]))
"""
import asyncio

# ── 固定常量 ──────────────────────────────────────────────────────────────
TOKEN_URL    = "http://gaia-hg.momo.com/ding/excel/token"
AEGIS_KEY    = "6e187070-8dfc-4260-94b2-3a87d2408479"
AEGIS_SECRET = "b64afa70-52ce-4c3f-9221-d4bf83ddf265"
WORKID       = "110762"
API_BASE     = "https://api.dingtalk.com/v1.0/doc"

_BASE_HEADERS = {"User-Agent": "Mozilla/5.0", "content-type": "application/json"}


def _auth_headers(token: str) -> dict:
    return {**_BASE_HEADERS, "x-acs-dingtalk-access-token": token}


# ── Token ────────────────────────────────────────────────────────────────
async def get_token() -> tuple[str, str]:
    """返回 (access_token, operatorId)"""
    import httpx

    url = f"{TOKEN_URL}?aegisKey={AEGIS_KEY}&aegisSecret={AEGIS_SECRET}&workid={WORKID}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, headers=_BASE_HEADERS)
        d = r.json()
        return d["data"]["token"], d["data"]["operatorId"]


# ── 列举 Sheet ───────────────────────────────────────────────────────────
async def list_sheets(token: str, op: str, workbook_id: str) -> list[dict]:
    """返回 [{"sheetId": ..., "name": ...}, ...]"""
    import httpx

    url = f"{API_BASE}/workbooks/{workbook_id}/sheets?operatorId={op}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, headers=_auth_headers(token))
        data = r.json()
        raw = data.get("sheets")
        if raw is None:
            raw = data.get("value")
        if not isinstance(raw, list):
            return []
        out: list[dict] = []
        for s in raw:
            if not isinstance(s, dict):
                continue
            sid = s.get("sheetId") or s.get("id")
            name = s.get("name")
            if sid and name:
                out.append({"sheetId": sid, "name": name})
        return out


async def find_sheet_id(token: str, op: str, workbook_id: str, sheet_name: str) -> str | None:
    """按 tab 名称查找 sheetId（API 可能返回 id 或 sheetId）"""
    sheets = await list_sheets(token, op, workbook_id)
    for s in sheets:
        if s.get("name") == sheet_name:
            return s.get("sheetId") or s.get("id")
    return None


# ── 读取 ─────────────────────────────────────────────────────────────────
async def read_range(token: str, op: str, workbook_id: str, sheet_id: str, range_str: str) -> list[list]:
    """读取指定范围，返回二维列表"""
    import httpx

    url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{range_str}?operatorId={op}"
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(url, headers=_auth_headers(token))
        return r.json().get("values", [])


async def find_last_data_row(token: str, op: str, workbook_id: str, sheet_id: str,
                              max_row: int = 600) -> int:
    """找 A 列最后有数据的行号（1-indexed）。勿用于补用例定位（表头 A 列常为空）。"""
    values = await read_range(token, op, workbook_id, sheet_id, f"A1:A{max_row}")
    last = 0
    for i, row in enumerate(values):
        if row and any(c for c in row):
            last = i + 1
    return last


def detect_header_row(values: list[list]) -> int:
    """表头行：B 列含「功能模块」或 A 列「用例编号」。默认 6。"""
    for row_1 in range(4, 16):
        if _cell_at(values, row_1, 0) == "用例编号":
            return row_1
        if "功能模块" in _cell_at(values, row_1, 1):
            return row_1
    return 6


def detect_case_start_row(values: list[list]) -> int:
    """
    首条用例行（1-based）。跳过 B=覆盖率任务代码质量平台 的配置行（常在 7–8 行）。
    """
    header = detect_header_row(values)
    row_1 = header + 1
    while row_1 <= min(len(values), header + 12):
        b = _cell_at(values, row_1, 1)
        if b.replace(" ", "") == COVERAGE_QUALITY_PLATFORM_B7.replace(" ", ""):
            row_1 += 1
            continue
        c, d = _cell_at(values, row_1, 2), _cell_at(values, row_1, 3)
        if c or d:
            return row_1
        row_1 += 1
    return header + 1


def protected_row_end(values: list[list]) -> int:
    """禁止写入 A–D 的上边界（含表头与覆盖率配置行）。"""
    start = detect_case_start_row(values)
    return max(1, start - 1)


def find_last_case_row_from_values(values: list[list], case_start: int | None = None) -> int:
    """按 C/D 列（步骤/预期）定位最后一条用例行，1-based。"""
    if case_start is None:
        case_start = detect_case_start_row(values)
    last = case_start - 1
    for i in range(case_start - 1, len(values)):
        row = values[i]
        if not row:
            continue
        c = str(row[2]).strip() if len(row) > 2 else ""
        d = str(row[3]).strip() if len(row) > 3 else ""
        if c or d:
            last = i + 1
    return last


async def find_last_case_row(token: str, op: str, workbook_id: str, sheet_id: str,
                             max_row: int = 800) -> tuple[int, int]:
    """
    返回 (last_case_row, append_start_row)。
    append_start_row = last_case_row + 1，且一定大于 protected_row_end。
    """
    values = await read_range(token, op, workbook_id, sheet_id, f"A1:D{max_row}")
    case_start = detect_case_start_row(values)
    last = find_last_case_row_from_values(values, case_start)
    append_at = max(last + 1, protected_row_end(values) + 1)
    return last, append_at


_REPO_NAME_RE = __import__("re").compile(
    r"(voga[_\-a-z0-9]+|yaahlan[_\-a-z0-9]+|voga_android|voga_ios(?:_modules)?)",
    __import__("re").I,
)


def _parse_repo_names_from_cell(raw: str) -> list[str]:
    """从覆盖率行 C 列解析仓名，如「服务端voga-mts-user，voga-mts-components」。"""
    if not raw:
        return []
    found = _REPO_NAME_RE.findall(raw.replace("，", ",").replace("、", ","))
    out: list[str] = []
    for name in found:
        name = name.strip().rstrip("，,。")
        if name and name not in out:
            out.append(name)
    return out


def extract_coverage_platform_repos(values: list[list]) -> list[dict]:
    """
    扫描 B=覆盖率任务代码质量平台 的行：C 列仓库描述，D 列分支。
  常见为多行（服务端一行、H5 一行）。
    """
    repos: list[dict] = []
    for row_1 in range(6, min(len(values) + 1, 25)):
        b = _cell_at(values, row_1, 1)
        if b.replace(" ", "") != COVERAGE_QUALITY_PLATFORM_B7.replace(" ", ""):
            continue
        branch = _parse_branch_cell(_cell_at(values, row_1, 3)) or _cell_at(values, row_1, 3)
        for repo in _parse_repo_names_from_cell(_cell_at(values, row_1, 2)):
            repos.append({"repo": repo, "branch": branch or "main", "coverage_row": row_1})
    return repos


COVERAGE_QUALITY_PLATFORM_B7 = "覆盖率任务代码质量平台"


def _cell_at(values: list[list], row_1indexed: int, col_0indexed: int) -> str:
    """Sheet 行号为 1 起；values 下标 0 对应第 1 行。"""
    ridx = row_1indexed - 1
    if ridx < 0 or ridx >= len(values):
        return ""
    row = values[ridx]
    if col_0indexed < 0 or col_0indexed >= len(row):
        return ""
    return str(row[col_0indexed] or "").strip()


def _parse_branch_cell(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if "分支：" in s or "分支:" in s:
        parts = s.replace("分支：", "分支:").split("分支:")
        if len(parts) > 1:
            return parts[1].strip().split()[0].strip("，,。")
    return s.split()[0].strip("，,。") if s else ""


def extract_b7_requirement_branches(values: list[list]) -> list[str]:
    """
    覆盖率配置行：分支在 **D 列**（C 列为仓库描述，勿当分支解析）。
    """
    out: list[str] = []
    for row_1 in range(6, min(len(values) + 1, 25)):
        if _cell_at(values, row_1, 1).replace(" ", "") != COVERAGE_QUALITY_PLATFORM_B7.replace(" ", ""):
            continue
        br = _parse_branch_cell(_cell_at(values, row_1, 3)) or _cell_at(values, row_1, 3)
        if not br:
            continue
        low = br.lower()
        if "voga" in low or "yaahlan" in low or "服务端" in br or "前端" in br:
            continue
        if br not in out:
            out.append(br)
    return out


def _extract_repo_info_from_remarks(values: list[list]) -> list[dict]:
    """从 E 列等备注扫描「仓库：」「分支：」。"""
    repos: list[dict] = []
    repo, branch = None, None
    for row in values:
        for cell in row:
            cell = str(cell or "")
            if "仓库：" in cell or "仓库:" in cell:
                parts = cell.replace("仓库：", "仓库:").split("仓库:")
                for p in parts[1:]:
                    names = p.strip().split("、")
                    for n in names:
                        n = n.split()[0].strip().strip("，,。")
                        if n:
                            repo = n
            if "分支：" in cell or "分支:" in cell:
                parts = cell.replace("分支：", "分支:").split("分支:")
                if len(parts) > 1:
                    branch = parts[1].strip().split()[0].strip("，,。")
    if repo:
        for r in str(repo).split("、"):
            r = r.strip()
            if r:
                repos.append({"repo": r, "branch": branch or "main"})
    return repos


def _merge_b7_branches(repos: list[dict], b7_branches: list[str]) -> list[dict]:
    """B7 分支按顺序补全备注中缺省或未写明的 checkout 分支。"""
    if not b7_branches:
        return repos
    if not repos:
        return [{"repo": "", "branch": br, "from_b7": True} for br in b7_branches]
    for i, entry in enumerate(repos):
        if i >= len(b7_branches):
            break
        cur = (entry.get("branch") or "").strip()
        if not cur or cur == "main":
            entry["branch"] = b7_branches[i]
            entry["branch_from_b7"] = True
    return repos


def extract_sheet_git_context(values: list[list]) -> dict:
    """
    汇总拉代码所需信息。
    返回 {"repos", "requirement_branches", "case_start_row", "protected_end_row"}。
    优先：覆盖率配置行 C/D；其次 E 列备注；B7 C/D 分支补全。
    """
    b7_branches = extract_b7_requirement_branches(values)
    repos = extract_coverage_platform_repos(values)
    if not repos:
        repos = _extract_repo_info_from_remarks(values)
    repos = _merge_b7_branches(repos, b7_branches)
    return {
        "repos": repos,
        "requirement_branches": b7_branches,
        "case_start_row": detect_case_start_row(values),
        "protected_end_row": protected_row_end(values),
    }


def extract_repo_info(values: list[list]) -> list[dict]:
    """
    从 Sheet values 中提取仓库/分支信息。
    扫描备注「仓库：」「分支：」；若 B7=覆盖率任务代码质量平台，则读取 C7/D7 分支名并补全缺省分支。
    返回 [{"repo": "voga-mts-user", "branch": "feature/buddyType"}, ...]
    """
    return extract_sheet_git_context(values)["repos"]


# ── 写入 ─────────────────────────────────────────────────────────────────
async def write_range(token: str, op: str, workbook_id: str, sheet_id: str,
                       rows: list[list], start_row: int, start_col: str = "A",
                       protected_end_row: int = 0) -> bool:
    """
    从 start_row 起批量写入 rows（每行 = [A, B, C, D] 等）。
    protected_end_row>0 时禁止覆盖表头/覆盖率行。
    """
    if protected_end_row and start_row <= protected_end_row:
        raise ValueError(
            f"拒绝写入：start_row={start_row} 位于保护区 1–{protected_end_row}（表头/覆盖率配置）"
        )
    if not rows:
        return True
    num_cols = max(len(r) for r in rows)
    end_col = chr(ord(start_col) + num_cols - 1)
    end_row = start_row + len(rows) - 1
    range_str = f"{start_col}{start_row}:{end_col}{end_row}"
    url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{range_str}?operatorId={op}"
    normalized = [[str(c) for c in row] for row in rows]
    import httpx

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.put(url, headers=_auth_headers(token), json={"values": normalized})
        ok = r.status_code in (200, 204)
        print(f"写入 {range_str}：{'OK' if ok else f'失败 {r.status_code} {r.text[:100]}'}")
        return ok


async def mark_fail(token: str, op: str, workbook_id: str, sheet_id: str,
                     row_nums: list[int], reason: str = "") -> None:
    """
    在指定行的 E 列写入 'fail'，可选在 F 列写原因。
    """
    import httpx

    async with httpx.AsyncClient(timeout=20) as c:
        for row in row_nums:
            if reason:
                rng = f"E{row}:F{row}"
                val = [["fail", reason]]
            else:
                rng = f"E{row}"
                val = [["fail"]]
            url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{rng}?operatorId={op}"
            r = await c.put(url, headers=_auth_headers(token), json={"values": val})
            print(f"  行{row} E列 → fail {'(+ reason)' if reason else ''}，状态 {r.status_code}")


# ── 同步 HTTP（无 httpx 时 Web Agent / 本机 CLI 使用）────────────────────
import json as _json
import urllib.request as _urllib_request


def get_token_sync() -> tuple[str, str]:
    url = f"{TOKEN_URL}?aegisKey={AEGIS_KEY}&aegisSecret={AEGIS_SECRET}&workid={WORKID}"
    req = _urllib_request.Request(url, headers=_BASE_HEADERS)
    with _urllib_request.urlopen(req, timeout=30) as r:
        d = _json.loads(r.read())
    return d["data"]["token"], d["data"]["operatorId"]


def _http_get_sync(url: str, token: str) -> dict:
    headers = {**_auth_headers(token)}
    req = _urllib_request.Request(url, headers=headers)
    with _urllib_request.urlopen(req, timeout=60) as r:
        return _json.loads(r.read())


def _http_put_sync(url: str, token: str, payload: dict) -> int:
    body = _json.dumps(payload).encode()
    headers = {**_auth_headers(token)}
    req = _urllib_request.Request(url, data=body, headers=headers, method="PUT")
    with _urllib_request.urlopen(req, timeout=60) as r:
        return r.status


def find_sheet_id_sync(token: str, op: str, workbook_id: str, sheet_name: str) -> str | None:
    data = _http_get_sync(f"{API_BASE}/workbooks/{workbook_id}/sheets?operatorId={op}", token)
    for s in data.get("sheets") or data.get("value") or []:
        if s.get("name") == sheet_name:
            return s.get("sheetId") or s.get("id")
    return None


def read_range_sync(token: str, op: str, workbook_id: str, sheet_id: str, range_str: str) -> list[list]:
    url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{range_str}?operatorId={op}"
    return _http_get_sync(url, token).get("values", [])


def write_range_sync(
    token: str,
    op: str,
    workbook_id: str,
    sheet_id: str,
    rows: list[list],
    start_row: int,
    start_col: str = "A",
    protected_end_row: int = 0,
) -> int:
    if protected_end_row and start_row <= protected_end_row:
        raise ValueError(
            f"拒绝写入：start_row={start_row} 位于保护区 1–{protected_end_row}"
        )
    if not rows:
        return 204
    num_cols = max(len(r) for r in rows)
    end_col = chr(ord(start_col) + num_cols - 1)
    end_row = start_row + len(rows) - 1
    range_str = f"{start_col}{start_row}:{end_col}{end_row}"
    url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{range_str}?operatorId={op}"
    normalized = [[str(c) for c in row] for row in rows]
    return _http_put_sync(url, token, {"values": normalized})


def mark_fail_sync(
    token: str,
    op: str,
    workbook_id: str,
    sheet_id: str,
    items: list[tuple[int, str]],
) -> None:
    for row, reason in items:
        rng = f"E{row}:F{row}" if reason else f"E{row}"
        val = [["fail", reason[:450]]] if reason else [["fail"]]
        url = f"{API_BASE}/workbooks/{workbook_id}/sheets/{sheet_id}/ranges/{rng}?operatorId={op}"
        _http_put_sync(url, token, {"values": val})


def workbook_id_from_url(url: str) -> str:
    """从 alidocs 链接提取 nodes/{id}。"""
    if "/nodes/" not in url:
        raise ValueError("非 AliDocs nodes URL")
    return url.split("/nodes/", 1)[1].split("?")[0].strip("/")


# ── 快速入口（命令行测试用）───────────────────────────────────────────────
if __name__ == "__main__":
    async def _demo():
        token, op = await get_token()
        print(f"Token 获取成功，operatorId={op}")

    asyncio.run(_demo())
