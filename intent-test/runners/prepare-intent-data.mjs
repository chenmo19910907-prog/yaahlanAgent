#!/usr/bin/env node
/**
 * Tunnel 数据准备入口：调用 tunnel-preflight.py，可选写入 midscene/.env
 *
 * 用法:
 *   npm run preflight
 *   npm run preflight -- --write-env
 *   npm run preflight -- --momoid 100312107 --since 3600
 */
import { spawnSync } from 'child_process';
import { existsSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { applyBaseProfileEnv } from './load-base-profile.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const REPO = resolve(ROOT, '..');
const PREFLIGHT = resolve(ROOT, 'runners/tunnel-preflight.py');

if (!existsSync(PREFLIGHT)) {
  console.error('[prepare-intent-data] 缺少', PREFLIGHT);
  process.exit(1);
}

const args = process.argv.slice(2);
applyBaseProfileEnv();
const passthrough = ['--out', resolve(ROOT, '.generated/preflight/latest.json')];

if (!args.includes('--write-env') && process.env.INTENT_PREFLIGHT_WRITE_ENV === '1') {
  passthrough.push('--write-env');
}

const py = spawnSync('python3', [PREFLIGHT, ...passthrough, ...args], {
  cwd: REPO,
  stdio: 'inherit',
  encoding: 'utf8',
});

if (py.error) {
  console.error('[prepare-intent-data] python3 不可用:', py.error.message);
  process.exit(1);
}

process.exit(py.status ?? 1);
