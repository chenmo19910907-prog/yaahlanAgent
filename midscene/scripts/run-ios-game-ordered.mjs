#!/usr/bin/env node
/**
 * 按文件名顺序依次执行 testcases-yaml/ios/game/*.yaml（单文件失败则停止）。
 * 前提：WDA 已启动；设备已在「游戏中心」页面。
 *
 * 用法：node scripts/run-ios-game-ordered.mjs
 */

import { readdirSync, readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const gameDir = resolve(root, 'testcases-yaml/ios/game');

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
    const child = spawn('npx', ['midscene', yamlPath], {
      stdio: 'inherit',
      env: process.env,
      cwd: root,
      shell: true,
    });
    child.on('close', resolveExit);
  });
}

async function main() {
  loadEnv();

  const { ok, host, port } = await checkWda();
  if (!ok) {
    console.error(`\n[run-ios-game] ❌ WDA 未运行（http://${host}:${port}/status 无响应）`);
    process.exit(1);
  }
  console.log(`[run-ios-game] ✓ WDA 运行正常（http://${host}:${port}）`);

  const files = readdirSync(gameDir)
    .filter((f) => f.endsWith('.yaml'))
    .sort()
    .map((f) => resolve(gameDir, f));

  if (!files.length) {
    console.error('[run-ios-game] 未找到任何 .yaml');
    process.exit(1);
  }

  console.log(`[run-ios-game] 将按顺序执行 ${files.length} 个用例：`);
  for (const f of files) console.log(`  - ${f.replace(`${root}/`, '')}`);

  for (let i = 0; i < files.length; i++) {
    const yamlPath = files[i];
    const label = yamlPath.split('/').pop();
    console.log(`\n[run-ios-game] (${i + 1}/${files.length}) 开始：${label}`);
    const exitCode = await runMidscene(yamlPath);
    if (exitCode !== 0) {
      console.error(`[run-ios-game] ❌ 失败：${label}，退出码 ${exitCode}，后续用例不再执行`);
      process.exit(exitCode ?? 1);
    }
    console.log(`[run-ios-game] ✓ 完成：${label}`);
  }

  console.log('\n[run-ios-game] 🎉 全部用例执行成功');
}

main().catch((err) => {
  console.error('[run-ios-game] 错误:', err.message);
  process.exit(1);
});
