#!/usr/bin/env node
/**
 * intent-run 共享逻辑（单端 / 双端 worker 复用）
 */

import { spawnSync } from 'child_process';
import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import {
  parseIntentFile,
  getGeneratedDir,
  MIDSCENE_ROOT,
} from './compile-intent.mjs';
import { applyBaseProfileEnv, applyPlatformProfileEnv } from './load-base-profile.mjs';
import { ensureIntentData } from './ensure-intent-data.mjs';
import { generateReport, mergeResultsFromDisk, archiveCaseReportSnapshot } from './generate-report.mjs';
import { autoFixAfterRun, isRetryableFailure } from './auto-fix-assertions.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const COMPILE = resolve(ROOT, 'runners/compile-intent.mjs');
const MIDSCENE_RUN = resolve(MIDSCENE_ROOT, 'scripts/midscene-run.mjs');
const TUNNEL_VERIFY = resolve(ROOT, 'runners/tunnel-verify.py');
const REPORT_DIR = resolve(ROOT, '../midscene/midscene_run/report');
const RUNS_DIR = resolve(ROOT, '.generated/runs');
const CASE_TIMEOUT_MS = Number(process.env.CASE_TIMEOUT_MS ?? 5 * 60 * 1000);
const SETUP_RETRY_ENABLED = process.env.INTENT_SETUP_RETRY !== '0';

export function loadCatalog() {
  const path = resolve(ROOT, 'intents/catalog.json');
  return JSON.parse(readFileSync(path, 'utf8'));
}

export function resolveInputs(args) {
  const moduleIdx = args.indexOf('--module');
  if (moduleIdx !== -1) {
    const mod = args[moduleIdx + 1];
    const catalog = loadCatalog();
    const paths = catalog.modules?.[mod]?.intents ?? [];
    if (!paths.length) {
      throw new Error(`模块未找到: ${mod}`);
    }
    return { paths: paths.map((p) => resolve(ROOT, p)), filterId: null };
  }

  const idIdx = args.indexOf('--id');
  const filterId = idIdx !== -1 ? args[idIdx + 1] : null;
  const flagValues = new Set(
    ['--module', '--id', '--platform']
      .map((flag) => {
        const i = args.indexOf(flag);
        return i !== -1 ? args[i + 1] : null;
      })
      .filter(Boolean),
  );
  const files = args.filter((a) => !a.startsWith('--') && !flagValues.has(a));

  if (filterId) {
    return {
      paths: files.map((f) => resolve(process.cwd(), f)),
      filterId,
    };
  }

  if (!files.length) {
    throw new Error(
      '用法: intent-run <intent.yaml> | --module <名> | --id <ID> [intent.yaml]',
    );
  }
  return { paths: files.map((f) => resolve(process.cwd(), f)), filterId: null };
}

export function findSourceById(id) {
  const catalog = loadCatalog();
  for (const mod of Object.values(catalog.modules ?? {})) {
    for (const rel of mod.intents ?? []) {
      const full = resolve(ROOT, rel);
      const docs = parseIntentFile(full);
      if (docs.some((d) => d.id === id)) return full;
    }
  }
  return null;
}

function androidEnv(extra = {}) {
  const androidHome =
    process.env.ANDROID_HOME ?? `${process.env.HOME}/Library/Android/sdk`;
  return {
    ...process.env,
    ...extra,
    ANDROID_HOME: androidHome,
    ANDROID_SDK_ROOT: androidHome,
    PATH: `${androidHome}/platform-tools:${process.env.PATH ?? ''}`,
  };
}

function reportDirName(id, platform, useSuffix) {
  const suffix = useSuffix ? `-${platform}` : '';
  return `${id.toLowerCase()}${suffix}`;
}

/**
 * 智能回退：尝试返回首五帧，避免每条 case 都重启 App。
 * 策略：系统 back 键 → 左上角坐标点击返回，共尝试 2 轮。
 * 返回 true 表示已在主界面可跳过重启，false 表示需要重启。
 */
