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
    """按 tab 名称查找 sheetId"""
    sheets = await list_sheets(token, op, workbook_id)
    for s in sheets:
        if s.get("name") == sheet_name:
            return s.get("sheetId")
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
    """找 A 列最后有数据的行号（1-indexed）"""
    values = await read_range(token, op, workbook_id, sheet_id, f"A1:A{max_row}")
    last = 0
    for i, row in enumerate(values):
        if row and any(c for c in row):
            last = i + 1
    return last


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
    版本用例表第 7 行：B7 为「覆盖率任务代码质量平台」时，C7、D7 可填需求所属分支名；否则忽略。
    """
    b7 = _cell_at(values, 7, 1)
    if b7.replace(" ", "") != COVERAGE_QUALITY_PLATFORM_B7.replace(" ", ""):
        return []
    out: list[str] = []
    for col in (2, 3):
        br = _parse_branch_cell(_cell_at(values, 7, col))
        if br and br not in out:
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
    返回 {"repos": [...], "requirement_branches": [...]}；
    requirement_branches 仅当 B7 为覆盖率任务代码质量平台且 C7/D7 有内容时非空。
    """
    b7_branches = extract_b7_requirement_branches(values)
    repos = _merge_b7_branches(_extract_repo_info_from_remarks(values), b7_branches)
    return {"repos": repos, "requirement_branches": b7_branches}


def extract_repo_info(values: list[list]) -> list[dict]:
    """
    从 Sheet values 中提取仓库/分支信息。
    扫描备注「仓库：」「分支：」；若 B7=覆盖率任务代码质量平台，则读取 C7/D7 分支名并补全缺省分支。
    返回 [{"repo": "voga-mts-user", "branch": "feature/buddyType"}, ...]
    """
    return extract_sheet_git_context(values)["repos"]


# ── 写入 ─────────────────────────────────────────────────────────────────
async def write_range(token: str, op: str, workbook_id: str, sheet_id: str,
                       rows: list[list], start_row: int, start_col: str = "A") -> bool:
    """
    从 start_row 起批量写入 rows（每行 = [A, B, C, D] 等）。
    自动推算结束列（按 rows[0] 的长度）。
    """
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


# ── 快速入口（命令行测试用）───────────────────────────────────────────────
if __name__ == "__main__":
    async def _demo():
        token, op = await get_token()
        print(f"Token 获取成功，operatorId={op}")

        # 示例：列举 sheets
        # sheets = await list_sheets(token, op, "YOUR_WORKBOOK_ID")
        # for s in sheets:
        #     print(f"  {s['name']} -> {s['sheetId']}")

    asyncio.run(_demo())
