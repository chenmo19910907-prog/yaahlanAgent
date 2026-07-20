#!/usr/bin/env node
import { existsSync, readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import { getPlatformProfile, loadBaseProfile } from './load-base-profile.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MIDSCENE = resolve(ROOT, '../midscene');

let ok = true;
function check(label, pass, hint) {
  console.log(`${pass ? '✓' : '✗'} ${label}${hint ? ` — ${hint}` : ''}`);
  if (!pass) ok = false;
}

check('midscene 目录', existsSync(MIDSCENE), MIDSCENE);
check('midscene/.env', existsSync(resolve(MIDSCENE, '.env')), 'cp midscene/.env.example .env');
check('midscene node_modules', existsSync(resolve(MIDSCENE, 'node_modules')), 'cd midscene && npm install');
check('intent-test yaml 依赖', existsSync(resolve(ROOT, 'node_modules/yaml')), 'cd intent-test && npm install');

try {
  execSync('adb devices', { stdio: 'pipe' });
  const out = execSync('adb devices', { encoding: 'utf8' });
  const devices = out.split('\n').filter((l) => l.includes('\tdevice'));
  check('ADB 设备', devices.length > 0, devices.length ? devices[0].split('\t')[0] : 'adb devices 无 device');
} catch {
  check('ADB 可用', false, '安装 android-platform-tools');
}

try {
  const profilePath = resolve(ROOT, 'config/base-profile.yaml');
  if (existsSync(profilePath)) {
    const ios = getPlatformProfile('ios', loadBaseProfile());
    const host = ios?.env?.WDA_HOST ?? 'localhost';
    const port = ios?.env?.WDA_PORT ?? '8100';
    const wdaUrl = `http://${host}:${port}/status`;
    let wdaOk = false;
    try {
      execSync(`curl -sf --max-time 3 ${wdaUrl}`, { stdio: 'pipe' });
      wdaOk = true;
    } catch {
      wdaOk = false;
    }
    console.log(
      `${wdaOk ? '✓' : '○'} WDA (${host}:${port})${wdaOk ? '' : ' — 双端 iOS 跑测前需启动 WebDriverAgent'}`,
    );
  }
} catch {
  /* optional */
}

try {
  const catalog = JSON.parse(readFileSync(resolve(ROOT, 'intents/catalog.json'), 'utf8'));
  const count = Object.values(catalog.modules ?? {}).reduce(
    (n, m) => n + (m.intents?.length ?? 0),
    0,
  );
  check('意图 catalog', count > 0, `${count} 个意图文件`);
} catch (e) {
  check('意图 catalog', false, e.message);
}

try {
  const repo = resolve(ROOT, '..');
  const paths = [
    resolve(repo, 'Tunnel/.env.local'),
    resolve(repo, 'MOA/.env.local'),
  ];
  const hasTunnel = paths.some((p) => {
    try {
      const text = readFileSync(p, 'utf8');
      return text.includes('TUNNEL_COOKIE') || text.includes('MOA_COOKIE');
    } catch {
      return false;
    }
  });
  check('Tunnel Cookie 配置', hasTunnel, 'Tunnel/.env.local 或 MOA/.env.local');
} catch (e) {
  check('Tunnel Cookie 配置', false, e.message);
}

const momoid = process.env.TEST_TUNNEL_MOMOID;
if (existsSync(resolve(MIDSCENE, '.env'))) {
  const envText = readFileSync(resolve(MIDSCENE, '.env'), 'utf8');
  const hasMomoid = /TEST_TUNNEL_MOMOID=\d+/.test(envText);
  check('TEST_TUNNEL_MOMOID', hasMomoid, momoid || '写入 midscene/.env');
}

try {
  const latest = resolve(ROOT, '.generated/preflight/latest.json');
  if (existsSync(latest)) {
    const report = JSON.parse(readFileSync(latest, 'utf8'));
    const ready = Object.values(report.intents ?? {}).filter((x) => x.ready).length;
    const total = Object.values(report.intents ?? {}).length;
    console.log(
      `${report.ok ? '✓' : '○'} Tunnel 预检（可选） — ${ready}/${total} 意图就绪，报告 ${latest}`,
    );
  } else {
    console.log('○ Tunnel 预检（可选） — 真机进房开礼物面板后 npm run preflight -- --write-env');
  }
} catch (e) {
  console.log(`○ Tunnel 预检（可选） — ${e.message}`);
}

process.exit(ok ? 0 : 1);
