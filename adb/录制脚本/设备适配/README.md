# 设备型号坐标适配

录制脚本里的 `tap_pct` 按 **基准设备**（`基准设备.json`，默认 1080×2340）书写。  
**同一机型型号**只需校准一次；之后自动 **复用已存换算**，不重新拟合。

## 原则

| 情况 | 做法 |
|------|------|
| 型号已有档案 | `device info` 为 `matched` → 直接 `macro` / `flow run` |
| 分辨率与基准相同、无档案 | `identity`，比例 1:1 |
| 新型号、无档案 | 先 `device calibrate` → `set` → `commit` |
| **操作失败**（点偏、未进页） | `device recalibrate` → 重新读图填点 → `commit --reason correction` |

档案按 **`ro.product.model`（设备型号）** 匹配，并记录厂商、分辨率、`transform`、校准点 `anchors` 与变更历史 `history`。

## 首次：在基准录制机上（可选）

```bash
python3 adb/adb_execute.py device record-reference
```

把当前手机的 **型号、分辨率** 写入 `基准设备.json`，与片段里 `recordedOn` 对齐。

## 换机：新型号校准一次

```bash
python3 adb/adb_execute.py device info
python3 adb/adb_execute.py device calibrate --script 发布纯文本动态
# 读图填点
python3 adb/adb_execute.py device set --note "Moment" --pixel 756 2220
python3 adb/adb_execute.py device commit --id vivo_v2245 --name "vivo V2245"
```

`commit` 会写入 `档案/<id>.json`，索引里登记 **deviceModel**。

## 已保存机型：直接跑脚本

```bash
python3 adb/adb_execute.py device info
# matched → canRunRecordedScripts: true

python3 adb/adb_execute.py flow run 发布纯文本动态 --text 5555
```

执行结果含 `adaptation.reuseSavedTransform: true`，表示沿用档案中的 `scale/offset`，**基准 tap_pct 未改**。

若再次执行 `device calibrate` 且已有档案，会 **跳过** 并提示复用；勿重复计算。

## 操作失败：更正换算

1. 确认仍为目标 App、页面正确（导航阶段可 `flow locate` + 截图）。
2. 强制重新校准：

```bash
python3 adb/adb_execute.py device recalibrate --script 发布纯文本动态
python3 adb/adb_execute.py device set --note "Post" --pixel 979 119
# … 补全各 anchor
python3 adb/adb_execute.py device commit --id vivo_v2245 --name "vivo V2245" --reason correction
```

`commit --reason correction` 会 **更新** 同 id 档案、追加 `history`，不新建文件。

3. 再跑 `flow run` 验证。

## 换算公式（pct_linear）

\(x_{dev} = scale_x \cdot x_{ref} + offset_x\)，Y 同理。由校准点拟合，保存在档案 `transform`。

## 目录

| 路径 | 说明 |
|------|------|
| `基准设备.json` | 录制参考机型与分辨率 |
| `索引.json` | 已登记档案（含 deviceModel） |
| `档案/*.json` | 每机型换算 + anchors + history |
| `校准草稿/<serial>.json` | 进行中的校准 |

## 查看档案

```bash
python3 adb/adb_execute.py device profiles
python3 adb/adb_execute.py device show vivo_v2245
```
