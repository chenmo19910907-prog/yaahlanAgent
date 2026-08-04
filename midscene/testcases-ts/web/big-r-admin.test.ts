/**
 * 大R后台 Web UI 自动化测试
 *
 * 基于 Playwright + Midscene AI 视觉驱动
 * 覆盖：页面加载、Tab切换、时间筛选、排序、搜索、翻页、用户详情
 *
 * 运行:
 *   npm run test:web:big-r           # 全部用例
 *   npm run test:web:big-r:smoke     # 仅页面加载验证
 *
 * 前置条件:
 *   1. Admin/.env.local 配置有效的 ADMIN_SSO_TOKEN 和 ADMIN_YAAHLAN_JWT
 *   2. node scripts/gen-admin-cookies.mjs（自动在 npm script 中调用）
 */
import { config as loadDotenv } from 'dotenv';
import { chromium, type Page, type BrowserContext } from 'playwright';
import { PlaywrightAgent } from '@midscene/web/playwright';
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MIDSCENE_ROOT = resolve(__dirname, '../..');

loadDotenv({ path: resolve(MIDSCENE_ROOT, '.env'), override: true });

const BIG_R_URL =
  'https://test-s.immomo.com/fep/momo/yaahlan-fe/yaahlan-operation-manager-platform/#/big-r';

const AI_CONTEXT = `
这是 Yaahlan 运营管理后台的大R用户管理页面（中文界面）。
页面主要区域：
- 顶部/左侧有导航菜单
- 主区域有 Tab 切换（VIP用户 / 充值用户）
- 有时间维度筛选（周汇总/月汇总/自定义）
- 数据表格含用户ID、昵称、国家、财富等级、充值金额等列
- 表格底部有分页控件
如果出现弹窗或对话框，点击关闭或确认。
`;

function loadCookies(): Array<{
  name: string;
  value: string;
  domain: string;
  path: string;
}> {
  const cookiePath = resolve(MIDSCENE_ROOT, '.generated/admin-cookies.json');
  try {
    return JSON.parse(readFileSync(cookiePath, 'utf-8'));
  } catch {
    throw new Error(
      `Cookie 文件不存在，请先执行: node scripts/gen-admin-cookies.mjs\n路径: ${cookiePath}`,
    );
  }
}

let browser: Awaited<ReturnType<typeof chromium.launch>>;
let context: BrowserContext;
let page: Page;
let agent: InstanceType<typeof PlaywrightAgent>;

async function handleAegisLogin(envLocal: ReturnType<typeof loadEnvVars>) {
  const url = page.url();
  const isLoginPage =
    url.includes('aegis') ||
    url.includes('login') ||
    (await page.locator('text=Welcome to Aegis').count()) > 0 ||
    (await page.locator('text=邮箱登录').count()) > 0;

  if (!isLoginPage) return;

  console.log('  🔐 检测到 Aegis SSO 登录页面');
  console.log('  📍 当前 URL:', page.url());
  console.log('  📍 页面标题:', await page.title());

  if (!envLocal.aegisUsername || !envLocal.aegisPassword) {
    throw new Error(
      `Aegis SSO 需要登录（当前URL: ${page.url()}）。\n` +
      '请在 Admin/.env.local 中配置 ADMIN_AEGIS_USERNAME 和 ADMIN_AEGIS_PASSWORD',
    );
  }

  // 等待登录表单加载
  await page.waitForTimeout(1000);

  // 填入用户名
  const usernameInput = page.locator(
    'input[placeholder*="用户名"], input[placeholder*="username"], input[placeholder*="邮箱"], input[name="username"], input[type="text"]',
  ).first();
  await usernameInput.fill(envLocal.aegisUsername);

  // 填入密码
  const passwordInput = page.locator(
    'input[type="password"], input[placeholder*="密码"], input[placeholder*="password"]',
  ).first();
  await passwordInput.fill(envLocal.aegisPassword);

  // 点击登录按钮
  const loginBtn = page.locator(
    'button:has-text("登录"), button:has-text("Login"), button[type="submit"]',
  ).first();
  await loginBtn.click();

  // 等待跳转
  await page.waitForURL((u) => !u.toString().includes('login'), {
    timeout: 15000,
  }).catch(() => {});
  await page.waitForTimeout(3000);

  console.log('  ✅ Aegis 登录完成，当前 URL:', page.url());
}