function trySmartReset() {
  const deviceId = process.env.ADB_DEVICE_ID || process.env.ANDROID_DEVICE_ID;
  const adbPrefix = deviceId ? `adb -s ${deviceId}` : 'adb';
  const w = Number(process.env.DEVICE_WIDTH ?? 1080);
  const h = Number(process.env.DEVICE_HEIGHT ?? 2424);
  const backX = Math.round(w * 0.05);
  const backY = Math.round(h * 0.04);

  function isOnMainScreen() {
    spawnSync('sh', ['-c',
      `${adbPrefix} shell uiautomator dump /sdcard/ui_check.xml`,
    ], { stdio: 'ignore' });
    const pull = spawnSync('sh', ['-c',
      `${adbPrefix} shell cat /sdcard/ui_check.xml`,
    ], { encoding: 'utf8' });
    const xml = pull.stdout ?? '';
    const tabs = ['Game', 'Room', 'Message', 'Moment'].filter(
      (t) => xml.includes(`text="${t}"`),
    );
    return tabs.length >= 3;
  }

  for (let i = 0; i < 3; i++) {
    if (i < 2) {
      spawnSync('sh', ['-c', `${adbPrefix} shell input keyevent KEYCODE_BACK`], { stdio: 'ignore' });
    } else {
      spawnSync('sh', ['-c', `${adbPrefix} shell input tap ${backX} ${backY}`], { stdio: 'ignore' });
    }
    spawnSync('sh', ['-c', 'sleep 1.5'], { stdio: 'ignore' });

    if (isOnMainScreen()) {
      const method = i < 2 ? `系统back×${i + 1}` : '左上角tap';
      console.log(`[intent-run] ↩ ${method} → 检测到底部导航栏，跳过重启`);
      return true;
    }
  }

  console.log('[intent-run] ↩ 3次返回未回到主界面（底部导航栏不可见），将重启 App');
  return false;
}

function runMidscene(yamlPath, platform) {
  return spawnSync(
    process.execPath,
    [
      MIDSCENE_RUN,
      ...(platform === 'ios' ? ['--platform=ios'] : ['--no-vcode']),
      yamlPath,
    ],
    {
      stdio: 'inherit',
      cwd: MIDSCENE_ROOT,
      env: androidEnv({ INTENT_PLATFORM: platform }),
      timeout: CASE_TIMEOUT_MS,
      killSignal: 'SIGTERM',
    },
  );
}

function runTunnel(tunnelPath, startTime) {
  return spawnSync(
    'python3',
    [
      TUNNEL_VERIFY,
      '--spec',
      tunnelPath,
      '--start-time',
      String(startTime),
      '--out',
      tunnelPath.replace(/\.json$/, '.result.json'),
    ],
    { stdio: 'inherit', cwd: ROOT, env: process.env },
  );
}

export function docPlatform(doc) {
  return String(doc.platform ?? 'android').toLowerCase();
}

export function collectRuns(sources, filterId, platform, filterByPlatform = true) {
  const generated = getGeneratedDir();
  const runs = [];
  for (const p of sources) {
    for (const doc of parseIntentFile(p)) {
      if (filterId && doc.id !== filterId) continue;
      if (filterByPlatform && platform && docPlatform(doc) !== platform) continue;
      runs.push({
        id: doc.id,
        platform: docPlatform(doc),
        yaml: resolve(generated, `${doc.id}.midscene.yaml`),
        tunnel: resolve(generated, `${doc.id}.tunnel.json`),
      });
    }
  }
  return runs;
}

function compileSources(sources, platform, filterByPlatform) {
  process.env.INTENT_PLATFORM = platform;
  for (const p of sources) {
    const args = [COMPILE, p];
    if (filterByPlatform && platform) {
      args.push('--platform', platform);
    }
    const r = spawnSync(process.execPath, args, { stdio: 'inherit', cwd: ROOT, env: process.env });
    if (r.status !== 0) {
      throw new Error(`编译失败: ${p}`);
    }
  }
}

function forceRelaunchCompile(sources, platform, filterByPlatform) {
  process.env.INTENT_SKIP_RELAUNCH = '0';
  compileSources(sources, platform, filterByPlatform);
}

function isMidsceneTimeout(ui) {
  return ui.error?.code === 'ETIMEDOUT' || ui.signal === 'SIGTERM';
}

/**
 * 执行单条 UI case；setup/flaky 失败或 replan 超时时强制重启 App 重试一次
 */
