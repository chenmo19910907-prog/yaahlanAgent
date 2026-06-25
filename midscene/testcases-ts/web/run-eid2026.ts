/**
 * eid2026 H5 自动化测试（SoulChill WebView raw CDP）
 *
 * 运行:
 *   npm run test:eid2026:app           # 运行全部用例
 *   npm run test:eid2026:app -- --smoke  # 仅运行前 5 条用例（快速验证）
 *
 * 前置条件:
 * 1. 手机已 USB 连接并开启 USB 调试
 * 2. 安装 SoulChill debug 包（WebView 调试需 debug 包）
 * 3. SoulChill 内活动 H5 已打开（或首次运行自动打开）
 *
 * 原理：Android WebView 不支持 Browser 级 CDP，通过 adb forward + raw WebSocket
 *       直连 SoulChill WebView 的 page 级 CDP，实现页面交互与断言。
 */
import { execSync } from 'child_process';
import WebSocket from 'ws';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { openH5InSoulChill, checkAdbDevices } from '../../utils/sc-webview';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface EidCase {
  id: string;
  module: string;
  steps: string;
  expected: string;
  priority: string;
}

const casesPath = path.resolve(__dirname, '../temporary_testcase/eid2026-cases.json');
const cases: EidCase[] = JSON.parse(fs.readFileSync(casesPath, 'utf-8'));

/** 按模块分组用例 */
const casesByModule = cases.reduce<Record<string, EidCase[]>>((acc, c) => {
  const key = c.module || '其他';
  if (!acc[key]) acc[key] = [];
  acc[key].push(c);
  return acc;
}, {});

/** 限制用例数量（--smoke 时仅跑前 N 条） */
function limitCases(
  byModule: Record<string, EidCase[]>,
  maxTotal: number
): Record<string, EidCase[]> {
  if (maxTotal <= 0) return byModule;
  let count = 0;
  const out: Record<string, EidCase[]> = {};
  for (const [k, arr] of Object.entries(byModule)) {
    const take = Math.min(arr.length, Math.max(0, maxTotal - count));
    if (take > 0) {
      out[k] = arr.slice(0, take);
      count += take;
    }
    if (count >= maxTotal) break;
  }
  return out;
}

/** 找 SoulChill 主进程对应的 webview_devtools_remote socket */
function findSoulChillSocket(pkg = 'com.live.soulchill'): string | null {
  const unix = execSync('adb shell cat /proc/net/unix 2>/dev/null').toString();
  const matches = [...unix.matchAll(/@(webview_devtools_remote_(\d+))/g)];
  for (const m of matches) {
    const pid = m[2];
    try {
      const cmdline = execSync(`adb shell cat /proc/${pid}/cmdline 2>/dev/null`)
        .toString()
        .replace(/\0/g, ' ')
        .trim()
        .split(' ')[0];
      if (cmdline === pkg) return m[1];
    } catch {
      /* ignore */
    }
  }
  return null;
}

/** 原始 CDP 客户端（page 级 WebSocket） */
class CDPClient {
  private ws: WebSocket;
  private id = 0;
  private handlers = new Map<number, (r: Record<string, unknown>) => void>();

  constructor(ws: WebSocket) {
    this.ws = ws;
    ws.on('message', (data: Buffer) => {
      const msg = JSON.parse(data.toString()) as { id?: number; result?: unknown; error?: unknown };
      if (msg.id && this.handlers.has(msg.id)) {
        this.handlers.get(msg.id)!({ result: msg.result, error: msg.error } as Record<string, unknown>);
        this.handlers.delete(msg.id);
      }
    });
  }

