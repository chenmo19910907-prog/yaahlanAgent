import { config } from './env';

const GET_VERIFY_CODE_URL = 'https://fproject.immomo.com/inner/admin/ui/getVerifyCode';

/**
 * 从后台管理接口获取测试账号的最新验证码。
 * 响应格式：{ "ec": 0, "data": { "code": "987598" } }
 *
 * 使用前提：先在 App 中点击"下一步"/"获取验证码"按钮触发短信发送，
 * 再调此接口从后台拿到实际下发的验证码。
 */
export async function getVerifyCode(phone?: string, prefix?: string): Promise<string> {
  const p  = phone  ?? config.testPhone;
  const pf = prefix ?? config.testPhonePrefix;

  const url = `${GET_VERIFY_CODE_URL}?phone=${encodeURIComponent(p)}&prefix=${encodeURIComponent(pf)}`;
  const res = await fetch(url);
  const json = await res.json().catch(() => null);

  if (!res.ok || json?.ec !== 0 || !json?.data?.code) {
    throw new Error(
      `getVerifyCode 失败：HTTP ${res.status}，ec=${json?.ec}，em=${json?.em}`
    );
  }

  const code = String(json.data.code);
  console.log(`[getVerifyCode] ✓ phone=${p} code=${code}`);
  return code;
}
