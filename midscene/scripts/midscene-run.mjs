#!/usr/bin/env node
/**
 * YAML 测试包装脚本
 *
 * Android 模式（默认）：
 *   1. 推送 run_input.sh 到设备（用于验证码输入，绕开 midscene 的引号包裹问题）
 *   2. 并行：启动 midscene + HOST 侧轮询 getVerifyCode
 *   3. 轮询到验证码后 adb push 写入 /data/local/tmp/vcode.txt
 *   4. YAML 中 runAdbShell: "sh /data/local/tmp/run_input.sh" 读文件输入验证码
 *
 * iOS 模式（--platform=ios）：
 *   - 检查 WDA 是否在运行
 *   - 单个 YAML：直接运行
 *   - 两个 YAML（login 两阶段）：依次执行，中间获取验证码并注入 TEST_VERIFY_CODE
 *
 * 用法:
 *   Android: node scripts/midscene-run.mjs <yaml-glob> [...]
 *   Android（已登录游戏，跳过验证码）: 路径含 game- / game-center- 的 YAML 会自动跳过轮询
 *   Android（强制跳过验证码）: node scripts/midscene-run.mjs --no-vcode <yaml>
 *   iOS:     node scripts/midscene-run.mjs --platform=ios <yaml1> [yaml2]
 */

import { spawn, execSync } from 'child_process';
import { readFileSync, writeFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import os from 'os';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const VCODE_FILE   = '/data/local/tmp/vcode.txt';
const INPUT_SCRIPT = '/data/local/tmp/run_input.sh';
const GET_CODE_URL = 'https://fproject.immomo.com/inner/admin/ui/getVerifyCode';

// 手动加载 .env
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
      if (key && !process.env[key]) process.env[key] = val;
    }
  } catch { /* .env 不存在时忽略 */ }
}

