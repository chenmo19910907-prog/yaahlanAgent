#!/usr/bin/env node
/**
 * 意图 YAML → Midscene YAML 编译器
 *
 * 用法:
 *   node runners/compile-intent.mjs <intent.yaml> [intent2.yaml ...]
 *   node runners/compile-intent.mjs --all
 *
 * 输出: intent-test/.generated/<id>.midscene.yaml
 */

import { readFileSync, writeFileSync, mkdirSync, readdirSync, statSync, existsSync } from 'fs';
import { dirname, resolve, basename, relative } from 'path';
import { fileURLToPath } from 'url';
import { applyBaseProfileEnv } from './load-base-profile.mjs';
import { parseAllDocuments, parse } from 'yaml';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const GENERATED = resolve(ROOT, '.generated');
const FRAGMENTS_DIR = resolve(ROOT, 'intents/_fragments');
const MIDSCENE_ROOT = process.env.MIDSCENE_ROOT
  ? resolve(ROOT, process.env.MIDSCENE_ROOT)
  : resolve(ROOT, '../midscene');

const POPUP_POLICY_AI_CONTEXT =
  '【全局弹窗策略】执行任意 aiAct 时若遇挡路弹窗：' +
  '(1) 系统权限（位置/通知/麦克风/摄像头/相册/存储）及用户协议/隐私政策：点允许、好或同意；' +
  '(2) 带 X、× 或 Close 关闭按钮的业务弹窗、广告、活动、青少年模式：优先点 X 关闭，不要点弹窗主体进入活动；' +
  '(3) 邀请类弹窗（进房、游戏、语音房、好友、活动邀请等）：默认点拒绝、Decline、Reject、不了或 Cancel，不要点接受/Join；' +
  '(4) 二次确认弹窗仅在用例步骤或 aiContext 明确要求时点确定，否则点取消或 X。' +
  '仅当 aiContext 或 setup.acceptInvites 明确说明需通过弹窗进入某场景时，才可对邀请弹窗点接受。';

const DEFAULT_AI_CONTEXT = POPUP_POLICY_AI_CONTEXT;

function buildAiContext(doc, setup = {}) {
  if (setup.popupPolicy === 'none') {
    const custom = doc.aiContext ? expandTemplate(String(doc.aiContext)).trim() : '';
    return custom || '按用例 aiContext 与步骤执行，不附加默认弹窗策略。';
  }

  let policy = POPUP_POLICY_AI_CONTEXT;
  if (setup.acceptInvites) {
    policy +=
      ' 【本用例例外】遇到邀请弹窗时可点接受/Join 进入用例目标场景；其他带 X 的弹窗仍优先点 X 关闭。';
  }

  const custom = doc.aiContext ? expandTemplate(String(doc.aiContext)).trim() : '';
  return custom ? `${policy}\n${custom}` : policy;
}

const DEFAULT_ACT_SLEEP_MS = Number(process.env.INTENT_ACT_SLEEP_MS ?? 1000);

