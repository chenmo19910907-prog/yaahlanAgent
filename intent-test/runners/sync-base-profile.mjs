#!/usr/bin/env node
/**
 * 将 config/base-profile.yaml 的 env 段同步到 midscene/.env
 *
 * 用法: npm run sync-profile
 */

import { existsSync, readFileSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { loadBaseProfile, getPlatformProfile, BASE_PROFILE_PATH } from './load-base-profile.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MIDSCENE_ENV = resolve(ROOT, '../midscene/.env');

function patchEnvFile(envVars) {
  if (!existsSync(MIDSCENE_ENV)) {
    throw new Error(`未找到 ${MIDSCENE_ENV}，请先 cp midscene/.env.example midscene/.env`);
  }

  const lines = readFileSync(MIDSCENE_ENV, 'utf8').split('\n');
  const updated = [];
  const seen = new Set();
  const newLines = [];

  for (const line of lines) {
    if (!line.includes('=') || line.trim().startsWith('#')) {
      newLines.push(line);
      continue;
    }
    const key = line.split('=', 1)[0].trim();
    if (Object.prototype.hasOwnProperty.call(envVars, key)) {
      newLines.push(`${key}=${envVars[key]}`);
      updated.push(key);
      seen.add(key);
    } else {
      newLines.push(line);
    }
  }

  const missing = Object.keys(envVars).filter((k) => !seen.has(k));
  if (missing.length) {
    if (newLines.length && newLines[newLines.length - 1].trim()) {
      newLines.push('');
    }
    newLines.push('# ---- intent-test base-profile 同步 ----');
    for (const key of missing) {
      newLines.push(`${key}=${envVars[key]}`);
      updated.push(key);
    }
  }

  writeFileSync(MIDSCENE_ENV, `${newLines.join('\n')}\n`, 'utf8');
  return updated;
}

function main() {
  const platform = process.argv.includes('--ios') ? 'ios' : 'android';
  const profile = loadBaseProfile();
  const plat = getPlatformProfile(platform, profile);
  const envMap = { ...(profile?.env ?? {}), ...(plat?.env ?? {}) };

  if (!Object.keys(envMap).length) {
    console.error(`[sync-profile] ✗ 无 env 段: ${BASE_PROFILE_PATH}`);
    process.exit(1);
  }

  const envVars = {};
  for (const [key, value] of Object.entries(envMap)) {
    if (value == null) continue;
    envVars[key] = String(value).trim();
  }

  const updated = patchEnvFile(envVars);
  console.log(`[sync-profile] ✓ 已写入 midscene/.env (${platform}): ${updated.join(', ')}`);
  console.log(
    `[sync-profile] 账号 ${profile.account?.userId ?? '-'} · 房间 ${profile.room?.voiceRoomId ?? '-'}`,
  );
}

main();
