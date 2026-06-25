#!/usr/bin/env python3
"""将客服转工单用例测试步骤转换为 1. 2. 编号格式。"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "temporary_testcase/客服转工单_测试用例.md"
DST = SRC


def _normalize_existing(step: str) -> str:
    parts = re.split(r"(?:<br>|\n)+", step.strip())
    lines = []
    n = 1
    for p in parts:
        p = re.sub(r"^\d+[\.\、]\s*", "", p.strip())
        if p:
            lines.append(f"{n}.{p}")
            n += 1
    return "\n".join(lines)


def _split_comma(step: str) -> list[str]:
    """按中文逗号拆分，保留语义完整的子句。"""
    raw = [p.strip() for p in step.split("，") if p.strip()]
    if len(raw) <= 1:
        return raw

    merged: list[str] = []
    buf = ""
    for part in raw:
        candidate = f"{buf}，{part}" if buf else part
        # 过短片段与下一片段合并（如「用户 VIP≥1」）
        if buf and len(part) < 8 and not any(
            k in part for k in ("点击", "查看", "打开", "进入", "选择", "确认", "长按", "滑动", "分别", "对比")
        ):
            buf = candidate
        else:
            if buf:
                merged.append(buf)
            buf = part
    if buf:
        merged.append(buf)
    return merged


def convert_step(step: str, module: str, expected: str) -> str:
    step = step.strip()
    if re.match(r"^1[\.\、]", step):
        return _normalize_existing(step)

    if "→" in step:
        parts = [p.strip() for p in step.split("→") if p.strip()]
        return "\n".join(f"{i + 1}.{p}" for i, p in enumerate(parts))

    for sep in ("；", ";"):
        if sep in step:
            parts = [p.strip() for p in step.split(sep) if p.strip()]
            return "\n".join(f"{i + 1}.{p}" for i, p in enumerate(parts))

    # 特殊：全链路/分别/对比类补充前置
    if step.startswith("分别以"):
        return f"1.{step}\n2.分别执行转单相关操作并观察结果"

    if "分别用" in step or "对比" in step:
        parts = _split_comma(step)
        if len(parts) > 1:
            return "\n".join(f"{i + 1}.{p}" for i, p in enumerate(parts))

    parts = _split_comma(step)
    if len(parts) >= 2:
        return "\n".join(f"{i + 1}.{p}" for i, p in enumerate(parts))

    # 单句补充操作+验证两步
    if any(k in step for k in ("查看", "观察", "核对", "对比")):
        return f"1.{step}\n2.核对展示/交互结果"

    if any(k in step for k in ("点击", "打开", "进入", "选择", "确认", "长按", "滑动")):
        return f"1.{step}\n2.观察页面反馈与状态变化"

    # 纯状态/条件描述，补操作步骤
    if "服务端" in step:
        return f"1.{step}\n2.客服已接工单，进入聊天页执行转单操作"

    if step.startswith("用户") and "联系" in step:
        return f"1.准备满足条件的测试用户\n2.{step}"

    if "客服" in step and ("转出" in step or "转单" in step or "接单" in step):
        return f"1.准备满足前置条件的客服账号与工单\n2.{step}\n3.观察工单/会话状态"

    if "App 语言" in step or "iOS" in step or "Android" in step:
        return f"1.{step}\n2.执行转单相关操作并查看文案/布局"

    return f"1.{step}\n2.验证预期结果"


def parse_and_convert(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("|------"):
                continue
            if "编号" in line and "功能模块" in line:
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) < 4 or not parts[0].startswith("KFZD_"):
                continue
            num, module, step, expected = parts[0], parts[1], parts[2], parts[3]
            new_step = convert_step(step, module, expected)
            rows.append([num, module, new_step, expected])
    return rows


def write_md(rows: list[list[str]], path: Path) -> None:
    header = """# 客服转工单测试用例

> 来源：[Yaahlan-2.5.4 版本需求](https://alidocs.dingtalk.com/i/nodes/o14dA3GK8g5ZowNwsKLPGKpAV9ekBD76) · 客服转工单模块  
> 目标 Excel：[Sheet22](https://alidocs.dingtalk.com/i/nodes/m9bN7RYPWdlGBEgEtbAR2yr9WZd1wyK0)  
> 步骤格式：`1.xxx\\n2.xxx` 编号步骤

| 编号 | 功能模块 | 测试步骤 | 预期结果 |
|------|----------|----------|----------|
"""
    body_lines = []
    for r in rows:
        step_md = r[2].replace("\n", "\\n")
        body_lines.append(f"| {r[0]} | {r[1]} | {step_md} | {r[3]} |")
    body = "\n".join(body_lines)
    path.write_text(header + body + "\n", encoding="utf-8")


def main():
    rows = parse_and_convert(SRC)
    # 重新从当前文件读原始（若已转换则基于最新）
    # 首次运行：先读旧版再转换
    old_path = SRC
    content = old_path.read_text(encoding="utf-8")
    if "1." not in content.split("KFZD_001")[1][:80]:
        # 从备份逻辑：直接解析当前单行版
        pass
    write_md(rows, DST)
    print(f"Converted {len(rows)} cases -> {DST}")
    # 打印样例
    for r in rows[:3]:
        print(r[0], "=>", r[2][:120])


if __name__ == "__main__":
    main()
