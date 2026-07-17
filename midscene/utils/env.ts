import 'dotenv/config';

function requireEnv(key: string, fallback?: string): string {
  const value = process.env[key] ?? fallback;
  if (!value) {
    throw new Error(`缺少必要环境变量：${key}，请检查 .env 文件`);
  }
  return value;
}

export const config = {
  // iOS
  wdaHost: process.env.WDA_HOST ?? 'localhost',
  wdaPort: parseInt(process.env.WDA_PORT ?? '8100', 10),
  iosAppId: process.env.IOS_APP_ID ?? 'live.soulchill.ios',

  // Android（Yaahlan 正式包 com.immomo.biz.yaahlan，见 adb/adb/apps.py）
  androidDeviceId: process.env.ANDROID_DEVICE_ID ?? '',
  androidAppId: process.env.ANDROID_APP_ID ?? 'com.immomo.biz.yaahlan',
  androidLaunchMode: process.env.ANDROID_LAUNCH_MODE ?? 'launcher',
  androidMainActivity: process.env.ANDROID_MAIN_ACTIVITY ?? '.personalityIcon4',
  androidForceStopYaha: process.env.ANDROID_FORCE_STOP_YAHA ?? 'com.immomo.yaha',

  // 测试账号
  testPhone: requireEnv('TEST_PHONE', '13800138000'),
  testPhonePrefix: process.env.TEST_PHONE_PREFIX ?? '+966',
  testVerifyCode: process.env.TEST_VERIFY_CODE ?? '123456',
  testPassword: process.env.TEST_PASSWORD ?? 'Test@123456',
} as const;

/** 通用 AI 上下文提示：自动处理各类弹窗 */
export const AI_ACTION_CONTEXT =
  '如果出现位置权限、通知权限、麦克风权限、摄像头权限等系统弹窗，点击"允许"或"好"。' +
  '如果出现用户协议或隐私政策弹窗，点击同意。' +
  '如果出现青少年模式弹窗，点击关闭。' +
  '如果出现广告或活动弹窗，点击右上角关闭按钮。';

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
