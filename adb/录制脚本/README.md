# Yaahlan 录制脚本库

本目录集中存放已验证的 ADB 操作脚本，**统一使用中文名**调用；英文 `id` 仍兼容。

## 目录结构（积木模型）

```
录制脚本/
  索引.json              # 总目录；片段 module 对齐 testcase-kb
  片段/
    注册登录/            # testcase-kb/注册登录.md
    游戏/                # testcase-kb/游戏.md
    房间/                # testcase-kb/房间.md
    房间PK/              # testcase-kb/房间PK.md
    礼物/                # testcase-kb/礼物.md
    消息/                # testcase-kb/消息.md
    动态/                # testcase-kb/动态.md
    个人主页/            # testcase-kb/个人主页.md
    家族/ … 装扮/ …      # 其余独立功能 kb 同名目录
```

**自动化只用片段（`macro`）+ 读图 / 抓包验收**，不用组合脚本。

### AI 读图模块（禁用 macro，除非 `--force-script`）

见 `索引.json` → `aiOperateModules`（与 testcase-kb 模块名一致，如 `游戏`、`房间`、`个人主页` 等）。

| 仍用固定脚本 | 说明 |
|-------------|------|
| **注册登录** | 登录、冷启、设置、弹窗 |
| **消息** | 消息帧 Tab 与子页 |
| **动态** | 发动态、话题、详情 |

**RTL 语言**：阿语等下原生 UI 可能左右镜像；`tap_pct` 按英文 LTR 录制。见 [`../README.md`](../README.md#app-语言与-rtl-镜像)。

知识库映射见 [`KB对照.md`](KB对照.md)（按 `testcase-kb/` 模块列出全部片段）。

## 命令示例

```bash
python3 adb/adb_execute.py scripts    # 含 fragmentsByModule 分组
python3 adb/adb_execute.py macro 切换动态底栏
python3 adb/adb_execute.py macro 退出登录
python3 adb/adb_execute.py macro 手机号登录 --text 13311111115
```

调用 **macro 只用片段中文名或 id**；步骤间 `capture` 读图或 Tunnel/Admin 验收。

## 成功即落库（Agent 必做）

验收通过且退出码 **0** 后：

1. **片段** `片段/<testcase-kb模块>/<中文名>.json`（`module` 与目录名、kb 文件名一致）
2. **登记** `索引.json`：`kind: fragment`、`module`、`file`
3. 更新本 README 与 `KB对照.md`

详见 [`../README.md`](../README.md#片段间验收串联多个-macro-时) 与 [`../使用方法.md`](../使用方法.md)。

## 开屏广告 / 设备适配

开屏与 Tunnel 说明见下文及 [`../README.md`](../README.md)；设备型号适配见 [`设备适配/README.md`](设备适配/README.md)。