function executeUiCase(run, platform, sources, filterByPlatform, snapOpts = {}) {
  let startTime = Math.floor(Date.now() / 1000) - 5;

  function finish(outcome) {
    const archived = archiveCaseReportSnapshot(run.id, snapOpts);
    return { ...outcome, snapshotRunId: archived?.runId ?? null };
  }

  let ui = runMidscene(run.yaml, platform);

  const timedOut = isMidsceneTimeout(ui);
  if (!timedOut && ui.status === 0) {
    return finish({ startTime, passed: true });
  }

  const shouldRetry = SETUP_RETRY_ENABLED
    && platform === 'android'
    && !run.setupRetried
    && isRetryableFailure(run.id, { timedOut });

  if (shouldRetry) {
    console.log(
      `[intent-run:${platform}] 🔄 ${run.id} ${timedOut ? '超时且疑似 replan' : '疑似 setup/flaky 失败'}，强制重启 App 重试...`,
    );
    forceRelaunchCompile(sources, platform, filterByPlatform);
    run.setupRetried = true;
    startTime = Math.floor(Date.now() / 1000) - 5;
    ui = runMidscene(run.yaml, platform);

    if (isMidsceneTimeout(ui)) {
      return finish({ startTime, passed: false, timedOut: true, setupRetried: true });
    }
    if (ui.status === 0) {
      return finish({ startTime, passed: true, setupRetried: true });
    }
    return finish({ startTime, passed: false, setupRetried: true });
  }

  if (timedOut) {
    return finish({ startTime, passed: false, timedOut: true });
  }
  return finish({ startTime, passed: false });
}

/**
 * @param {object} opts
 * @param {string} opts.platform android | ios
 * @param {string[]} opts.sources
 * @param {string|null} opts.filterId
 * @param {boolean} [opts.skipDataPrep]
 * @param {boolean} [opts.usePlatformSubdir] 双端 worker 使用 .generated/<platform>/
 */
