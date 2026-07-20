#!/usr/bin/env node
/**
 * 双端聚合 HTML 报告（Android + iOS 各平台 summary 合并）
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { resolve, dirname, basename } from 'path';
import { fileURLToPath } from 'url';
import { parseAllDocuments } from 'yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const REPORT_DIR = resolve(ROOT, '../midscene/midscene_run/report');

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function parseSourceDocs(filePath) {
  const raw = readFileSync(filePath, 'utf8');
  return parseAllDocuments(raw)
    .map((d) => d.toJSON())
    .filter((d) => d && d.id);
}

function summarizePlatform(label, payload) {
  if (!payload) {
    return { label, total: 0, pass: 0, fail: 0, skip: 0, timeout: 0, skippedRun: true };
  }
  const results = payload.results ?? [];
  const pass = results.filter((r) => r.passed).length;
  const skip = results.filter((r) => r.skipped).length;
  const timeout = results.filter((r) => r.timedOut).length;
  const fail = results.length - pass - skip - timeout;
  return {
    label,
    total: results.length,
    pass,
    fail,
    skip,
    timeout,
    skippedRun: payload.skipped === true,
    exitCode: payload.exitCode ?? 0,
  };
}

function buildCaseRows(results, platform) {
  return (results ?? []).map((r) => {
    const status = r.timedOut
      ? 'timeout'
      : r.skipped
        ? 'skip'
        : r.passed
          ? 'pass'
          : 'fail';
    const statusLabel = r.timedOut
      ? '超时'
      : r.skipped
        ? '未执行'
        : r.passed
          ? '通过'
          : '失败';
    const reportDir = `${String(r.id).toLowerCase()}-${platform}`;
    const reportLink = resolve(REPORT_DIR, reportDir, 'index.html');
    const link = existsSync(reportLink)
      ? `<a href="file://${reportLink}">Midscene 报告</a>`
      : '-';
    return `<tr class="${status}">
      <td>${escHtml(r.id)}</td>
      <td><span class="badge ${status}">${statusLabel}</span></td>
      <td>${link}</td>
    </tr>`;
  }).join('');
}

function buildHtml(moduleName, androidSummary, iosSummary, androidRows, iosRows, ts) {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>${escHtml(moduleName)} · 双端意图测试报告</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "PingFang SC", sans-serif; background: #f0f2f5; padding: 24px; max-width: 1100px; margin: 0 auto; }
h1 { text-align: center; font-size: 22px; margin-bottom: 8px; }
.meta { text-align: center; color: #666; font-size: 14px; margin-bottom: 24px; }
.platform { background: #fff; border-radius: 12px; padding: 20px; margin: 16px 0; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.platform h2 { font-size: 16px; margin-bottom: 12px; }
.stats { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.stat { padding: 8px 16px; background: #f8f9fa; border-radius: 8px; font-size: 13px; }
.stat b { font-size: 18px; display: block; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; }
th { color: #999; font-weight: 600; font-size: 11px; text-transform: uppercase; }
.badge { padding: 2px 10px; border-radius: 12px; color: #fff; font-size: 11px; }
.badge.pass { background: #4CAF50; }
.badge.fail { background: #F44336; }
.badge.skip { background: #9E9E9E; }
.badge.timeout { background: #FF9800; }
tr.fail td { color: #c62828; }
.footer { text-align: center; margin-top: 24px; font-size: 12px; color: #aaa; }
</style>
</head>
<body>
<h1>${escHtml(moduleName)} · 双端意图测试报告</h1>
<div class="meta">生成时间: ${ts}</div>

<div class="platform">
  <h2>Android ${androidSummary.skippedRun ? '（无匹配用例）' : androidSummary.exitCode ? '✗' : '✓'}</h2>
  <div class="stats">
    <div class="stat"><b>${androidSummary.total}</b>总用例</div>
    <div class="stat"><b style="color:#4CAF50">${androidSummary.pass}</b>通过</div>
    <div class="stat"><b style="color:#F44336">${androidSummary.fail}</b>失败</div>
    ${androidSummary.timeout ? `<div class="stat"><b style="color:#FF9800">${androidSummary.timeout}</b>超时</div>` : ''}
  </div>
  <table>
    <thead><tr><th>用例 ID</th><th>结果</th><th>详情</th></tr></thead>
    <tbody>${androidRows || '<tr><td colspan="3">无数据</td></tr>'}</tbody>
  </table>
</div>

<div class="platform">
  <h2>iOS ${iosSummary.skippedRun ? '（无匹配用例）' : iosSummary.exitCode ? '✗' : '✓'}</h2>
  <div class="stats">
    <div class="stat"><b>${iosSummary.total}</b>总用例</div>
    <div class="stat"><b style="color:#4CAF50">${iosSummary.pass}</b>通过</div>
    <div class="stat"><b style="color:#F44336">${iosSummary.fail}</b>失败</div>
    ${iosSummary.timeout ? `<div class="stat"><b style="color:#FF9800">${iosSummary.timeout}</b>超时</div>` : ''}
  </div>
  <table>
    <thead><tr><th>用例 ID</th><th>结果</th><th>详情</th></tr></thead>
    <tbody>${iosRows || '<tr><td colspan="3">无数据</td></tr>'}</tbody>
  </table>
</div>

<div class="footer">Intent Test Dual Report · Auto Generated</div>
</body>
</html>`;
}

export function generateDualReport({ sources, android, ios }) {
  let moduleName = 'intent-dual';
  for (const src of sources ?? []) {
    const docs = parseSourceDocs(src);
    if (docs[0]?.module) {
      moduleName = docs[0].module;
      break;
    }
    moduleName = basename(src, '.yaml');
  }

  const androidSummary = summarizePlatform('Android', android);
  const iosSummary = summarizePlatform('iOS', ios);
  const androidRows = buildCaseRows(android?.results, 'android');
  const iosRows = buildCaseRows(ios?.results, 'ios');

  const slugBase = moduleName.replace(/[^a-zA-Z0-9\u4e00-\u9fff-]/g, '-').toLowerCase();
  const outDir = resolve(REPORT_DIR, `${slugBase}-dual-summary`);
  mkdirSync(outDir, { recursive: true });

  const ts = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
  const html = buildHtml(
    moduleName,
    androidSummary,
    iosSummary,
    androidRows,
    iosRows,
    ts,
  );
  const outPath = resolve(outDir, 'index.html');
  writeFileSync(outPath, html, 'utf8');
  return outPath;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  console.error('请通过 intent-run-dual.mjs 调用 generateDualReport');
  process.exit(1);
}
