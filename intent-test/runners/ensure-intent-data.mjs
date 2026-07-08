#!/usr/bin/env node
/**
 * 跑意图用例前自动：preflight 抓包写 env → 不足则 seed UI 造抓包 → 再 preflight
 *
 * 环境:
 *   INTENT_SKIP_DATA_PREP=1   跳过整套数据准备
 *   INTENT_SKIP_TUNNEL_SEED=1 仅 preflight，不跑 seed UI
 *   INTENT_REQUIRE_DATA=1     数据未就绪则 exit 1（默认仅告警继续）
 *   INTENT_PREFLIGHT_SINCE=7200
 */

import { spawnSync } from 'child_process';
import { existsSync, readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { applyBaseProfileEnv } from './load-base-profile.mjs';
import { parseIntentFile, MIDSCENE_ROOT } from './compile-intent.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(ROOT, '..');
const PREFLIGHT = resolve(ROOT, 'runners/prepare-intent-data.mjs');
const COMPILE = resolve(ROOT, 'runners/compile-intent.mjs');
const MIDSCENE_RUN = resolve(MIDSCENE_ROOT, 'scripts/midscene-run.mjs');
const SEED_INTENT = resolve(ROOT, 'intents/_seed/gift-custom-tunnel-seed.yaml');
const PREFLIGHT_REPORT = resolve(ROOT, '.generated/preflight/latest.json');

const GIFT_INTENTS_NEED_SUBJECT = new Set([
  'IT-GIFT-NICK-001',
  'IT-GIFT-NICK-002',
  'IT-GIFT-NICK-004',
  'IT-GIFT-UID-001',
  'IT-GIFT-UID-002',
]);

function androidEnv() {
  const androidHome = process.env.ANDROID_HOME ?? `${process.env.HOME}/Library/Android/sdk`;
  return {
    ...process.env,
    ANDROID_HOME: androidHome,
    ANDROID_SDK_ROOT: androidHome,
    PATH: `${androidHome}/platform-tools:${process.env.PATH ?? ''}`,
  };
}

function collectIntentIds(sources, filterId) {
  const ids = new Set();
  for (const source of sources) {
    for (const doc of parseIntentFile(source)) {
      if (filterId && doc.id !== filterId) continue;
      ids.add(doc.id);
    }
  }
  return [...ids];
}

function needsGiftSubject(intentIds) {
  return intentIds.some((id) => GIFT_INTENTS_NEED_SUBJECT.has(id));
}

function runPreflight(writeEnv = true) {
  const since = process.env.INTENT_PREFLIGHT_SINCE ?? '7200';
  const args = [PREFLIGHT, '--since', since, '--out', resolve(ROOT, '.generated/preflight/latest.json')];
  if (writeEnv) args.push('--write-env');
  return spawnSync(process.execPath, args, { cwd: REPO, stdio: 'inherit', env: process.env });
}

function loadPreflightReport() {
  if (!existsSync(PREFLIGHT_REPORT)) return null;
  try {
    return JSON.parse(readFileSync(PREFLIGHT_REPORT, 'utf8'));
  } catch {
    return null;
  }
}

function giftSubjectReady(report, intentIds) {
  if (!report?.intents) return false;
  const relevant = intentIds.filter((id) => GIFT_INTENTS_NEED_SUBJECT.has(id));
  if (!relevant.length) return true;
  return relevant.every((id) => report.intents[id]?.ready);
}

function runSeedMidscene() {
  if (!existsSync(SEED_INTENT)) {
    console.error('[ensure-data] 缺少 seed 意图:', SEED_INTENT);
    return { ok: false, status: 1 };
  }
  if (!existsSync(MIDSCENE_RUN)) {
    console.error('[ensure-data] 未找到 Midscene:', MIDSCENE_RUN);
    return { ok: false, status: 1 };
  }

  console.log('[ensure-data] ▶ 执行 Tunnel 种子 UI（周榜 + 搜索）...');
  const compile = spawnSync(process.execPath, [COMPILE, SEED_INTENT], {
    cwd: ROOT,
    stdio: 'inherit',
    env: process.env,
  });
  if (compile.status !== 0) return { ok: false, status: compile.status ?? 1 };

  const yaml = resolve(ROOT, '.generated/IT-SEED-GIFT-TUNNEL.midscene.yaml');
  if (!existsSync(yaml)) {
    console.error('[ensure-data] seed 编译输出不存在:', yaml);
    return { ok: false, status: 1 };
  }

  const ui = spawnSync(
    process.execPath,
    [MIDSCENE_RUN, '--no-vcode', yaml],
    { stdio: 'inherit', cwd: MIDSCENE_ROOT, env: androidEnv() },
  );
  return { ok: ui.status === 0, status: ui.status ?? 1 };
}

/**
 * @param {{ sources: string[], filterId?: string|null }} opts
 */
export function ensureIntentData(opts) {
  if (process.env.INTENT_SKIP_DATA_PREP === '1') {
    console.log('[ensure-data] INTENT_SKIP_DATA_PREP=1，跳过抓包写 env');
    return { ready: true, skipped: true };
  }

  applyBaseProfileEnv();
  const intentIds = collectIntentIds(opts.sources, opts.filterId ?? null);
  if (!needsGiftSubject(intentIds)) {
    return { ready: true, skipped: true, reason: 'no_gift_subject_intents' };
  }

  console.log('[ensure-data] 定制礼物用例：自动 preflight 抓包写 env...');
  runPreflight(true);
  let report = loadPreflightReport();
  if (giftSubjectReady(report, intentIds)) {
    console.log('[ensure-data] ✓ 测试数据已就绪');
    return { ready: true, report };
  }

  if (process.env.INTENT_SKIP_TUNNEL_SEED === '1') {
    console.warn('[ensure-data] ! 数据未就绪，INTENT_SKIP_TUNNEL_SEED=1 跳过 seed');
    return { ready: false, report };
  }

  const seed = runSeedMidscene();
  if (!seed.ok) {
    console.warn('[ensure-data] ! Tunnel 种子 UI 未成功，仍尝试二次 preflight');
  }

  console.log('[ensure-data] 二次 preflight（seed 后写 env）...');
  runPreflight(true);
  report = loadPreflightReport();
  const ready = giftSubjectReady(report, intentIds);

  if (ready) {
    console.log('[ensure-data] ✓ seed 后测试数据已就绪');
    return { ready: true, report };
  }

  const missing = intentIds
    .filter((id) => GIFT_INTENTS_NEED_SUBJECT.has(id) && !report?.intents?.[id]?.ready)
    .map((id) => `${id}: ${report?.intents?.[id]?.reason ?? 'unknown'}`);
  console.warn('[ensure-data] ✗ 仍缺少测试数据:');
  for (const line of missing) console.warn(`  - ${line}`);

  if (process.env.INTENT_REQUIRE_DATA === '1') {
    return { ready: false, report, fatal: true };
  }

  console.warn('[ensure-data] 将继续跑用例（命中类 case 可能仍失败）');
  return { ready: false, report };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const sources = process.argv.slice(2).filter((a) => a.endsWith('.yaml') || a.endsWith('.yml'));
  if (!sources.length) {
    console.error('用法: node runners/ensure-intent-data.mjs <intent.yaml> [...]');
    process.exit(1);
  }
  const result = ensureIntentData({
    sources: sources.map((p) => resolve(process.cwd(), p)),
  });
  process.exit(result.fatal ? 1 : 0);
}