function adb(...args) {
  const serial = process.env.ANDROID_DEVICE_ID;
  const prefix = serial ? ['adb', '-s', serial] : ['adb'];
  return execSync([...prefix, ...args].join(' '), { stdio: 'pipe' });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 检查 WDA 是否在运行 */
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

/** 向设备推送 run_input.sh（Android 专用） */
function pushInputScript() {
  const localPath = resolve(os.tmpdir(), 'midscene_run_input.sh');
  writeFileSync(localPath, `input text $(cat ${VCODE_FILE})\n`);
  adb('push', localPath, INPUT_SCRIPT);
  adb('shell', 'chmod', '+x', INPUT_SCRIPT);
  console.log('[midscene-run] ✓ 验证码输入脚本已推送到设备');
}

/** 向接口轮询获取验证码（最多 90s） */
async function fetchVerifyCode() {
  const phone  = process.env.TEST_PHONE;
  const prefix = process.env.TEST_PHONE_PREFIX ?? '966';
  const url    = `${GET_CODE_URL}?phone=${encodeURIComponent(phone)}&prefix=${encodeURIComponent(prefix)}`;

  for (let i = 0; i < 30; i++) {
    await sleep(3000);
    try {
      const res  = await fetch(url);
      const json = await res.json();
      if (json?.ec === 0 && json?.data?.code) {
        return String(json.data.code);
      }
      console.log(`[midscene-run] 轮询第 ${i + 1} 次：暂无验证码（ec=${json?.ec}）`);
    } catch (e) {
      console.log(`[midscene-run] 轮询第 ${i + 1} 次异常：${e.message}`);
    }
  }
  return null;
}

/** 轮询验证码并 adb push 写入设备文件（Android 专用，与 midscene 并行） */
async function pollAndPushCode() {
  const phone  = process.env.TEST_PHONE;
  const prefix = process.env.TEST_PHONE_PREFIX ?? '966';
  const url    = `${GET_CODE_URL}?phone=${encodeURIComponent(phone)}&prefix=${encodeURIComponent(prefix)}`;

  console.log('[midscene-run] 开始后台轮询验证码（每 3s）...');
  for (let i = 0; i < 30; i++) {
    await sleep(3000);
    try {
      const res  = await fetch(url);
      const json = await res.json();
      if (json?.ec === 0 && json?.data?.code) {
        const code = String(json.data.code);
        const localVcode = resolve(os.tmpdir(), 'midscene_vcode.txt');
        writeFileSync(localVcode, code + '\n');
        adb('push', localVcode, VCODE_FILE);
        console.log(`[midscene-run] ✓ 验证码 ${code} 已写入设备 ${VCODE_FILE}`);
        return code;
      }
      console.log(`[midscene-run] 轮询第 ${i + 1} 次：暂无验证码（ec=${json?.ec}）`);
    } catch (e) {
      console.log(`[midscene-run] 轮询第 ${i + 1} 次异常：${e.message}`);
    }
  }
  console.warn('[midscene-run] ⚠ 90s 内未获取到验证码，测试将继续');
  return null;
}

/** 清理 Android 设备临时文件 */
function cleanDeviceFiles() {
  try { adb('shell', 'rm', '-f', VCODE_FILE, INPUT_SCRIPT); } catch { /* ignore */ }
}

/** 是否需要在 Android 模式下轮询验证码（仅 login-p*.yaml 使用 run_input.sh） */
function needsAndroidVerifyCode(yamlPaths, rawArgs) {
  if (rawArgs.includes('--no-vcode')) return false;

  let hasConcrete = false;
  let needs = false;

  for (const arg of yamlPaths) {
    const normalized = arg.replace(/\\/g, '/');

    if (/[*?[\]]/.test(normalized)) {
      // 仅 game 相关 glob 可跳过；混合 glob（如 *-p1.yaml）仍保留轮询
      if (!/\/game-/.test(normalized) && !/game-center-/.test(normalized)) {
        return true;
      }
      continue;
    }

    hasConcrete = true;
    const fullPath = resolve(root, normalized);
    try {
      const content = readFileSync(fullPath, 'utf8');
      if (content.includes('run_input.sh') || content.includes('vcode.txt')) {
        needs = true;
      }
    } catch {
      if (/login-p/.test(normalized)) needs = true;
    }
  }

  return hasConcrete ? needs : false;
}

/** 运行 midscene，返回退出码 */
function runMidscene(yamlArgs, extraEnv = {}) {
  return new Promise((resolve) => {
    const child = spawn('npx', ['midscene', ...yamlArgs], {
      stdio: 'inherit',
      env: { ...process.env, ...extraEnv },
      cwd: root,
      shell: true,
    });
    child.on('close', resolve);
  });
}

// ─────────────────────────────────────────────────────────────────
// 主流程
// ─────────────────────────────────────────────────────────────────
async function main() {
  loadEnv();

  const rawArgs = process.argv.slice(2);
  if (!rawArgs.length) {
    console.error('用法: node scripts/midscene-run.mjs [--platform=ios] <yaml-glob> [...]');
    process.exit(1);
  }

  const isIos = rawArgs.includes('--platform=ios');
  const yamlArgs = rawArgs.filter((a) => !a.startsWith('--'));

  // ── iOS 模式 ─────────────────────────────────────────────────
  if (isIos) {
    const { ok, host, port } = await checkWda();
    if (!ok) {
      console.error(`\n[midscene-run] ❌ WDA 未运行（http://${host}:${port}/status 无响应）`);
      console.error('[midscene-run] 请先启动 WebDriverAgent，参考 README iOS 调试环境搭建章节');
      process.exit(1);
    }
    console.log(`[midscene-run] ✓ WDA 运行正常（http://${host}:${port}）`);

    if (yamlArgs.length === 2) {
      // 两阶段登录：phase1 触发 SMS → 取码 → phase2 注入验证码
      const [trigger, complete] = yamlArgs;

      console.log('[midscene-run] iOS 登录 Phase1：触发 SMS...');
      const exit1 = await runMidscene([trigger]);
      if (exit1 !== 0) process.exit(exit1);

      console.log('[midscene-run] iOS 登录：获取动态验证码...');
      const code = await fetchVerifyCode();
      if (!code) {
        console.error('[midscene-run] ❌ 90s 内未获取到验证码，终止测试');
        process.exit(1);
      }
      console.log(`[midscene-run] ✓ 验证码已获取：${code}`);

      console.log('[midscene-run] iOS 登录 Phase2：填入验证码...');
      const exit2 = await runMidscene([complete], { TEST_VERIFY_CODE: code });
      process.exit(exit2 ?? 0);

    } else {
      // 单 YAML（recharge 等，不需要验证码阶段）
      const exitCode = await runMidscene(yamlArgs);
      process.exit(exitCode ?? 0);
    }
  }

  // ── Android 模式（默认）────────────────────────────────────────
  const withVerifyCode = needsAndroidVerifyCode(yamlArgs, rawArgs);

  if (withVerifyCode) {
    try {
      pushInputScript();
    } catch (e) {
      console.warn(`[midscene-run] 推送脚本失败（ADB 未连接？）：${e.message}`);
    }
  } else {
    console.log('[midscene-run] 已登录用例，跳过验证码轮询');
  }

  const midscenePromise = runMidscene(yamlArgs);
  const pollPromise = withVerifyCode ? pollAndPushCode() : Promise.resolve(null);

  const [exitCode] = await Promise.all([midscenePromise, pollPromise]);
  if (withVerifyCode) cleanDeviceFiles();
  process.exit(exitCode ?? 0);
}

main().catch((err) => {
  console.error('[midscene-run] 错误:', err.message);
  process.exit(1);
});