  send(method: string, params: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.handlers.set(id, (r) => {
        if (r.error) reject(new Error(`CDP ${method}: ${JSON.stringify(r.error)}`));
        else resolve((r.result ?? {}) as Record<string, unknown>);
      });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.handlers.has(id)) {
          this.handlers.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, 10000);
    });
  }

  async eval(expression: string): Promise<unknown> {
    const r = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    const res = r.result as { type: string; value?: unknown; description?: string } | undefined;
    if ((r as { exceptionDetails?: unknown }).exceptionDetails) {
      throw new Error(`eval error: ${expression.slice(0, 50)}`);
    }
    return res?.value;
  }

  async url(): Promise<string> {
    return (await this.eval('location.href')) as string;
  }

  /**
   * 等待满足条件的元素出现（最多 timeoutMs）
   * cssOrText：CSS 选择器 或 '~包含文本'（以 ~ 开头时用 XPath 文本搜索）
   */
  async waitForElement(
    cssOrText: string,
    state: 'visible' | 'exists' = 'visible',
    timeoutMs = 8000
  ): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      let found: unknown;
      if (cssOrText.startsWith('~')) {
        const text = cssOrText.slice(1).replace(/'/g, "\\'");
        found = await this.eval(
          `(function(){
            var els=[...document.querySelectorAll('*')].filter(e=>e.textContent.trim().includes('${text}') && e.offsetParent!==null);
            return els.length > 0;
          })()`
        );
      } else {
        found = await this.eval(
          state === 'visible'
            ? `(function(){var e=document.querySelector(${JSON.stringify(cssOrText)});return !!(e&&e.offsetParent!==null);})() `
            : `!!document.querySelector(${JSON.stringify(cssOrText)})`
        );
      }
      if (found) return;
      await new Promise((r) => setTimeout(r, 300));
    }
    throw new Error(`waitForElement timeout: ${cssOrText}`);
  }

  /** 点击元素（先找再 click） */
  async click(cssOrText: string, timeoutMs = 8000): Promise<void> {
    await this.waitForElement(cssOrText, 'visible', timeoutMs);
    if (cssOrText.startsWith('~')) {
      const text = cssOrText.slice(1).replace(/'/g, "\\'");
      await this.eval(
        `[...document.querySelectorAll('*')].filter(e=>e.textContent.trim().includes('${text}')&&e.offsetParent!==null)[0]?.click()`
      );
    } else {
      await this.eval(`document.querySelector(${JSON.stringify(cssOrText)})?.click()`);
    }
    await new Promise((r) => setTimeout(r, 400));
  }

  close(): void {
    this.ws.close();
  }
}

