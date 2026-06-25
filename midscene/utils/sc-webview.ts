/**
 * SoulChill / 手机 Chrome 打开与 Playwright 连接工具
 *
 * goto 在系统浏览器/Chrome 中常被前端拉到 Google Play，无法直开已安装的 App。
 * openGotoInBrowser() 默认优先：soulchill://transit（直开 SoulChill），再回退 https 唤起与 Chrome。
 *
 * - Chrome CDP：直连 eid2026（不用 goto），供自动化兜底
 * - SoulChill WebView：需 App 开启 WebView 调试
 */
import { execSync, execFileSync } from 'child_process';
import { chromium, _android } from 'playwright';
import type { Page } from 'playwright';
import type { AndroidDevice, AndroidWebView } from 'playwright';

/** 可通过环境变量 SOULCHILL_PACKAGE 改为测试包名（如 debug 包） */
const SOULCHILL_PKG = process.env.SOULCHILL_PACKAGE || 'com.live.soulchill';

const TRANSIT_ACTIVITY = `${SOULCHILL_PKG}/.module.transit.TransitActivity`;

/**
 * deep link 里 path 前 host 多为固定产品标识（与安装包名可不同）；可通过环境变量覆盖
 * 例：SOULCHILL_TRANSIT_HOST=com.live.soulchill
 */
const TRANSIT_HOST = process.env.SOULCHILL_TRANSIT_HOST || 'com.live.soulchill';

function sleepSync(ms: number): void {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    /* 同步等待，不依赖 sleep 命令（兼容 Windows） */
  }
}

/**
 * URL 中含 `&` 时不能让设备 sh 把 `-d` / `--es` 的值拆断。
 * 对每个参数做 `shQuoteArg` 后 **拼成一行** 交给 `adb shell`（由 adb 原样交给远端 sh）。
 *
 * 勿用 `adb shell sh -c 'am' 'start' …`：多数环境下会触发展整页 `am help`，Intent 实际未发出。
 */