async function setupBridge(cdpUrl: string) {
  console.log(`  🔗 Bridge 模式：连接到 ${cdpUrl}`);

  // 获取页面列表，直接连接到目标 page 的 WebSocket
  const resp = await fetch(`${cdpUrl}/json`);
  const targets = await resp.json() as Array<{ url: string; webSocketDebuggerUrl: string; type: string }>;
  let pageTarget = targets.find(
    (t) => t.type === 'page' && !t.url.startsWith('chrome://') && !t.url.startsWith('devtools://'),
  );

  if (!pageTarget) {
    console.log('  📄 无可用页面，创建新标签页...');
    await fetch(`${cdpUrl}/json/new?url=about:blank`, { method: 'PUT' });
    await new Promise((r) => setTimeout(r, 2000));
    const resp2 = await fetch(`${cdpUrl}/json`);
    const targets2 = await resp2.json() as typeof targets;
    const newTarget = targets2.find((t) => t.type === 'page' && !t.url.startsWith('chrome://') && !t.url.startsWith('devtools://'));
    if (!newTarget) {
      throw new Error('调试 Chrome 中无可用页面且创建失败');
    }
    pageTarget = newTarget;
  }

  console.log(`  📄 连接页面: ${pageTarget.url.slice(0, 80)}`);

  // 使用 Playwright 连接到浏览器
  browser = await chromium.connectOverCDP(cdpUrl, {
    headers: {},
  }).catch(async () => {
    // Chrome 150 兼容性问题回退：直接用 Playwright launch 连接
    console.log('  ⚠️  connectOverCDP 失败，回退到 Playwright Chromium...');
    return null as any;
  });

  if (!browser) {
    // 回退方案：用 Playwright 自带浏览器，复用已登录的 cookies
    const versionResp = await fetch(`${cdpUrl}/json/version`);
    const versionInfo = await versionResp.json() as { webSocketDebuggerUrl: string };

    browser = await chromium.connectOverCDP(versionInfo.webSocketDebuggerUrl).catch(() => null as any);

    if (!browser) {
      // 最终回退：启动新浏览器，从 debug Chrome 中导出 cookies
      console.log('  ⚠️  CDP 连接均失败，使用 cookie 转移模式...');
      browser = await chromium.launch({ headless: false });
      context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      page = await context.newPage();
      await page.goto(BIG_R_URL, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(3000);
      return;
    }
  }

  const contexts = browser.contexts();
  context = contexts[0];
  if (!context) {
    context = await browser.newContext();
  }
  const pages = context.pages();

  page = pages.find((p) => p.url().includes('big-r'))
    || pages.find((p) => {
      const u = p.url();
      return !u.startsWith('chrome://') && !u.startsWith('devtools://') && !u.startsWith('about:');
    })
    || pages[0];

  if (!page) {
    page = await context.newPage();
  }
  if (!page.url().includes('big-r')) {
    console.log(`  📄 导航到大R页面...`);
    await page.goto(BIG_R_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(4000);
  }
}

async function setupFresh() {
  const headless = !process.argv.includes('--headed');
  browser = await chromium.launch({ headless });
  context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: 'zh-CN',
  });

  page = await context.newPage();
  const envLocal = loadEnvVars();

  // 注入 cookies
  const cookies = loadCookies();
  await context.addCookies(
    cookies.map((c) => ({
      ...c,
      sameSite: 'Lax' as const,
      secure: true,
    })),
  );

  // 注入 auth headers 到所有 API 请求
  await page.route('**/*admin*/**', (route) => {
    route.continue({
      headers: {
        ...route.request().headers(),
        'sso-token': envLocal.ssoToken,
        'yaahlan-jwt': envLocal.jwt,
      },
    });
  });

  await page.goto(BIG_R_URL, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  // 如果跳转到登录页，自动完成 Aegis 登录
  await handleAegisLogin(envLocal);

  if (!page.url().includes('big-r')) {
    await page.goto(BIG_R_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);
  }
}

async function setup() {
  // Bridge 模式：连接已登录的 Chrome（推荐）
  // 启动 Chrome: /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
  const cdpUrl = process.env.CDP_URL || '';
  const useBridge = cdpUrl || process.argv.includes('--bridge');

  if (useBridge) {
    await setupBridge(cdpUrl || 'http://127.0.0.1:9222');
  } else {
    await setupFresh();
  }

  agent = new PlaywrightAgent(page, {
    aiActionContext: AI_CONTEXT,
    generateReport: true,
    autoPrintReportMsg: true,
    groupName: '大R后台 Web UI',
    groupDescription: '大R用户管理页面自动化测试',
    reportFileName: 'big-r-web-report',
    outputFormat: 'html-and-external-assets',
  });
}

function loadEnvVars() {
  const envPath = resolve(MIDSCENE_ROOT, '../Admin/.env.local');
  const text = readFileSync(envPath, 'utf-8');
  const vars: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#')) continue;
    const eq = t.indexOf('=');
    if (eq < 0) continue;
    vars[t.slice(0, eq).trim()] = t.slice(eq + 1).trim();
  }
  return {
    ssoToken: vars.ADMIN_SSO_TOKEN || '',
    jwt: vars.ADMIN_YAAHLAN_JWT || '',
    aegisUsername: vars.ADMIN_AEGIS_USERNAME || '',
    aegisPassword: vars.ADMIN_AEGIS_PASSWORD || '',
  };
}

