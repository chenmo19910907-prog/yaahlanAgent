# Yaahlan Web Agent · 钉钉小程序

钉钉小程序 **只做 UI 壳**，内嵌现有 Web Agent H5（`chat.html`）。Agent 执行、MOA/Tunnel/ADB 仍在本地 `platform/web_agent/server.py`。

## 架构

```text
钉钉小程序 (web-view)
  └─► HTTPS Web Agent /chat.html
        └─► 本地 Python 服务 (:18766) + cursor_sdk + 工具链
```

## 前置条件

1. 本地 Web Agent 已启动：`python3 platform/web_agent/server.py --serve`
2. 公网 HTTPS 地址（小程序 **不能** 填 `127.0.0.1`）：
   ```bash
   python3 platform/web_agent/expose_public.py
   ```
3. `platform/dingtalk_gateway/.env.local` 已配置：
   - `DINGTALK_CORP_ID`
   - `DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET`（或 Aegis 凭证）
   - `WEB_AGENT_DINGTALK_OAUTH=1`

## 钉钉开放平台配置

登录 [钉钉开放平台](https://open-dev.dingtalk.com/) → 你的小程序应用：

| 配置项 | 说明 |
|--------|------|
| **HTTP 安全域名** | Web Agent 公网域名，如 `xxx.trycloudflare.com` |
| **Webview 可信域名** | 同上（web-view 加载 H5 必须配置） |
| **应用首页** | 小程序发布版，非 H5 地址 |

保存后需用 **钉钉开发者工具** 重新上传小程序版本，域名才会生效。

## 本地配置

1. 复制配置：
   ```bash
   cp platform/dingtalk_miniapp/config.example.json platform/dingtalk_miniapp/config.json
   ```
2. 编辑 `config.json`：
   ```json
   {
     "webAgentBaseUrl": "https://你的公网域名",
     "corpId": "dingxxxx"
   }
   ```
   `corpId` 可与 `.env.local` 中 `DINGTALK_CORP_ID` 一致；留空则仅打开 H5，由页面内 OAuth 处理。

3. `config.json` 已 gitignore，勿提交公网地址。

## 开发与上传

1. 安装 [钉钉开发者工具](https://open.dingtalk.com/document/org/download-development-tools)
2. 导入目录：`platform/dingtalk_miniapp`
3. 填写小程序 AppId（开放平台应用详情）
4. 编译 → 真机预览 / 上传版本 → 工作台发布

## 登录流程

1. 小程序首页 `dd.getAuthCode` 取免登码
2. `dd.httpRequest` → `POST /api/auth/dingtalk-oauth`（与 H5 相同接口）
3. 成功后 `web-view` 打开 `{baseUrl}/chat.html`

若免登失败，web-view 会降级打开 `/login.html`（OTP 验证码登录）。

## 与 H5 微应用的区别

| 方式 | 说明 |
|------|------|
| **钉钉小程序（本目录）** | 独立小程序入口，web-view 嵌 H5 |
| **H5 微应用** | 工作台直接配 HTTPS 首页，已有 `dingtalk_oauth.js` |

两者 UI 相同；小程序多一层壳，便于单独上架/固定入口。

## 限制

- 服务端必须在手机可达的网络（局域网 IP 或 tunnel HTTPS）
- web-view 内 H5 的钉钉 JSAPI 能力有限，免登优先在小程序页完成
- SSE 流式对话依赖 web-view 内浏览器能力，与 H5 一致
