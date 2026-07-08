#!/usr/bin/env node
/**
 * 编译并执行意图测试：Midscene UI + Tunnel 抓包验收
 */

import { spawnSync } from 'child_process';
import { readFileSync, existsSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { parseIntentFile, GENERATED, MIDSCENE_ROOT } from './compile-intent.mjs';
import { applyBaseProfileEnv } from './load-base-profile.mjs';
import { ensureIntentData } from './ensure-intent-data.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const COMPILE = resolve(ROOT, 'runners/compile-intent.mjs');
const MIDSCENE_RUN = resolve(MIDSCENE_ROOT, 'scripts/midscene-run.mjs');
const TUNNEL_VERIFY = resolve(ROOT, 'runners/tunnel-verify.py');

function loadCatalog() {
  const path = resolve(ROOT, 'intents/catalog.json');
  return JSON.parse(readFileSync(path, 'utf8'));
}

function resolveInputs(args) {
  const moduleIdx = args.indexOf('--module');
  if (moduleIdx !== -1) {
    const mod = args[moduleIdx + 1];
    const catalog = loadCatalog();
    const paths = catalog.modules?.[mod]?.intents ?? [];
    if (!paths.length) {
      console.error(`[intent-run] 模块未找到: ${mod}`);
      process.exit(1);
    }
    return { paths: paths.map((p) => resolve(ROOT, p)), filterId: null };
  }

  const idIdx = args.indexOf('--id');
  if (idIdx !== -1) {
    return { paths: [], filterId: args[idIdx + 1] };
  }

  const files = args.filter((a) => !a.startsWith('--'));
  if (!files.length) {
    console.error('用法: node runners/intent-run.mjs <intent.yaml> | --module <名> | --id <ID>');
    console.error('环境: INTENT_TUNNEL=0 跳过抓包；INTENT_CONTINUE=1 失败后继续');
    console.error('      INTENT_SKIP_DATA_PREP=1 跳过自动抓包写 env');
    process.exit(1);
  }
  return { paths: files.map((f) => resolve(process.cwd(), f)), filterId: null };
}

function findSourceById(id) {
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

function androidEnv() {
  const androidHome =
    process.env.ANDROID_HOME ?? `${process.env.HOME}/Library/Android/sdk`;
  return {
    ...process.env,
    ANDROID_HOME: androidHome,
    ANDROID_SDK_ROOT: androidHome,
    PATH: `${androidHome}/platform-tools:${process.env.PATH ?? ''}`,
  };
}

function runMidscene(yamlPath) {
  const platform = process.env.INTENT_PLATFORM ?? 'android';
  return spawnSync(
    process.execPath,
    [
      MIDSCENE_RUN,
      ...(platform === 'ios' ? ['--platform=ios'] : ['--no-vcode']),
      yamlPath,
    ],
    { stdio: 'inherit', cwd: MIDSCENE_ROOT, env: androidEnv() },
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

function collectRuns(sources, filterId) {
  const runs = [];
  for (const p of sources) {
    for (const doc of parseIntentFile(p)) {
      if (filterId && doc.id !== filterId) continue;
      runs.push({
        id: doc.id,
        yaml: resolve(GENERATED, `${doc.id}.midscene.yaml`),
        tunnel: resolve(GENERATED, `${doc.id}.tunnel.json`),
      });
    }
  }
  return runs;
}

function main() {
  applyBaseProfileEnv();
  if (!existsSync(MIDSCENE_RUN)) {
    console.error(`[intent-run] 未找到: ${MIDSCENE_RUN}`);
    process.exit(1);
  }

  const cliArgs = process.argv.slice(2);
  const skipTunnel = process.env.INTENT_TUNNEL === '0';
  const continueOnError = process.env.INTENT_CONTINUE === '1';
  const { paths, filterId } = resolveInputs(cliArgs);
  let sources = paths;

  if (filterId) {
    const source = findSourceById(filterId);
    if (!source) {
      console.error(`[intent-run] catalog 中未找到: ${filterId}`);
      process.exit(1);
    }
    sources = [source];
  }

  const dataPrep = ensureIntentData({ sources, filterId });
  if (dataPrep.fatal) {
    process.exit(1);
  }

  for (const p of sources) {
    const r = spawnSync(process.execPath, [COMPILE, p], { stdio: 'inherit', cwd: ROOT });
    if (r.status !== 0) process.exit(r.status ?? 1);
  }

  const runs = collectRuns(sources, filterId);
  if (!runs.length) {
    console.error('[intent-run] 无待执行用例');
    process.exit(1);
  }

  console.log(`[intent-run] 共 ${runs.length} 条（逐条 UI${skipTunnel ? '' : ' + Tunnel'}）`);
  let failed = 0;

  for (const run of runs) {
    console.log(`\n[intent-run] ▶ ${run.id}`);
    const startTime = Math.floor(Date.now() / 1000) - 5;
    const ui = runMidscene(run.yaml);
    if (ui.status !== 0) {
      failed += 1;
      console.error(`[intent-run] ✗ ${run.id} UI 失败`);
      if (!continueOnError) break;
      continue;
    }
    console.log(`[intent-run] ✓ ${run.id} UI 通过`);

    if (skipTunnel || !existsSync(run.tunnel)) {
      if (!skipTunnel && !existsSync(run.tunnel)) {
        console.log(`[intent-run] ○ ${run.id} 无 tunnel 配置，跳过抓包`);
      }
      continue;
    }

    console.log(`[intent-run] ◆ ${run.id} Tunnel 验收...`);
    const tv = runTunnel(run.tunnel, startTime);
    if (tv.status !== 0) {
      failed += 1;
      console.error(`[intent-run] ✗ ${run.id} Tunnel 失败`);
      if (!continueOnError) break;
      continue;
    }
    console.log(`[intent-run] ✓ ${run.id} Tunnel 通过`);
  }

  if (failed) {
    console.error(`\n[intent-run] 完成：${runs.length - failed}/${runs.length} 通过`);
    process.exit(1);
  }
  console.log(`\n[intent-run] 全部通过（${runs.length} 条）`);
}

main();
