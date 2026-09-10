#!/usr/bin/env bash
# 一键准备钉钉小程序本地联调：启动 Web Agent → 写 config.json → 提示开放平台配置
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"
ENV_LOCAL="$REPO_ROOT/platform/dingtalk_gateway/.env.local"
PY="$REPO_ROOT/platform/dingtalk_gateway/.venv/bin/python3"
PORT=18766

pick_url() {
  if [[ -f "$REPO_ROOT/platform/web_agent/data/public_url.txt" ]]; then
    cat "$REPO_ROOT/platform/web_agent/data/public_url.txt"
    return 0
  fi
  local ip=""
  for iface in en0 en1 en5; do
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    [[ -n "$ip" ]] && break
  done
  if [[ -n "$ip" ]]; then
    echo "http://${ip}:${PORT}"
    return 0
  fi
  echo "http://127.0.0.1:${PORT}"
}

read_env() {
  local key="$1"
  grep -E "^${key}=" "$ENV_LOCAL" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r' || true
}

echo "==> 1/4 检查 Web Agent"
if ! curl -sf "http://127.0.0.1:${PORT}/api/meta" >/dev/null; then
  echo "    启动 Web Agent…"
  "$PY" "$REPO_ROOT/platform/web_agent/server.py" --ensure
fi
echo "    OK http://127.0.0.1:${PORT}/"

echo "==> 2/4 检查钉钉 OAuth 凭证"
CLIENT_ID="$(read_env DINGTALK_CLIENT_ID)"
CORP_ID="$(read_env DINGTALK_CORP_ID)"
if [[ -z "$CLIENT_ID" ]]; then
  echo "    ⚠️  DINGTALK_CLIENT_ID 为空"
  echo "    请打开 钉钉开放平台 → Yaahlan智能工具 → 凭证与基础信息"
  echo "    填入 platform/dingtalk_gateway/.env.local："
  echo "      DINGTALK_CLIENT_ID=dingxxxx"
  echo "      DINGTALK_CLIENT_SECRET=xxxx"
  echo "    免登暂不可用，小程序会降级到 OTP 登录页。"
else
  echo "    OK ClientId 已配置"
fi

echo "==> 3/4 写入小程序 config.json"
BASE_URL="$(pick_url)"
cat > "$DIR/config.json" <<EOF
{
  "webAgentBaseUrl": "${BASE_URL}",
  "corpId": "${CORP_ID}"
}
EOF
echo "    webAgentBaseUrl = ${BASE_URL}"
echo "    corpId = ${CORP_ID:-（空）}"

echo "==> 4/4 开放平台待办（需人工）"
HOST="$(python3 -c "from urllib.parse import urlparse; u=urlparse('${BASE_URL}'); print(u.hostname or '')")"
cat <<EOF

请在 https://open-dev.dingtalk.com/ 小程序应用里配置：
  - HTTP 安全域名：${HOST}
  - Webview 可信域名：${HOST}
  - 用钉钉开发者工具导入：${DIR}

若手机 4G 访问，请另开 tunnel：
  python3 platform/web_agent/expose_public.py
  然后把 config.json 的 webAgentBaseUrl 改成 HTTPS 公网地址。

EOF

if [[ -d "/Applications/钉钉开发者工具.app" ]]; then
  open -a "钉钉开发者工具" "$DIR" || true
  echo "已尝试打开钉钉开发者工具。"
else
  echo "未检测到钉钉开发者工具，请手动安装后导入目录。"
fi
