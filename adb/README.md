# ADB 截图视觉循环（adb/）

通过 **adb 连手机 → 截图 → Agent 读图算坐标 → 点击 → 再截图** 完成 UI 操作。截图目录默认只保留**最新 2 张**，更早的自动删除。

> **坐标由读图得出**：本工具负责截屏、清理旧图、按坐标点击；在 Cursor 对话里对最新 PNG 用视觉能力看元素位置，再换算为像素坐标执行 `tap`。

## 前置条件

- 已安装 `adb`（Android platform-tools）
- 手机 USB 调试已开启，或 `adb connect <ip>:5555`
- `adb devices` 中状态为 `device`

## 视觉循环流程

```text
1. capture          → 得到最新截图路径 + 宽高
2. （Agent 读 PNG） → 根据画面说明要点的元素，计算 (x, y)
3. tap x y          → 点击
4. capture          → 再找下一元素（旧图自动删到只剩 2 张）
```

## 命令

```bash
# 列出设备
python3 adb/adb_execute.py devices

# 截屏（JSON 含 path、width、height、kept、removed）
python3 adb/adb_execute.py capture

# 仅打印路径（方便脚本）
python3 adb/adb_execute.py capture --no-json

# 点击坐标
python3 adb/adb_execute.py tap 540 1200

# 滑动
python3 adb/adb_execute.py swipe 540 1800 540 600 --duration 400

# 返回键 / Home
python3 adb/adb_execute.py key 4
python3 adb/adb_execute.py key 3

# 屏幕尺寸 + 最新截图
python3 adb/adb_execute.py info

# 多台设备
python3 adb/adb_execute.py -s <serial> capture
```

## 截图目录

- 默认：`adb/screenshots/`
- 文件名：`screen_YYYYMMDD_HHMMSS_*.png`
- **保留策略**：每次 `capture` 后按修改时间排序，只留最新 **2** 张（可用 `--max-screenshots` 修改）

## 与 Agent 协作示例

用户对 Agent 说：「点礼物面板里的定制礼物」

1. Agent 执行：`python3 adb/adb_execute.py capture`
2. Agent 读取返回的 `path` 对应 PNG（Read 工具）
3. Agent 根据图中按钮位置与 `width`/`height` 计算中心点，例如 `(412, 1680)`
4. Agent 执行：`python3 adb/adb_execute.py tap 412 1680`
5. 需要下一步时再 `capture`，重复 2–4

## 说明

- 仅支持 **Android + adb**。
- 坐标原点为屏幕左上角；截图 PNG 像素与 `wm size` 一致时可直接用于 `tap`。
- 若截图与物理分辨率不一致，需按比例换算坐标。
