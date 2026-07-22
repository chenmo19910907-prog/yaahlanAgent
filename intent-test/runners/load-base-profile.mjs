#!/usr/bin/env node
/**
 * 加载 intent-test/config/base-profile.yaml，支持单端 / 双端 profile。
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

function mergeEnv(profile, platform) {
  const shared = profile.env && typeof profile.env === 'object' ? profile.env : {};
  const platformBlock = profile.platforms?.[platform];
  const platformEnv =
    platformBlock?.env && typeof platformBlock.env === 'object'
      ? platformBlock.env
      : {};

  if (platform === 'android' && !Object.keys(platformEnv).length) {
    return { ...shared };
  }
  return { ...shared, ...platformEnv };
}

/** 读取某平台的 device/app/env 配置（android 可回退到顶层 device/app/env） */
export function getPlatformProfile(platform = 'android', profile = loadBaseProfile()) {
  if (!profile) return null;
  const key = String(platform).toLowerCase();
  const block = profile.platforms?.[key];

  if (block) {
    return {
      platform: key,
      account: profile.account,
      room: profile.room,
      intent: profile.intent,
      device: block.device ?? {},
      app: block.app ?? {},
      env: mergeEnv(profile, key),
    };
  }

  if (key === 'android') {
    return {
      platform: 'android',
      account: profile.account,
      room: profile.room,
      intent: profile.intent,
      device: profile.device ?? {},
      app: profile.app ?? {},
      env: mergeEnv(profile, 'android'),
    };
  }

  return {
    platform: key,
    account: profile.account,
    room: profile.room,
    intent: profile.intent,
    device: {},
    app: {},
    env: mergeEnv(profile, key),
  };
}

/** 将 profile.env 与 profile.intent 写入 process.env（已有值不覆盖） */
export function applyBaseProfileEnv(profile = loadBaseProfile()) {
  if (!profile) {
    return { profile, applied: [] };
  }
  return applyPlatformProfileEnv('android', profile);
}

/** 按平台注入 env；platform=android 时兼容旧版扁平 env 段 */
export function applyPlatformProfileEnv(platform = 'android', profile = loadBaseProfile()) {
  if (!profile) {
    return { profile: null, platform, applied: [] };
  }

  const plat = getPlatformProfile(platform, profile);
  const applied = [];
  const intent = plat.intent ?? profile.intent;
  if (intent && typeof intent === 'object') {
    const autoDebugOff = intent.autoDebug === false;
    const setupRetryOn = !autoDebugOff && intent.setupRetry !== false;
    const autoFixOn = !autoDebugOff && intent.autoFix !== false;
    const intentEnv = {
      ...(intent.requireData ? { INTENT_REQUIRE_DATA: '1' } : {}),
      ...(intent.continueOnError ? { INTENT_CONTINUE: '1' } : {}),
      ...(intent.skipTunnel ? { INTENT_TUNNEL: '0' } : {}),
      ...(setupRetryOn ? { INTENT_SETUP_RETRY: '1' } : { INTENT_SETUP_RETRY: '0' }),
      ...(autoFixOn ? { INTENT_AUTO_FIX: '1' } : { INTENT_AUTO_FIX: '0' }),
    };
    for (const [key, value] of Object.entries(intentEnv)) {
      if (!process.env[key]) {
        process.env[key] = value;
        applied.push(key);
      }
    }
  }

  const envMap = plat.env ?? {};
  for (const [key, value] of Object.entries(envMap)) {
    if (value == null || String(value).trim() === '') continue;
    if (process.env[key]) continue;
    process.env[key] = String(value).trim();
    applied.push(key);
  }

  if (!process.env.INTENT_PLATFORM) {
    process.env.INTENT_PLATFORM = platform;
    applied.push('INTENT_PLATFORM');
  }

  return { profile: plat, platform, applied };
}

export function dumpBaseProfileEnvJson() {
  const profile = loadBaseProfile();
  return JSON.stringify(
    {
      profile,
      android: getPlatformProfile('android', profile),
      ios: getPlatformProfile('ios', profile),
    },
    null,
    2,
  );
}

if (import.meta.url === `file://${process.argv[1]}`) {
  if (process.argv.includes('--json')) {
    console.log(dumpBaseProfileEnvJson());
  } else {
    const platform = process.argv.includes('--ios') ? 'ios' : 'android';
    const { profile, applied } = applyPlatformProfileEnv(platform);
    console.log(
      `[base-profile] ${profile ? '已加载' : '未找到'} ${BASE_PROFILE_PATH} (${platform})`,
    );
    if (applied.length) {
      console.log(`[base-profile] 注入 env: ${applied.join(', ')}`);
    }
  }
}
