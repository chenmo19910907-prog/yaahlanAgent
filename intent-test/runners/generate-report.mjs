#!/usr/bin/env node
/**
 * 聚合报告生成器 — 从 Midscene 单条报告中提取截图与步骤，生成合并 HTML
 *
 * 用法:
 *   node runners/generate-report.mjs <intent.yaml> [--results <json>]
 *
 * --results JSON 格式: [{"id":"...", "passed": true/false}, ...]
 * 不传 --results 时，按报告目录是否存在判定
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync, statSync, copyFileSync } from 'fs';
import { resolve, dirname, basename } from 'path';
import { fileURLToPath } from 'url';
import { parseAllDocuments } from 'yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const REPORT_DIR = resolve(ROOT, '../midscene/midscene_run/report');
const OUTPUT_DIR = resolve(ROOT, '../midscene/midscene_run/output');
const DEVICE_WIDTH = Number(process.env.DEVICE_WIDTH ?? 1080);
const DEVICE_HEIGHT = Number(process.env.DEVICE_HEIGHT ?? 2424);

function extractReportData(htmlPath) {
  if (!existsSync(htmlPath)) return [];
  const html = readFileSync(htmlPath, 'utf8');
  const regex = /<script type="midscene_web_dump"[^>]*>([\s\S]*?)<\/script>/g;
  const groups = [];
  let match;
  while ((match = regex.exec(html)) !== null) {
    try {
      groups.push(JSON.parse(match[1]));
    } catch { /* skip malformed */ }
  }
  return groups;
}

function extractScreenshots(groups) {
  const screenshots = [];
  for (const group of groups) {
    for (const exec of group.executions ?? []) {
      for (const task of exec.tasks ?? []) {
        if (task.recorder) {
          for (const rec of task.recorder) {
            if (rec.type === 'screenshot' && rec.screenshot?.storage === 'inline') {
              screenshots.push(rec.screenshot);
            }
          }
        }
        if (task.uiContext?.screenshot?.storage === 'inline') {
          screenshots.push(task.uiContext.screenshot);
        }
      }
    }
  }
  return screenshots;
}

function findInlineImages(htmlPath) {
  if (!existsSync(htmlPath)) return [];
  const html = readFileSync(htmlPath, 'utf8');

  const images = [];
  const dataRegex = /<script type="midscene-image" data-id="([^"]+)">([^<]+)<\/script>/g;
  let m;
  while ((m = dataRegex.exec(html)) !== null) {
    let data = m[2];
    const commaIdx = data.indexOf(',');
    if (commaIdx !== -1 && commaIdx < 40) {
      data = data.slice(commaIdx + 1);
    }
    images.push({ id: m[1], base64: data });
  }
  return images;
}

function getLastScreenshots(htmlPath, count = 2) {
  if (!existsSync(htmlPath)) return [];
  const html = readFileSync(htmlPath, 'utf8');

  const screenshotIds = [];
  const groups = extractReportData(htmlPath);
  for (const group of groups) {
    for (const exec of group.executions ?? []) {
      for (const task of exec.tasks ?? []) {
        if (task.recorder) {
          for (const rec of task.recorder) {
            if (rec.type === 'screenshot' && rec.screenshot?.id) {
              screenshotIds.push(rec.screenshot.id);
            }
          }
        }
        if (task.uiContext?.screenshot?.id) {
          screenshotIds.push(task.uiContext.screenshot.id);
        }
      }
    }
  }

  const allImages = findInlineImages(htmlPath);
  const imageMap = new Map(allImages.map((img) => [img.id, img]));

  const filtered = [];
  for (const id of screenshotIds) {
    const img = imageMap.get(id);
    if (!img?.base64) continue;
    const buf = Buffer.from(img.base64, 'base64');
    const headerBytes = buf.slice(16, 24);
    if (headerBytes.length >= 8) {
      const w = headerBytes.readUInt32BE(0);
      const h = headerBytes.readUInt32BE(4);
      if (w !== DEVICE_WIDTH || h !== DEVICE_HEIGHT) continue;
    }
    filtered.push(img);
  }
  return filtered.slice(-count);
}

