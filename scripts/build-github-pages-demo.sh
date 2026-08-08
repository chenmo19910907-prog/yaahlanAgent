#!/usr/bin/env bash
# 构建 GitHub Pages 静态演示（Keynote + Web Agent 完整界面，假数据无服务端）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="$ROOT/docs"
SRC="$ROOT/platform/web_agent"
STATIC="$SRC/static-demo"
OUT_WEB="$DOCS/web-agent"
BUILD_VERSION="$(date -u +%Y%m%d%H%M%S)"

rm -rf "$DOCS"
mkdir -p "$DOCS/keynote" "$OUT_WEB" "$OUT_WEB/config" "$OUT_WEB/assets" "$OUT_WEB/fixtures"

echo "==> 导出演示 fixtures"
python3 "$STATIC/export-fixtures.py"

echo "==> 复制 Keynote"
cp "$SRC/keynote/preview.html" "$DOCS/keynote/index.html"
mkdir -p "$DOCS/keynote/pk-atm-guide"
cp "$SRC/keynote/pk_atm_guide.html" "$DOCS/keynote/pk-atm-guide/index.html"
cp "$SRC/keynote/pk_atm_guide.md" "$DOCS/keynote/pk-atm-guide/pk_atm_guide.md"

echo "==> 复制 Platform Guide / Family PK Showcase"
mkdir -p "$DOCS/platform-guide"
cp "$ROOT/platform/exports/cursor-platform-guide/index.html" "$DOCS/platform-guide/index.html"
mkdir -p "$DOCS/family-pk-showcase"
if [[ -d "$ROOT/platform/family_pk_report/exports" ]] && [[ -n "$(ls -A "$ROOT/platform/family_pk_report/exports" 2>/dev/null)" ]]; then
  cp -R "$ROOT/platform/family_pk_report/exports/." "$DOCS/family-pk-showcase/"
else
  echo "    (跳过 family-pk-showcase：本地 exports 不存在，CI 环境可忽略)"
fi

echo "==> 修正静态页资源路径"
python3 - <<'PY' "$DOCS"
import sys
from pathlib import Path

docs = Path(sys.argv[1])

platform_guide = docs / "platform-guide" / "index.html"
if platform_guide.is_file():
    html = platform_guide.read_text(encoding="utf-8")
    html = html.replace('href="/assets/fonts/', 'href="../web-agent/assets/fonts/')
    html = html.replace('src="/platform-guide/images/', 'src="images/')
    html = html.replace('href="/keynote"', 'href="../keynote/"')
    html = html.replace('href="/keynote/"', 'href="../keynote/"')
    platform_guide.write_text(html, encoding="utf-8")

pk_guide = docs / "keynote" / "pk-atm-guide" / "index.html"
if pk_guide.is_file():
    html = pk_guide.read_text(encoding="utf-8")
    html = html.replace('href="/keynote"', 'href="../"')
    html = html.replace('href="/keynote/"', 'href="../"')
    pk_guide.write_text(html, encoding="utf-8")
PY

echo "==> 复制 Web Agent 静态资源"
cp "$SRC/chat.html" "$OUT_WEB/index.html"
cp "$STATIC/demo-fixtures.js" "$OUT_WEB/demo-fixtures.js"
cp "$STATIC/demo-api.js" "$OUT_WEB/demo-api.js"
cp "$STATIC/fixtures/"*.json "$OUT_WEB/fixtures/"

for js in theme.js logo.js dingtalk_oauth.js analytics.js bookmarks_panel.js \
  message_board_panel.js about_panel.js catalog_panel.js moa_record_panel.js waiting_fx.js; do
  cp "$SRC/$js" "$OUT_WEB/$js"
done

cp -R "$SRC/assets/." "$OUT_WEB/assets/"
cp "$SRC/config.json" "$OUT_WEB/config.json"
cp "$SRC/config/bookmarks.json" "$OUT_WEB/config/bookmarks.json"
cp "$SRC/config/web_docs.json" "$OUT_WEB/config/web_docs.json"

echo "==> 注入演示 API 与 keynote 路径 (build=$BUILD_VERSION)"
python3 - <<'PY' "$OUT_WEB/index.html" "$BUILD_VERSION"
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
build_version = sys.argv[2]
html = path.read_text(encoding="utf-8")