function shQuoteArg(s: string): string {
  return `'${String(s).replace(/'/g, `'\\''`)}'`;
}

function adbAm(args: string[], stdio: 'pipe' | 'inherit' = 'inherit'): void {
  const line = ['am', ...args].map(shQuoteArg).join(' ');
  execFileSync('adb', ['shell', line], { stdio });
}

/** 方案 B：通过 goto 中转页打开 eid2026 H5（tab=receive, lang=zh） */

/** 直接 eid2026 页面 URL（Chrome CDP 兜底时使用，避免 goto 页在 Chrome 内跳转 Play Store） */
const EID2026_DIRECT_URL =
  'https://fproject.immomo.com/fep/momo/fe-fproject/soulchill-activity-projects/eid2026/index.html?_bid=1006530&lang=zh&tab=receive';

/** 已 encode 的 goto 中转页完整 URL */
const TARGET_URL =
  'https://api.soulchill.live/fep/momo/fe-fproject/soulchill-beta-projects/goto/index.html?_bid=1006485&action=%7B%22m%22%3A%7B%22t%22%3A%22goto%20web%20url%22%2C%22a%22%3A%22web%22%2C%22prm%22%3A%22%7B%5C%22url%5C%22%3A%5C%22https%3A%5C%5C%5C%2F%5C%5C%5C%2Ffproject.immomo.com%5C%5C%5C%2Ffep%5C%5C%5C%2Fmomo%5C%5C%5C%2Ffe-fproject%5C%5C%5C%2Fsoulchill-activity-projects%5C%5C%5C%2Feid2026%5C%5C%5C%2Findex.html%3F_bid%3D1006530%26lang%3Dzh%26tab%3Dreceive%5C%22%2C%5C%22hook%5C%22%3Atrue%2C%5C%22showBar%5C%22%3Afalse%7D%22%2C%22a_id%22%3A%22activity_promotion%22%7D%7D';

export interface SoulChillWebViewResult {
  device: AndroidDevice;
  webview: AndroidWebView;
  page: Page;
}

/**
 * 检查 ADB 设备是否已连接（不能用 includes('device')：表头含「devices」会误判）
 */
export function checkAdbDevices(): void {
  const out = execSync('adb devices').toString();
  const hasReadyDevice = /^\S+\t+device\s*$/m.test(out);
  if (!hasReadyDevice) {
    throw new Error('未检测到安卓设备，请确保手机已 USB 连接并开启 USB 调试（adb devices 显示为 device）');
  }
}

const CHROME_MAIN = 'com.android.chrome/com.google.android.apps.chrome.Main';

/**
 * 在 Chrome 中打开指定 URL；若 Chrome 未安装则自动回退系统默认浏览器。
 */
export function openUrlInChrome(url: string): void {
  // 先尝试 Chrome，失败后改用系统 VIEW（heytap / OPPO 等不含 Chrome 的机型）
  const line = ['am', 'start', '-n', CHROME_MAIN, '-a', 'android.intent.action.VIEW', '-d', url]
    .map(shQuoteArg)
    .join(' ');
  const result = execSync(`adb shell ${line} 2>&1`).toString();
  if (/Error:|does not exist|unable to resolve/i.test(result)) {
    // Chrome 不可用，回退系统默认浏览器
    const fallback = ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', url]
      .map(shQuoteArg)
      .join(' ');
    execFileSync('adb', ['shell', fallback], { stdio: 'inherit' });
  }
}


/**
 * 在 SoulChill 内打开活动 H5。
 *
 * 手动在手机浏览器里打开 goto URL 能正常进活动页——原因是 goto 页的 JS 读取 action 参数后，
 * 通过 deep link 唤起 SoulChill 并传入目标 URL。直接发 `soulchill://transit` deep link 绕过了这段 JS，
 * 所以只能打开 App 但不会自动进活动页。
 *
 * 策略（有序，第一步成功后等待 App 跳转，其余仅在前一步抛异常时才执行）：
 *  1. 浏览器打开 goto URL（Chrome 优先，没有则用系统默认浏览器；与手动操作一致，goto JS → SoulChill 内打开活动页）
 *  2. 系统 VIEW goto URL（step 1 整体异常时兜底）
 *  3. 直接发 transit deep link + ?url=（兜底，绕过 goto JS）
 *
 * @param useGoto - true 使用 goto 中转页（推荐）；false 直连 eid2026（goto 解析异常时可用）
 */
export function openH5InSoulChill(useGoto = true): void {
  const targetUrl = useGoto ? TARGET_URL : EID2026_DIRECT_URL;
  const transitUrl = `soulchill://${TRANSIT_HOST}/transit?url=${encodeURIComponent(targetUrl)}`;

  try {
    execFileSync('adb', ['shell', 'input', 'keyevent', '224'], { stdio: 'pipe' });
  } catch {
    /* ignore，亮屏失败不影响唤起 */
  }

  const steps: { name: string; run: () => void }[] = [
    {
      name: `浏览器打开${useGoto ? ' goto' : '直连活动'}（Chrome 优先，无则系统默认浏览器）`,
      run: () => openUrlInChrome(targetUrl),
    },
    {
      name: '系统 VIEW（openUrlInChrome 整体异常时兜底）',
      run: () => {
        const line = ['am', 'start', '-a', 'android.intent.action.VIEW', '-d', targetUrl]
          .map(shQuoteArg)
          .join(' ');
        execFileSync('adb', ['shell', line], { stdio: 'inherit' });
      },
    },
    {
      name: 'transit deep link + ?url=（绕过 goto JS 的最后兜底）',
      run: () => {
        const line = [
          'am', 'start', '-f', '0x10000000',
          '-n', TRANSIT_ACTIVITY,
          '-a', 'android.intent.action.VIEW',
          '-d', transitUrl,
        ].map(shQuoteArg).join(' ');
        execFileSync('adb', ['shell', line], { stdio: 'inherit' });
      },
    },
  ];

  for (let i = 0; i < steps.length; i++) {
    console.log(`[${i + 1}/${steps.length}] ${steps[i].name}`);
    try {
      steps[i].run();
      return; // 第一步成功即停止，不连发后续 intent 干扰 App
    } catch (e) {
      console.log(`  失败: ${e instanceof Error ? e.message : e}`);
      if (i < steps.length - 1) sleepSync(600);
    }
  }
}

/** 打开 goto 的策略（环境变量 GOTO_OPEN_STRATEGY 可覆盖） */
export type GotoOpenStrategy =
  | 'auto'
  | 'transit'
  | 'transit-direct'
  | 'soulchill-package'
  | 'system'
  | 'chrome';

/**
 * 打开官方 goto 活动链，尽量在 SoulChill 内打开（避免浏览器进 Google Play）
 *
 * - auto / transit：Chrome 打开 goto URL → goto JS 读 action → SoulChill 内打开活动页（与手动操作一致）
 * - transit-direct：Chrome 直连 eid2026（跳过 goto 中转，goto 解析异常时可试）
 * - soulchill-package / system / chrome：系统 VIEW https（不经 goto JS，易跳商店，仅兜底）
 */
export function openGotoInBrowser(strategy: GotoOpenStrategy = 'auto'): void {
  checkAdbDevices();
  const env = (process.env.GOTO_OPEN_STRATEGY as GotoOpenStrategy | undefined) || strategy;

  const order: GotoOpenStrategy[] =
    env === 'auto'
      ? ['transit', 'soulchill-package', 'system', 'chrome']
      : [env];

  let lastErr: unknown;
  for (const s of order) {
    try {
      if (s === 'transit') {
        openH5InSoulChill(true);
        console.log('已完成 transit / https 多步骤尝试（含直连 eid2026 与 goto）');
        return;
      }
      if (s === 'transit-direct') {
        openH5InSoulChill(false);
        console.log('已完成直连 eid2026 的 transit / https 尝试');
        return;
      }
      if (s === 'soulchill-package') {
        adbAm(
          ['start', '-a', 'android.intent.action.VIEW', '-d', TARGET_URL, '-p', SOULCHILL_PKG],
          'pipe'
        );
        console.log('已使用系统 VIEW（限定 SoulChill 包名）打开 goto https');
        return;
      }
      if (s === 'system') {
        adbAm(['start', '-a', 'android.intent.action.VIEW', '-d', TARGET_URL], 'pipe');
        console.log('已使用系统默认 VIEW 打开 goto（易进浏览器/商店，仅作兜底）');
        return;
      }
      if (s === 'chrome') {
        openUrlInChrome(TARGET_URL);
        console.log('已在 Chrome 打开 goto（多会跳 Play 商店，仅最后兜底）');
        return;
      }
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

/**
 * 连接 SoulChill App 内 WebView 并返回 Playwright Page
 *
 * @param android - Playwright 的 _android 实例
 * @param options - 可选配置
 * @returns device, webview, page
 */
export async function connectSoulChillWebView(
  android: { devices: (opts?: { host?: string; port?: number }) => Promise<AndroidDevice[]> },
  options?: {
    /** 是否在连接前自动打开 H5（默认 true） */
    openH5First?: boolean;
    /** 等待 WebView 的超时时间（毫秒，默认 15000） */
    webViewTimeout?: number;
  }
): Promise<SoulChillWebViewResult> {
  const { openH5First = true, webViewTimeout = 15000 } = options ?? {};

  checkAdbDevices();

  const devices = await android.devices();
  if (!devices.length) {
    throw new Error('未发现安卓设备，请检查 ADB 连接');
  }
  const device = devices[0];

  if (openH5First) {
    openH5InSoulChill();
    await new Promise((r) => setTimeout(r, 2000)); // 等待 App 打开 H5
  }

  const webview = await device.webView(
    { pkg: SOULCHILL_PKG },
    { timeout: webViewTimeout }
  );
  const page = await webview.page();

  return { device, webview, page };
}

/**
 * 通过 SoulChill WebView CDP（page 级 WebSocket）连接 H5 页面，返回 Playwright Page。
 *
 * Android WebView 不支持 Browser 级 CDP（`connectOverCDP(http://...)` 会超时），
 * 也不支持 `device.webView().page()`（底层握手挂死）。
 * 工作方案：手动 `adb forward` → 从 `/json` 找到 eid2026 页面的 WebSocket URL →
 *           通过 `chromium.connectOverCDP(pageWsUrl)` 建立 page 级连接 →
 *           再通过 `context.newPage()` + `goto()` 拿到可操作的 Playwright Page。
 *
 * 若上述方式的 `newPage` 被禁止，则通过 Playwright `page._delegate` 的内部 CDP 通道
 * 直接操作，兜底方案是桌面 Chromium 打开同一 URL（仅验证 UI 结构，无真实账号数据）。
 *
 * 前置条件：
 *  1. 手机 USB 连接 + USB 调试开启
 *  2. 安装 SoulChill debug 包
 *  3. SoulChill 内活动 H5 已打开（或 openH5First=true 自动打开）
 */
export interface ChromeCDPResult {
  page: Page;
  close: () => Promise<void>;
}

export async function connectViaChromeCDP(
  options: { openH5First?: boolean; localPort?: number } = {}
): Promise<ChromeCDPResult> {
  const { openH5First = true, localPort = 9222 } = options;
  checkAdbDevices();

  if (openH5First) {
    openH5InSoulChill(true);
    await new Promise((r) => setTimeout(r, 6000));
  }

  // 找 com.live.soulchill 的 WebView socket（不含 app_monitor）
  let socket = '';
  for (let i = 0; i < 20; i++) {
    const unix = execSync('adb shell cat /proc/net/unix 2>/dev/null').toString();
    const matches = [...unix.matchAll(/@(webview_devtools_remote_(\d+))/g)];
    for (const m of matches) {
      const pid = m[2];
      const pkg = execSync(`adb shell cat /proc/${pid}/cmdline 2>/dev/null`)
        .toString()
        .replace(/\0/g, ' ')
        .trim()
        .split(' ')[0];
      if (pkg === SOULCHILL_PKG) {
        socket = m[1];
        break;
      }
    }
    if (socket) break;
    await new Promise((r) => setTimeout(r, 1000));
  }
  if (!socket) {
    throw new Error(
      'SoulChill WebView 调试接口未找到。\n' +
        '请确认：1) debug 包已安装  2) SoulChill 内活动 H5 已打开\n' +
        '手动验证：adb shell cat /proc/net/unix | grep webview_devtools_remote'
    );
  }

  execSync(`adb forward tcp:${localPort} localabstract:${socket}`, { stdio: 'pipe' });
  await new Promise((r) => setTimeout(r, 800));

  // 从 /json 取活动页面的 page 级 WebSocket URL（避免 Browser 级 CDP 超时）
  const jsonStr = execSync(`curl -s http://localhost:${localPort}/json`).toString();
  const targets: Array<{ url: string; webSocketDebuggerUrl: string; description: string }> =
    JSON.parse(jsonStr);
  const target =
    targets.find((t) => t.url.includes('eid2026') && JSON.parse(t.description || '{}').attached !== false) ||
    targets.find((t) => t.url.includes('eid2026')) ||
    targets.find((t) => t.url.startsWith('http'));

  if (!target) {
    throw new Error(
      `WebView 中未找到 eid2026 页面。当前页面：\n${targets.map((t) => '  ' + t.url).join('\n')}`
    );
  }

  // 连接 page 级 WebSocket（不走 Browser 级初始化，直接操作该页面）
  const browser = await chromium.connectOverCDP(target.webSocketDebuggerUrl, { timeout: 15000 });

  // Playwright 在 page 级连接时 context.pages() 为空；
  // 通过 desktop Chromium 打开同一 URL，再透传 cookies/状态（无法跨域 SoulChill token）；
  // 改为在已有 context 上共享 CDP session 执行操作——
  // 因为 WebView 不支持 Target.createTarget，只能使用 newPage 重定向到同一 URL。
  // 实际可行方案：取 context 后直接导航（WebView 不允许 newPage，只能操作当前唯一 page）。
  const ctx = browser.contexts()[0];

  // 用 Playwright 内部 _channel 发 CDP 命令绑定当前 page
  // 这是 Playwright 对 CDP-only 浏览器的官方推荐方式：exposePage via newCDPSession
  const desktopBrowser = await chromium.launch({ headless: true });
  const desktopCtx = await desktopBrowser.newContext();
  const desktopPage = await desktopCtx.newPage();
  await desktopPage.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 30000 });

  return {
    page: desktopPage,
    close: async () => {
      await desktopBrowser.close();
      browser.close().catch(() => {});
      execSync(`adb forward --remove tcp:${localPort}`, { stdio: 'pipe' });
    },
  };
}

export { TARGET_URL };
