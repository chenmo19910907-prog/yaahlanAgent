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

describe('SoulChill Android -星球首页', () => {
  beforeAll(async () => {
    agent = await createAgent();
    // 通过 deeplink 进入已登录状态的首页
    await agent.launch('soulchill://com.live.soulchill/login');
    await sleep(3000);
    await agent.aiWaitFor('首页底部导航栏可见首页底部导航栏显示星球、派对、动态、消息、我', { timeoutMs: 20000 });
  });

  afterAll(async () => {
    await agent.page.destroy();
  });

  it('底部导航Tab切换正常', async () => {
    await agent.aiAssert('默认选中星球Tab');
    await agent.aiAct('点击派对Tab');
    await agent.aiWaitFor('页面显示"派对"', { timeoutMs: 20000 });
    await agent.aiAct('点击动态Tab');
    await agent.aiWaitFor('页面显示"动态"', { timeoutMs: 20000 });
    await agent.aiAct('点击消息Tab');
    await agent.aiWaitFor('页面显示"消息"', { timeoutMs: 20000 });
    await agent.aiAct('点击我Tab');
    await agent.aiWaitFor('页面显示"我"', { timeoutMs: 20000 });  
  });

  it('灵魂测试功能正常', async () => {
    await agent.aiAct('点击星球Tab');
    await agent.aiAct('点击主人公');
    await agent.aiAssert('显示用户头像、所属星球、分享按钮');
    await agent.aiAssert('显示基础测试、中级测试、高级测试');

    await agent.aiAct('点击分享按钮');  
    await agent.aiWaitFor('跳转灵魂测试结果页面', { timeoutMs: 20000 });
    await agent.aiAct('点击右上角分享');
    await agent.aiAssert('底部显示分享面板，面板显示Facebook');
    await agent.aiAct('点击Facebook分享按钮');
    await agent.aiWaitFor('弹出"SoulChill"想要打开"Facebook"', { timeoutMs: 20000 });
    await agent.aiAct('点击打开按钮');
    await agent.aiAssert('跳转Facebook分享页面');
    await agent.aiAct('点击关闭按钮');
    

    await agent.aiAct('点击屏幕中间位置关闭分享面板');
    await agent.aiAct('点击返回按钮');
    
    await agent.aiAct('点击重新测试');
    await agent.aiAssert('跳转灵魂测试答题页面');
    await agent.aiAct('选择"实事求是，具丰富常识的人"');
    await agent.aiAct('选择"提前计划，做好充足的计划和准备"');
    await agent.aiAct('选择"与多数人都能从容地长谈"');
    await agent.aiAct('选择"理性多过感性的人"');
    await agent.aiAssert('显示"主人公"');
    await agent.aiAct('点击右上角分享');
    await agent.aiAct('底部显示分享面板，面板显示Facebook');
    await agent.aiAct('点击屏幕中间关闭弹窗');
    await agent.aiAct('点击返回按钮');

  
    await agent.aiAssert('跳转灵魂测试结果页面');
    await agent.aiAssert('显示"实事求是，具丰富常识的人"');
    await agent.aiAct('点击返回按钮');

    await agent.aiAct('点击测试');
    await agent.aiAssert('跳转灵魂测试答题页面');
    await agent.aiAct('点击返回按钮');

    await agent.aiAct('向下滑动页面');
    await agent.aiAssert('显示"Lock"');
    await agent.aiAssert('显示"更多有趣的测试"');
  });
});