/** 执行用例步骤 */
async function executeSteps(cdp: CDPClient, steps: string): Promise<void> {
  const s = steps.replace(/\n/g, ' ');

  if (s.includes('规则按钮') || s.includes('规则弹窗')) {
    await cdp.click('.rules-btn:not(.award-btn)');
  }
  if (s.includes('奖励按钮') || s.includes('奖励页面')) {
    await cdp.click('.award-btn');
  }
  if (s.includes('开斋旅行tab') || s.includes('开斋旅行tab下')) {
    await cdp.click('~旅行');
  }
  if (s.includes('开斋红包tab') || s.includes('开斋礼包')) {
    await cdp.click('~礼包');
  }
  if (s.includes('开斋榜单tab') || s.includes('开斋榜单tab下')) {
    await cdp.click('~榜单');
  }
  if (s.includes('点击关闭') || (s.includes('关闭') && (s.includes('弹窗') || s.includes('页面')))) {
    try {
      await cdp.click(
        '.close-icon, [class*="close-icon"], .close-btn, [class*="close-btn"], .back-icon, [class*="back-icon"]',
        3000
      );
    } catch {
      // 找不到关闭按钮时，用 Android 返回键关闭弹窗
      execSync('adb shell input keyevent KEYCODE_BACK', { stdio: 'pipe' });
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  if (s.includes('频繁切换') || s.includes('切换不同tab')) {
    await cdp.click('~旅行');
    await cdp.click('~礼包');
    await cdp.click('~榜单');
  }
}

/** 执行断言 */
async function runAssertions(cdp: CDPClient, c: EidCase): Promise<void> {
  const url = await cdp.url();
  if (!url.includes('eid2026')) throw new Error(`URL 不含 eid2026: ${url}`);

  if (c.module.startsWith('头图')) {
    // 页面实际结构：.common-top（顶部栏）或 .home-wrap（主体容器）
    await cdp.waitForElement('.common-top, .home-wrap, .app, [class*="banner"], [class*="header"]', 'visible', 5000);
  }
  if (
    c.module.includes('规则') &&
    !c.module.includes('关闭') &&
    (c.steps.includes('规则') || c.steps.includes('弹窗'))
  ) {
    await cdp.waitForElement('.rule-wrap[isshowrulespop="true"]', 'visible', 5000);
  }
  if (c.module.includes('奖励') && !c.module.includes('关闭') && c.steps.includes('奖励')) {
    await cdp.waitForElement('.reward, [class*="reward"]', 'visible', 5000);
  }
  if (c.module.startsWith('一级tab-展示') && !c.steps.includes('活动结束')) {
    await cdp.waitForElement('.nav, .first-nav-wrap', 'visible', 5000);
  }
}

async function main() {
  const smoke = process.argv.includes('--smoke');
  const casesToRun = smoke ? limitCases(casesByModule, 5) : casesByModule;

  console.log('🚀 eid2026 H5 自动化（SoulChill WebView raw CDP）');
  console.log(`   用例总数: ${cases.length}，本次运行: ${smoke ? '前 5 条 (smoke)' : '全部'}\n`);

  checkAdbDevices();

  // 找 SoulChill 活动页面 WebSocket URL
  const LOCAL_PORT = 9222;
  execSync('adb forward --remove-all', { stdio: 'pipe' });

  let socket: string | null = null;
  for (let i = 0; i < 3; i++) {
    socket = findSoulChillSocket();
    if (socket) break;
    console.log('WebView 接口未找到，尝试自动打开活动页...');
    openH5InSoulChill(true);
    await new Promise((r) => setTimeout(r, 7000));
  }
  if (!socket) throw new Error('无法找到 SoulChill WebView 调试接口，请手动打开活动页后重试');

  execSync(`adb forward tcp:${LOCAL_PORT} localabstract:${socket}`, { stdio: 'pipe' });
  await new Promise((r) => setTimeout(r, 800));

  const EID_DIRECT_URL =
    'https://fproject.immomo.com/fep/momo/fe-fproject/soulchill-activity-projects/eid2026/index.html?_bid=1006530&lang=zh&tab=receive';

  // Chrome 146+ WebView 需要空 origin 才能通过 WebSocket 握手
  const WS_OPTIONS = { origin: '' };

  // 找到任意已开启的 WebView page，然后通过 CDP navigate 到 eid2026
  type CdpTarget = { url: string; webSocketDebuggerUrl: string; description: string; type: string };

  function getTargets(): CdpTarget[] {
    const jsonStr = execSync(`curl -s http://localhost:${LOCAL_PORT}/json`).toString();
    return JSON.parse(jsonStr) as CdpTarget[];
  }

  async function navigateViaWs(wsUrl: string, url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(wsUrl, WS_OPTIONS);
      ws.on('open', () => ws.send(JSON.stringify({ id: 1, method: 'Page.navigate', params: { url } })));
      ws.on('message', (data: Buffer) => {
        const msg = JSON.parse(data.toString());
        if (msg.id === 1) { ws.close(); resolve(); }
      });
      ws.on('error', reject);
      setTimeout(() => { ws.close(); reject(new Error('CDP navigate timeout')); }, 10000);
    });
  }

  // 1. 先找 eid2026 已加载的 target
  let target = getTargets().find((t) => t.url.includes('eid2026'));

  if (!target) {
    // 2. 找任意 page 类型的 target，用 CDP 导航到 eid2026
    const anyPage = getTargets().find((t) => t.type === 'page' || t.url.startsWith('http'));
    if (anyPage) {
      console.log(`🔀 通过 CDP 导航: ${anyPage.url.slice(0, 60)} → eid2026`);
      await navigateViaWs(anyPage.webSocketDebuggerUrl, EID_DIRECT_URL);
      await new Promise((r) => setTimeout(r, 6000));
      target = getTargets().find((t) => t.url.includes('eid2026'));
    }
  }

  if (!target) {
    // 3. 当前无任何 WebView 页面，尝试打开 Banner（tap 屏幕中下方）并等待
    console.log('📱 无已打开页面，尝试点击 SoulChill 促销 Banner...');
    const screenSize = execSync('adb shell wm size').toString().match(/(\d+)x(\d+)/);
    if (screenSize) {
      const [, w, h] = screenSize.map(Number);
      execSync(`adb shell input tap ${Math.floor(w / 2)} ${Math.floor(h * 0.85)}`, { stdio: 'pipe' });
      await new Promise((r) => setTimeout(r, 5000));
      const openedPage = getTargets().find((t) => t.type === 'page' || t.url.startsWith('http'));
      if (openedPage) {
        console.log(`🔀 通过 CDP 导航: ${openedPage.url.slice(0, 60)} → eid2026`);
        await navigateViaWs(openedPage.webSocketDebuggerUrl, EID_DIRECT_URL);
        await new Promise((r) => setTimeout(r, 6000));
        target = getTargets().find((t) => t.url.includes('eid2026'));
      }
    }
  }

  if (!target) {
    const all = getTargets().map((t) => t.url.slice(0, 80)).join('\n  ') || '(空)';
    throw new Error(`WebView 中未找到 eid2026 页面，且 CDP 导航失败。\n当前页面:\n  ${all}`);
  }

  console.log(`✅ 连接 WebView: ${target.url.slice(0, 80)}\n`);

  const ws = new WebSocket(target.webSocketDebuggerUrl, WS_OPTIONS);
  await new Promise<void>((resolve, reject) => {
    ws.on('open', resolve);
    ws.on('error', reject);
    setTimeout(() => reject(new Error('WebSocket connect timeout')), 8000);
  });

  const cdp = new CDPClient(ws);

  // 验证页面 URL
  const pageUrl = await cdp.url();
  if (!pageUrl.includes('eid2026')) {
    throw new Error(`页面 URL 不符: ${pageUrl}`);
  }
  console.log(`📄 页面 URL: ${pageUrl.slice(0, 100)}\n`);

  // 检测地区限制
  const pageText = (await cdp.eval(`document.body?.innerText || ''`)) as string;
  const isGeoRestricted = pageText.includes('not open for this area') ||
    pageText.includes('not available in your area');

  if (isGeoRestricted) {
    console.log('⚠️  地区限制提示: "This event is not open for this area"');
    console.log('   当前 IP 不在活动开放区域，将仅验证页面加载和限制提示是否正常显示。\n');
    // 验证地区限制场景：页面正常加载 + 限制文字存在
    const rootExists = (await cdp.eval(`!!document.querySelector('.home-wrap, .app, #app')`)) as boolean;
    if (!rootExists) throw new Error('地区限制场景：页面根元素未找到，页面加载异常');
    console.log('✅ 地区限制场景通过（页面正常加载，地区提示已显示）');
    console.log(`\n📊 结果: 1 通过, 0 失败（地区限制模式，跳过 UI 交互用例）`);
    cdp.close();
    execSync(`adb forward --remove tcp:${LOCAL_PORT}`, { stdio: 'pipe' });
    process.exit(0);
  }

  let passed = 0;
  let failed = 0;

  if (smoke) console.log('⚠️ Smoke 模式：仅运行前 5 条用例\n');

  for (const [moduleName, moduleCases] of Object.entries(casesToRun)) {
    console.log(`\n📦 ${moduleName}`);
    for (let i = 0; i < moduleCases.length; i++) {
      const c = moduleCases[i];
      const testName = `${c.id} [${i}] ${c.steps.slice(0, 40).replace(/\n/g, ' ')}...`;
      try {
        await executeSteps(cdp, c.steps);
        await runAssertions(cdp, c);
        passed++;
        process.stdout.write('.');
      } catch (err) {
        failed++;
        const msg = err instanceof Error ? err.message : String(err);
        console.log(`\n  ❌ ${testName}`);
        console.log(`     ${msg.slice(0, 200)}`);
      }
    }
  }

  console.log(`\n\n📊 结果: ${passed} 通过, ${failed} 失败`);
  cdp.close();
  execSync(`adb forward --remove tcp:${LOCAL_PORT}`, { stdio: 'pipe' });
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error('❌ 运行失败:', err);
  process.exit(1);
});
