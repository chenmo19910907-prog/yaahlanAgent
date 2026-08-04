/**
 * 从 Admin/.env.local 读取 SSO/JWT token，生成 Midscene web YAML 可用的 cookie JSON 文件。
 * 同时生成 localStorage 注入脚本供 setup YAML 使用。
 *
 * 用法: node scripts/gen-admin-cookies.mjs
 * 产物: .generated/admin-cookies.json
 */
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const ADMIN_DIR = resolve(ROOT, '../Admin');

function loadEnvLocal() {
  const envPath = resolve(ADMIN_DIR, '.env.local');
  let text;
  try {
    text = readFileSync(envPath, 'utf-8');
  } catch {
    console.error(`❌ 未找到 ${envPath}，请先配置 Admin/.env.local`);
    process.exit(1);
  }
  const vars = {};
  for (const line of text.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx < 0) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim();
    vars[key] = val;
  }
  return vars;
}

function main() {
  const env = loadEnvLocal();

  const ssoToken = env.ADMIN_SSO_TOKEN;
  const jwt = env.ADMIN_YAAHLAN_JWT;
  if (!ssoToken || !jwt) {
    console.error('❌ ADMIN_SSO_TOKEN 或 ADMIN_YAAHLAN_JWT 为空，请更新 Admin/.env.local');
    process.exit(1);
  }

  const domain = 'test-s.immomo.com';
  const apiDomain = 'yaahlan-admin-alpha.wemomo.com';
  const ssoDomain = '.immomo.com';

  // Aegis SSO cookies
  const aegisCna = env.ADMIN_AEGIS_CNA || '';
  const aegisSession = env.ADMIN_AEGIS_SESSION || '';
  const aegisV3Session = env.ADMIN_AEGIS_V3_SESSION || '';

  const cookies = [
    {
      name: 'sso-token',
      value: ssoToken,
      domain: domain,
      path: '/',
      httpOnly: false,
      secure: true,
      sameSite: 'None',
    },
    {
      name: 'sso-token',
      value: ssoToken,
      domain: apiDomain,
      path: '/',
      httpOnly: false,
      secure: true,
      sameSite: 'None',
    },
    {
      name: 'yaahlan-jwt',
      value: jwt,
      domain: domain,
      path: '/',
      httpOnly: false,
      secure: true,
      sameSite: 'None',
    },
    {
      name: 'yaahlan-jwt',
      value: jwt,
      domain: apiDomain,
      path: '/',
      httpOnly: false,
      secure: true,
      sameSite: 'None',
    },
  ];

  // 注入 Aegis SSO session cookies（绕过 aegis.immomo.com 登录页）
  const aegisDomain = 'aegis.immomo.com';
  const targetDomains = [aegisDomain, ssoDomain, domain];

  if (aegisCna) {
    for (const d of targetDomains) {
      cookies.push({
        name: 'cna',
        value: aegisCna,
        domain: d,
        path: '/',
        httpOnly: false,
        secure: true,
        sameSite: 'None',
      });
    }
  }
  if (aegisSession) {
    for (const d of targetDomains) {
      cookies.push({
        name: 'tunnel_login_session',
        value: aegisSession,
        domain: d,
        path: '/',
        httpOnly: true,
        secure: true,
        sameSite: 'None',
      });
    }
  }
  // aegis_v3_session —— Aegis SSO 关键 session cookie
  if (aegisV3Session) {
    for (const d of targetDomains) {
      cookies.push({
        name: 'aegis_v3_session',
        value: aegisV3Session,
        domain: d,
        path: '/',
        httpOnly: true,
        secure: true,
        sameSite: 'Lax',
      });
    }
  }

  const outDir = resolve(ROOT, '.generated');
  mkdirSync(outDir, { recursive: true });

  const cookiePath = resolve(outDir, 'admin-cookies.json');
  writeFileSync(cookiePath, JSON.stringify(cookies, null, 2));
  console.log(`✅ Cookie 文件已生成: ${cookiePath}`);

  // 生成 localStorage 数据（部分前端 SPA 用 localStorage 存 token）
  const storageData = {
    'sso-token': ssoToken,
    'yaahlan-jwt': jwt,
    'token': ssoToken,
  };
  const storagePath = resolve(outDir, 'admin-storage.json');
  writeFileSync(storagePath, JSON.stringify(storageData, null, 2));
  console.log(`✅ Storage 文件已生成: ${storagePath}`);
}

main();
