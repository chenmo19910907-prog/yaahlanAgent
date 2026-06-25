#!/usr/bin/env node
/**
 * 按固定顺序依次执行 testcases-yaml/ios/game-slots/*.yaml（单文件失败则停止）。
 * 前提：WDA 已启动；设备已在「游戏中心」页面。
 *
 * 用法：node scripts/run-ios-game-slots-ordered.mjs
 *       npm run yaml:ios:game-slots:all
 */

import { existsSync, readFileSync, readdirSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const slotsDir = resolve(root, 'testcases-yaml/ios/game-slots');

/** 执行顺序（与业务约定一致） */
const ORDERED_FILES = [
  'game-center-MoneyComing2-spin-p1.yaml',
  'game-center-fortune-Jewels-spin-p1.yaml',
  'game-center-frenzy-spin-p1.yaml',
  'game-center-yummy-spin-p1.yaml',
  'game-center-Original777-spin-p1.yaml',
  'game-center-CrzayGems-spin-p1.yaml', // CrazyGems
  'game-center-BookOfDeath-spin-p1.yaml',
  'game-center-WealthyTiger-spin-p1.yaml',
  'game-center-PokerAce-spin-p1.yaml',
  'game-center-Golden-Tree-spin-p1.yaml',
  'game-center-Mahjong-Slot-spin-p1.yaml',
  'game-center-Sphinx-spin-p1.yaml',
  'game-center-MagicLamp-spin-p1.yaml',
  'game-center-SuperSweet-spin-p1.yaml',
  'game-center-DJlive-spin-p1.yaml',
  'game-center-1001Nights-spin-p1.yaml',
  'game-center-Gladiator-spin-p1.yaml',
  'game-center-Lucky-Aladdin-spin-p1.yaml',
];

function loadEnv() {
  try {
    const lines = readFileSync(resolve(root, '.env'), 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const idx = trimmed.indexOf('=');
      if (idx === -1) continue;
      const key = trimmed.slice(0, idx).trim();
      const val = trimmed.slice(idx + 1).trim().replace(/\s*#.*$/, '').trim();
      if (key && process.env[key] === undefined) process.env[key] = val;
    }
  } catch {
    /* no .env */
  }
}

async function checkWda() {
  const host = process.env.WDA_HOST || 'localhost';
  const port = process.env.WDA_PORT || '8100';
  try {
    const res = await fetch(`http://${host}:${port}/status`, {
      signal: AbortSignal.timeout(3000),
    });
    return { ok: res.ok, host, port };
  } catch {
    return { ok: false, host, port };
  }
}

function runMidscene(yamlPath) {
  return new Promise((resolveExit) => {
    const child = spawn(
      'node',
      ['scripts/midscene-run.mjs', '--platform=ios', yamlPath],
      {
        stdio: 'inherit',
        env: process.env,
        cwd: root,
        shell: true,
      },
    );
    child.on('close', resolveExit);
  });
}

function resolveOrderedPaths() {
  const paths = [];
  const missing = [];

  for (const name of ORDERED_FILES) {
    const full = resolve(slotsDir, name);
    if (existsSync(full)) {
      paths.push(full);
    } else {
      missing.push(name);
    }
  }

  const allInDir = new Set(
    readdirSync(slotsDir)
      .filter((f) => f.endsWith('.yaml'))
      .map((f) => resolve(slotsDir, f)),
  );
  const orderedSet = new Set(paths);
  const notInOrder = [...allInDir].filter((p) => !orderedSet.has(p));

  return { paths, missing, notInOrder };
}

async function main() {
  loadEnv();

  const { ok, host, port } = await checkWda();
  if (!ok) {
    console.error(`\n[run-ios-game-slots] ❌ WDA 未运行（http://${host}:${port}/status 无响应）`);
    process.exit(1);
  }
  console.log(`[run-ios-game-slots] ✓ WDA 运行正常（http://${host}:${port}）`);

  const { paths, missing, notInOrder } = resolveOrderedPaths();

  if (missing.length) {
    console.warn('[run-ios-game-slots] ⚠ 顺序列表中缺失文件（将跳过）：');
    for (const m of missing) console.warn(`  - ${m}`);
  }
  if (notInOrder.length) {
    console.warn('[run-ios-game-slots] ⚠ 目录中存在未纳入执行顺序的文件（本次不执行）：');
    for (const p of notInOrder) console.warn(`  - ${p.replace(`${root}/`, '')}`);
  }

  if (!paths.length) {
    console.error('[run-ios-game-slots] 未找到任何可执行的 .yaml');
    process.exit(1);
  }

  console.log(`[run-ios-game-slots] 将按顺序执行 ${paths.length} 个用例：`);
  for (const f of paths) console.log(`  - ${f.replace(`${root}/`, '')}`);

  for (let i = 0; i < paths.length; i++) {
    const yamlPath = paths[i];
    const label = yamlPath.split('/').pop();
    console.log(`\n[run-ios-game-slots] (${i + 1}/${paths.length}) 开始：${label}`);
    const exitCode = await runMidscene(yamlPath);
    if (exitCode !== 0) {
      console.error(
        `[run-ios-game-slots] ❌ 失败：${label}，退出码 ${exitCode}，后续用例不再执行`,
      );
      process.exit(exitCode ?? 1);
    }
    console.log(`[run-ios-game-slots] ✓ 完成：${label}`);
  }

  console.log('\n[run-ios-game-slots] 🎉 全部用例执行成功');
}

main().catch((err) => {
  console.error('[run-ios-game-slots] 错误:', err.message);
  process.exit(1);
});