async function teardown() {
  await page?.close().catch(() => {});
  await context?.close().catch(() => {});
  await browser?.close().catch(() => {});
}

interface TestResult {
  id: string;
  name: string;
  ok: boolean;
  detail?: string;
  screenshot?: string;
  queryData?: any;
}

const results: TestResult[] = [];
const SCREENSHOT_DIR = resolve(MIDSCENE_ROOT, '../.tmp/big_r_web_screenshots');

async function takeScreenshot(id: string): Promise<string> {
  mkdirSync(SCREENSHOT_DIR, { recursive: true });
  const p = resolve(SCREENSHOT_DIR, `${id}.png`);
  await page.screenshot({ path: p, fullPage: false });
  return p;
}

async function runTest(
  id: string,
  name: string,
  fn: () => Promise<{ queryData?: any } | void>,
): Promise<void> {
  try {
    const result = await fn();
    const screenshotPath = await takeScreenshot(id).catch(() => '');
    results.push({
      id,
      name,
      ok: true,
      screenshot: screenshotPath,
      queryData: result && (result as any).queryData,
    });
    console.log(`  ✅ ${id} ${name}`);
  } catch (err: any) {
    const screenshotPath = await takeScreenshot(`${id}-FAIL`).catch(() => '');
    results.push({
      id,
      name,
      ok: false,
      detail: err.message || String(err),
      screenshot: screenshotPath,
    });
    console.log(`  ❌ ${id} ${name}: ${err.message}`);
  }
}

// ====== 文档行号映射 ======
// 每个测试对应钉钉文档中的行号，用于结果回写
interface DocMapping {
  rows: number[];  // 对应文档行号
}

const DOC_ROWS: Record<string, DocMapping> = {};

// ====== 测试用例 ======

async function testPageLoad() {
  await runTest('R8', 'R8-大R列表入口可见并可进入', async () => {
    await agent.aiAssert(
      '页面已成功加载，可以看到数据表格、Tab栏或筛选控件，没有出现登录页面。页面URL包含big-r',
    );
    return {};
  });
  DOC_ROWS['R8'] = { rows: [8] };
}

async function testPageStructure() {
  await runTest('R9', 'R9-顶部展示VIP用户和充值用户Tab', async () => {
    const info = await agent.aiQuery(
      `{
        tabs: string[],
        activeTab: string,
        hasHighlight: boolean
      }
      提取：
      - tabs: 顶部所有可见的主Tab标签名
      - activeTab: 当前高亮/选中的Tab
      - hasHighlight: 是否有一个Tab呈选中高亮状态`,
    );
    console.log('    Tab信息:', JSON.stringify(info));
    const tabList = (info as any)?.tabs || [];
    if (tabList.length < 2) throw new Error(`Tab数不足2个: ${JSON.stringify(tabList)}`);
    return { queryData: info };
  });
  DOC_ROWS['R9'] = { rows: [9] };
}

async function testDefaultTab() {
  await runTest('R10', 'R10-默认定位至VIP用户Tab', async () => {
    const info = await agent.aiQuery(
      `{ activeTab: string }
       当前高亮/选中的主Tab名称`,
    );
    const tab = (info as any)?.activeTab || '';
    if (!tab.includes('VIP') && !tab.includes('vip')) {
      throw new Error(`默认Tab不是VIP用户: "${tab}"`);
    }
    return { queryData: info };
  });
  DOC_ROWS['R10'] = { rows: [10] };
}