function loadEnvFromMidscene() {
  applyBaseProfileEnv();
  try {
    const lines = readFileSync(resolve(MIDSCENE_ROOT, '.env'), 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
      const idx = trimmed.indexOf('=');
      const key = trimmed.slice(0, idx).trim();
      const val = trimmed.slice(idx + 1).trim().replace(/\s*#.*$/, '').trim();
      if (key) process.env[key] = val;
    }
  } catch {
    /* midscene/.env 可选 */
  }
}

function expandTemplate(str) {
  if (typeof str !== 'string') return str;
  return str.replace(/\$\{(\w+)\}/g, (_, key) => process.env[key] ?? `\${${key}}`);
}

function yamlQuote(str) {
  if (/[:#\n"'\\]/.test(str) || str.includes('${')) {
    return JSON.stringify(str);
  }
  return str;
}

/** setup.steps 支持 string | { act } | { waitFor } | { sleep: ms } */
function appendSetupStep(flow, step) {
  if (typeof step === 'string') {
    flow.push({ aiAct: expandTemplate(step) });
    flow.push({ sleep: DEFAULT_ACT_SLEEP_MS });
    return;
  }
  if (step?.act) {
    flow.push({ aiAct: expandTemplate(String(step.act)) });
    flow.push({ sleep: step.afterSleep ?? DEFAULT_ACT_SLEEP_MS });
  }
  if (step?.waitFor) {
    flow.push({ aiWaitFor: expandTemplate(String(step.waitFor)) });
  }
  if (step?.sleep) {
    flow.push({ sleep: Number(step.sleep) });
  }
}

let fragmentIndexCache = null;

function parseFragmentFile(filePath) {
  const raw = readFileSync(filePath, 'utf8');
  const docs = parseAllDocuments(raw).map((d) => d.toJSON()).filter(Boolean);
  if (docs.length === 1 && docs[0] && typeof docs[0] === 'object') {
    return docs[0];
  }
  const parsed = parse(raw);
  if (parsed && typeof parsed === 'object') {
    return parsed;
  }
  throw new Error(`片段文件格式无效: ${filePath}`);
}

function loadFragmentIndex() {
  if (fragmentIndexCache) return fragmentIndexCache;

  const byName = new Map();
  const byQualified = new Map();

  if (!existsSync(FRAGMENTS_DIR)) {
    fragmentIndexCache = { byName, byQualified };
    return fragmentIndexCache;
  }

  function walk(dir, prefix = '') {
    for (const name of readdirSync(dir)) {
      const p = resolve(dir, name);
      if (statSync(p).isDirectory()) {
        walk(p, prefix ? `${prefix}/${name}` : name);
        continue;
      }
      if (!name.endsWith('.yaml') && !name.endsWith('.yml')) continue;

      const stem = basename(name, name.endsWith('.yaml') ? '.yaml' : '.yml');
      const qualifiedPrefix = prefix ? `${prefix}/${stem}` : stem;
      const doc = parseFragmentFile(p);

      for (const [key, steps] of Object.entries(doc)) {
        if (key.startsWith('#') || !Array.isArray(steps)) continue;
        const qualified = `${qualifiedPrefix}/${key}`;
        byQualified.set(qualified, steps);
        byQualified.set(`${stem}/${key}`, steps);
        if (byName.has(key)) {
          const prev = byName.get(key);
          throw new Error(
            `片段名冲突: ${JSON.stringify(key)}（${prev.qualified} 与 ${qualified}）`,
          );
        }
        byName.set(key, { steps, qualified, file: relative(ROOT, p) });
      }
    }
  }

  walk(FRAGMENTS_DIR);
  fragmentIndexCache = { byName, byQualified };
  return fragmentIndexCache;
}

function resolveFragmentSteps(ref, stack = []) {
  const name = String(ref).trim();
  if (!name) {
    throw new Error('setup.include 片段名不能为空');
  }
  if (stack.includes(name)) {
    throw new Error(`setup.include 循环引用: ${[...stack, name].join(' → ')}`);
  }

  const { byName, byQualified } = loadFragmentIndex();
  const steps = byQualified.get(name) ?? byName.get(name)?.steps;
  if (!steps) {
    const known = [...byQualified.keys()].sort().slice(0, 12).join(', ');
    throw new Error(`未知 setup.include 片段: ${JSON.stringify(name)}（示例: base-navigation/enter_room_frame；已知: ${known}…）`);
  }
  return steps;
}

function expandSetupSteps(setup, stack = []) {
  const out = [];
  const includes = setup?.include;
  if (Array.isArray(includes)) {
    for (const ref of includes) {
      const steps = resolveFragmentSteps(ref, stack);
      out.push(...steps);
    }
  }
  if (Array.isArray(setup?.steps)) {
    out.push(...setup.steps);
  }
  return out;
}

function loadTunnelCatalogItem(catalogId) {
  const path = resolve(ROOT, '../adb/config/tunnel_capture_catalog.json');
  const cat = JSON.parse(readFileSync(path, 'utf8'));
  const item = (cat.items || []).find((x) => x.id === catalogId);
  if (!item) {
    throw new Error(`未知 tunnel catalogId: ${catalogId}`);
  }
  return item;
}

function buildTunnelSpec(doc) {
  const raw = doc.tunnel;
  if (!raw || raw === false) return null;

  const spec = typeof raw === 'object' ? { ...raw } : {};
  if (spec.catalogId) {
    const item = loadTunnelCatalogItem(spec.catalogId);
    if (!spec.keyword && item.keyword) spec.keyword = item.keyword;
    if (spec.expectResponseEc == null && item.expectEc != null) {
      spec.expectResponseEc = item.expectEc;
    }
    if (!spec.name && item.name) spec.name = item.name;
  }

  const expand = (v) => (typeof v === 'string' ? expandTemplate(v) : v);
  if (spec.momoid) spec.momoid = expand(String(spec.momoid));
  if (spec.account) spec.account = expand(String(spec.account));
  if (spec.keyword) spec.keyword = expand(String(spec.keyword));
  if (spec.gAppid) spec.gAppid = expand(String(spec.gAppid));
  if (spec.gEnv) spec.gEnv = expand(String(spec.gEnv));
  if (Array.isArray(spec.requestContains)) {
    spec.requestContains = spec.requestContains.map((x) => expand(String(x)));
  }
  if (Array.isArray(spec.responseContains)) {
    spec.responseContains = spec.responseContains.map((x) => expand(String(x)));
  }

  spec.intentId = doc.id;
  if (!spec.keyword && !spec.catalogId) {
    throw new Error(`${doc.id}: tunnel 须配置 keyword 或 catalogId`);
  }
  if (!spec.momoid && !spec.account && !process.env.TEST_TUNNEL_MOMOID) {
    throw new Error(
      `${doc.id}: tunnel 须配置 momoid/account 或环境变量 TEST_TUNNEL_MOMOID`,
    );
  }
  if (!spec.momoid && !spec.account) {
    spec.momoid = process.env.TEST_TUNNEL_MOMOID;
  }
  return spec;
}

function compileOne(doc) {
  const id = doc.id ?? 'IT-UNKNOWN';
  const name = doc.name ?? id;
  const platform = (doc.platform ?? 'android').toLowerCase();
  const action = doc.intent?.action;
  const expected = doc.intent?.expected ?? [];
  const setup = doc.setup ?? {};
  const timeoutMs = doc.timeoutMs ?? 120000;
  const aiContext = buildAiContext(doc, setup);

  if (!action) {
    throw new Error(`${id}: 缺少 intent.action`);
  }
  if (!Array.isArray(expected) || expected.length === 0) {
    throw new Error(`${id}: 缺少 intent.expected（至少一条）`);
  }

  const flow = [];

  if (setup.launchApp && platform === 'android') {
    const pkg = process.env.ANDROID_APP_ID ?? 'com.immomo.biz.yaahlan';
    const yaha = process.env.ANDROID_FORCE_STOP_YAHA ?? 'com.immomo.yaha';
    const mode = process.env.ANDROID_LAUNCH_MODE ?? 'launcher';
    flow.push({ runAdbShell: `am force-stop ${yaha}` });
    flow.push({ runAdbShell: `am force-stop ${pkg}` });
    flow.push({ sleep: 1000 });
    if (mode === 'launcher') {
      flow.push({
        runAdbShell: `monkey -p ${pkg} -c android.intent.category.LAUNCHER 1`,
      });
    } else {
      const act = process.env.ANDROID_MAIN_ACTIVITY ?? '.personalityIcon4';
      flow.push({ launch: `${pkg}/${act}` });
    }
    flow.push({ sleep: 4000 });
  } else if (setup.launchApp && platform === 'ios') {
    flow.push({ launch: '${IOS_APP_ID}' }, { sleep: 3000 });
  }

  if (setup.deeplink) {
    const link = expandTemplate(String(setup.deeplink));
    const pkg = process.env.ANDROID_APP_ID ?? 'com.immomo.biz.yaahlan';
    if (platform === 'android') {
      flow.push({
        runAdbShell: `am start -a android.intent.action.VIEW -d "${link}" ${pkg}`,
      });
    } else {
      flow.push({ launch: link });
    }
    flow.push({ sleep: 3000 });
  }

  if (!setup.skipPopupDismiss) {
    for (const step of resolveFragmentSteps('popup-handling/dismiss_blocking_popups')) {
      appendSetupStep(flow, step);
    }
  }

  if (Array.isArray(setup.steps) || Array.isArray(setup.include)) {
    for (const step of expandSetupSteps(setup)) {
      appendSetupStep(flow, step);
    }
  }

  flow.push({ aiAct: expandTemplate(action) });
  flow.push({ sleep: DEFAULT_ACT_SLEEP_MS });

  for (const exp of expected) {
    flow.push({
      aiAssert: expandTemplate(String(exp)),
      errorMessage: `${id} 失败：${exp}`,
    });
  }

  const lines = [];
  lines.push(`# Auto-generated from intent ${id}`);
  lines.push(`# ${name}`);
  lines.push('');

  if (platform === 'ios') {
    lines.push('ios: {}');
  } else {
    lines.push('android: {}');
  }

  lines.push('');
  lines.push('agent:');
  lines.push(`  testId: "${id}"`);
  lines.push(`  groupName: "${doc.module ?? name}"`);
  lines.push('  generateReport: true');
  lines.push(`  reportFileName: "${id.toLowerCase()}"`);
  lines.push(`  aiActContext: >`);
  for (const line of aiContext.split('\n')) {
    lines.push(`    ${line.trim()}`);
  }

  lines.push('');
  lines.push('tasks:');
  lines.push(`  - name: "${name}"`);
  lines.push(`    flow:`);

  for (const step of flow) {
    const [key, val] = Object.entries(step)[0];
    if (key === 'sleep') {
      lines.push(`      - sleep: ${val}`);
    } else if (key === 'aiAssert') {
      lines.push(`      - aiAssert: ${yamlQuote(val)}`);
      if (step.errorMessage) {
        lines.push(`        errorMessage: ${yamlQuote(step.errorMessage)}`);
      }
    } else if (key === 'aiWaitFor') {
      lines.push(`      - aiWaitFor: ${yamlQuote(val)}`);
    } else if (typeof val === 'string') {
      lines.push(`      - ${key}: ${yamlQuote(val)}`);
    } else {
      lines.push(`      - ${key}: ${JSON.stringify(val)}`);
    }
  }

  lines.push('');
  lines.push(`# timeout hint: ${timeoutMs}ms`);

  return {
    id,
    platform,
    content: lines.join('\n'),
    tunnelSpec: buildTunnelSpec(doc),
  };
}

function parseIntentFile(filePath) {
  const raw = readFileSync(filePath, 'utf8');
  const docs = parseAllDocuments(raw).map((d) => d.toJSON()).filter(Boolean);
  if (!docs.length) {
    throw new Error(`未解析到意图文档: ${filePath}`);
  }
  return docs.map((doc) => ({ ...compileOne(doc), source: filePath }));
}

function collectIntentFiles(arg) {
  if (arg === '--all') {
    const out = [];
    function walk(dir) {
      for (const name of readdirSync(dir)) {
        const p = resolve(dir, name);
        if (statSync(p).isDirectory()) {
          if (name === '.generated' || name === 'templates') continue;
          walk(p);
        } else if (name.endsWith('.yaml') || name.endsWith('.yml')) {
          out.push(p);
        }
      }
    }
    walk(resolve(ROOT, 'intents'));
    return out.sort();
  }
  return [resolve(process.cwd(), arg)];
}

function main() {
  loadEnvFromMidscene();
  const args = process.argv.slice(2);
  if (!args.length) {
    console.error('用法: node runners/compile-intent.mjs <intent.yaml> | --all');
    process.exit(1);
  }

  mkdirSync(GENERATED, { recursive: true });

  const outputs = [];
  for (const arg of args) {
    const files = arg.endsWith('.yaml') || arg.endsWith('.yml') ? [resolve(process.cwd(), arg)] : collectIntentFiles(arg);
    for (const file of files) {
      if (!file.includes('/intents/') && !file.includes('\\intents\\')) {
        console.warn(`[compile-intent] 跳过非 intents 目录: ${file}`);
        continue;
      }
      const compiled = parseIntentFile(file);
      for (const item of compiled) {
        const outPath = resolve(GENERATED, `${item.id}.midscene.yaml`);
        writeFileSync(outPath, item.content, 'utf8');
        if (item.tunnelSpec) {
          const tunnelPath = resolve(GENERATED, `${item.id}.tunnel.json`);
          writeFileSync(tunnelPath, `${JSON.stringify(item.tunnelSpec, null, 2)}\n`, 'utf8');
          console.log(`[compile-intent] ✓ ${item.id} tunnel → ${relative(ROOT, tunnelPath)}`);
        }
        outputs.push({ ...item, outPath });
        console.log(`[compile-intent] ✓ ${item.id} → ${relative(ROOT, outPath)}`);
      }
    }
  }

  if (!outputs.length) {
    console.error('[compile-intent] 无输出');
    process.exit(1);
  }

  return outputs;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}

export { compileOne, parseIntentFile, GENERATED, MIDSCENE_ROOT };
