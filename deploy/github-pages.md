# GitHub Pages 演示部署

固定地址（`yaahlan` 分支推送后自动更新）：

```text
https://chenmo19910907-prog.github.io/yaahlanAgent/
```

| 入口 | 路径 |
|------|------|
| Web Agent 对话演示 | `/web-agent/` |
| Keynote 产品演示 | `/keynote/` |

## 一次性开通

1. 打开 https://github.com/chenmo19910907-prog/yaahlanAgent/settings/pages
2. **Source** → **Deploy from a branch**
3. **Branch** → `gh-pages` / **(root)**
4. Save

## 本地构建

```bash
bash scripts/build-github-pages-demo.sh
```

## 说明

- **Keynote**：完整静态演示，可直接浏览。
- **Web Agent**：公网为界面演示（Keynote 内嵌 `new-chat` 场景）；完整对话、MOA、Tunnel 等需本机运行 `platform/web_agent/server.py`。
