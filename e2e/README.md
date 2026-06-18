# E2E · 识别 → 思考 → 执行（单步 ≤3s）

与 **`adb/` 宏片段路线独立**的自然语言安卓自动化。

**命令速查**：[使用方法.md](使用方法.md)

## 单步预算（默认 3 秒）

```text
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐
│ 识别     │ → │ 思考     │ → │ 执行     │ → │ 步后轻验收  │
│ ≤1.4s    │   │ ≤0.1s    │   │ ≤0.6s    │   │ ≤0.8s      │
│ observe  │   │ 内存匹配 │   │ tap/text │   │ activity   │
└──────────┘   └──────────┘   └──────────┘   └────────────┘
```

| 阶段 | 模块 | 快路径 |
|------|------|--------|
| 识别 | `perceive.py` | `observe --fast --ui-limit 30` |
| 思考 | `think.py` | 自然语言 → Plan（无 IO） |
| 执行 | `act.py` | 单次 adb 子进程，超时 2.5s |
| 步后 | `perceive.py` | 默认 **`activity` + sceneGate** |

配置：[config.json](config.json) → `loop.timing`、`loop.postAct`；步骤门禁 → [config/step_hints.json](config/step_hints.json) 的 `requireSceneBefore` / `expectSceneAfter`。

## 目录结构

```
e2e/
├── e2e_execute.py
├── config.json              # 单步 3s 预算
├── cases/                   # 自然语言 flow[]
├── reports/                 # 含 timingMs
└── e2e/
    ├── budget.py            # StepBudget / StepTimer
    ├── loop_cycle.py        # 单步流水线
    ├── perceive.py          # 识别（快/轻量）
    ├── think.py             # 思考
    ├── act.py               # 执行
    ├── runner.py              # 用例编排
    ├── kb.py                # 知识库 hints 缓存
    └── adb_bridge.py        # adb 子进程
```

## 用例（自然语言）

```json
{
  "module": "注册登录",
  "flow": ["点击手机号登录", "输入手机号", "点击登录"],
  "verify": [{ "type": "tunnel", "keyword": "login" }]
}
```

## 命令

```bash
python3 e2e/e2e_execute.py doctor          # 显示 stepBudgetMs
python3 e2e/e2e_execute.py cycle --step "点击手机号登录" --case nl-login-smoke
python3 e2e/e2e_execute.py run --case nl-login-smoke
```

报告字段 `timingMs`：`perceive` / `think` / `act` / `postAct` / `total` / `withinBudget`。

## 调优

| 场景 | 调整 |
|------|------|
| 步后需 UI 变化 | `postAct.mode` → `wait_observe`，`maxWaitSec` ≤ 0.5 |
| 仍超 3s | 降 `perceive.uiLimit`；WebView 才开 `--image` |
| 验收靠抓包 | `verify.tunnel` 放在用例末，不占单步预算 |

## 与 adb/

e2e **禁止** `macro` / `chain` / `accounts`；读屏用 `observe|locate|activity`，操作用 **e2e driver**（`launch`/`tap`/`text`/`key`）。步骤坐标来自 `e2e/config/step_hints.json`（对齐 verified-kb 路径，非 adb 片段）。

```bash
export E2E_DEVICE_SERIAL=172.18.212.12:5555   # 可选
python3 e2e/e2e_execute.py run --case nl-post-video-moment
```

规则：`.cursor/rules/e2e-perceive-think-act.mdc`