export function runIntentPlatform(opts) {
  const platform = String(opts.platform ?? 'android').toLowerCase();
  if (!['android', 'ios'].includes(platform)) {
    throw new Error(`不支持的平台: ${platform}`);
  }

  const usePlatformSubdir = opts.usePlatformSubdir === true;
  const filterByPlatform = usePlatformSubdir;

  applyBaseProfileEnv();
  applyPlatformProfileEnv(platform);

  process.env.INTENT_PLATFORM = platform;
  if (opts.usePlatformSubdir) {
    process.env.INTENT_GENERATED_SUBDIR = platform;
    process.env.INTENT_REPORT_PLATFORM_SUFFIX = '1';
  } else {
    delete process.env.INTENT_GENERATED_SUBDIR;
    delete process.env.INTENT_REPORT_PLATFORM_SUFFIX;
  }

  if (!existsSync(MIDSCENE_RUN)) {
    throw new Error(`未找到: ${MIDSCENE_RUN}`);
  }

  const skipTunnel = process.env.INTENT_TUNNEL === '0';
  const continueOnError = process.env.INTENT_CONTINUE === '1';
  const sources = opts.sources ?? [];
  const filterId = opts.filterId ?? null;

  if (!opts.skipDataPrep) {
    const dataPrep = ensureIntentData({ sources, filterId });
    if (dataPrep.fatal) {
      return { platform, exitCode: 1, runs: [], results: [] };
    }
  }

  process.env.INTENT_SKIP_RELAUNCH = '0';
  compileSources(sources, platform, filterByPlatform);

  const runs = collectRuns(sources, filterId, platform, filterByPlatform);
  if (!runs.length) {
    console.log(`[intent-run:${platform}] 无匹配 ${platform} 用例，跳过`);
    const empty = { platform, exitCode: 0, runs: [], results: [], skipped: true };
    if (opts.writeResultJson) writeRunResult(platform, empty);
    return empty;
  }

  console.log(
    `[intent-run:${platform}] 共 ${runs.length} 条（${platform}${skipTunnel ? '' : ' + Tunnel'}，超时 ${CASE_TIMEOUT_MS / 1000}s${SETUP_RETRY_ENABLED ? '，setup 失败可重启重试' : ''}）`,
  );

  let failed = 0;
  const failedIds = new Set();
  const timedOutIds = new Set();
  const snapshotRunIds = new Map();

  let isFirstCase = true;

  for (const run of runs) {
    console.log(`\n[intent-run:${platform}] ▶ ${run.id}`);

    if (!isFirstCase && platform === 'android') {
      const skipRelaunch = trySmartReset();
      if (skipRelaunch && process.env.INTENT_SKIP_RELAUNCH !== '1') {
        process.env.INTENT_SKIP_RELAUNCH = '1';
        compileSources(sources, platform, filterByPlatform);
      } else if (!skipRelaunch && process.env.INTENT_SKIP_RELAUNCH !== '0') {
        process.env.INTENT_SKIP_RELAUNCH = '0';
        compileSources(sources, platform, filterByPlatform);
      }
    }
    isFirstCase = false;

    const snapOpts = usePlatformSubdir ? { platform } : {};
    const outcome = executeUiCase(run, platform, sources, filterByPlatform, snapOpts);
    const { startTime, passed, timedOut, setupRetried, snapshotRunId } = outcome;
    if (snapshotRunId) snapshotRunIds.set(run.id, snapshotRunId);

    if (timedOut) {
      failed += 1;
      failedIds.add(run.id);
      timedOutIds.add(run.id);
      console.error(
        `[intent-run:${platform}] ⏱ ${run.id} 超时（>${CASE_TIMEOUT_MS / 1000}s），已中断`,
      );
      if (!continueOnError) break;
      continue;
    }

    if (!passed) {
      failed += 1;
      failedIds.add(run.id);
      console.error(
        `[intent-run:${platform}] ✗ ${run.id} UI 失败${setupRetried ? '（setup 重试仍失败）' : ''}`,
      );
      if (!continueOnError) break;
      continue;
    }
    console.log(
      `[intent-run:${platform}] ✓ ${run.id} UI 通过${setupRetried ? '（setup 重试成功）' : ''}`,
    );

    if (skipTunnel || !existsSync(run.tunnel)) {
      if (!skipTunnel && !existsSync(run.tunnel)) {
        console.log(`[intent-run:${platform}] ○ ${run.id} 无 tunnel 配置，跳过抓包`);
      }
      continue;
    }

    console.log(`[intent-run:${platform}] ◆ ${run.id} Tunnel 验收...`);
    const tv = runTunnel(run.tunnel, startTime);
    if (tv.status !== 0) {
      failed += 1;
      failedIds.add(run.id);
      console.error(`[intent-run:${platform}] ✗ ${run.id} Tunnel 失败`);
      if (!continueOnError) break;
      continue;
    }
    console.log(`[intent-run:${platform}] ✓ ${run.id} Tunnel 通过`);
  }

  const executedIds = new Set([...failedIds]);

  for (const run of runs) {
    if (!failedIds.has(run.id)) {
      const reportExists = existsSync(
        resolve(REPORT_DIR, reportDirName(run.id, platform, usePlatformSubdir), 'index.html'),
      );
      if (reportExists) executedIds.add(run.id);
    }
  }

  const results = runs.map((run) => ({
    id: run.id,
    platform,
    passed: !failedIds.has(run.id) && executedIds.has(run.id),
    skipped: !executedIds.has(run.id),
    timedOut: timedOutIds.has(run.id),
    snapshotRunId: snapshotRunIds.get(run.id) ?? null,
    noPassResult: !executedIds.has(run.id),
  }));

  try {
    if (!opts.skipSummaryReport) {
      const reportOpts = usePlatformSubdir
        ? { platform, platformLabel: platform === 'ios' ? 'iOS' : 'Android' }
        : { platformLabel: platform === 'ios' ? 'iOS' : 'Android' };
      const mergeLatest = process.env.INTENT_REPORT_MERGE_LATEST !== '0';
      const reportResults = mergeLatest ? mergeResultsFromDisk(sources, results) : results;
      const reportPath = generateReport(sources, reportResults, reportOpts);
      console.log(`[intent-run:${platform}] 📊 聚合报告: ${reportPath}`);
    }
  } catch (e) {
    console.error(`[intent-run:${platform}] 报告生成失败: ${e.message}`);
  }

  if (failed > 0 && process.env.INTENT_AUTO_FIX !== '0') {
    try {
      autoFixAfterRun(sources, results);
    } catch (e) {
      console.error(`[intent-run:${platform}] auto-fix 失败: ${e.message}`);
    }
  }

  const exitCode = failed ? 1 : 0;
  if (failed) {
    console.error(
      `\n[intent-run:${platform}] 完成：${runs.length - failed}/${runs.length} 通过`,
    );
  } else {
    console.log(`\n[intent-run:${platform}] 全部通过（${runs.length} 条）`);
  }

  const payload = { platform, exitCode, runs, results, skipped: false };
  if (opts.writeResultJson) writeRunResult(platform, payload);
  return payload;
}

export function writeRunResult(platform, payload) {
  mkdirSync(RUNS_DIR, { recursive: true });
  const path = resolve(RUNS_DIR, `${platform}-latest.json`);
  writeFileSync(path, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  return path;
}

export function readRunResult(platform) {
  const path = resolve(RUNS_DIR, `${platform}-latest.json`);
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf8'));
}

export { ROOT, RUNS_DIR, REPORT_DIR };
