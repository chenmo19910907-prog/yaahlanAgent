import { agentFromAdbDevice, getConnectedDevices, AndroidAgent } from '@midscene/android';
import { describe, it, beforeAll, afterAll } from 'vitest';
import { config, AI_ACTION_CONTEXT, sleep } from '../../utils/env';

let agent: AndroidAgent;

async function createAgent(): Promise<AndroidAgent> {
  let deviceId = config.androidDeviceId;
  if (!deviceId) {
    const devices = await getConnectedDevices();
    if (!devices.length) throw new Error('未找到已连接的 Android 设备');
    deviceId = devices[0].udid;
  }
  return agentFromAdbDevice(deviceId, {
    aiActionContext: AI_ACTION_CONTEXT,
    autoDismissKeyboard: true,
  });
}

describe('SoulChill Android - 个人主页模块', () => {
  beforeAll(async () => {
    agent = await createAgent();
    await agent.launch('soulchill://com.live.soulchill/login');
    await sleep(3000);
    await agent.aiWaitFor('首页底部导航栏可见', { timeoutMs: 20000 });
  });

  afterAll(async () => {
    await agent.page.destroy();
  });

  it('应能进入个人主页', async () => {
    await agent.aiAct('点击底部导航栏的"我的"Tab 或个人头像');
    await sleep(1500);

    await agent.aiWaitFor('个人主页加载完成', { timeoutMs: 15000 });

    const profileInfo = await agent.aiQuery(
      '{ nickname: string, userId: string, followersCount: string, followingCount: string }, 获取个人主页上的昵称、用户ID、粉丝数和关注数',
    );
    console.log('[个人信息]', JSON.stringify(profileInfo, null, 2));
    await agent.aiAssert('个人主页正常显示昵称和用户信息');
  });

  it('应能查看关注/粉丝列表', async () => {
    await agent.aiAct('点击"关注"数字入口');
    await sleep(1500);

    await agent.aiWaitFor('关注列表页面加载完成', { timeoutMs: 15000 });
    await agent.aiAssert('关注列表页面正常显示');

    await agent.aiAct('点击返回按钮回到个人主页');
    await sleep(1000);
  });

  it('应能查看动态/作品列表', async () => {
    await agent.aiAct('在个人主页找到"动态"或"作品"Tab 并点击');
    await sleep(1500);

    await agent.aiWaitFor('动态或作品列表加载完成', { timeoutMs: 15000 });
    await agent.aiAssert('动态或作品列表页面正常显示，无报错');
  });

  it('应能进入编辑资料页面', async () => {
    await agent.aiAct('找到"编辑资料"或"编辑个人信息"入口并点击');
    await sleep(1500);

    await agent.aiWaitFor('编辑资料页面加载完成', { timeoutMs: 15000 });
    await agent.aiAssert('编辑资料页面正常显示昵称、简介等可编辑字段');

    await agent.aiAct('点击返回按钮，不保存任何修改');
    await sleep(1000);
  });
});
