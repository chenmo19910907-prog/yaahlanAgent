# Yaahlan 录制脚本库

本目录集中存放已验证的 ADB 操作脚本，**统一使用中文名**调用；英文 `id` 仍兼容。

## 目录结构

```
录制脚本/
  索引.json          # 总目录（中文名 ↔ 文件）
  片段/              # 单段录制（原 macro）
  流程/              # 两阶段流程（locate → run）
```

## 脚本一览

| 中文名 | id | 类型 | 说明 |
|--------|-----|------|------|
| 切换动态底栏 | moment-tab | 片段 | 点底部 Moment |
| 切换我的底栏 | me-tab | 片段 | 点底部 Me |
| 进入个人资料详情页 | my-profile | 片段/流程 | Me → 头像 → 资料页 |
| 我的页进入个人资料详情 | my-profile-from-me | 片段 | 已在 Me 时点头像 |
| 发布纯文本动态 | post-moment | 片段/流程 | Moment → + → 输入 → Post |

## 命令示例

```bash
# 查看全部
python3 adb/adb_execute.py scripts

# 执行片段（中文名）
python3 adb/adb_execute.py macro 发布纯文本动态 --text 5555 --no-capture
python3 adb/adb_execute.py macro 进入个人资料详情页

# 两阶段流程（中文名）
python3 adb/adb_execute.py flow locate 发布纯文本动态
python3 adb/adb_execute.py flow bootstrap 发布纯文本动态 --from outside_app
python3 adb/adb_execute.py flow run 发布纯文本动态 --text 5555
```

目标 App 为 **Yaahlan**（`com.immomo.biz.yaahlan`），不是 Yaha。

## 设备型号适配

换机后先读 [`设备适配/README.md`](设备适配/README.md)：`device info` → `device calibrate`（截图填点）→ `device commit` → 再 `macro` / `flow run`。
