#!/usr/bin/env node
/**
 * 加载 intent-test/config/base-profile.yaml，注入 process.env（不覆盖已存在变量）。
 */

import { existsSync, readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { parse } from 'yaml';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const BASE_PROFILE_PATH = resolve(ROOT, 'config/base-profile.yaml');

export function loadBaseProfile(path = BASE_PROFILE_PATH) {
  if (!existsSync(path)) {
    return null;
  }
  const doc = parse(readFileSync(path, 'utf8'));
  if (!doc || typeof doc !== 'object') {
    throw new Error(`base-profile 格式无效: ${path}`);
  }
  return doc;
}

/** 将 profile.env 与 profile.intent 写入 process.env（已有值不覆盖） */
export function applyBaseProfileEnv(profile = loadBaseProfile()) {
  if (!profile) {
    return { profile, applied: [] };
  }
  const applied = [];
  const intent = profile.intent;
  if (intent && typeof intent === 'object') {
    const intentEnv = {
      ...(intent.requireData ? { INTENT_REQUIRE_DATA: '1' } : {}),
      ...(intent.continueOnError ? { INTENT_CONTINUE: '1' } : {}),
      ...(intent.skipTunnel ? { INTENT_TUNNEL: '0' } : {}),
    };
    for (const [key, value] of Object.entries(intentEnv)) {
      if (!process.env[key]) {
        process.env[key] = value;
        applied.push(key);
      }
    }
  }
  if (!profile.env || typeof profile.env !== 'object') {
    return { profile, applied };
  }
  for (const [key, value] of Object.entries(profile.env)) {
    if (value == null || String(value).trim() === '') continue;
    if (process.env[key]) continue;
    process.env[key] = String(value).trim();
    applied.push(key);
  }
  return { profile, applied };
}
export function dumpBaseProfileEnvJson() {
  const profile = loadBaseProfile();
  const env = profile?.env && typeof profile.env === 'object' ? profile.env : {};
  return JSON.stringify({ profile, env }, null, 2);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  if (process.argv.includes('--json')) {
    console.log(dumpBaseProfileEnvJson());
  } else {
    const { profile, applied } = applyBaseProfileEnv();
    console.log(`[base-profile] ${profile ? '已加载' : '未找到'} ${BASE_PROFILE_PATH}`);
    if (applied.length) {
      console.log(`[base-profile] 注入 env: ${applied.join(', ')}`);
    }
  }
}
