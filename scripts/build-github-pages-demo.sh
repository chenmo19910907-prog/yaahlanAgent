#!/usr/bin/env bash
# 构建 GitHub Pages 静态演示（Keynote + Web Agent 界面演示）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DOCS="$ROOT/docs"
SRC="$ROOT/platform/web_agent"

rm -rf "$DOCS"
mkdir -p "$DOCS/keynote" "$DOCS/web-agent"

cp "$SRC/keynote/preview.html" "$DOCS/keynote/index.html"

cat > "$DOCS/web-agent/index.html" <<'HTML'
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Yaahlan Web Agent · 对话演示</title>
  <style>
    html, body { margin: 0; height: 100%; background: #0b0e14; }
    iframe { border: 0; width: 100%; height: 100%; display: block; }
  </style>
</head>
<body>
  <iframe src="../keynote/?embed=new-chat" title="Web Agent 对话演示"></iframe>
</body>
</html>
HTML

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
    <p>对外演示入口（GitHub Pages 静态托管）。完整 MOA / Tunnel / 用例生成能力需内网 Web Agent 服务。</p>
    <div class="links">
      <a href="web-agent/"><strong>Web Agent 对话入口</strong><span>交互式界面演示（新建对话场景）</span></a>
      <a href="keynote/"><strong>Keynote 产品演示</strong><span>全屏产品演示与功能亮点</span></a>
    </div>
  </main>
</body>
</html>
HTML

touch "$DOCS/.nojekyll"

echo "GitHub Pages 演示包已生成: $DOCS"
echo "  Keynote:  /keynote/"
echo "  Web Agent: /web-agent/"
