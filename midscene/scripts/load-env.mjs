#!/usr/bin/env node
/**
 * 加载 midscene/.env；MIDSCENE_* 始终以文件为准，避免 shell 空变量覆盖真实 Key。
 */

import { readFileSync, existsSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const DEFAULT_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MIDSCENE_PREFIX = /^MIDSCENE_/;

export function parseEnvFile(content) {
  const vars = {};
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx === -1) continue;
    const key = trimmed.slice(0, idx).trim();
    let val = trimmed.slice(idx + 1).trim().replace(/\s*#.*$/, '').trim();
    if (
      (val.startsWith('"') && val.endsWith('"'))
      || (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (key) vars[key] = val;
  }
  return vars;
}

/** @returns {Record<string, string>} */
export function loadMidsceneEnv(opts = {}) {
  const root = opts.root ?? DEFAULT_ROOT;
  const envPath = resolve(root, '.env');
  if (!existsSync(envPath)) {
    return {};
  }

  const vars = parseEnvFile(readFileSync(envPath, 'utf8'));
  for (const [key, val] of Object.entries(vars)) {
    if (!key) continue;
    const forceFromFile = MIDSCENE_PREFIX.test(key);
    const current = process.env[key];
    const currentEmpty = current == null || String(current).trim() === '';
    if (forceFromFile || currentEmpty) {
      process.env[key] = val;
    }
  }
  return vars;
}

export function readMidsceneEnv(opts = {}) {
  const root = opts.root ?? DEFAULT_ROOT;
  const envPath = resolve(root, '.env');
  if (!existsSync(envPath)) return {};
  return parseEnvFile(readFileSync(envPath, 'utf8'));
}

export function validateModelEnv(vars = readMidsceneEnv()) {
  const required = [
    'MIDSCENE_MODEL_BASE_URL',
    'MIDSCENE_MODEL_API_KEY',
    'MIDSCENE_MODEL_NAME',
    'MIDSCENE_MODEL_FAMILY',
  ];
  const missing = required.filter((k) => !String(vars[k] ?? '').trim());
  return { ok: missing.length === 0, missing, vars };
}
