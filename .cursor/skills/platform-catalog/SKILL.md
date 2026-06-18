---
name: platform-catalog
description: 工具平台能力目录网页。用户提到「工具平台」「输入工作台」「新手引导」「说明书」「平台能做什么」「工具平台清单」等时，必须执行 python3 platform/open_catalog.py 刷新并用浏览器打开 http://127.0.0.1:18765/catalog.html，再简要说明页面用法。
---

# 工具平台能力目录

## 触发词

- 工具平台、工具平台功能、工具平台能力、工具平台清单
- 输入工作台、工具工作台
- 新手引导、新手上手引导（指工具能力引导页，非 App 内新手引导）
- 说明书、工具说明书、平台说明书、能力说明书
- 平台能做什么、有哪些工具能力、打开工具平台

## 必须执行

```bash
python3 platform/open_catalog.py
```

该命令会：

1. 从各 registry 刷新 `platform/catalog.html` 并启动本地 HTTP 服务（`127.0.0.1:18765`）
2. 用系统默认浏览器打开 `http://127.0.0.1:18765/catalog.html`

## 回复用户

打开后简要说明：

- 页面为**跨工具合并的一级模块目录**（如用户、家族、定制），每项标注来源工具
- 每项可展开 **「提示语」**：**点击能力名称** 展开/收起；可变参数为输入框；**执行** 经本地 bridge 填入 Cursor 当前输入框（复用已打开窗口）
- 左侧 **检查环境配置**：经 bridge 向 Cursor 填入 `@新手上手.md 运行环境检查`
- 左侧 **导出到桌面**：下载离线版（提示语为 **复制** 按钮）；或 `python3 platform/export_catalog.py`
- 左侧可按一级模块筛选，搜索框可按能力名、分类、来源过滤

## 不要

- 不要只贴 Markdown 清单代替打开网页（除非用户明确不要开浏览器）
- 不要编造未在 registry 登记的能力
- 上下文明确讨论 App「新手引导」Bug/用例时，不触发本技能

## 维护

- 各模块更新 `config/registry.json` 后执行 `python3 <模块>/scripts/generate_index.py`，会**自动**刷新 `platform/catalog.html`
- 新增整个工具模块时，还须登记 `platform/config/sources.json`
- 打开工作台时 `open_catalog.py` 也会重新生成页面