function buildHtml(testModule, cases, timestamp, platformLabel = 'Android') {
  const passCount = cases.filter((c) => c.passed).length;
  const skipCount = cases.filter((c) => c.skipped).length;
  const timeoutCount = cases.filter((c) => c.timedOut).length;
  const failCount = cases.length - passCount - skipCount - timeoutCount;

  let cards = '';
  for (const tc of cases) {
    const statusClass = tc.timedOut ? 'timeout' : tc.skipped ? 'skip' : tc.passed ? 'pass' : 'fail';
    const statusLabel = tc.timedOut
      ? '超时'
      : tc.skipped
        ? (tc.yamlSkipped ? '已跳过' : '未执行')
        : tc.passed
          ? (tc.historicalPass ? '通过（历史）' : '通过')
          : '失败';
    const statusBg = tc.timedOut ? '#FF9800' : tc.skipped ? '#9E9E9E' : tc.passed ? '#4CAF50' : '#F44336';

    let resultNote = '';
    if (tc.yamlSkipped) {
      const reason = tc.skipReason ? `跳过原因：${escHtml(tc.skipReason)} · ` : '';
      resultNote = `<div class="result-note skip-reason">${reason}无通过结果</div>`;
    } else if (tc.skipped && tc.noPassResult) {
      resultNote = '<div class="result-note">无通过结果（本次未执行）</div>';
    } else if (tc.passed && tc.historicalPass) {
      resultNote = '<div class="result-note historical">通过结果来自历史跑批（本次未执行）</div>';
    }

    const stepItems = (tc.steps ?? [])
      .map((s) => `<li>${escHtml(s)}</li>`)
      .join('');
    const expectItems = (tc.expected ?? [])
      .map((e) => `<li>${escHtml(e)}</li>`)
      .join('');
    const imgs = (tc.screenshots ?? [])
      .map(
        (img) =>
          `<img class="screenshot-thumb" src="data:image/png;base64,${img.base64}" alt="截图" loading="lazy"/>`,
      )
      .join('');
    const screenshotNote = tc.screenshotStale
      ? '<div class="screenshot-note">⚠ 通过结果来自历史跑批，暂无对应截图快照（请重跑该 case 以刷新截图）</div>'
      : tc.screenshotFallback
        ? '<div class="screenshot-note">ℹ 截图来自历史跑批快照（与本次通过 runId 非精确匹配，仅供参看）</div>'
        : '';

    cards += `
<div class="case-card ${statusClass}">
  <div class="case-header">
    <div>
      <div class="case-id">${escHtml(tc.id)}</div>
      <div class="case-title">${escHtml(tc.name)}</div>
    </div>
    <span class="case-status" style="background:${statusBg}">${statusLabel}</span>
  </div>
  ${resultNote}
  <div class="case-body">
    <div class="steps-section">
      <div class="section-title">测试步骤</div>
      <ul class="step-list">${stepItems || '<li>-</li>'}</ul>
    </div>
    <div class="expects-section">
      <div class="section-title">预期结果</div>
      <ul class="step-list">${expectItems || '<li>-</li>'}</ul>
    </div>
  </div>
  ${screenshotNote}${imgs ? `<div class="screenshots">${imgs}</div>` : ''}
</div>`;
  }

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>${escHtml(testModule)} · 意图测试报告</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, "SF Pro", "PingFang SC", "Helvetica Neue", sans-serif; background: #f0f2f5; padding: 24px; max-width: 1200px; margin: 0 auto; }
.header { text-align: center; padding: 32px 0 24px; }
.header h1 { font-size: 22px; color: #1a1a1a; font-weight: 700; }
.header .meta { margin-top: 8px; font-size: 14px; color: #666; }
.summary-bar { display: flex; justify-content: center; gap: 24px; margin: 16px 0 28px; }
.summary-item { padding: 12px 24px; background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); text-align: center; }
.summary-item .num { font-size: 28px; font-weight: 700; }
.summary-item .label { font-size: 12px; color: #999; margin-top: 4px; }
.num-total { color: #333; }
.num-pass { color: #4CAF50; }
.num-fail { color: #F44336; }
.num-skip { color: #9E9E9E; }
.num-timeout { color: #FF9800; }

.case-card { background: #fff; border-radius: 12px; margin: 20px 0; padding: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border-left: 4px solid #e0e0e0; }
.case-card.pass { border-left-color: #4CAF50; }
.case-card.fail { border-left-color: #F44336; }
.case-card.skip { border-left-color: #9E9E9E; }
.case-card.timeout { border-left-color: #FF9800; }
.case-header { display: flex; align-items: center; justify-content: space-between; }
.case-id { font-size: 12px; color: #999; font-weight: 500; letter-spacing: 0.5px; }
.case-title { font-size: 16px; font-weight: 600; color: #1a1a1a; margin-top: 4px; }
.case-status { padding: 4px 14px; border-radius: 16px; color: #fff; font-size: 12px; font-weight: 600; }

.case-body { margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.steps-section, .expects-section { padding: 12px 16px; border-radius: 8px; }
.steps-section { background: #F8F9FA; }
.expects-section { background: #F1F8E9; }
.section-title { font-size: 11px; font-weight: 600; color: #999; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.step-list { list-style: none; }
.step-list li { font-size: 13px; color: #333; padding: 4px 0; padding-left: 18px; position: relative; line-height: 1.5; }
.step-list li::before { content: ""; position: absolute; left: 4px; top: 11px; width: 6px; height: 6px; border-radius: 50%; }
.steps-section .step-list li::before { background: #90A4AE; }
.expects-section .step-list li::before { background: #66BB6A; }

.result-note { margin-top: 12px; padding: 10px 12px; border-radius: 8px; font-size: 13px; line-height: 1.5; }
.result-note.skip-reason { background: #f5f5f5; color: #616161; }
.result-note.historical { background: #e8f5e9; color: #2e7d32; }
.result-note:not(.skip-reason):not(.historical) { background: #fafafa; color: #757575; }

.screenshots { margin-top: 16px; display: flex; gap: 10px; overflow-x: auto; padding: 8px 0; }
.screenshot-note { margin: 12px 0 4px; padding: 10px 12px; background: #fff8e1; border-radius: 8px; font-size: 13px; color: #8d6e00; }
.screenshots img { height: 360px; border-radius: 8px; border: 1px solid #eee; flex-shrink: 0; cursor: zoom-in; transition: transform 0.15s, box-shadow 0.15s; }
.screenshots img:hover { transform: scale(1.02); box-shadow: 0 4px 16px rgba(0,0,0,0.12); }

.lightbox { position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center; }
.lightbox.hidden { display: none; }
.lightbox-backdrop { position: absolute; inset: 0; background: rgba(0,0,0,0.85); cursor: zoom-out; }
.lightbox-panel { position: relative; z-index: 1; max-width: calc(100vw - 48px); max-height: calc(100vh - 48px); display: flex; flex-direction: column; align-items: center; }
.lightbox-panel img { max-width: 100%; max-height: calc(100vh - 96px); object-fit: contain; border-radius: 8px; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
.lightbox-close { position: fixed; top: 16px; right: 20px; z-index: 2; width: 40px; height: 40px; border: none; border-radius: 50%; background: rgba(255,255,255,0.15); color: #fff; font-size: 24px; line-height: 1; cursor: pointer; }
.lightbox-close:hover { background: rgba(255,255,255,0.25); }
.lightbox-hint { margin-top: 12px; color: rgba(255,255,255,0.6); font-size: 12px; }

.footer { text-align: center; margin-top: 32px; font-size: 12px; color: #aaa; }
</style>
</head>
<body>
<div class="header">
  <h1>${escHtml(testModule)} · 意图测试报告</h1>
  <div class="meta">生成时间: ${timestamp} · 平台: ${escHtml(platformLabel)}</div>
</div>
<div class="summary-bar">
  <div class="summary-item"><div class="num num-total">${cases.length}</div><div class="label">总用例</div></div>
  <div class="summary-item"><div class="num num-pass">${passCount}</div><div class="label">通过</div></div>
  <div class="summary-item"><div class="num num-fail">${failCount}</div><div class="label">失败</div></div>
  ${timeoutCount ? `<div class="summary-item"><div class="num num-timeout">${timeoutCount}</div><div class="label">超时</div></div>` : ''}
  ${skipCount ? `<div class="summary-item"><div class="num num-skip">${skipCount}</div><div class="label">跳过</div></div>` : ''}
</div>
${cards}
<div class="footer">Intent Test Report · Auto Generated</div>
<div id="lightbox" class="lightbox hidden" aria-hidden="true">
  <div class="lightbox-backdrop" data-lightbox-close></div>
  <button class="lightbox-close" type="button" aria-label="关闭" data-lightbox-close>&times;</button>
  <div class="lightbox-panel">
    <img id="lightbox-img" src="" alt="截图预览"/>
    <div class="lightbox-hint">点击背景或按 Esc 关闭</div>
  </div>
</div>
<script>
(function () {
  var lightbox = document.getElementById('lightbox');
  var lightboxImg = document.getElementById('lightbox-img');
  if (!lightbox || !lightboxImg) return;

  function openLightbox(src) {
    lightboxImg.src = src;
    lightbox.classList.remove('hidden');
    lightbox.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeLightbox() {
    lightbox.classList.add('hidden');
    lightbox.setAttribute('aria-hidden', 'true');
    lightboxImg.src = '';
    document.body.style.overflow = '';
  }

  document.querySelectorAll('.screenshot-thumb').forEach(function (img) {
    img.addEventListener('click', function () { openLightbox(img.src); });
  });

  lightbox.querySelectorAll('[data-lightbox-close]').forEach(function (el) {
    el.addEventListener('click', closeLightbox);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !lightbox.classList.contains('hidden')) closeLightbox();
  });
})();
</script>
</body>
</html>`;
}

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

function extractOutputRunId(outputFileName) {
  const m = outputFileName.match(/\.midscene-(\d+)\.json$/);
  return m ? m[1] : null;
}

/** 解析 case 报告 HTML 路径；优先使用与通过跑批对应的 snapshots/{runId}.html */
export function resolveCaseReportHtml(caseId, opts = {}) {
  const platform = opts.platform ? String(opts.platform).toLowerCase() : '';
  const useSuffix = platform && process.env.INTENT_REPORT_PLATFORM_SUFFIX === '1';
  const dirName = `${String(caseId).toLowerCase()}${useSuffix ? `-${platform}` : ''}`;
  const base = resolve(REPORT_DIR, dirName);
  const snapshotRunId = opts.snapshotRunId ?? null;
  if (snapshotRunId) {
    const snap = resolve(base, 'snapshots', `${snapshotRunId}.html`);
    if (existsSync(snap)) return snap;
  }
  return resolve(base, 'index.html');
}

/** 每次 case 跑完后归档 report 快照，供 merge-latest 对齐通过结果与截图 */
export function archiveCaseReportSnapshot(caseId, opts = {}) {
  const outputs = listCaseOutputFiles(caseId);
  if (!outputs.length) return null;
  const runId = extractOutputRunId(outputs[0].name);
  if (!runId) return null;

  const liveHtml = resolveCaseReportHtml(caseId, opts);
  if (!existsSync(liveHtml)) return null;

  const snapDir = resolve(dirname(liveHtml), 'snapshots');
  mkdirSync(snapDir, { recursive: true });
  const snapPath = resolve(snapDir, `${runId}.html`);
  copyFileSync(liveHtml, snapPath);
  return { runId, snapPath };
}

function listCaseOutputFiles(caseId) {
  if (!existsSync(OUTPUT_DIR)) return [];
  const prefix = `${caseId}.midscene-`;
  return readdirSync(OUTPUT_DIR)
    .filter((name) => name.startsWith(prefix) && name.endsWith('.json'))
    .map((name) => {
      const full = resolve(OUTPUT_DIR, name);
      return { name, full, mtime: statSync(full).mtimeMs };
    })
    .sort((a, b) => b.mtime - a.mtime);
}

function readOutputJson(filePath) {
  try {
    return JSON.parse(readFileSync(filePath, 'utf8'));
  } catch {
    return null;
  }
}

function isOutputPassed(data) {
  if (!data || typeof data !== 'object') return false;
  for (const v of Object.values(data)) {
    if (v && typeof v === 'object' && v.pass === false) return false;
  }
  return true;
}

function isOutputTimedOut(data) {
  if (!data || typeof data !== 'object') return false;
  for (const v of Object.values(data)) {
    if (v && typeof v === 'object' && v.pass === false) {
      const msg = String(v.message ?? v.thought ?? '');
      if (/timeout|超时|waitFor timeout/i.test(msg)) return true;
    }
  }
  return false;
}

function findLatestPassOutput(caseId) {
  return listCaseOutputFiles(caseId).find((f) => isOutputPassed(readOutputJson(f.full))) ?? null;
}

function listCaseSnapshotFiles(caseDir) {
  const snapDir = resolve(caseDir, 'snapshots');
  if (!existsSync(snapDir)) return [];
  return readdirSync(snapDir)
    .filter((name) => name.endsWith('.html'))
    .map((name) => {
      const runId = name.replace(/\.html$/, '');
      return { name, runId, full: resolve(snapDir, name) };
    })
    .sort((a, b) => Number(b.runId) - Number(a.runId));
}

/**
 * 通过结果对应的截图 HTML：优先精确 runId；否则用不晚于 passRunId 的最近快照（历史通过但后续失败重跑时常见）
 */
function resolvePassAlignedReportHtml(caseDir, snapshotRunId) {
  if (snapshotRunId) {
    const exact = resolve(caseDir, 'snapshots', `${snapshotRunId}.html`);
    if (existsSync(exact)) {
      return { htmlPath: exact, snapshotExact: true, snapshotFallback: false };
    }
  }

  const passNum = Number(snapshotRunId);
  if (Number.isFinite(passNum)) {
    const aligned = listCaseSnapshotFiles(caseDir).find((snap) => Number(snap.runId) <= passNum);
    if (aligned) {
      return {
        htmlPath: aligned.full,
        snapshotExact: false,
        snapshotFallback: true,
      };
    }
  }

  return { htmlPath: null, snapshotExact: false, snapshotFallback: false };
}

function shouldUseLiveReport(caseId, passOutputFile) {
  const outputs = listCaseOutputFiles(caseId);
  if (!outputs.length || !passOutputFile) return false;
  return outputs[0].name === passOutputFile.name;
}

/** 合并磁盘历史：后续重跑通过的 case 在聚合报告中仍计为通过 */
export function mergeResultsFromDisk(sources, currentResults = []) {
  const currentMap = new Map((currentResults ?? []).map((r) => [r.id, r]));
  const hasCurrentBatch = (currentResults ?? []).length > 0;
  const merged = [];

  for (const src of sources) {
    for (const doc of parseSourceDocs(src)) {
      const id = doc.id;
      if (doc.skip) {
        merged.push({
          id,
          passed: false,
          skipped: true,
          timedOut: false,
          yamlSkipped: true,
          skipReason: doc.skipReason ?? null,
          noPassResult: true,
        });
        continue;
      }

      const outputs = listCaseOutputFiles(id);
      const latestPass = outputs.find((f) => isOutputPassed(readOutputJson(f.full)));
      const current = currentMap.get(id);
      const currentSkipped = !current || current.skipped;

      if (latestPass) {
        merged.push({
          id,
          passed: true,
          skipped: false,
          timedOut: false,
          snapshotRunId: extractOutputRunId(latestPass.name),
          historicalPass: hasCurrentBatch && currentSkipped,
        });
        continue;
      }

      if (current && !current.skipped) {
        merged.push({
          ...current,
          skipped: false,
          noPassResult: false,
        });
        continue;
      }

      if (outputs.length) {
        const latest = readOutputJson(outputs[0].full);
        merged.push({
          id,
          passed: false,
          skipped: false,
          timedOut: isOutputTimedOut(latest),
          noPassResult: false,
        });
        continue;
      }

      merged.push({
        id,
        passed: false,
        skipped: true,
        timedOut: false,
        noPassResult: true,
      });
    }
  }

  return merged;
}

function collectAllDocs(sources) {
  const docs = [];
  for (const src of sources) {
    docs.push(...parseSourceDocs(src));
  }
  return docs;
}

export function generateReport(sources, results, opts = {}) {
  const platformLabel = opts.platformLabel ?? (opts.platform === 'ios' ? 'iOS' : 'Android');
  const platform = opts.platform ? String(opts.platform).toLowerCase() : '';
  const reportSuffix =
    platform && process.env.INTENT_REPORT_PLATFORM_SUFFIX === '1' ? `-${platform}` : '';

  const allCases = [];
  let moduleName = '';

  for (const src of sources) {
    const docs = parseSourceDocs(src);
    for (const doc of docs) {
      if (!moduleName) moduleName = doc.module ?? basename(src, '.yaml');
      const result = results?.find((r) => r.id === doc.id);
      const yamlSkipped = Boolean(doc.skip);
      const skipReason = doc.skipReason ?? result?.skipReason ?? null;
      const skipped = yamlSkipped || (result?.skipped ?? false);
      const passed = yamlSkipped ? false : (result ? result.passed : false);
      const timedOut = yamlSkipped ? false : (result?.timedOut ?? false);
      const historicalPass = yamlSkipped ? false : (result?.historicalPass ?? false);
      const noPassResult = yamlSkipped ? true : (result?.noPassResult ?? skipped);
      const snapshotRunId = result?.snapshotRunId ?? null;
      const caseDir = resolve(REPORT_DIR, `${String(doc.id).toLowerCase()}${reportSuffix}`);
      const passOutput = passed ? findLatestPassOutput(doc.id) : null;
      const aligned = passed
        ? resolvePassAlignedReportHtml(caseDir, snapshotRunId)
        : { htmlPath: null, snapshotExact: false, snapshotFallback: false };
      const liveHtml = resolve(caseDir, 'index.html');
      const useLiveReport = !aligned.htmlPath && passed && shouldUseLiveReport(doc.id, passOutput);
      const reportHtml = aligned.htmlPath ?? (useLiveReport ? liveHtml : null);
      const screenshotStale = passed && !reportHtml;
      const screenshotFallback = passed && aligned.snapshotFallback;
      const screenshots = (skipped || timedOut || !reportHtml || screenshotStale)
        ? []
        : getLastScreenshots(reportHtml, 2);

      const steps = [];
      if (doc.setup?.include) {
        for (const inc of doc.setup.include) {
          steps.push(`导航: ${inc}`);
        }
      }
      if (doc.setup?.steps) {
        for (const s of doc.setup.steps) {
          if (typeof s === 'string') steps.push(s);
          else if (s.act) steps.push(s.act);
          else if (s.waitFor) steps.push(`等待: ${s.waitFor}`);
        }
      }
      if (doc.intent?.action) steps.push(doc.intent.action);

      allCases.push({
        id: doc.id,
        name: doc.name ?? doc.id,
        passed,
        skipped,
        timedOut,
        yamlSkipped,
        skipReason,
        historicalPass,
        noPassResult,
        screenshotStale,
        screenshotFallback,
        steps,
        expected: doc.intent?.expected ?? [],
        screenshots,
      });
    }
  }

  const displayModule = opts.moduleName ?? moduleName;
  const slugBase = (opts.reportSlug ?? displayModule).replace(/[^a-zA-Z0-9\u4e00-\u9fff-]/g, '-').toLowerCase();
  const slug = opts.platform ? `${slugBase}-${opts.platform}` : slugBase;
  const outDir = resolve(REPORT_DIR, `${slug}-summary`);
  mkdirSync(outDir, { recursive: true });

  const ts = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });
  const html = buildHtml(displayModule, allCases, ts, platformLabel);
  const outPath = resolve(outDir, 'index.html');
  writeFileSync(outPath, html, 'utf8');
  console.log(`[report] 聚合报告已生成: ${outPath}`);
  return outPath;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const resIdx = args.indexOf('--results');
  const mergeLatest = args.includes('--merge-latest');
  let results = null;
  const files = [];

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--results') {
      results = JSON.parse(args[++i]);
    } else if (args[i] === '--merge-latest') {
      /* flag */
    } else if (!args[i].startsWith('--')) {
      files.push(resolve(process.cwd(), args[i]));
    }
  }

  if (!files.length) {
    console.error(
      '用法: node runners/generate-report.mjs <intent.yaml> [--results \'[...]\'] [--merge-latest]',
    );
    process.exit(1);
  }

  const finalResults = mergeLatest ? mergeResultsFromDisk(files, results ?? []) : results;
  if (mergeLatest) {
    const docs = collectAllDocs(files);
    const pass = finalResults.filter((r) => r.passed).length;
    const skip = finalResults.filter((r) => r.skipped).length;
    const timeout = finalResults.filter((r) => r.timedOut).length;
    const fail = docs.length - pass - skip - timeout;
    console.log(
      `[report] merge-latest: ${docs.length} 条 → 通过 ${pass} / 失败 ${fail} / 超时 ${timeout} / 跳过 ${skip}`,
    );
  }
  generateReport(files, finalResults);
}