inject = (
    f'  <script src="demo-fixtures.js?v={build_version}"></script>\n'
    f'  <script src="demo-api.js?v={build_version}"></script>\n'
)
if "demo-api.js" not in html:
    html = html.replace(
        '<meta charset="utf-8" />\n',
        '<meta charset="utf-8" />\n' + inject,
        1,
    )
else:
    html = re.sub(
        r'<script src="demo-fixtures\.js[^"]*"></script>\n'
        r'\s*<script src="demo-api\.js[^"]*"></script>\n',
        inject,
        html,
        count=1,
    )

html = html.replace('src="/keynote?embed=', 'src="../keynote/?embed=')
html = html.replace('`/keynote?embed=', '`../keynote/?embed=')

html = re.sub(
    r"请运行：python3 platform/web_agent/open_web_agent\.py",
    "当前为 GitHub Pages 静态演示（假数据）",
    html,
)

demo_restore = """
      if (window.__WEB_AGENT_DEMO__) {
        const demoIds = ['demo0001stagegift', 'demo0002prdcases', 'demo0003moalookup'];
        for (const sid of demoIds) {
          try {
            await api(`/api/sessions/${sid}/messages`);
            if (await activateSession(sid, { force: true })) return;
          } catch { /* try next demo session */ }
        }
      }
"""
if "demo0001stagegift" not in html:
    html = html.replace(
        "async function restoreOrCreateInitialSession() {",
        "async function restoreOrCreateInitialSession() {" + demo_restore,
        1,
    )

html = html.replace("window.location.href = '/login.html'", "return")

path.write_text(html, encoding="utf-8")
PY

cp "$OUT_WEB/index.html" "$OUT_WEB/chat.html"

cat > "$DOCS/index.html" <<'HTML'
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Yaahlan 智能工具 Agent · 演示</title>
  <style>
    body {
      font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      background: linear-gradient(180deg, #0b0e14 0%, #151923 100%);
      color: #e8edf5;
    }
    main { width: min(92vw, 560px); padding: 2rem; }
    h1 { font-size: 1.5rem; margin: 0 0 0.5rem; }
    p { color: #a4adbd; line-height: 1.6; }
    .links { display: grid; gap: 12px; margin-top: 1.5rem; }
    a {
      display: block; padding: 16px 18px; border-radius: 12px; text-decoration: none;
      border: 1px solid rgba(148,163,184,.2); background: rgba(255,255,255,.03);
      color: #c7d2fe; transition: .15s ease;
    }
    a:hover { border-color: rgba(91,140,255,.55); background: rgba(91,140,255,.08); }
    strong { display: block; color: #f2f5fa; margin-bottom: 4px; }
    span { font-size: 0.9rem; color: #94a3b8; }
  </style>
</head>
<body>
  <main>
    <h1>Yaahlan 智能工具 Agent</h1>
    <p>对外演示入口（GitHub Pages 静态托管）。Web Agent 使用假数据模拟对话，不依赖服务端；完整 MOA / Tunnel / 用例生成需内网服务。</p>
    <div class="links">
      <a href="web-agent/"><strong>Web Agent 对话</strong><span>完整界面 + 假数据演示（可发消息、切换会话）</span></a>
      <a href="keynote/"><strong>Keynote 产品演示</strong><span>全屏产品演示与功能亮点</span></a>
      <a href="platform-guide/"><strong>用 Cursor 搭建智能工具平台</strong><span>从 MOA 到 Admin、Tunnel、钉钉文档、ADB 自动化</span></a>
      <a href="keynote/pk-atm-guide/"><strong>PK 提款机：从零到 MOA 与自动化</strong><span>真实协作案例与验收工作流</span></a>
      <a href="family-pk-showcase/"><strong>家族 PK 测试 Showcase</strong><span>复杂活动数据造表与验收演示</span></a>
    </div>
  </main>
</body>
</html>
HTML

touch "$DOCS/.nojekyll"

echo ""
echo "GitHub Pages 演示包已生成: $DOCS"
echo "  首页:      /"
echo "  Keynote:   /keynote/"
echo "  Web Agent: /web-agent/"
echo "  Platform Guide: /platform-guide/"
echo "  PK ATM Guide:   /keynote/pk-atm-guide/"
echo "  Family PK:      /family-pk-showcase/"
