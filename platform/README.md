# platform · 工具平台能力目录

汇总 **Admin / MOA / Risk / Tunnel / online / DingTalk** 已登记能力，生成交互式网页目录（**按功能模块合并展示**）。

## 打开目录

提到 **工具平台 / 输入工作台 / 新手引导 / 说明书** 等时，Agent 会自动执行：

```bash
python3 platform/open_catalog.py
```

生成 `catalog.html` 后**默认自动打开浏览器**（通过本地 HTTP 服务 `http://127.0.0.1:18765/catalog.html`）；若不要打开：`python3 platform/scripts/generate_catalog.py --no-open`

**执行**按钮与左侧 **检查环境配置** 均依赖本地 bridge（`open_catalog.py` 自动启动）：向 Cursor 输入框粘贴提示语。检查环境配置填入 `@新手上手.md 运行环境检查`。

## 页面内容

- **跨工具合并**：测试环境能力按 **一级功能模块** 归并；**线上环境能力** 单独归并在「线上环境」模块
- 一级模块 → 分类（完整 category 名）→ **能力名称**
- 每项标注来源工具（yaahlan后台 / MOA / 线上环境能力 等），线上能力高亮
- 每项左侧 **点击能力名称** 可展开/收起 **提示语**；可变参数为输入框；**执行** 经本地 bridge 填入 Cursor 当前聊天输入框（已打开则复用现有窗口，未打开则启动 Cursor）
- 支持按能力名、分类、来源、提示语搜索；左侧按一级模块筛选

归并规则：`platform/config/sources.json` 的 `top_level_rules`（如 `用户*` → 用户、`定制*` → 定制）

## 数据来源

| 工具模块 | registry |
|------|----------|
| yaahlan后台 | `Admin/config/registry.json` |
| MOA | `MOA/config/registry.json` |
| 风险控制 | `Risk/config/registry.json` |
| Tunnel抓包 | `Tunnel/config/registry.json` |
| 线上环境能力 | `online/config/registry.json` |
| 钉钉文档 | `DingTalk/config/registry.json` |

配置清单：`platform/config/sources.json`（含 `top_level_rules` 归并规则与 `top_level_order` 侧栏排序）

## 维护

各模块更新 `config/registry.json` 后，执行该模块的 `generate_index.py` 即可（**会自动同步** `platform/catalog.html`）：

```bash
python3 Admin/scripts/generate_index.py   # 或 MOA / Risk / Tunnel / online / DingTalk
```

也可单独刷新工具台，或导出离线版到桌面（**复制**按钮，无 Cursor bridge）：

```bash
python3 platform/scripts/generate_catalog.py
python3 platform/export_catalog.py          # → ~/Desktop/Yaahlan智能工具平台.html
# 或
python3 platform/open_catalog.py            # 左侧「导出到桌面」下载离线版
```

**新增整个工具模块**：除 `config/registry.json` 外，须在 `platform/config/sources.json` 的 `modules` 登记；未登记时生成 catalog 会 WARN。
