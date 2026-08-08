# GitHub Pages 演示部署

固定地址（`yaahlan` 分支推送后自动更新）：

```text
https://chenmo19910907-prog.github.io/yaahlanAgent/
```

| 入口 | 路径 |
|------|------|
| Web Agent 对话（假数据） | `/web-agent/` |
| Keynote 产品演示 | `/keynote/` |

## 一次性开通

1. 打开 https://github.com/chenmo19910907-prog/yaahlanAgent/settings/pages
2. **Source** → **Deploy from a branch**
3. **Branch** → `gh-pages` / **(root)**
4. Save

## 本地构建与预览

```bash
bash scripts/build-github-pages-demo.sh
cd docs && python3 -m http.server 8765
# 浏览器打开 http://127.0.0.1:8765/web-agent/
```

## 说明

- **Keynote**：完整静态演示，可直接浏览。
- **Web Agent**：完整 `chat.html` 界面 + `demo-api.js` 假数据 Mock（会话列表、发消息、流式回复、能力目录等），**不依赖服务端**。
- 完整 MOA / Tunnel / 钉钉 / 真实 Agent 执行需本机运行 `platform/web_agent/server.py`。

## 实现要点

- 构建脚本：`scripts/build-github-pages-demo.sh`
- Mock 层：`platform/web_agent/static-demo/demo-api.js`
- Fixtures 导出：`platform/web_agent/static-demo/export-fixtures.py`
