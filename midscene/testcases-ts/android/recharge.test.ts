import 'dotenv/config';
import {
  AndroidAgent,
  AndroidDevice,
  getConnectedDevices,
} from '@midscene/android';

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env: ${name}`);
  }
  return value;
}

async function launchSoulChill(device: AndroidDevice, pkg: string, activity?: string) {
  const adb = await device.getAdb();

  if (activity) {
    await adb.shell(`am start -n ${activity}`);
    return;
  }

  await adb.shell(`monkey -p ${pkg} -c android.intent.category.LAUNCHER 1`);
}

async function main() {
  requiredEnv('MIDSCENE_MODEL_BASE_URL');
  requiredEnv('MIDSCENE_MODEL_API_KEY');
  requiredEnv('MIDSCENE_MODEL_NAME');
  requiredEnv('MIDSCENE_MODEL_FAMILY');

  const pkg = process.env.SOULCHILL_PACKAGE || 'com.soulchill.live';
  const launchActivity = process.env.SOULCHILL_LAUNCH_ACTIVITY;
  const preferredUdid = process.env.ANDROID_UDID;

  const devices = await getConnectedDevices();
  if (!devices.length) {
    throw new Error('No Android device connected. Please run: adb devices -l');
  }

  const target =
    (preferredUdid
      ? devices.find((d) => d.udid === preferredUdid)
      : devices[0]) || devices[0];

  const device = new AndroidDevice(target.udid);
  await device.connect();

  const agent = new AndroidAgent(device, {
    aiActionContext:
      '如果出现权限弹窗、用户协议、青少年模式或登录弹窗，优先关闭或同意后继续测试流程。',
  });

  console.log(`Using device: ${target.udid}`);
  console.log(`Launching SoulChill package: ${pkg}`);
  await launchSoulChill(device, pkg, launchActivity);
  await sleep(5000);

  await agent.aiAct('点击"我"tab');
  await agent.aiAct('点击"我的钱包"');
  await agent.aiWaitFor('进入钱包页面，页面中可见充值或地区相关选项');
  // 1. 先判断：当前地区是否为非埃及（即需要切换地区）
  const hasButtonA = await agent.aiBoolean('页面上是否存在地区切换按钮，且当前地区不是"埃及"');

  // 2. 如果存在，就点击切换到埃及
  if (hasButtonA) {
    await agent.aiAct('点击页面中显示当前地区或货币的按钮，以打开地区选择列表');
    await agent.aiWaitFor('打开地区选择弹窗');
    await agent.aiAct('在地区选择列表中向下滑动，直到看到"埃及"选项');
    await agent.aiAct('点击列表中的"埃及"选项');
  }
  await agent.aiAct('点击"EGP50.60"');
  await agent.aiAct('cvv 输入"111"');
  await agent.aiAct('点击"支付"', { abortSignal: AbortSignal.timeout(60000) });
  await agent.aiAssert('显示"付款成功"');
  await agent.aiAct('点击"返回"');

  const result = await agent.aiQuery(
    '{pageType: string, hasChatInput: boolean, visibleTabs: string[]}, 识别当前页面类型、是否有输入框、以及底部可见标签',
  );

  console.log('SoulChill page snapshot:', result);
  await agent.aiAssert('当前页面没有崩溃提示，也没有明显网络错误提示。');

  console.log('SoulChill Midscene smoke test finished.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