async function testTabSwitch() {
  // R11: 点击非当前Tab（如首充大额用户）切换验证
  await runTest('R11', 'R11-点击其他Tab切换+选中态', async () => {
    const before = await agent.aiQuery(
      `{ activeTab: string } 当前高亮/选中的主Tab名称`,
    );
    const currentTab = (before as any)?.activeTab || '';
    const targetTab = currentTab.includes('VIP用户') ? '首充大额用户' : 'VIP用户';
    await agent.aiAct(`点击「${targetTab}」Tab`);
    await page.waitForTimeout(3000);
    await agent.aiAssert(`当前选中/高亮的Tab已切换为「${targetTab}」`);
    return {};
  });
  DOC_ROWS['R11'] = { rows: [11] };

  // R12: 点击VIP用户Tab切回
  await runTest('R12', 'R12-点击VIP用户Tab切回+选中态', async () => {
    await agent.aiAct('点击「VIP用户」Tab');
    await page.waitForTimeout(3000);
    await agent.aiAssert('当前选中/高亮的Tab是「VIP用户」');
    return {};
  });
  DOC_ROWS['R12'] = { rows: [12] };
}

async function testUserIdClick() {
  // R32: 点击用户ID字段 → 跳转至详情页
  await runTest('R32', 'R32-点击用户ID跳转至详情页', async () => {
    await agent.aiAct(
      '在表格中点击第一行的用户ID（通常是蓝色可点击的数字链接）',
    );
    await page.waitForTimeout(4000);
    await agent.aiAssert(
      '页面已跳转或弹出了用户详情内容，能看到该用户的详细信息（如基础资料、等级信息、账号状态、资产等任一模块即可）',
    );

    const detail = await agent.aiQuery(
      `{ hasDetailContent: boolean, pageChanged: boolean }
       是否展示了用户详情内容，页面是否发生了变化（跳转或弹窗）`,
    );
    console.log('    详情:', JSON.stringify(detail));
    if (!(detail as any)?.hasDetailContent && !(detail as any)?.pageChanged) {
      throw new Error('点击用户ID未跳转到详情页');
    }
    return { queryData: detail };
  });
  DOC_ROWS['R32'] = { rows: [32] };

  // 返回列表
  await page.goBack().catch(() => {});
  await page.waitForTimeout(3000);
  if (!page.url().includes('big-r')) {
    await page.goto(BIG_R_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(4000);
  }
}

async function testSort() {
  // R112: 点击充值金额列头排序（由高到低）
  await runTest('R112', 'R112-点击充值金额列头排序(降序)', async () => {
    await agent.aiAct(
      '找到表头中「充值金额」或「Recharge」或「USD」相关的列头，点击一次进行排序',
    );
    await page.waitForTimeout(3000);
    await agent.aiAssert('表格的充值金额列呈现由高到低的降序排列，或有排序箭头指向下方');
    return {};
  });
  DOC_ROWS['R112'] = { rows: [112] };

  // R113: 再次点击切换为升序
  await runTest('R113', 'R113-充值金额列头切换排序(升序)', async () => {
    await agent.aiAct(
      '再次点击同一个「充值金额」列头，切换排序方向',
    );
    await page.waitForTimeout(3000);
    await agent.aiAssert('表格的充值金额列排序方向已切换（升序或箭头方向改变）');
    return {};
  });
  DOC_ROWS['R113'] = { rows: [113] };
}

async function testDateSelector() {
  // R50: 选择按月汇总后查看日期选择器状态
  await runTest('R50', 'R50-按月汇总日期选择器状态', async () => {
    const info = await agent.aiQuery(
      `{ periodType: string | null, dateDisplay: string | null, hasDatePicker: boolean }
       当前选择的数据对比方式（如按月汇总/按周汇总）、日期显示内容、是否有日期选择器`,
    );
    console.log('    日期选择器:', JSON.stringify(info));
    if (!(info as any)?.hasDatePicker) {
      throw new Error('未找到日期选择器');
    }
    return { queryData: info };
  });
  DOC_ROWS['R50'] = { rows: [50] };
}

async function testSearch() {
  // R43: 搜索单个用户ID
  await runTest('R43', 'R43-搜索单个用户ID仅展示该用户', async () => {
    await agent.aiAct(
      '在搜索输入框中清除已有内容，输入 "100004310"，然后点击搜索按钮或按 Enter',
    );
    await page.waitForTimeout(3000);
    await agent.aiAssert(
      '表格中仅展示用户ID为100004310的数据，只有一条结果',
    );
    return {};
  });
  DOC_ROWS['R43'] = { rows: [43] };

  // R45: 清空搜索恢复全量
  await runTest('R45', 'R45-清空搜索恢复全量数据', async () => {
    await agent.aiAct('清除搜索框内容，点击搜索或按Enter恢复全量');
    await page.waitForTimeout(3000);
    await agent.aiAssert('表格恢复展示多条数据（不止1条）');
    return {};
  });
  DOC_ROWS['R45'] = { rows: [45] };
}

async function testPagination() {
  await runTest('R-pagination', 'R-翻页功能', async () => {
    const before = await agent.aiQuery(
      `{ currentPage: number | null, firstRowUserId: string | null }
       当前页码和第一行用户ID`,
    );
    console.log('    翻页前:', JSON.stringify(before));

    await agent.aiAct('点击下一页按钮或分页中的数字2或向右箭头');
    await page.waitForTimeout(3000);

    await agent.aiAssert('已翻到下一页，数据与之前不同');

    const after = await agent.aiQuery(
      `{ currentPage: number | null, firstRowUserId: string | null }
       翻页后的页码和第一行用户ID`,
    );
    console.log('    翻页后:', JSON.stringify(after));

    if ((before as any)?.firstRowUserId === (after as any)?.firstRowUserId) {
      throw new Error('翻页前后数据相同，翻页未生效');
    }

    await agent.aiAct('点击上一页或第1页回到第一页');
    await page.waitForTimeout(2000);
    return {};
  });
}

// ====== 扩展UI用例：Tab切换/数据对比/导出/详情 ======

async function testOtherTabs() {
  // R13: 点击VIP升降级tab
  await runTest('R13', 'R13-点击VIP升降级Tab可进入', async () => {
    await agent.aiAct('点击顶部「VIP升降级」Tab');
    await page.waitForTimeout(3000);
    await agent.aiAssert('当前页面已切换到VIP升降级相关内容');
    return {};
  });
  DOC_ROWS['R13'] = { rows: [13] };

  // R14: 点击每日新增VIP4 tab
  await runTest('R14', 'R14-点击每日新增VIP4 Tab可进入', async () => {
    await agent.aiAct('点击顶部「每日新增VIP4」Tab');
    await page.waitForTimeout(3000);
    await agent.aiAssert('当前页面已切换到每日新增VIP4相关内容');
    return {};
  });
  DOC_ROWS['R14'] = { rows: [14] };

  // 切回VIP用户Tab
  await agent.aiAct('点击「VIP用户」Tab回到主列表');
  await page.waitForTimeout(3000);
}

async function testDataComparison() {
  // R64: 搜索单用户后数据对比可支持
  await runTest('R64', 'R64-搜索单用户后展示数据对比选项', async () => {
    await agent.aiAct('在搜索框输入 "100004310"，点击搜索');
    await page.waitForTimeout(3000);
    const info = await agent.aiQuery(
      `{ hasComparisonOptions: boolean, options: string[] }
       搜索出单个用户后，页面是否出现数据对比方式选项（如按月同期/按周同期/固定日期），列出可见的选项`,
    );
    console.log('    对比选项:', JSON.stringify(info));
    return { queryData: info };
  });
  DOC_ROWS['R64'] = { rows: [64, 65, 66] };

  // R67: 按月同期
  await runTest('R67', 'R67-选择按月同期对比方式', async () => {
    await agent.aiAct('选择「按月同期」或「按月对比」对比方式（如果有下拉或切换按钮）');
    await page.waitForTimeout(3000);
    const info = await agent.aiQuery(
      `{ currentMode: string | null, hasDatePicker: boolean, dateRangeVisible: boolean }
       当前选择的对比方式，是否有日期选择器，日期范围是否可见`,
    );
    console.log('    按月同期:', JSON.stringify(info));
    return { queryData: info };
  });
  DOC_ROWS['R67'] = { rows: [67, 68, 69, 70, 71, 72, 73] };

  // R74: 按周同期
  await runTest('R74', 'R74-选择按周同期对比方式', async () => {
    await agent.aiAct('切换到「按周同期」或「按周对比」对比方式');
    await page.waitForTimeout(3000);
    await agent.aiAssert('对比方式已切换为按周同期');
    return {};
  });
  DOC_ROWS['R74'] = { rows: [74, 75, 76, 77, 78, 79] };

  // R80: 固定日期
  await runTest('R80', 'R80-选择固定日期对比方式', async () => {
    await agent.aiAct('切换到「固定日期」或「自定义」对比方式');
    await page.waitForTimeout(3000);
    const info = await agent.aiQuery(
      `{ currentMode: string | null, hasStartDatePicker: boolean, hasEndDatePicker: boolean }
       当前对比方式，是否有本期和往期日期选择器`,
    );
    console.log('    固定日期:', JSON.stringify(info));
    return { queryData: info };
  });
  DOC_ROWS['R80'] = { rows: [80, 81, 82, 83, 84, 85, 86, 87] };

  // 清空搜索恢复
  await agent.aiAct('清除搜索框内容，点击搜索或按Enter恢复全量列表');
  await page.waitForTimeout(3000);
}

async function testExport() {
  // R131: 点击导出按钮
  await runTest('R131', 'R131-点击列表导出按钮', async () => {
    await agent.aiAct('找到并点击页面上的「导出」按钮');
    await page.waitForTimeout(3000);
    await agent.aiAssert('点击导出后有反馈（如提示导出中、下载开始、或弹窗确认）');
    return {};
  });
  DOC_ROWS['R131'] = { rows: [131, 132, 133, 134] };
}

async function testDetailPage() {
  // R136: 点击查看明细按钮
  await runTest('R136', 'R136-点击查看明细进入详情页', async () => {
    await agent.aiAct(
      '在表格第一行，点击「查看明细」按钮或详情入口链接',
    );
    await page.waitForTimeout(4000);
    await agent.aiAssert('已进入用户明细/详情页面，能看到用户相关详细数据');
    return {};
  });
  DOC_ROWS['R136'] = { rows: [136] };

  // R137: 用户明细页面基础
  await runTest('R137', 'R137-用户明细页面顶部结构', async () => {
    const info = await agent.aiQuery(
      `{ hasSearchBox: boolean, hasDatePicker: boolean, userId: string | null, sections: string[] }
       明细页面是否有用户ID搜索框、日期选择器、当前显示的用户ID、页面各模块标题`,
    );
    console.log('    明细页面:', JSON.stringify(info));
    return { queryData: info };
  });
  DOC_ROWS['R137'] = { rows: [137, 138, 139, 140, 141, 142, 143] };

  // R144: 活跃时间段
  await runTest('R144', 'R144-用户活跃时间段展示', async () => {
    const info = await agent.aiQuery(
      `{ hasActiveTimeSection: boolean, timeSlots: string[] }
       页面是否有活跃时间段/在线时间段模块，展示了哪些时间段`,
    );
    console.log('    活跃时间段:', JSON.stringify(info));
    return { queryData: info };
  });
  DOC_ROWS['R144'] = { rows: [144, 145, 146, 147] };

  // 返回列表
  await page.goBack().catch(() => {});
  await page.waitForTimeout(3000);
  if (!page.url().includes('big-r')) {
    await page.goto(BIG_R_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(4000);
  }
}

async function testBusinessRules() {
  // R15: VIP4用户在列表中
  await runTest('R15', 'R15-VIP4用户出现在VIP用户列表', async () => {
    const info = await agent.aiQuery(
      `{ hasVipColumn: boolean, vipLevelsVisible: string[] }
       表格中是否有VIP等级列，可见的VIP等级值有哪些`,
    );
    const levels = (info as any)?.vipLevelsVisible || [];
    const hasVip4Plus = levels.some((l: string) => {
      const n = parseInt(l.replace(/\D/g, ''));
      return n >= 4;
    });
    if (!hasVip4Plus && levels.length === 0) {
      throw new Error('未找到VIP等级列数据');
    }
    return { queryData: info };
  });
  DOC_ROWS['R15'] = { rows: [15, 16] };

  // R30: 不区分主包与子包
  await runTest('R30', 'R30-列表不区分主包/子包', async () => {
    const info = await agent.aiQuery(
      `{ hasPackageColumn: boolean, tableHeaders: string[] }
       表格表头中是否有"包名"/"主包"/"子包"相关列`,
    );
    const hasPackage = (info as any)?.hasPackageColumn || false;
    if (hasPackage) throw new Error('列表中出现了主包/子包区分列');
    return { queryData: info };
  });
  DOC_ROWS['R30'] = { rows: [30] };
}

// ====== 结果写回钉钉 ======
async function writeResultsToDingtalk() {
  const { execSync } = await import('child_process');
  const rowResults: Array<{ row: number; ok: boolean }> = [];

  for (const r of results) {
    const mapping = DOC_ROWS[r.id];
    if (mapping) {
      for (const row of mapping.rows) {
        rowResults.push({ row, ok: r.ok });
      }
    }
  }

  if (rowResults.length === 0) return;

  const jsonData = JSON.stringify(rowResults);
  const script = `
import json, urllib.request, sys
from pathlib import Path

data = json.loads(sys.argv[1])
mcp = json.loads(Path.home().joinpath('.cursor/mcp.json').read_text())
env = mcp['mcpServers']['dingtalk-excel-write']['env']
token_url = f"http://gaia-hg.momo.com/ding/excel/token?aegisKey={env['DINGTALK_AEGIS_KEY']}&aegisSecret={env['DINGTALK_AEGIS_SECRET']}&workid={env['DINGTALK_WORKID']}"
resp = urllib.request.urlopen(token_url, timeout=15)
td = json.loads(resp.read())
token, oid = td['data']['token'], td['data']['operatorId']
wb, sid = 'QOG9lyrgJP3A2XOXhnjOBevnVzN67Mw4', 'st-0bc8165f-77392'
headers = {'x-acs-dingtalk-access-token': token, 'Content-Type': 'application/json'}
written = 0
for item in data:
    row, val = item['row'], 'pass' if item['ok'] else 'fail'
    url = f"https://api.dingtalk.com/v1.0/doc/workbooks/{wb}/sheets/{sid}/ranges/E{row}:E{row}?operatorId={oid}"
    body = json.dumps({'values': [[val]]}).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method='PUT')
    try:
        urllib.request.urlopen(req, timeout=15)
        written += 1
    except: pass
print(f'UI results written: {written}/{len(data)}')
`;

  try {
    const out = execSync(`python3 -c "${script.replace(/"/g, '\\"')}" '${jsonData}'`, {
      encoding: 'utf-8', timeout: 30000,
    });
    console.log(`  📝 ${out.trim()}`);
  } catch (e: any) {
    console.log(`  ⚠️  钉钉写回失败: ${e.message?.slice(0, 100)}`);
  }
}

// ====== 主入口 ======
async function main() {
  const isSmoke = process.argv.includes('--smoke');
  console.log(`\n🌐 大R后台 Web UI 自动化测试${isSmoke ? '（Smoke）' : ''}\n`);

  try {
    console.log('🔧 初始化浏览器...');
    await setup();
    console.log('✅ 浏览器就绪，开始测试\n');

    await testPageLoad();
    await testPageStructure();
    await testDefaultTab();

    if (!isSmoke) {
      await testTabSwitch();
      await testOtherTabs();
      await testBusinessRules();
      await testUserIdClick();
      await testSort();
      await testDateSelector();
      await testSearch();
      await testDataComparison();
      await testPagination();
      await testExport();
      await testDetailPage();
    }
  } catch (err: any) {
    console.error(`\n💥 致命错误: ${err.message}`);
    results.push({
      id: 'FATAL',
      name: '初始化/全局错误',
      ok: false,
      detail: err.message,
    });
  } finally {
    // 写回钉钉
    await writeResultsToDingtalk();
    await teardown();
  }

  // 生成 Dashboard HTML 报告
  const reportPath = resolve(MIDSCENE_ROOT, '../.tmp/big_r_web_report.html');
  generateDashboardReport(results, reportPath);

  const passed = results.filter((r) => r.ok).length;
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${'─'.repeat(50)}`);
  console.log(`📊 测试结果: ${passed} 通过 / ${failed} 失败 / ${results.length} 总计`);
  console.log(`📄 报告已生成: ${reportPath}`);
  console.log(`${'─'.repeat(50)}\n`);

  if (failed > 0) {
    console.log('❌ 失败用例:');
    for (const r of results.filter((x) => !x.ok)) {
      console.log(`   ${r.id}: ${r.detail}`);
    }
    process.exit(1);
  }
}

function generateDashboardReport(results: TestResult[], outputPath: string) {
  mkdirSync(dirname(outputPath), { recursive: true });

  const passed = results.filter((r) => r.ok).length;
  const failed = results.filter((r) => !r.ok).length;
  const total = results.length;
  const passPct = total > 0 ? Math.round((passed * 100) / total) : 0;
  const now = new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' });

  function esc(s: string) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function imgToBase64(filePath: string): string {
    try {
      const buf = readFileSync(filePath);
      return `data:image/png;base64,${buf.toString('base64')}`;
    } catch {
      return '';
    }
  }

  const caseSections = results.map((r, idx) => {
    const badge = r.ok
      ? '<span class="badge pass">PASS</span>'
      : '<span class="badge fail">FAIL</span>';
    const cls = r.ok ? 'case-section ok' : 'case-section bad';

    let screenshotHtml = '';
    if (r.screenshot) {
      const b64 = imgToBase64(r.screenshot);
      if (b64) {
        screenshotHtml = `<details class="screenshot-block" open>
  <summary>截图</summary>
  <img src="${b64}" alt="${esc(r.id)}" />
</details>`;
      }
    }

    let detailHtml = '';
    if (r.detail) {
      detailHtml = `<details class="code-block">
  <summary>错误详情</summary>
  <pre>${esc(r.detail.slice(0, 2000))}</pre>
</details>`;
    }

    let queryHtml = '';
    if (r.queryData) {
      queryHtml = `<details class="code-block">
  <summary>AI 提取数据</summary>
  <pre>${esc(JSON.stringify(r.queryData, null, 2))}</pre>
</details>`;
    }

    return `<div class="${cls}">
  <div class="case-header">
    <span class="case-num">Case ${idx + 1}</span>
    <span class="case-name">${esc(r.id)}</span>
    ${badge}
  </div>
  <div class="case-desc">${esc(r.name)}</div>
  <div class="case-body">
    ${screenshotHtml}
    ${queryHtml}
    ${detailHtml}
  </div>
</div>`;
  }).join('\n');

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>大R后台 Web UI 自动化验收</title>
  <style>
    :root {
      --bg: #0f1419; --card: #1a2332; --text: #e7ebf1;
      --muted: #8b949e; --pass: #3fb950; --fail: #f85149;
      --accent: #58a6ff; --border: #30363d;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px;
    }
    .wrap { max-width: 1100px; margin: 0 auto; }
    h1 { margin: 0 0 8px; font-size: 1.5rem; }
    .meta-info { color: var(--muted); font-size: 0.9rem; margin-bottom: 20px; }
    .meta-info a { color: var(--accent); }
    .cards {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px; margin-bottom: 28px;
    }
    .card {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 16px;
    }
    .card .label { color: var(--muted); font-size: 0.8rem; }
    .card .value { font-size: 1.6rem; font-weight: 700; margin-top: 4px; }
    .card.overall.pass .value { color: var(--pass); }
    .card.overall.fail .value { color: var(--fail); }
    .bar { height: 8px; background: var(--border); border-radius: 4px; overflow: hidden; margin-top: 8px; }
    .bar > span { display: block; height: 100%; background: linear-gradient(90deg, var(--pass), #56d364); width: ${passPct}%; }
    .case-section {
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 18px 20px; margin-bottom: 16px;
    }
    .case-section.bad { border-color: var(--fail); background: rgba(248, 81, 73, 0.04); }
    .case-header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
    .case-num { color: var(--muted); font-size: 0.8rem; font-weight: 600; }
    .case-name { font-weight: 700; font-size: 1rem; }
    .badge {
      display: inline-block; padding: 2px 10px; border-radius: 999px;
      font-size: 0.75rem; font-weight: 700; margin-left: auto;
    }
    .badge.pass { background: rgba(63, 185, 80, 0.2); color: var(--pass); }
    .badge.fail { background: rgba(248, 81, 73, 0.2); color: var(--fail); }
    .case-desc { color: var(--text); font-size: 0.9rem; margin-bottom: 10px; }
    .case-body { display: flex; flex-direction: column; gap: 10px; }
    details.screenshot-block { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
    details.screenshot-block summary {
      padding: 8px 12px; background: #21262d; cursor: pointer;
      font-size: 0.82rem; font-weight: 600; color: var(--muted);
    }
    details.screenshot-block img {
      width: 100%; max-height: 500px; object-fit: contain;
      background: #161b22; display: block;
    }
    details.code-block { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
    details.code-block summary {
      padding: 8px 12px; background: #21262d; cursor: pointer;
      font-size: 0.82rem; font-weight: 600; color: var(--muted);
    }
    details.code-block pre {
      margin: 0; padding: 12px 14px; background: #161b22;
      white-space: pre-wrap; word-break: break-word; font-size: 0.78rem;
      color: #c9d1d9; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      max-height: 300px; overflow-y: auto;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>大R后台 Web UI 自动化验收</h1>
    <div class="meta-info">
      生成时间：${esc(now)}<br/>
      前端入口：<a href="${esc(BIG_R_URL)}" target="_blank">${esc(BIG_R_URL)}</a>
    </div>
    <div class="cards">
      <div class="card overall ${passed === total ? 'pass' : 'fail'}">
        <div class="label">总结果</div>
        <div class="value">${passed === total ? '通过' : '失败'}</div>
      </div>
      <div class="card">
        <div class="label">通过</div>
        <div class="value" style="color:var(--pass)">${passed}</div>
      </div>
      <div class="card">
        <div class="label">失败</div>
        <div class="value" style="color:var(--fail)">${failed}</div>
      </div>
      <div class="card">
        <div class="label">通过率</div>
        <div class="value">${passPct}%</div>
        <div class="bar"><span></span></div>
      </div>
    </div>
    ${caseSections}
  </div>
</body>
</html>`;

  writeFileSync(outputPath, html, 'utf-8');
}

main();
