/**
 * 工具台能力目录面板（Web Agent 深色主题版）
 * onRunPrompt(text) — 填参后点击「执行」时回调（填入提问栏，不自动发送）
 */
(function (global) {
  'use strict';

  const PROMPT_PLACEHOLDER_RE = /<([^>|]+)(?:\|([^>]+))?>/g;
  const PROMPT_FIELD_WIDE_CHAR_RE =
    /[\u1100-\u11ff\u2e80-\u9fff\uf900-\ufaff\ufe10-\ufe19\ufe30-\ufe6f\uff00-\uffef]/;

  /** 占位 label 按宽字符（CJK 等）估算 em 宽度，避免 placeholder 被截断 */
  function promptFieldWidthEm(label) {
    let units = 0;
    for (const ch of String(label || '')) {
      units += PROMPT_FIELD_WIDE_CHAR_RE.test(ch) ? 2 : 1;
    }
    return Math.min(22, Math.max(5, units + 2));
  }
  const NAV_COLLAPSED_LS_KEY = 'web_agent_catalog_nav_collapsed';

  function readLsStringSet(key) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      const arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return null;
      return new Set(arr.map(String).filter(Boolean));
    } catch (_) {
      return null;
    }
  }

  function writeLsStringSet(key, set) {
    try {
      localStorage.setItem(key, JSON.stringify(Array.from(set || [])));
    } catch (_) { /* ignore quota */ }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/"/g, '&quot;');
  }

  /** 无 <key|label> 时占位框默认中文 label */
  const PROMPT_KEY_LABELS = {
    userId: '用户 ID',
    senderUserId: '送礼用户 ID',
    receiverUserId: '收礼用户 ID',
    cpUserId: 'CP 用户 ID',
    remoteId: '对方用户 ID',
    roomId: '房间 ID',
    familyId: '家族 ID',
    giftId: '礼物 ID',
    phone: '手机号',
    mmuidv3: '设备 mmuidv3',
    device: '设备标识',
    serviceUrl: 'MOA 服务地址',
    method: '方法名',
    bodyFile: '抓包 body 文件',
    timeoutMs: '超时（毫秒）',
    strict: '严格模式',
    payloadOut: '产物路径',
    workbookUrl: '表格链接',
    pkDate: 'PK 日期',
    baseProductId: '礼物 ID',
    expectRemain: '期望剩余数量',
    num: '数量',
    smashCount: '砸蛋次数',
    fromUserId: '用户 A ID',
    toUserId: '用户 B ID',
    applicantUserId: '申请人 ID',
    ownerUserId: '房主 ID',
    propId: '装扮 ID',
    propTypeCode: '装扮类型码',
    expectedDays: '有效天数',
    toleranceDays: '天数容差',
    referenceTs: '参考时间戳',
    outFile: '输出文件',
    propTypes: '装扮类型列表',
    intimateId: '挚友 ID',
    tier: '档位',
    level: '等级',
    exp: '经验值',
    value: '数值',
    area: '大区',
    rankDate: '榜单日期',
    sinceSeconds: '抓包时间范围（秒）',
  };

  /** 能力快捷提示语中的非常用英文 → 中文（不影响 <占位> 语法） */
  function humanizeCatalogPromptText(text) {
    let s = String(text || '');
    if (!s) return '';
    const protectedChunks = [];
    s = s.replace(/<[^>]+>/g, (tag) => {
      const i = protectedChunks.length;
      protectedChunks.push(tag);
      return `\x00PH${i}\x00`;
    });
    const replacements = [
      [/\bcooldown\b/gi, '冷却时间'],
      [/\bHEADER_FRAME\b/g, '头像框'],
      [/\bVEHICLE\b/g, '座驾'],
      [/\bNAMEPLATE\b/g, '铭牌'],
      [/\bMEDAL\b/g, '勋章'],
      [/\bMENA\b/g, '中东区'],
      [/\bpayload\b/gi, '请求体'],
      [/\bstrict\b/gi, '严格校验'],
      [/\bsnapshot\b/gi, '快照'],
      [/\bdiff\b/gi, '差异对比'],
      [/\bbaseline\b/gi, '起点数据'],
      [/\bStage\b/g, '测试环境'],
      [/\bmock\b/gi, '模拟'],
      [/\bE2E\b/g, '端到端'],
      [/\bVIP\b/g, 'VIP'],
    ];
    for (const [re, rep] of replacements) {
      s = s.replace(re, rep);
    }
    s = s.replace(/\x00PH(\d+)\x00/g, (_, i) => protectedChunks[Number(i)] || '');
    return s;
  }

  function promptPlaceholderLabel(key, explicitLabel) {
    const k = String(key || '').trim();
    const explicit = String(explicitLabel || '').trim();
    if (explicit && explicit !== k) {
      return humanizeCatalogPromptText(explicit);
    }
    if (PROMPT_KEY_LABELS[k]) return PROMPT_KEY_LABELS[k];
    if (PLAYBOOK_DEFAULT_LABELS[k]) return PLAYBOOK_DEFAULT_LABELS[k];
    return humanizeCatalogPromptText(explicit || k);
  }

  const PLAYBOOK_DEFAULT_LABELS = {
    userId: '用户',
    senderUserId: '送礼用户',
    receiverUserId: '收礼用户',
    giftId: '礼物 ID',
    runTag: '本轮标记',
    tierFrom: '起始档位',
    tierTo: '结束档位',
    expectedDays: '装扮有效天数',
    toleranceDays: '天数容差',
    sinceSeconds: '抓包时间范围（秒）',
    workbookUrl: '钉钉表格链接',
    pkDate: 'PK 日期',
    rankDate: '收礼榜日期',
    timeoutMs: '超时（毫秒）',
  };

  /** 将 registry 中的技术摘要/说明转为更易读的展示文案（保留含义，弱化箭头与字段名） */
  function humanizePlaybookProse(text) {
    let s = String(text || '').trim();
    if (!s) return '';
    s = s.replace(/\s*(?:→|->|—>)\s*/g, '，然后 ');
    s = s.replace(/；/g, '。');
    const replacements = [
      [/getCpLoveChestHomepage/gi, '查询宝箱主页'],
      [/cpLoveChestConfigAreaMap/g, '爱意宝箱盘古配置'],
      [/snapshot\/diff/gi, '发奖前后快照对比'],
      [/\bbaseline\b/gi, '起点数据'],
      [/claimedTierId/g, '已领取档位'],
      [/currentLoveValue/g, '当前周期爱意值'],
      [/tiers\[\]\.status/g, '各档领取状态'],
      [/tiers\[\]\.threshold/g, '各档爱意门槛'],
      [/playbook\s+(\S+)/gi, '工作流「$1」'],
      [/workflow_execute\s+run\s+(\S+)/gi, '工作流 $1'],
      [/intimate_cp_form/gi, '结 CP 表单'],
      [/reward_dispatch_verify/g, '单档奖励下发验收'],
      [/E2E/g, '端到端'],
      [/MSE\s+盘古/g, '盘古（MSE）'],
      [/Stage\s+私聊/g, '测试环境私聊'],
      [/gift_execute/g, '送礼脚本'],
      [/plan_cp_love_gift/g, '规划送礼数量'],
      [/\bcooldown\b/gi, '冷却时间'],
      [/\bHEADER_FRAME\b/g, '头像框'],
      [/\bsnapshot\b/gi, '快照'],
      [/\bdiff\b/gi, '差异对比'],
      [/\bbaseline\b/gi, '起点数据'],
      [/\bpayload\b/gi, '请求体'],
      [/\bstrict\b/gi, '严格校验'],
      [/\bmock\b/gi, '模拟'],
    ];
    for (const [re, rep] of replacements) {
      s = s.replace(re, rep);
    }
    s = s.replace(/\s+/g, ' ').replace(/。+/g, '。').trim();
    return s;
  }

  function playbookDefaultLabel(key) {
    return PLAYBOOK_DEFAULT_LABELS[key] || key;
  }

  /** 将步骤里的 python 命令转为一句操作说明（详情区不展示原始命令） */
  function humanizePlaybookCommand(cmd) {
    const c = String(cmd || '').trim();
    if (!c) return '';
    const rules = [
      [/plan_cp_love_gift\.py[\s\S]*/i, '按爱意增量规划 Rose 送礼数量'],
      [/gift_execute\.py[\s\S]*/i, '测试环境私聊送礼（Rose）'],
      [/form_cp_love_chest_homepage[\s\S]*/i, '查询 CP 爱意宝箱主页'],
      [/mse_execute\.py[\s\S]*share-link-only[\s\S]*/i, '生成盘古配置分享链接，便于浏览器打开核对'],
      [/mse_execute\.py[\s\S]*/i, '从盘古读取爱意宝箱配置（各档门槛、奖励与跨档礼物）'],
      [/reward_verify\.py\s+snapshot[\s\S]*/i, '拍摄用户资产快照（钻石、背包、装扮、CP 勋章等）'],
      [/reward_verify\.py\s+diff[\s\S]*/i, '对比发奖前后资产差异'],
      [/reward_verify\.py\s+compare[\s\S]*/i, '对照期望清单验收发奖结果'],
      [/workflow_execute\.py\s+run\s+(\S+)[\s\S]*/i, '运行工作流 $1'],
      [/adb_execute\.py\s+tunnel\s+capture\s+run\s+(\S+)[\s\S]*/i, 'Tunnel 抓包验收：$1'],
      [/intimate_cp_form[\s\S]*/i, '结 CP 表单'],
    ];
    for (const [re, rep] of rules) {
      if (re.test(c)) return rep;
    }
    if (/^python3\s/m.test(c)) {
      return '执行本步自动化脚本';
    }
    if (/^mkdir\s+-p\s/m.test(c)) {
      return '创建本轮产物目录';
    }
    return humanizePlaybookProse(c);
  }

  function humanizePlaybookPersistLine(line) {
    const s = String(line || '').trim();
    if (/mse_config/i.test(s)) {
      return '将盘古配置保存到本轮产物目录，供后续对照';
    }
    if (/homepage_baseline/i.test(s)) {
      return '将宝箱主页起点数据保存到本轮产物目录';
    }
    if (/cp_love_chest_mse_config/i.test(s)) {
      return '将盘古配置保存到本地，供期望值与发奖验收对照';
    }
    if (/tier\d+_before/i.test(s) || /_before_/i.test(s)) {
      return '保存本档发奖前的资产快照文件';
    }
    if (/report_partial/i.test(s)) {
      return '汇总各档结论写入本轮报告';
    }
    if (/expected_t/i.test(s)) {
      return '整理各档期望奖励清单';
    }
    if (/diff_t/i.test(s)) {
      return '保存本档发奖前后差异对比结果';
    }
    return '将本步结果保存到本轮产物目录';
  }

  function humanizePlaybookInlineLabel(label) {
    let s = String(label || '').trim();
    if (!s) return '';
    s = s.replace(/^\d+[a-z]?\s+/i, '');
    return humanizePlaybookProse(s);
  }

  /** 将 registry 中单条 operation 转为可读短句 */
  function humanizePlaybookStepHint(text) {
    let s = String(text || '').trim();
    if (!s) return '';
    if (/^落盘\b/.test(s) || /^落盘\s+\.tmp/i.test(s)) {
      return humanizePlaybookPersistLine(s);
    }
    if (/^mkdir\s+-p\s/i.test(s)) {
      return '创建本轮产物目录';
    }
    const stepColon = s.match(/^(\d+[a-z]?)\s+(.+?[：:])\s*(.+)$/i);
    if (stepColon) {
      const subLabel = humanizePlaybookInlineLabel(stepColon[2].replace(/[：:]$/, ''));
      const tail = stepColon[3].trim();
      if (/^python3\s/m.test(tail)) {
        const action = humanizePlaybookCommand(tail);
        return subLabel ? `${subLabel}：${action}` : action;
      }
      const tailHuman = humanizePlaybookStepHint(tail);
      return subLabel ? `${subLabel}：${tailHuman}` : tailHuman;
    }
    const replacements = [
      [/^可选[：:]\s*/i, '（可选）'],
      [/从 tiers 整理各档 expected[^\s]*\.json[^。]*/i, '整理各档期望奖励清单，并与盘古配置交叉核对'],
      [/homepage[：:]\s*该档 status=0[^，]*currentLoveValue=threshold−1/i, '核对该档未达成，当前爱意值为「门槛减 1」'],
      [/homepage[：:]\s*该档 status=1、claimedTierId≥n/i, '核对该档已达成，且已领档位不低于本档'],
      [/双方发奖前 snapshot[^。]*/i, '双方分别拍摄发奖前资产快照'],
      [/双方发奖后 snapshot \+ diff[^。]*/i, '双方拍摄发奖后快照并对比差异'],
      [/跨档 \+1 钻[^。]*/i, '再送 1 钻 Rose 完成跨档'],
      [/sleep 3–5s/i, '等待 3～5 秒，让异步发奖完成'],
      [/记录 referenceTs[^。]*/i, '记录操作时间戳，便于查流水'],
      [/下一档[^。]*/i, '进入下一档，从本档门槛作为起点重复上述步骤'],
      [/可选 reward_verify compare expected[^\s]*\.json[^。]*/i, '（可选）对照期望清单验收；失败则停档排查'],
      [/汇总写入[^\s]*report_partial[^\s]*/i, '汇总写入本轮阶段性报告'],
      [/各档 diff 生成 Markdown[^。]*/i, '（可选）将各档差异整理为 Markdown 报告'],
      [/从 cpInfo\.userId 取[^\n]*/i, '从主页结果取出 CP 用户 ID，供后续快照使用'],
      [/tiers\[\]\.reward 可整理为 expected\.json[^。]*/i, '从各档奖励字段整理期望清单，并与盘古配置核对'],
      [/门槛与步骤 1 MSE 配置交叉核对/i, '各档门槛与盘古配置交叉核对'],
    ];
    for (const [re, rep] of replacements) {
      if (re.test(s)) {
        s = s.replace(re, rep);
        break;
      }
    }
    return humanizePlaybookProse(s);
  }

  function humanizePlaybookOperationLine(op) {
    const raw = String(op || '').trim();
    if (!raw) return '';
    const parts = splitPlaybookOperation(raw);
    if (parts.cmd) {
      const action = humanizePlaybookCommand(parts.cmd);
      const label = parts.label ? humanizePlaybookInlineLabel(parts.label) : '';
      if (label && action) return `${label}：${action}`;
      return action;
    }
    if (parts.hint) return humanizePlaybookStepHint(parts.hint);
    if (parts.label) return humanizePlaybookStepHint(parts.label);
    return humanizePlaybookStepHint(raw);
  }

  function splitPlaybookOperation(op) {
    const raw = String(op || '').trim();
    if (!raw) return { label: '', cmd: '', hint: '' };
    if (/^python3\s/m.test(raw) || /^mkdir\s+-p\s/m.test(raw)) {
      return { label: '', cmd: raw, hint: '' };
    }
    const colonMatch = raw.match(/^(.+?[：:])\s*(.+)$/);
    if (colonMatch) {
      const before = colonMatch[1].replace(/[：:]$/, '').trim();
      const after = colonMatch[2].trim();
      const stepPrefix = before.match(/^(\d+[a-z]?)\s*(.+)$/i);
      const label = stepPrefix ? stepPrefix[2].trim() : before;
      if (/^python3\s/m.test(after) || /^mkdir\s/m.test(after)) {
        return { label, cmd: after, hint: '' };
      }
      return { label: '', cmd: '', hint: raw };
    }
    return { label: '', cmd: '', hint: raw };
  }

  function collectPlaybookStepOps(step) {
    const hints = [];
    const cmd = String(step.command || '').trim();
    if (cmd) hints.push(humanizePlaybookCommand(cmd));
    for (const op of step.operations || []) {
      const line = humanizePlaybookOperationLine(op);
      if (line) hints.push(line);
    }
    return { hints };
  }

  function smallIcon(name) {
    const icons = {
      module: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M4 5h7v7H4zM13 5h7v7h-7zM4 14h7v5H4zM13 14h7v5h-7z"/></svg>',
      spark: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M12 3l1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>',
      play: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>',
    };
    return icons[name] || icons.spark;
  }

  function assemblePromptLine(lineEl) {
    let result = '';
    lineEl.querySelector('.prompt-text').childNodes.forEach(node => {
      if (node.nodeType === Node.TEXT_NODE) {
        result += node.textContent;
      } else if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('prompt-field')) {
        const val = node.value.trim();
        const key = node.getAttribute('data-key') || node.placeholder;
        result += val || ('<' + key + '>');
      }
    });
    return result;
  }

  function newFolderId() {
    return `nav-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  }

  let navDialogFinish = null;
  let navDialogKeyHandler = null;

  function navDialogRefs() {
    return {
      modal: document.getElementById('catalog-nav-dialog-modal'),
      title: document.getElementById('catalog-nav-dialog-title'),
      message: document.getElementById('catalog-nav-dialog-message'),
      input: document.getElementById('catalog-nav-dialog-input'),
      sourceRow: document.getElementById('catalog-nav-dialog-source'),
      sourceSelect: document.getElementById('catalog-nav-dialog-source-select'),
      cancel: document.getElementById('catalog-nav-dialog-cancel'),
      submit: document.getElementById('catalog-nav-dialog-submit'),
    };
  }

  function hideNavDialogSource(refs) {
    if (refs?.sourceRow) refs.sourceRow.hidden = true;
    if (refs?.sourceSelect) {
      refs.sourceSelect.innerHTML = '';
      refs.sourceSelect.onchange = null;
    }
  }

  function finishNavDialog(value) {
    const finish = navDialogFinish;
    navDialogFinish = null;
    const refs = navDialogRefs();
    if (navDialogKeyHandler) {
      document.removeEventListener('keydown', navDialogKeyHandler);
      navDialogKeyHandler = null;
    }
    hideNavDialogSource(refs);
    if (refs.modal) {
      refs.modal.classList.remove('open');
      window.setTimeout(() => {
        if (refs.modal) refs.modal.hidden = true;
      }, 200);
    }
    if (finish) finish(value);
  }

  function openNavDialogShell() {
    const refs = navDialogRefs();
    if (!refs.modal) return refs;
    refs.modal.hidden = false;
    requestAnimationFrame(() => refs.modal.classList.add('open'));
    return refs;
  }

  function openNavTextPrompt(title, defaultValue) {
    const refs = navDialogRefs();
    if (!refs.modal) {
      return Promise.resolve(window.prompt(title, defaultValue || ''));
    }
    return new Promise((resolve) => {
      navDialogFinish = resolve;
      refs.title.textContent = title;
      refs.message.hidden = true;
      refs.message.textContent = '';
      hideNavDialogSource(refs);
      refs.input.hidden = false;
      refs.input.value = defaultValue || '';
      refs.cancel.hidden = false;
      refs.submit.textContent = '确定';
      refs.cancel.onclick = () => finishNavDialog(null);
      refs.submit.onclick = () => finishNavDialog(refs.input.value);
      refs.modal.onclick = (event) => {
        if (event.target === refs.modal) finishNavDialog(null);
      };
      navDialogKeyHandler = (event) => {
        if (event.key === 'Escape') finishNavDialog(null);
        if (event.key === 'Enter' && !refs.input.hidden) {
          event.preventDefault();
          finishNavDialog(refs.input.value);
        }
      };
      document.addEventListener('keydown', navDialogKeyHandler);
      openNavDialogShell();
      refs.input.focus();
      refs.input.select();
    });
  }

  function openNavAddCapabilityPrompt(opts) {
    const options = opts || {};
    const title = options.title || '新能力名称';
    const sources = Array.isArray(options.sources) ? options.sources : [];
    const refs = navDialogRefs();
    if (!refs.modal || !sources.length) {
      const name = window.prompt(title, options.defaultValue || '');
      if (name == null) return Promise.resolve(null);
      const sid = String(options.defaultSourceId || sources[0]?.id || '').trim();
      if (!sid) return Promise.resolve(null);
      return Promise.resolve({ name, sourceId: sid });
    }
    let selectedId = String(options.defaultSourceId || sources[0].id || '').trim();
    if (!sources.some((s) => s.id === selectedId)) selectedId = String(sources[0].id || '').trim();

    const paintSourceSelect = () => {
      if (!refs.sourceSelect) return;
      refs.sourceSelect.innerHTML = sources.map((src) => {
        const id = escapeAttr(String(src.id || ''));
        const label = escapeHtml(String(src.label || src.id || ''));
        const sel = src.id === selectedId ? ' selected' : '';
        return `<option value="${id}"${sel}>${label}</option>`;
      }).join('');
    };

    const submitAddCap = () => {
      const name = String(refs.input.value || '').trim();
      if (!name) return;
      const sourceId = String(refs.sourceSelect?.value || selectedId || '').trim();
      if (!sourceId) return;
      finishNavDialog({ name, sourceId });
    };

    return new Promise((resolve) => {
      navDialogFinish = resolve;
      refs.title.textContent = title;
      refs.message.hidden = true;
      refs.message.textContent = '';
      refs.input.hidden = false;
      refs.input.value = options.defaultValue || '';
      if (refs.sourceRow) refs.sourceRow.hidden = false;
      paintSourceSelect();
      if (refs.sourceSelect) {
        refs.sourceSelect.onchange = () => {
          selectedId = refs.sourceSelect.value || '';
        };
      }
      refs.cancel.hidden = false;
      refs.submit.textContent = '确定';
      refs.cancel.onclick = () => finishNavDialog(null);
      refs.submit.onclick = () => submitAddCap();
      refs.modal.onclick = (event) => {
        if (event.target === refs.modal) finishNavDialog(null);
      };
      navDialogKeyHandler = (event) => {
        if (event.key === 'Escape') finishNavDialog(null);
        if (event.key === 'Enter' && !refs.input.hidden) {
          event.preventDefault();
          submitAddCap();
        }
      };
      document.addEventListener('keydown', navDialogKeyHandler);
      openNavDialogShell();
      refs.input.focus();
    });
  }

  function openNavConfirm(message) {
    const refs = navDialogRefs();
    if (!refs.modal) return Promise.resolve(window.confirm(message));
    return new Promise((resolve) => {
      navDialogFinish = (value) => resolve(!!value);
      refs.title.textContent = '请确认';
      refs.message.hidden = false;
      refs.message.textContent = message;
      hideNavDialogSource(refs);
      refs.input.hidden = true;
      refs.cancel.hidden = false;
      refs.submit.textContent = '确定';
      refs.cancel.onclick = () => finishNavDialog(false);
      refs.submit.onclick = () => finishNavDialog(true);
      refs.modal.onclick = (event) => {
        if (event.target === refs.modal) finishNavDialog(false);
      };
      navDialogKeyHandler = (event) => {
        if (event.key === 'Escape') finishNavDialog(false);
      };
      document.addEventListener('keydown', navDialogKeyHandler);
      openNavDialogShell();
      refs.submit.focus();
    });
  }

  function openNavAlert(message) {
    const refs = navDialogRefs();
    if (!refs.modal) {
      window.alert(message);
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      navDialogFinish = () => resolve();
      refs.title.textContent = '提示';
      refs.message.hidden = false;
      refs.message.textContent = message;
      hideNavDialogSource(refs);
      refs.input.hidden = true;
      refs.cancel.hidden = true;
      refs.submit.textContent = '好';
      refs.submit.onclick = () => finishNavDialog();
      refs.modal.onclick = (event) => {
        if (event.target === refs.modal) finishNavDialog();
      };
      navDialogKeyHandler = (event) => {
        if (event.key === 'Escape' || event.key === 'Enter') finishNavDialog();
      };
      document.addEventListener('keydown', navDialogKeyHandler);
      openNavDialogShell();
      refs.submit.focus();
    });
  }

  function navFolderIconSvg(expanded) {
    const svgOpen = `<svg class="nav-folder-svg" viewBox="0 0 18 16" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M2 6.2h5.4l1.35 1.85h7.25v1.1L14.2 14H2V6.2z"/>
      <path d="M2 6.2V4.8c0-.66.54-1.2 1.2-1.2h3.9l1.15 1.45"/>
    </svg>`;
    const svgClosed = `<svg class="nav-folder-svg" viewBox="0 0 18 16" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M2.5 5.1h4.85l1.15 1.55h7.5v6.85H2.5V5.1z"/>
      <path d="M2.5 5.1V4.35c0-.47.38-.85.85-.85h3.55l1 .75"/>
      <path d="M7.2 10.1h3.6"/>
    </svg>`;
    return expanded ? svgOpen : svgClosed;
  }

  function navCapInterfaceIconSvg() {
    return `<svg class="nav-cap-if-svg" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linejoin="round" aria-hidden="true">
      <rect x="2.25" y="2.25" width="11.5" height="11.5" rx="1"/>
      <path d="M2.25 6.25h11.5M2.25 10.25h11.5"/>
    </svg>`;
  }

  function navCatalogListIconSvg() {
    return `<svg class="nav-all-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>
    </svg>`;
  }

  function navCategoryKey(moduleId, catIndex) {
    return `cat:${moduleId}:${catIndex}`;
  }

  function collapseNavDisplayLabel(text) {
    return String(text || '').replace(/\s+/g, ' ').trim();
  }

  function parseNavCategoryKey(key) {
    if (!key || !key.startsWith('cat:')) return null;
    const rest = key.slice(4);
    const sep = rest.lastIndexOf(':');
    if (sep <= 0) return null;
    const moduleId = rest.slice(0, sep);
    const catIndex = Number.parseInt(rest.slice(sep + 1), 10);
    if (!moduleId || Number.isNaN(catIndex)) return null;
    return { moduleId, catIndex };
  }

  function navPlaybookItemKey(playbookId) {
    return `pbi:${playbookId}`;
  }

  function navPbStepKey(playbookId, stepOrder) {
    return `pbs:${playbookId}:${stepOrder}`;
  }

  function parseNavPbStepKey(key) {
    if (!key || !key.startsWith('pbs:')) return null;
    const rest = key.slice(4);
    const sep = rest.indexOf(':');
    if (sep <= 0) return null;
    const playbookId = rest.slice(0, sep);
    const stepOrder = Number.parseInt(rest.slice(sep + 1), 10);
    if (!playbookId || Number.isNaN(stepOrder)) return null;
    return { playbookId, stepOrder };
  }

  function parseNavPlaybookItemKey(key) {
    if (!key || !key.startsWith('pbi:')) return null;
    const playbookId = key.slice(4).trim();
    return playbookId ? { playbookId } : null;
  }

  function navChevronSvg(collapsed) {
    if (collapsed) {
      return `<svg class="nav-chevron-svg" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.25 2.25 8 6l-3.75 3.75"/></svg>`;
    }
    return `<svg class="nav-chevron-svg" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.25 4.25 6 8l3.75-3.75"/></svg>`;
  }

  function defaultNavTree(data) {
    const tree = [{ kind: 'all' }];
    for (const mod of data?.modules || []) {
      if (mod?.id) tree.push({ kind: 'module', moduleId: mod.id });
    }
    return tree;
  }

  function CatalogPanel(options) {
    this.onRunPrompt = options.onRunPrompt || function () {};
    this.root = options.root;
    this.searchEl = options.searchEl;
    this.navEl = options.navEl;
    this.mainEl = options.mainEl;
    this.envCheckBtn = options.envCheckBtn || null;
    this.canEditNav = !!options.canEditNav;
    this.canDeleteNav = !!options.canDeleteNav;
    this.saveNav = options.saveNav || null;
    this.savePrompt = options.savePrompt || null;
    this.onPromptsSaved = options.onPromptsSaved || null;
    this.DATA = null;
    this.activeKey = 'all';
    this.navTree = [];
    this.collapsed = new Set();
    this.capExpanded = new Set();
    this.query = '';
    this._navMenuEl = null;
    this._navMenuTarget = null;
    this._promptMenuEl = null;
    this._promptMenuTarget = null;
    this._promptEditTarget = null;
    this._promptEditBound = false;
    this._promptMenuDocBound = false;
    this._dragNodePath = null;
    this._navDragActive = false;
    this._pendingNavMove = null;
  }

  CatalogPanel.prototype.load = async function load(fetchData, opts) {
    const preserveNavUi = !!(opts && opts.preserveNavUi);
    const prevActiveKey = this.activeKey;
    const prevQuery = this.query;
    const prevCollapsed = preserveNavUi ? new Set(this.collapsed) : null;

    this.DATA = typeof fetchData === 'function' ? await fetchData() : fetchData;
    if (this.envCheckBtn) {
      const envCfg = this.DATA.env_check || {};
      if (envCfg.label) this.envCheckBtn.textContent = envCfg.label;
      this.envCheckBtn.onclick = () => {
        this.onRunPrompt(envCfg.prompt || '@新手上手.md 运行环境检查');
      };
    }
    const nav = this.DATA?.nav;
    this.navTree = Array.isArray(nav?.tree) && nav.tree.length
      ? JSON.parse(JSON.stringify(nav.tree))
      : defaultNavTree(this.DATA);
    this.ensureFolderChildren(this.navTree);
    this.hydrateNavCaps(this.navTree);
    this.hydrateNavPlaybooks(this.navTree);
    this.removeEmptyDuplicateFolders();
    this.sortNavTreeChildOrder(this.navTree);
    const resetNavCollapse = !!(opts && opts.resetNavCollapse);
    if (preserveNavUi) {
      this.snapshotCapExpandedFromDom();
      this.activeKey = prevActiveKey;
      this.query = prevQuery;
      if (resetNavCollapse) this.resetNavCollapsedAll();
      else this.collapsed = prevCollapsed || new Set();
      if (this.searchEl) this.searchEl.value = prevQuery;
    } else if (resetNavCollapse) {
      this.resetNavCollapsedAll();
    } else {
      this.restoreNavCollapsed();
    }
    if (!preserveNavUi) this.capExpanded = new Set();
    this.renderNav();
    this.render();
  };

  CatalogPanel.prototype.reload = async function reload(fetchData, opts) {
    await this.load(fetchData, { preserveNavUi: true, ...(opts || {}) });
  };

  CatalogPanel.prototype.navCollapseKey = function navCollapseKey(node) {
    if (!node) return '';
    if (node.kind === 'folder') return String(node.id || '');
    if (node.kind === 'module') return `module:${node.moduleId}`;
    if (node.kind === 'playbook') return 'playbook';
    if (node.kind === 'playbookItem') return navPlaybookItemKey(node.playbookId);
    return '';
  };

  CatalogPanel.prototype.isNavContainer = function isNavContainer(node) {
    return !!node && (
      node.kind === 'folder'
      || node.kind === 'module'
      || node.kind === 'playbook'
    );
  };

  CatalogPanel.prototype.hasFolderChildren = function hasFolderChildren(node) {
    return (node?.children || []).some((child) => child && child.kind === 'folder');
  };

  CatalogPanel.prototype.navRowIsBranch = function navRowIsBranch(node) {
    if (!this.isNavContainer(node)) return false;
    if (node.kind === 'folder' || node.kind === 'module' || node.kind === 'playbook') {
      return true;
    }
    return this.hasFolderChildren(node);
  };

  CatalogPanel.prototype.navRowShowsFolderIcon = function navRowShowsFolderIcon(node) {
    if (!node) return false;
    return node.kind === 'folder'
      || node.kind === 'module'
      || node.kind === 'playbook';
  };

  CatalogPanel.prototype.navNodeDepth = function navNodeDepth(nodePath) {
    if (!nodePath || !nodePath.length) return 0;
    let depth = 0;
    for (const seg of nodePath) {
      if (seg === 'children') depth += 1;
    }
    return depth;
  };

  CatalogPanel.prototype.navNodeSupportsRename = function navNodeSupportsRename(node, depth) {
    if (!node) return false;
    if (node.kind === 'cap' || node.kind === 'pbStep' || node.kind === 'folder' || node.kind === 'playbookItem') {
      return true;
    }
    return depth === 0 && (node.kind === 'module' || node.kind === 'playbook');
  };

  CatalogPanel.prototype.navNodeSupportsDelete = function navNodeSupportsDelete(node, depth) {
    if (!node) return false;
    if (node.kind === 'folder') return true;
    return depth === 0 && (node.kind === 'module' || node.kind === 'playbook');
  };

  CatalogPanel.prototype.collectNavCollapseKeys = function collectNavCollapseKeys(nodes, depth) {
    const keys = [];
    const d = depth ?? 0;
    (nodes || []).forEach((node) => {
      if (this.navRowIsBranch(node)) {
        const ck = this.navCollapseKey(node);
        if (ck) keys.push(ck);
      }
      if (this.isNavContainer(node)) {
        keys.push(...this.collectNavCollapseKeys(node.children || [], d + 1));
      }
    });
    return keys;
  };

  CatalogPanel.prototype.resetNavCollapsedAll = function resetNavCollapsedAll() {
    this.collapsed = new Set(this.collectNavCollapseKeys(this.navTree, 0));
  };

  CatalogPanel.prototype.restoreNavCollapsed = function restoreNavCollapsed() {
    const allKeys = this.collectNavCollapseKeys(this.navTree, 0);
    const stored = readLsStringSet(NAV_COLLAPSED_LS_KEY);
    if (!stored) {
      this.collapsed = new Set(allKeys);
      return;
    }
    this.collapsed = new Set(allKeys.filter((k) => stored.has(k)));
  };

  CatalogPanel.prototype.persistNavCollapsed = function persistNavCollapsed() {
    writeLsStringSet(NAV_COLLAPSED_LS_KEY, this.collapsed);
  };

  CatalogPanel.prototype.capRegistryKey = function capRegistryKey(sourceId, registryId) {
    const sid = String(sourceId || '').trim();
    const rid = String(registryId || '').trim();
    if (!sid || !rid) return '';
    return `reg:${sid}:${rid}`;
  };

  CatalogPanel.prototype.capItemKey = function capItemKey(item, moduleId, catIndex) {
    const regKey = this.capRegistryKey(item?.source_id, item?.registry_id);
    if (regKey) return regKey;
    const sid = String(item?.source_id || '').trim();
    const name = String(item?.name || '').trim();
    return `${moduleId}:${catIndex}:${sid || name}`;
  };

  /** 刷新前列表仍可见时，用 DOM 同步展开态（避免 registry 刷新后 catIndex 变化丢状态） */
  CatalogPanel.prototype.snapshotCapExpandedFromDom = function snapshotCapExpandedFromDom() {
    const root = this.mainEl;
    if (!root) return;
    root.querySelectorAll('.cap[data-registry-id][data-source-id]').forEach((cap) => {
      const key = this.capRegistryKey(
        cap.getAttribute('data-source-id'),
        cap.getAttribute('data-registry-id'),
      );
      if (!key) return;
      const head = cap.querySelector('.cap-head.is-toggle');
      if (!head) return;
      if (head.getAttribute('aria-expanded') === 'true') this.capExpanded.add(key);
      else this.capExpanded.delete(key);
    });
  };

  CatalogPanel.prototype.collectCapKeysInTree = function collectCapKeysInTree(nodes, out) {
    const set = out || new Set();
    (nodes || []).forEach((node) => {
      if (!node || typeof node !== 'object') return;
      if (node.kind === 'cap') set.add(navCategoryKey(node.moduleId, node.catIndex));
      if (Array.isArray(node.children)) this.collectCapKeysInTree(node.children, set);
    });
    return set;
  };

  CatalogPanel.prototype.hydrateNavCaps = function hydrateNavCaps(nodes) {
    const placed = this.collectCapKeysInTree(this.navTree);
    (nodes || []).forEach((node) => {
      if (!node || typeof node !== 'object') return;
      if (node.kind === 'module' && node.moduleId) {
        if (!Array.isArray(node.children)) node.children = [];
        const mod = this.moduleById(node.moduleId);
        (mod?.categories || []).forEach((cat, catIndex) => {
          const key = navCategoryKey(node.moduleId, catIndex);
          if (placed.has(key)) return;
          node.children.push({ kind: 'cap', moduleId: node.moduleId, catIndex });
          placed.add(key);
        });
      }
      if (Array.isArray(node.children)) this.hydrateNavCaps(node.children);
    });
  };

  function normalizeWorkflowFolderLabel(label) {
    return String(label || '').trim().replace(/[·•]/g, '');
  }

  CatalogPanel.prototype.collectPlaybookIdsInTree = function collectPlaybookIdsInTree(nodes, out) {
    const set = out || new Set();
    (nodes || []).forEach((node) => {
      if (!node || typeof node !== 'object') return;
      if (node.kind === 'playbookItem') {
        const pid = String(node.playbookId || '').trim();
        if (pid) set.add(pid);
      }
      if (Array.isArray(node.children)) this.collectPlaybookIdsInTree(node.children, set);
    });
    return set;
  };

  CatalogPanel.prototype.findWorkflowRootFolder = function findWorkflowRootFolder(nodes) {
    for (const node of nodes || []) {
      if (!node || node.kind !== 'folder') continue;
      const label = String(node.label || '').trim();
      if (label === '工作流') return node;
    }
    return null;
  };

  CatalogPanel.prototype.findWorkflowSubfolder = function findWorkflowSubfolder(workflowRoot, categoryLabel) {
    const want = normalizeWorkflowFolderLabel(categoryLabel || '未分组') || '未分组';
    for (const child of workflowRoot.children || []) {
      if (!child || child.kind !== 'folder') continue;
      if (normalizeWorkflowFolderLabel(child.label) === want) return child;
    }
    return null;
  };

  CatalogPanel.prototype.ensureWorkflowSubfolder = function ensureWorkflowSubfolder(workflowRoot, categoryLabel) {
    const label = normalizeWorkflowFolderLabel(categoryLabel || '未分组') || '未分组';
    let folder = this.findWorkflowSubfolder(workflowRoot, label);
    if (folder) return folder;
    if (!Array.isArray(workflowRoot.children)) workflowRoot.children = [];
    folder = {
      kind: 'folder',
      id: newFolderId(),
      label,
      children: [],
      subfolder: true,
    };
    workflowRoot.children.push(folder);
    return folder;
  };

  CatalogPanel.prototype.hydrateNavPlaybooks = function hydrateNavPlaybooks(nodes) {
    (nodes || []).forEach((node) => {
      if (!node || typeof node !== 'object') return;
      if (node.kind === 'playbookItem' && Array.isArray(node.children)) {
        node.children = node.children.filter((c) => c && c.kind !== 'pbStep');
      }
      if (Array.isArray(node.children)) this.hydrateNavPlaybooks(node.children);
    });

    const placed = this.collectPlaybookIdsInTree(this.navTree);
    const workflowRoot = this.findWorkflowRootFolder(this.navTree);
    if (!workflowRoot) return;

    for (const pb of this.DATA?.playbooks || []) {
      const pid = String(pb?.id || '').trim();
      if (!pid || placed.has(pid)) continue;
      const folder = this.ensureWorkflowSubfolder(workflowRoot, pb.category || '未分组');
      if (!Array.isArray(folder.children)) folder.children = [];
      folder.children.push({ kind: 'playbookItem', playbookId: pid });
      placed.add(pid);
    }
  };

  CatalogPanel.prototype.navTreeRootSiblings = function navTreeRootSiblings() {
    return (this.navTree || []).filter((node) => node && node.kind !== 'all');
  };

  CatalogPanel.prototype.navAllCount = function navAllCount() {
    let sum = 0;
    for (const node of this.navTreeRootSiblings()) {
      sum += this.navNodeCount(node);
    }
    return sum;
  };

  CatalogPanel.prototype.navSiblingSortRank = function navSiblingSortRank(node) {
    if (!node) return 2;
    if (node.kind === 'folder') return 0;
    if (node.kind === 'cap' || node.kind === 'pbStep' || node.kind === 'playbookItem') return 1;
    return 0;
  };

  CatalogPanel.prototype.sortNavContainerChildren = function sortNavContainerChildren(node) {
    if (!node || !this.isNavContainer(node) || !Array.isArray(node.children)) return;
    const children = node.children;
    if (children.length < 2) return;
    const tagged = children.map((child, index) => ({ child, index }));
    tagged.sort((a, b) => {
      const ra = this.navSiblingSortRank(a.child);
      const rb = this.navSiblingSortRank(b.child);
      if (ra !== rb) return ra - rb;
      return a.index - b.index;
    });
    node.children = tagged.map((entry) => entry.child);
  };

  CatalogPanel.prototype.sortNavTreeChildOrder = function sortNavTreeChildOrder(nodes) {
    (nodes || []).forEach((node) => {
      if (!node || typeof node !== 'object') return;
      if (this.isNavContainer(node)) {
        this.sortNavContainerChildren(node);
        this.sortNavTreeChildOrder(node.children);
      }
    });
  };

  CatalogPanel.prototype.ensureFolderChildren = function ensureFolderChildren(nodes, atRoot) {
    if (atRoot === undefined) atRoot = true;
    (nodes || []).forEach((node) => {
      if (!node || typeof node !== 'object') return;
      if (node.kind === 'folder' && !atRoot) node.subfolder = true;
      if (this.isNavContainer(node)) {
        if (!Array.isArray(node.children)) node.children = [];
        this.ensureFolderChildren(node.children, false);
      }
    });
  };

  CatalogPanel.prototype.expandNavAncestors = function expandNavAncestors(itemPath) {
    if (!itemPath || !itemPath.length) return;
    let cur = this.navTree;
    for (let i = 0; i < itemPath.length; i += 1) {
      const seg = itemPath[i];
      if (seg === 'children') {
        cur = cur.children;
        continue;
      }
      if (!Array.isArray(cur) || typeof seg !== 'number') continue;
      const node = cur[seg];
      const ck = this.navCollapseKey(node);
      if (ck) this.collapsed.delete(ck);
      cur = node;
    }
    this.persistNavCollapsed();
  };

  CatalogPanel.prototype.scrollNavRowIntoView = function scrollNavRowIntoView(key) {
    if (!this.navEl || !key) return;
    const row = this.navEl.querySelector(`.nav-row[data-nav-key="${CSS.escape(key)}"]`);
    if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };

  CatalogPanel.prototype.setCanEditNav = function setCanEditNav(canEdit) {
    this.canEditNav = !!canEdit;
    this.renderNav();
  };

  CatalogPanel.prototype.setCanDeleteNav = function setCanDeleteNav(canDelete) {
    this.canDeleteNav = !!canDelete;
    this.renderNav();
  };

  CatalogPanel.prototype.moduleById = function moduleById(moduleId) {
    return (this.DATA?.modules || []).find((mod) => mod.id === moduleId) || null;
  };

  CatalogPanel.prototype.playbookCount = function playbookCount() {
    return (this.DATA?.playbooks || []).length;
  };

  CatalogPanel.prototype.playbookById = function playbookById(playbookId) {
    const id = String(playbookId || '').trim();
    if (!id) return null;
    return (this.DATA?.playbooks || []).find((pb) => pb.id === id) || null;
  };

  CatalogPanel.prototype.playbookStepByOrder = function playbookStepByOrder(playbookId, stepOrder) {
    const pb = this.playbookById(playbookId);
    const order = Number(stepOrder);
    if (!pb || Number.isNaN(order)) return null;
    return (pb.steps || []).find((step) => Number(step.order) === order) || null;
  };

  CatalogPanel.prototype.navNodeKey = function navNodeKey(node) {
    if (!node || !node.kind) return '';
    if (node.kind === 'all') return 'all';
    if (node.kind === 'playbook') return 'playbook';
    if (node.kind === 'module') return `module:${node.moduleId}`;
    if (node.kind === 'folder') return `folder:${node.id}`;
    if (node.kind === 'cap') return navCategoryKey(node.moduleId, node.catIndex);
    if (node.kind === 'playbookItem') return navPlaybookItemKey(node.playbookId);
    if (node.kind === 'pbStep') return navPbStepKey(node.playbookId, node.stepOrder);
    return '';
  };

  CatalogPanel.prototype.navNodeLabel = function navNodeLabel(node) {
    if (!node) return '';
    if (node.kind === 'all') return '全部';
    if (node.kind === 'playbook') {
      const custom = String(node.navLabel || '').trim();
      return custom || 'Playbook';
    }
    if (node.kind === 'module') {
      const custom = String(node.navLabel || '').trim();
      if (custom) return custom;
      const mod = this.moduleById(node.moduleId);
      return mod?.label || node.moduleId || '';
    }
    if (node.kind === 'folder') return node.label || '分组';
    if (node.kind === 'cap') {
      const custom = collapseNavDisplayLabel(node.label);
      if (custom) return custom;
      const mod = this.moduleById(node.moduleId);
      const cat = mod?.categories?.[node.catIndex];
      return collapseNavDisplayLabel(cat?.name) || '能力接口';
    }
    if (node.kind === 'playbookItem') {
      const custom = String(node.navLabel || '').trim();
      if (custom) return custom;
      const pb = this.playbookById(node.playbookId);
      return pb?.title || node.playbookId || '工作流';
    }
    if (node.kind === 'pbStep') {
      const custom = collapseNavDisplayLabel(node.label);
      if (custom) return custom;
      const step = this.playbookStepByOrder(node.playbookId, node.stepOrder);
      return collapseNavDisplayLabel(step?.workflowName || step?.note) || `步骤 ${node.stepOrder}`;
    }
    return '';
  };

  CatalogPanel.prototype.capItemCount = function capItemCount(node) {
    if (!node || node.kind !== 'cap') return 0;
    const mod = this.moduleById(node.moduleId);
    const cat = mod?.categories?.[node.catIndex];
    return (cat?.items || []).length;
  };

  CatalogPanel.prototype.navNodeCount = function navNodeCount(node) {
    if (!node) return 0;
    if (node.kind === 'all') return this.navAllCount();
    if (node.kind === 'playbook') return this.playbookCount();
    if (node.kind === 'cap') return this.capItemCount(node);
    if (node.kind === 'playbookItem') {
      const pb = this.playbookById(node.playbookId);
      return (pb?.steps || []).length;
    }
    if (node.kind === 'pbStep') {
      const step = this.playbookStepByOrder(node.playbookId, node.stepOrder);
      return (step?.prompts || []).length;
    }
    if (node.kind === 'module' || node.kind === 'folder') {
      let sum = 0;
      for (const child of node.children || []) sum += this.navNodeCount(child);
      return sum;
    }
    return 0;
  };

  CatalogPanel.prototype.collectCapsInSubtree = function collectCapsInSubtree(node, out) {
    const list = out || [];
    if (!node) return list;
    const walk = (n) => {
      if (!n || typeof n !== 'object') return;
      if (n.kind === 'cap') list.push(n);
      (n.children || []).forEach(walk);
    };
    walk(node);
    return list;
  };

  CatalogPanel.prototype.findNavNodeByKey = function findNavNodeByKey(key) {
    const path = this.findNodePath(key);
    return path ? this.getNodeAtPath(path) : null;
  };

  CatalogPanel.prototype.collectModuleIds = function collectModuleIds(node) {
    const ids = new Set();
    if (!node) return ids;
    if (node.kind === 'module' && node.moduleId) ids.add(node.moduleId);
    if (node.kind === 'folder' || node.kind === 'module' || node.kind === 'playbook') {
      for (const child of node.children || []) {
        this.collectModuleIds(child).forEach((id) => ids.add(id));
      }
    }
    return ids;
  };

  CatalogPanel.prototype.activeFilter = function activeFilter() {
    const key = this.activeKey || 'all';
    if (key === 'all') return { mode: 'all' };
    if (key === 'playbook') return { mode: 'playbook' };
    if (key.startsWith('module:')) {
      const node = this.findNavNodeByKey(key);
      if (node) {
        return {
          mode: 'navScope',
          node,
          title: this.navNodeLabel(node),
          icon: 'module',
        };
      }
      return { mode: 'modules', moduleIds: new Set([key.slice(7)]) };
    }
    if (key.startsWith('folder:')) {
      const node = this.findNavNodeByKey(key);
      if (node) {
        return {
          mode: 'navScope',
          node,
          title: this.navNodeLabel(node),
          icon: 'module',
        };
      }
      const folderId = key.slice(7);
      const folder = this.findFolderById(folderId);
      const moduleIds = folder ? this.collectModuleIds(folder) : new Set();
      return { mode: 'modules', moduleIds };
    }
    const cat = parseNavCategoryKey(key);
    if (cat) return { mode: 'category', moduleId: cat.moduleId, catIndex: cat.catIndex };
    const pbi = parseNavPlaybookItemKey(key);
    if (pbi) {
      return { mode: 'playbookItem', playbookId: pbi.playbookId, node: this.findNavNodeByKey(key) };
    }
    const pbs = parseNavPbStepKey(key);
    if (pbs) {
      return {
        mode: 'playbookStep',
        playbookId: pbs.playbookId,
        stepOrder: pbs.stepOrder,
        node: this.findNavNodeByKey(key),
      };
    }
    return { mode: 'all' };
  };

  CatalogPanel.prototype.findFolderById = function findFolderById(folderId, nodes) {
    const list = nodes || this.navTree;
    for (const node of list) {
      if (node.kind === 'folder' && node.id === folderId) return node;
      if (this.isNavContainer(node)) {
        const nested = this.findFolderById(folderId, node.children || []);
        if (nested) return nested;
      }
    }
    return null;
  };

  CatalogPanel.prototype.findNodePath = function findNodePath(key, nodes, prefix) {
    const list = nodes || this.navTree;
    const pathPrefix = prefix || [];
    for (let i = 0; i < list.length; i += 1) {
      const node = list[i];
      const nodeKey = this.navNodeKey(node);
      if (nodeKey === key) return pathPrefix.concat(i);
      if (Array.isArray(node.children) && node.children.length) {
        const nested = this.findNodePath(key, node.children, pathPrefix.concat([i, 'children']));
        if (nested) return nested;
      }
    }
    return null;
  };

  CatalogPanel.prototype.getNodeAtPath = function getNodeAtPath(path) {
    let cur = this.navTree;
    for (let i = 0; i < path.length; i += 1) {
      const seg = path[i];
      if (seg === 'children') cur = cur.children;
      else cur = Array.isArray(cur) ? cur[seg] : null;
    }
    return cur || null;
  };

  CatalogPanel.prototype.getParentListForPath = function getParentListForPath(path) {
    if (!path || !path.length) return this.navTree;
    if (path.length === 1) return this.navTree;
    let cur = this.navTree;
    for (let i = 0; i < path.length - 1; i += 1) {
      const seg = path[i];
      if (seg === 'children') cur = cur.children;
      else cur = Array.isArray(cur) ? cur[seg] : null;
    }
    return Array.isArray(cur) ? cur : this.navTree;
  };

  CatalogPanel.prototype.folderPathFromKey = function folderPathFromKey(folderKey) {
    if (!folderKey.startsWith('folder:')) return null;
    return this.findNodePath(folderKey);
  };

  /** renderNavNodes 的 data-path-key → getNodeAtPath 路径（避免同 folder id 时 findNodePath 命中首项） */
  CatalogPanel.prototype.itemPathFromPathKey = function itemPathFromPathKey(pathKey) {
    if (!pathKey || pathKey === 'r') return null;
    const parts = String(pathKey).split(':');
    if (parts[0] !== 'r') return null;
    const path = [];
    for (let i = 1; i < parts.length; ) {
      if (parts[i] === 'c') {
        path.push('children');
        i += 1;
        continue;
      }
      const idx = Number.parseInt(parts[i], 10);
      if (Number.isNaN(idx)) return null;
      path.push(idx);
      i += 1;
    }
    return path.length ? path : null;
  };

  CatalogPanel.prototype.navItemPathFromRow = function navItemPathFromRow(row) {
    if (!row) return null;
    const pathKey = row.getAttribute('data-path-key') || '';
    const fromPathKey = this.itemPathFromPathKey(pathKey);
    if (fromPathKey && this.getNodeAtPath(fromPathKey)) return fromPathKey;
    const key = row.getAttribute('data-nav-key') || '';
    return key ? this.findNodePath(key) : null;
  };

  /** 同 id 的空分组壳（拖拽误删/重复写入）清理，保留有内容的那棵 */
  CatalogPanel.prototype.removeEmptyDuplicateFolders = function removeEmptyDuplicateFolders() {
    const byId = new Map();
    const collect = (nodes, path) => {
      (nodes || []).forEach((node, i) => {
        const p = path.concat(i);
        if (node?.kind === 'folder') {
          const id = String(node.id || '').trim();
          if (id) {
            if (!byId.has(id)) byId.set(id, []);
            byId.get(id).push({
              path: p,
              empty: this.navNodeCount(node) === 0,
            });
          }
        }
        if (Array.isArray(node?.children)) collect(node.children, p.concat('children'));
      });
    };
    collect(this.navTree, []);
    const toRemove = [];
    byId.forEach((entries) => {
      if (entries.length < 2) return;
      const filled = entries.filter((e) => !e.empty);
      if (filled.length !== 1) return;
      entries.forEach((e) => {
        if (e.empty) toRemove.push(e.path);
      });
    });
    toRemove.sort((a, b) => {
      const depthA = a.filter((s) => s === 'children').length * 1000 + (a[a.length - 1] || 0);
      const depthB = b.filter((s) => s === 'children').length * 1000 + (b[b.length - 1] || 0);
      return depthB - depthA;
    });
    toRemove.forEach((path) => this.removeNodeAtPath(path));
  };

  CatalogPanel.prototype.removeNodeAtPath = function removeNodeAtPath(path) {
    const parent = this.getParentListForPath(path);
    const idx = path[path.length - 1];
    if (typeof idx !== 'number' || !Array.isArray(parent)) return null;
    return parent.splice(idx, 1)[0] || null;
  };

  CatalogPanel.prototype.parentFolderPath = function parentFolderPath(itemPath) {
    if (!itemPath || itemPath.length <= 1) return null;
    if (itemPath[itemPath.length - 2] !== 'children') return null;
    return itemPath.slice(0, -2);
  };

  /** 从树中移除 removedPath 后，修正仍指向原位置的 itemPath（如先删根级项再 insert）。 */
  CatalogPanel.prototype.adjustNavItemPathAfterRemoval = function adjustNavItemPathAfterRemoval(
    removedPath,
    itemPath,
  ) {
    if (!itemPath || !removedPath) return itemPath;
    const next = itemPath.slice();
    let i = 0;
    while (i < next.length && i < removedPath.length) {
      const a = next[i];
      const b = removedPath[i];
      if (a === b) {
        i += 1;
        continue;
      }
      if (typeof a === 'number' && typeof b === 'number') {
        if (i === removedPath.length - 1 && a > b) next[i] = a - 1;
        return next;
      }
      return next;
    }
    return next;
  };

  CatalogPanel.prototype.insertNode = function insertNode(parentPath, index, node) {
    let list = this.navTree;
    if (parentPath && parentPath.length) {
      const parent = this.getNodeAtPath(parentPath);
      if (!this.isNavContainer(parent)) return false;
      if (!Array.isArray(parent.children)) parent.children = [];
      list = parent.children;
    }
    const at = Math.max(0, Math.min(index, list.length));
    list.splice(at, 0, node);
    return true;
  };

  CatalogPanel.prototype.isDropInsideZone = function isDropInsideZone(targetNode, y, rectHeight) {
    if (!targetNode || !this.isNavContainer(targetNode)) return false;
    const ratio = y / Math.max(rectHeight, 1);
    return ratio > 0.18 && ratio < 0.82;
  };

  CatalogPanel.prototype.navListDepth = function navListDepth(parentPath) {
    if (!parentPath || !parentPath.length) return 0;
    return parentPath.filter((seg) => seg !== 'children').length;
  };

  CatalogPanel.prototype.navParentPathKey = function navParentPathKey(parentPath) {
    return JSON.stringify(parentPath || []);
  };

  CatalogPanel.prototype.resolveNavDropTarget = function resolveNavDropTarget(
    targetPath,
    y,
    rectHeight,
    fromPath,
  ) {
    const targetNode = this.getNodeAtPath(targetPath);
    if (targetNode && targetNode.kind === 'all') {
      const before = y < rectHeight / 2;
      return {
        kind: 'sibling',
        toParentPath: null,
        toIndex: before ? 1 : this.navTree.length,
      };
    }
    if (this.isDropInsideZone(targetNode, y, rectHeight)) {
      if (!Array.isArray(targetNode.children)) targetNode.children = [];
      return {
        kind: 'inside',
        toParentPath: targetPath,
        toIndex: targetNode.children.length,
      };
    }
    const before = y < rectHeight / 2;
    const targetParentPath = this.parentFolderPath(targetPath);
    const targetIdx = targetPath[targetPath.length - 1];
    let toIndex = targetIdx + (before ? 0 : 1);
    if (!targetParentPath || !targetParentPath.length) {
      toIndex = Math.max(1, toIndex);
    }
    return {
      kind: 'sibling',
      toParentPath: targetParentPath,
      toIndex,
    };
  };

  CatalogPanel.prototype.navChildrenListForDrop = function navChildrenListForDrop(parentPath) {
    if (!parentPath || !parentPath.length) return this.navTree;
    const parent = this.getNodeAtPath(parentPath);
    return Array.isArray(parent?.children) ? parent.children : [];
  };

  CatalogPanel.prototype.navItemPathForChildIndex = function navItemPathForChildIndex(parentPath, index) {
    if (!parentPath || !parentPath.length) return [index];
    return parentPath.concat(['children', index]);
  };

  CatalogPanel.prototype.navRowElForItemPath = function navRowElForItemPath(nav, itemPath) {
    if (!itemPath || !itemPath.length) return null;
    const node = this.getNodeAtPath(itemPath);
    if (!node) return null;
    const key = this.navNodeKey(node);
    if (!key) return null;
    return nav.querySelector(`.nav-row[data-nav-key="${CSS.escape(key)}"]`);
  };

  CatalogPanel.prototype.paintSiblingDropIndicator = function paintSiblingDropIndicator(nav, drop) {
    const parentPath = drop.toParentPath;
    const children = this.navChildrenListForDrop(parentPath);
    const idx = Math.max(0, Math.min(drop.toIndex, children.length));
    if (idx < children.length) {
      const el = this.navRowElForItemPath(nav, this.navItemPathForChildIndex(parentPath, idx));
      if (el) el.classList.add('drop-before');
      return;
    }
    if (children.length > 0) {
      const el = this.navRowElForItemPath(
        nav,
        this.navItemPathForChildIndex(parentPath, children.length - 1),
      );
      if (el) el.classList.add('drop-after');
      return;
    }
    if (parentPath && parentPath.length) {
      const el = this.navRowElForItemPath(nav, parentPath);
      if (el) el.classList.add('drop-inside');
    }
  };

  CatalogPanel.prototype.isNavDropPlacementAllowed = function isNavDropPlacementAllowed(fromPath, drop) {
    if (!drop || !fromPath) return false;
    if (drop.kind === 'inside') {
      return !this.cannotDropInside(fromPath, drop.toParentPath);
    }
    return !this.cannotDropInside(fromPath, drop.toParentPath);
  };

  CatalogPanel.prototype.clearNavDropIndicators = function clearNavDropIndicators(nav) {
    nav.querySelectorAll('.nav-row.drop-before, .nav-row.drop-after, .nav-row.drop-inside')
      .forEach((el) => el.classList.remove('drop-before', 'drop-after', 'drop-inside'));
  };

  CatalogPanel.prototype.applyNavDropIndicator = function applyNavDropIndicator(nav, row, fromPath, targetPath, y, rectHeight) {
    this.clearNavDropIndicators(nav);
    const drop = this.resolveNavDropTarget(targetPath, y, rectHeight, fromPath);
    if (!this.isNavDropPlacementAllowed(fromPath, drop)) return;
    const targetNode = this.getNodeAtPath(targetPath);
    if (targetNode && targetNode.kind === 'all') {
      row.classList.add('drop-inside');
      return;
    }
    if (drop.kind === 'inside') {
      row.classList.add('drop-inside');
      return;
    }
    this.paintSiblingDropIndicator(nav, drop);
  };

  CatalogPanel.prototype.cannotDropInside = function cannotDropInside(fromPath, toParentPath) {
    if (!toParentPath || !toParentPath.length) return false;
    const moving = this.getNodeAtPath(fromPath);
    const parent = this.getNodeAtPath(toParentPath);
    if (!moving || !parent || !this.isNavContainer(parent)) return true;
    if (moving.kind !== 'folder') return false;
    if (parent.kind !== 'folder') return false;
    if (moving.id === parent.id) return true;
    return this.folderContainsId(moving, parent.id);
  };

  CatalogPanel.prototype.folderContainsId = function folderContainsId(folderNode, folderId) {
    if (!folderNode || folderNode.kind !== 'folder') return false;
    if (folderNode.id === folderId) return true;
    for (const child of folderNode.children || []) {
      if (child.kind === 'folder' && this.folderContainsId(child, folderId)) return true;
    }
    return false;
  };

  CatalogPanel.prototype.buildNavPayload = function buildNavPayload() {
    this.removeEmptyDuplicateFolders();
    this.sortNavTreeChildOrder(this.navTree);
    return {
      version: 1,
      tree: JSON.parse(JSON.stringify(this.navTree)),
    };
  };

  CatalogPanel.prototype.persistNav = async function persistNav() {
    if (typeof this.saveNav !== 'function') return;
    const payload = this.buildNavPayload();
    await this.saveNav(payload);
  };

  CatalogPanel.prototype.matches = function matches(item, funcLabel, catName, q) {
    if (!q) return true;
    const prompts = (item.prompts || []).join('\n');
    const hay = (funcLabel + '\n' + catName + '\n' + item.name + '\n' +
      (item.source || '') + '\n' + prompts).toLowerCase();
    return hay.includes(q);
  };

  CatalogPanel.prototype.renderCategoryListItem = function renderCategoryListItem(catName, itemsHtml) {
    const label = collapseNavDisplayLabel(catName);
    return `<li><span class="cat-name">${escapeHtml(label)}</span><ul class="items">${itemsHtml}</ul></li>`;
  };

  CatalogPanel.prototype.renderModuleHead = function renderModuleHead(opts) {
    const icon = opts.icon || smallIcon('module');
    const title = opts.title || '';
    const sub = opts.sub || '';
    const moduleId = opts.moduleId || '';
    const category = opts.category || '';
    const attrs = ['data-module-head="1"'];
    if (moduleId) attrs.push(`data-module-id="${escapeAttr(moduleId)}"`);
    if (category) attrs.push(`data-category="${escapeAttr(category)}"`);
    return `<div class="module-head" ${attrs.join(' ')}>
            <span class="module-icon" aria-hidden="true">${icon}</span>
            <div>
              <h3>${escapeHtml(title)}</h3>
              <div class="sub">${escapeHtml(sub)}</div>
            </div>
          </div>`;
  };

  CatalogPanel.prototype._registrySourceFromItem = function _registrySourceFromItem(item, out) {
    if (!item || !out) return;
    const id = String(item.source_id || '').trim();
    if (!id || out.has(id)) return;
    out.set(id, {
      id,
      label: String(item.source || id).trim(),
      env: String(item.env || '').trim(),
    });
  };

  CatalogPanel.prototype.collectAllRegistrySources = function collectAllRegistrySources() {
    const map = new Map();
    for (const src of this.DATA?.registry_sources || []) {
      const id = String(src.id || '').trim();
      if (!id || map.has(id)) continue;
      map.set(id, {
        id,
        label: String(src.label || id).trim(),
        env: String(src.env || '').trim(),
      });
    }
    for (const mod of this.DATA?.modules || []) {
      for (const cat of mod.categories || []) {
        for (const item of cat.items || []) {
          this._registrySourceFromItem(item, map);
        }
      }
    }
    return [...map.values()].sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
  };

  CatalogPanel.prototype.collectRegistrySourcesForCategory = function collectRegistrySourcesForCategory(categoryName) {
    const catName = String(categoryName || '').trim();
    const map = new Map();
    if (!catName) return [];
    for (const mod of this.DATA?.modules || []) {
      for (const cat of mod.categories || []) {
        if (String(cat.name || '').trim() !== catName) continue;
        for (const item of cat.items || []) {
          this._registrySourceFromItem(item, map);
        }
      }
    }
    return [...map.values()].sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'));
  };

  CatalogPanel.prototype.resolveModuleHeadContext = function resolveModuleHeadContext(head) {
    let moduleId = head.getAttribute('data-module-id') || '';
    let category = head.getAttribute('data-category') || '';
    const filter = this.activeFilter();
    if (!moduleId && filter.mode === 'category') moduleId = filter.moduleId || '';
    if (!category && filter.mode === 'category') {
      const mod = this.moduleById(filter.moduleId);
      category = mod?.categories?.[filter.catIndex]?.name || '';
    }
    if (!moduleId && filter.mode === 'modules' && filter.moduleIds?.size === 1) {
      moduleId = [...filter.moduleIds][0];
    }
    if (!category) {
      const section = head.closest('.catalog-module');
      const catNames = section?.querySelectorAll('.cat-name');
      if (catNames?.length === 1) {
        category = String(catNames[0].textContent || '').trim();
      }
    }
    return { moduleId, category };
  };

  CatalogPanel.prototype.renderPromptLine = function renderPromptLine(text, ctx) {
    const raw = String(text || '');
    const line = humanizeCatalogPromptText(raw);
    const spanParts = [];
    let last = 0;
    let m;
    const re = new RegExp(PROMPT_PLACEHOLDER_RE.source, 'g');
    while ((m = re.exec(line)) !== null) {
      if (m.index > last) spanParts.push(escapeHtml(line.slice(last, m.index)));
      const key = m[1];
      const label = promptPlaceholderLabel(key, m[2]);
      const width = promptFieldWidthEm(label);
      spanParts.push(
        `<input type="text" class="prompt-field" data-key="${escapeHtml(key)}" ` +
        `placeholder="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" ` +
        `style="width:${width}em">`
      );
      last = re.lastIndex;
    }
    if (last < line.length) spanParts.push(escapeHtml(line.slice(last)));
    const meta = ctx && ctx.registryId && ctx.sourceId
      ? ` data-source-id="${escapeAttr(ctx.sourceId)}"` +
        ` data-registry-id="${escapeAttr(ctx.registryId)}"` +
        ` data-prompt-index="${Number(ctx.promptIndex) || 0}"` +
        ` data-prompt-raw="${escapeAttr(raw)}"`
      : '';
    return `<div class="prompt-line"${meta}>
      <span class="prompt-text">${spanParts.join('')}</span>
      <div class="prompt-line-footer">
        <button type="button" class="prompt-run" title="填入提问栏">执行</button>
      </div>
    </div>`;
  };

  CatalogPanel.prototype.renderCapItem = function renderCapItem(item, opts) {
    const prompts = item.prompts || [];
    const hasPrompts = prompts.length > 0;
    const sourceId = item.source_id || '';
    const registryId = item.registry_id || '';
    const promptHtml = prompts.map((t, i) => this.renderPromptLine(t, {
      sourceId,
      registryId,
      promptIndex: i,
    })).join('');
    const capDisplayName = collapseNavDisplayLabel(item.name);
    const headToggle = hasPrompts ? ' is-toggle' : '';
    const moduleId = opts && opts.moduleId;
    const catIndex = opts && opts.catIndex;
    const capKey = hasPrompts && moduleId != null && catIndex != null
      ? this.capItemKey(item, moduleId, catIndex)
      : '';
    const capOpen = capKey && this.capExpanded.has(capKey);
    const headAria = hasPrompts ? ` aria-expanded="${capOpen ? 'true' : 'false'}"` : '';
    const source = item.source
      ? `<span class="source-badge" data-env="${escapeHtml(item.env || '')}" data-source-id="${escapeHtml(item.source_id || '')}">${escapeHtml(item.source)}</span>`
      : '';
    const chevron = hasPrompts ? '<span class="cap-chevron" aria-hidden="true">▸</span>' : '';
    const capKeyAttr = capKey ? ` data-cap-key="${escapeHtml(capKey)}"` : '';
    const sourceTagId = item.source_tag_id || sourceId;
    const capRegAttr = registryId && sourceId
      ? ` data-source-id="${escapeAttr(sourceId)}" data-registry-id="${escapeAttr(registryId)}"` +
        ` data-source-tag-id="${escapeAttr(sourceTagId)}"`
      : '';
    const capNameAttr = registryId && sourceId
      ? ` data-cap-name="${escapeAttr(item.name || '')}"`
      : '';
    return `<li class="cap"${capKeyAttr}${capRegAttr}>
      <div class="cap-head${headToggle}"${headAria}${capNameAttr}>
        ${chevron}
        <span class="cap-icon" aria-hidden="true">${smallIcon('spark')}</span>
        <div class="cap-main">
          <span class="cap-name">${escapeHtml(capDisplayName)}</span>
          ${source}
        </div>
      </div>
      <div class="prompt-panel"${hasPrompts && !capOpen ? ' hidden' : ''}>${hasPrompts ? `<div class="prompt-list">${promptHtml}</div>` : ''}</div>
    </li>`;
  };

  CatalogPanel.prototype.bindPromptToggles = function bindPromptToggles(root) {
    root.querySelectorAll('.cap-head.is-toggle').forEach(head => {
      head.addEventListener('click', () => {
        const cap = head.closest('.cap');
        const panel = cap.querySelector('.prompt-panel');
        const open = head.getAttribute('aria-expanded') === 'true';
        head.setAttribute('aria-expanded', open ? 'false' : 'true');
        if (open) panel.setAttribute('hidden', '');
        else panel.removeAttribute('hidden');
        const capKey = this.capRegistryKey(
          cap.getAttribute('data-source-id'),
          cap.getAttribute('data-registry-id'),
        ) || cap.getAttribute('data-cap-key') || '';
        if (capKey) {
          if (open) this.capExpanded.delete(capKey);
          else this.capExpanded.add(capKey);
        }
      });
    });
  };

  CatalogPanel.prototype.bindPromptPanels = function bindPromptPanels(root) {
    this.bindPromptToggles(root);
  };

  CatalogPanel.prototype.renderPlaybookDefaults = function renderPlaybookDefaults(defaults) {
    const entries = Object.entries(defaults || {}).filter(([, v]) => v != null && String(v).trim());
    if (!entries.length) return '';
    const rows = entries.map(([k, v]) =>
      `<dt>${escapeHtml(playbookDefaultLabel(k))}</dt><dd><code>${escapeHtml(String(v))}</code></dd>`,
    ).join('');
    return `<div class="playbook-readable-defaults-wrap">
      <p class="playbook-readable-defaults-label">默认参数</p>
      <dl class="playbook-readable-defaults">${rows}</dl>
    </div>`;
  };

  CatalogPanel.prototype.renderPlaybookStepReadable = function renderPlaybookStepReadable(step, opts) {
    const outline = !!(opts && opts.outline);
    const title = step.name || step.note || `步骤 ${step.order}`;
    const optional = /可选/.test(title) || /可选/.test(String(step.note || ''));
    const lead = step.name
      ? humanizePlaybookProse(step.note || '')
      : '';
    const { hints } = collectPlaybookStepOps(step);

    if (outline) {
      const tag = optional ? ' <span class="playbook-readable-optional">可选</span>' : '';
      return `<li class="playbook-readable-outline-item">
        <span class="playbook-readable-outline-num">${step.order}</span>
        <span class="playbook-readable-outline-title">${escapeHtml(title)}${tag}</span>
      </li>`;
    }

    const leadBlock = lead ? `<p class="playbook-readable-step-note">${escapeHtml(lead)}</p>` : '';
    const hintBlock = hints.length
      ? `<ul class="playbook-readable-hints">${hints.map((h) =>
        `<li>${escapeHtml(humanizePlaybookProse(h))}</li>`,
      ).join('')}</ul>`
      : '';
    const optTag = optional ? '<span class="playbook-readable-optional">可选</span>' : '';
    const verifyBlock = step.sheet
      ? `<p class="playbook-readable-step-sheet">关联表：${escapeHtml(step.sheet)}</p>`
      : '';
    const stepPrompts = (step.prompts || [])
      .filter(Boolean)
      .map((t) => this.renderPromptLine(t))
      .join('');
    const promptsBlock = stepPrompts
      ? `<div class="playbook-readable-step-prompts"><div class="prompt-list">${stepPrompts}</div></div>`
      : '';

    return `<article class="playbook-readable-step">
      <header class="playbook-readable-step-head">
        <span class="playbook-readable-step-num">${step.order}</span>
        <h4 class="playbook-readable-step-title">${escapeHtml(title)}${optTag ? ` ${optTag}` : ''}</h4>
      </header>
      ${leadBlock}
      ${hintBlock}
      ${verifyBlock}
      ${promptsBlock}
    </article>`;
  };

  CatalogPanel.prototype.renderPlaybookReadable = function renderPlaybookReadable(pb, opts) {
    if (!pb) return '';
    const outline = !!(opts && opts.outline);
    const title = pb.title || pb.id;
    const category = pb.category || '工作流';
    const stepCount = (pb.steps || []).length;
    const summaryLead = humanizePlaybookProse(pb.summaryReadable || pb.summary || '');
    const prompts = (pb.prompts || [])
      .filter(Boolean)
      .map((t) => this.renderPromptLine(t))
      .join('');
    const defaultsHtml = !outline ? this.renderPlaybookDefaults(pb.defaults) : '';
    const stepsHtml = outline
      ? `<ol class="playbook-readable-outline">${(pb.steps || []).map((s) => this.renderPlaybookStepReadable(s, { outline: true })).join('')}</ol>`
      : `<div class="playbook-readable-steps">${(pb.steps || []).map((s) => this.renderPlaybookStepReadable(s)).join('')}</div>`;
    const notes = (pb.notes || []).filter(Boolean);
    const notesHtml = !outline && notes.length
      ? `<details class="playbook-readable-more">
          <summary>技术说明（${notes.length} 条）</summary>
          <ul>${notes.map((n) => `<li>${escapeHtml(n)}</li>`).join('')}</ul>
        </details>`
      : '';

    return `<section class="playbook-readable${outline ? ' is-outline' : ''}" id="playbook-${escapeHtml(pb.id)}">
      <header class="playbook-readable-head">
        <p class="playbook-readable-eyebrow">${escapeHtml(category)} · ${stepCount} 步</p>
        <h3 class="playbook-readable-title">${escapeHtml(title)}</h3>
        ${summaryLead ? `<p class="playbook-readable-lead">${escapeHtml(summaryLead)}</p>` : ''}
        ${defaultsHtml}
        ${prompts ? `<div class="playbook-readable-prompts"><p class="playbook-readable-prompts-label">快捷执行</p><div class="prompt-list">${prompts}</div></div>` : ''}
      </header>
      <div class="playbook-readable-body">
        <p class="playbook-readable-steps-label">${outline ? '步骤概览' : '分步操作'}</p>
        ${stepsHtml}
        ${notesHtml}
      </div>
    </section>`;
  };

  CatalogPanel.prototype.renderPlaybookStep = function renderPlaybookStep(step, opts) {
    const expandAll = !!(opts && opts.expandAllSteps);
    const ops = (step.operations || []).map((op) => {
      const text = humanizePlaybookOperationLine(op);
      return text ? `<li>${escapeHtml(text)}</li>` : '';
    }).filter(Boolean).join('');
    const prompts = (step.prompts || []).map(t => this.renderPromptLine(t)).join('');
    const title = step.name || step.workflowName || step.workflowId || step.note || `步骤 ${step.order}`;
    const subParts = [];
    if (step.workflowId && step.workflowName) subParts.push(`<code>${escapeHtml(step.workflowId)}</code>`);
    if (step.sheet) subParts.push(`Sheet「${escapeHtml(step.sheet)}」`);
    const sub = subParts.join(' · ');
    const noteBlock = (step.note && title !== step.note)
      ? `<div class="playbook-step-note">${escapeHtml(step.note)}</div>` : '';
    return `<div class="playbook-step">
      <div class="playbook-step-head" aria-expanded="${expandAll ? 'true' : 'false'}">
        <span class="playbook-step-num">${step.order}</span>
        <div>
          <div class="playbook-step-title">${escapeHtml(title)}</div>
          ${sub ? `<div class="playbook-step-sub">${sub}</div>` : ''}
        </div>
      </div>
      <div class="playbook-step-body"${expandAll ? '' : ' hidden'}>
        ${noteBlock}
        ${ops ? `<ol class="playbook-ops">${ops}</ol>` : ''}
        ${prompts ? `<div class="prompt-list">${prompts}</div>` : ''}
      </div>
    </div>`;
  };

  CatalogPanel.prototype.renderPlaybook = function renderPlaybook(pb, opts) {
    const steps = (pb.steps || []).map((s) => this.renderPlaybookStep(s, opts)).join('');
    const topPrompts = (pb.prompts || []).map(t => this.renderPromptLine(t)).join('');
    const stepCount = (pb.steps || []).length;
    const notesBlock = (pb.notes || []).length
      ? `<div class="playbook-notes"><strong>说明</strong><ul>${(pb.notes || []).map((n) => `<li>${escapeHtml(n)}</li>`).join('')}</ul></div>`
      : '';
    return `<section class="playbook-section" id="playbook-${escapeHtml(pb.id)}">
      <div class="playbook-head">
        <h3>${escapeHtml(pb.title)}</h3>
        <p class="playbook-summary">${escapeHtml(pb.summary || '')}</p>
        <div class="playbook-tag-row">
          <span class="playbook-tag">${escapeHtml(pb.category || '工作流')}</span>
          <span class="playbook-tag">${stepCount} 步</span>
        </div>
        ${topPrompts ? `<div class="prompt-list" style="margin-top:10px">${topPrompts}</div>` : ''}
        ${notesBlock}
      </div>
      <div class="playbook-steps">${steps}</div>
    </section>`;
  };

  CatalogPanel.prototype.bindPlaybookToggles = function bindPlaybookToggles(root) {
    root.querySelectorAll('.playbook-step-head').forEach(head => {
      head.addEventListener('click', () => {
        const body = head.nextElementSibling;
        const open = head.getAttribute('aria-expanded') === 'true';
        head.setAttribute('aria-expanded', open ? 'false' : 'true');
        if (body) body.hidden = open;
      });
    });
  };

  CatalogPanel.prototype.renderCapCategoryBlock = function renderCapCategoryBlock(capNode, q) {
    const mod = this.moduleById(capNode.moduleId);
    const cat = mod?.categories?.[capNode.catIndex];
    if (!cat) return { html: '', count: 0 };
    const catLabel = this.navNodeLabel(capNode);
    const filtered = cat.items.filter((it) => this.matches(it, mod.label, cat.name, q));
    if (!filtered.length) return { html: '', count: 0 };
    const items = filtered.map((it) => this.renderCapItem(it, {
      moduleId: capNode.moduleId,
      catIndex: capNode.catIndex,
      modLabel: mod.label,
      catName: cat.name,
    })).join('');
    return {
      count: filtered.length,
      html: this.renderCategoryListItem(catLabel || cat.name, items),
    };
  };

  CatalogPanel.prototype.appendNavScopeSections = function appendNavScopeSections(main, nodes, q) {
    let any = false;
    for (const rootNode of nodes || []) {
      if (!rootNode || rootNode.kind === 'all') continue;
      const body = this.renderNavScopeBody(rootNode, q);
      if (!body.visibleCount) continue;
      any = true;
      const section = document.createElement('section');
      section.className = 'catalog-module catalog-module-scope';
      if (rootNode.kind === 'module' && rootNode.moduleId) {
        section.id = 'catalog-mod-' + rootNode.moduleId;
      }
      section.innerHTML = `
          ${this.renderModuleHead({
            title: this.navNodeLabel(rootNode),
            sub: `${body.visibleCount} 项能力`,
            moduleId: rootNode.kind === 'module' ? (rootNode.moduleId || '') : '',
          })}
          ${body.partsHtml}
          ${body.catsHtml ? `<ol class="cats">${body.catsHtml}</ol>` : ''}`;
      main.appendChild(section);
    }
    return any;
  };

  CatalogPanel.prototype.renderNavScopeBody = function renderNavScopeBody(node, q) {
    let catsHtml = '';
    let visibleCount = 0;
    const parts = [];
    const scopeChildren = node.children || [];
    scopeChildren.forEach((child) => {
      if (child.kind === 'cap') {
        const block = this.renderCapCategoryBlock(child, q);
        if (block.count) {
          visibleCount += block.count;
          catsHtml += block.html;
        }
      } else if (child.kind === 'folder') {
        const nested = this.renderNavScopeBody(child, q);
        if (nested.visibleCount) {
          visibleCount += nested.visibleCount;
          parts.push(`<div class="catalog-scope-folder">
            <h4 class="catalog-scope-folder-title">${escapeHtml(child.label || '分组')}</h4>
            ${nested.partsHtml}
            ${nested.catsHtml ? `<ol class="cats">${nested.catsHtml}</ol>` : ''}
          </div>`);
        }
      } else if (child.kind === 'module') {
        const nested = this.renderNavScopeBody(child, q);
        if (nested.visibleCount) {
          visibleCount += nested.visibleCount;
          parts.push(`<div class="catalog-scope-module">
            <h4 class="catalog-scope-folder-title">${escapeHtml(this.navNodeLabel(child))}</h4>
            ${nested.partsHtml}${nested.catsHtml ? `<ol class="cats">${nested.catsHtml}</ol>` : ''}
          </div>`);
        }
      } else if (child.kind === 'playbookItem') {
        const pb = this.playbookById(child.playbookId);
        if (!pb) return;
        if (q) {
          const hay = [
            pb.title,
            pb.summary,
            pb.category,
            ...(pb.prompts || []),
            ...(pb.steps || []).flatMap((step) => [
              step.name,
              step.note,
              ...(step.operations || []),
            ]),
          ].join(' ').toLowerCase();
          if (!hay.includes(q)) return;
        }
        visibleCount += 1;
        parts.push(this.renderPlaybookReadable(pb, { outline: true }));
      }
    });
    return { catsHtml, partsHtml: parts.join(''), visibleCount };
  };

  CatalogPanel.prototype.renderPlaybooks = function renderPlaybooks(container) {
    const playbooks = this.DATA.playbooks || [];
    if (!playbooks.length) return;
    const filter = this.activeFilter();
    if (filter.mode !== 'playbook') return;
    const wrap = document.createElement('div');
    wrap.innerHTML = playbooks.map(pb => this.renderPlaybook(pb)).join('');
    while (wrap.firstChild) container.appendChild(wrap.firstChild);
    this.bindPlaybookToggles(container);
    this.bindPromptPanels(container);
  };

  CatalogPanel.prototype.render = function render() {
    const q = this.query.trim().toLowerCase();
    const main = this.mainEl;
    main.innerHTML = '';
    let any = false;

    this.renderPlaybooks(main);
    const filter = this.activeFilter();

    if (filter.mode === 'navScope') {
      const body = this.renderNavScopeBody(filter.node, q);
      if (body.visibleCount) {
        any = true;
        const icon = filter.icon === 'module' ? smallIcon('module') : smallIcon('spark');
        const section = document.createElement('section');
        section.className = 'catalog-module catalog-module-scope';
        section.innerHTML = `
          ${this.renderModuleHead({
            icon,
            title: filter.title,
            sub: `${body.visibleCount} 项能力`,
            moduleId: filter.node?.kind === 'module' ? (filter.node.moduleId || '') : '',
          })}
          ${body.partsHtml}
          ${body.catsHtml ? `<ol class="cats">${body.catsHtml}</ol>` : ''}`;
        main.appendChild(section);
      }
      if (!any) {
        main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
      } else {
        this.bindPromptPanels(main);
      }
      return;
    }

    if (filter.mode === 'playbookItem') {
      const pb = this.playbookById(filter.playbookId);
      if (pb) {
        any = true;
        const wrap = document.createElement('div');
        wrap.innerHTML = this.renderPlaybookReadable(pb);
        while (wrap.firstChild) main.appendChild(wrap.firstChild);
        this.bindPromptPanels(main);
      }
      if (!any) {
        main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
      }
      return;
    }

    if (filter.mode === 'playbookStep') {
      const step = this.playbookStepByOrder(filter.playbookId, filter.stepOrder);
      if (step) {
        any = true;
        const pb = this.playbookById(filter.playbookId);
        const section = document.createElement('section');
        section.className = 'catalog-module catalog-module-playbook-step';
        section.innerHTML = `
          <div class="module-head">
            <span class="module-icon" aria-hidden="true">${smallIcon('play')}</span>
            <div>
              <h3>${escapeHtml(this.navNodeLabel(filter.node) || `步骤 ${filter.stepOrder}`)}</h3>
              <div class="sub">${escapeHtml(pb?.title || filter.playbookId)} · 第 ${filter.stepOrder} 步</div>
            </div>
          </div>
          <div class="playbook-readable-steps">${this.renderPlaybookStepReadable(step)}</div>`;
        main.appendChild(section);
        this.bindPromptPanels(main);
      }
      if (!any) {
        main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
      }
      return;
    }

    if (filter.mode === 'category') {
      const mod = this.DATA.modules.find((m) => m.id === filter.moduleId);
      const cat = mod?.categories?.[filter.catIndex];
      if (cat) {
        const filtered = cat.items.filter((it) => this.matches(it, mod.label, cat.name, q));
        if (filtered.length) {
          any = true;
          const capNode = this.findNavNodeByKey(this.activeKey);
          const scopeTitle = capNode
            ? this.navNodeLabel(capNode)
            : collapseNavDisplayLabel(cat.name);
          const items = filtered.map((it) => this.renderCapItem(it, {
            moduleId: filter.moduleId,
            catIndex: filter.catIndex,
            modLabel: mod.label,
            catName: cat.name,
          })).join('');
          const section = document.createElement('section');
          section.className = 'catalog-module catalog-module-category';
          section.innerHTML = `
            ${this.renderModuleHead({
              icon: smallIcon('spark'),
              title: scopeTitle,
              sub: `${filtered.length} 项 MOA 能力`,
              moduleId: filter.moduleId,
              category: cat.name,
            })}
            <ol class="cats"><li><ul class="items">${items}</ul></li></ol>`;
          main.appendChild(section);
        }
      }
      if (!any) {
        main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
      } else {
        this.bindPromptPanels(main);
      }
      return;
    }

    if (filter.mode === 'all') {
      any = this.appendNavScopeSections(main, this.navTreeRootSiblings(), q);
      if (!any) {
        main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
      } else {
        this.bindPromptPanels(main);
      }
      return;
    }

    for (const mod of this.DATA.modules) {
      if (filter.mode === 'playbook') continue;
      if (filter.mode === 'modules' && !filter.moduleIds.has(mod.id)) continue;

      let catsHtml = '';
      let visibleCount = 0;
      for (let catIndex = 0; catIndex < mod.categories.length; catIndex += 1) {
        const cat = mod.categories[catIndex];
        const filtered = cat.items.filter(it => this.matches(it, mod.label, cat.name, q));
        if (!filtered.length) continue;
        visibleCount += filtered.length;
        const items = filtered.map((it) => this.renderCapItem(it, {
          moduleId: mod.id,
          catIndex,
          modLabel: mod.label,
          catName: cat.name,
        })).join('');
        catsHtml += this.renderCategoryListItem(cat.name, items);
      }
      if (!visibleCount) continue;
      any = true;

      const section = document.createElement('section');
      section.className = 'catalog-module';
      section.id = 'catalog-mod-' + mod.id;
      section.innerHTML = `
        ${this.renderModuleHead({
          title: mod.label,
          sub: `${visibleCount} 项能力`,
          moduleId: mod.id,
        })}
        <ol class="cats">${catsHtml}</ol>`;
      main.appendChild(section);
    }

    if (!any) {
      main.innerHTML = '<div class="catalog-empty">没有匹配的能力</div>';
    } else {
      this.bindPromptPanels(main);
    }
  };

  CatalogPanel.prototype.renderNavRow = function renderNavRow(node, depth, pathKey) {
    const key = this.navNodeKey(node);
    const label = this.navNodeLabel(node);
    const count = this.navNodeCount(node);
    const isFolder = node.kind === 'folder';
    const collapseKey = this.navCollapseKey(node);
    const branch = this.navRowIsBranch(node);
    const collapsed = branch && collapseKey && this.collapsed.has(collapseKey);
    const active = this.activeKey === key;
    const indent = Math.min(depth, 8) * 14;
    const showsFolderIcon = this.navRowShowsFolderIcon(node);
    const folderExpanded = showsFolderIcon && branch && !collapsed;
    const isAll = node.kind === 'all';
    const folderMark = isAll
      ? `<span class="nav-folder-icon nav-all-icon" aria-hidden="true">${navCatalogListIconSvg()}</span>`
      : showsFolderIcon
        ? `<span class="nav-folder-icon${folderExpanded ? ' is-open' : ' is-closed'}" aria-hidden="true">${navFolderIconSvg(folderExpanded)}</span>`
        : '';
    const chevron = branch
      ? `<button type="button" class="nav-fold" data-collapse-key="${escapeHtml(collapseKey)}" aria-label="${collapsed ? '展开' : '收起'}">${navChevronSvg(collapsed)}</button>`
      : '<span class="nav-fold-spacer" aria-hidden="true"></span>';
    const drag = this.canEditNav && node.kind !== 'all' ? ' draggable="true"' : '';
    return `<div class="nav-row${active ? ' active' : ''}${isFolder ? ' is-folder' : ''}${branch ? ' is-branch' : ''}" data-nav-key="${escapeHtml(key)}" data-path-key="${escapeHtml(pathKey)}" style="--nav-depth:${indent}px"${drag}>
      ${chevron}
      <button type="button" class="nav-select">
        ${folderMark}
        <span class="nav-label">${escapeHtml(label)}</span>
        <span class="count">${count}</span>
      </button>
    </div>`;
  };

  CatalogPanel.prototype.renderNavPbStepFromNode = function renderNavPbStepFromNode(node, depth, pathKey) {
    const step = this.playbookStepByOrder(node.playbookId, node.stepOrder);
    if (!step && !node.label) return '';
    const key = this.navNodeKey(node);
    const label = this.navNodeLabel(node);
    const active = this.activeKey === key;
    const indent = Math.min(depth, 8) * 14;
    const count = this.navNodeCount(node);
    const drag = this.canEditNav ? ' draggable="true"' : '';
    return `<div class="nav-row nav-cap-if nav-pb-step${active ? ' active' : ''}" data-nav-key="${escapeHtml(key)}" data-path-key="${escapeHtml(pathKey)}" style="--nav-depth:${indent}px"${drag}>
      <span class="nav-cap-lead" aria-hidden="true"><span class="nav-folder-icon nav-cap-if-icon">${smallIcon('play')}</span></span>
      <button type="button" class="nav-select nav-select-cap-if">
        <span class="nav-label">${escapeHtml(label)}</span>
        <span class="count">${count}</span>
      </button>
    </div>`;
  };

  CatalogPanel.prototype.renderNavPlaybookItemFromNode = function renderNavPlaybookItemFromNode(node, depth, pathKey) {
    const pb = this.playbookById(node.playbookId);
    if (!pb && !node.navLabel) return '';
    const key = this.navNodeKey(node);
    const label = this.navNodeLabel(node);
    const active = this.activeKey === key;
    const indent = Math.min(depth, 8) * 14;
    const count = this.navNodeCount(node);
    const drag = this.canEditNav ? ' draggable="true"' : '';
    return `<div class="nav-row nav-cap-if nav-playbook-cap${active ? ' active' : ''}" data-nav-key="${escapeHtml(key)}" data-path-key="${escapeHtml(pathKey)}" style="--nav-depth:${indent}px"${drag}>
      <span class="nav-cap-lead" aria-hidden="true"><span class="nav-folder-icon nav-cap-if-icon">${navCapInterfaceIconSvg()}</span></span>
      <button type="button" class="nav-select nav-select-cap-if">
        <span class="nav-label">${escapeHtml(label)}</span>
        <span class="count">${count}</span>
      </button>
    </div>`;
  };

  CatalogPanel.prototype.renderNavCapFromNode = function renderNavCapFromNode(node, depth, pathKey) {
    const mod = this.moduleById(node.moduleId);
    const cat = mod?.categories?.[node.catIndex];
    if (!cat) return '';
    const key = this.navNodeKey(node);
    const label = this.navNodeLabel(node);
    const active = this.activeKey === key;
    const indent = Math.min(depth, 8) * 14;
    const count = (cat.items || []).length;
    const drag = this.canEditNav ? ' draggable="true"' : '';
    return `<div class="nav-row nav-cap-if${active ? ' active' : ''}" data-nav-key="${escapeHtml(key)}" data-path-key="${escapeHtml(pathKey)}" style="--nav-depth:${indent}px"${drag}>
      <span class="nav-cap-lead" aria-hidden="true"><span class="nav-folder-icon nav-cap-if-icon">${navCapInterfaceIconSvg()}</span></span>
      <button type="button" class="nav-select nav-select-cap-if">
        <span class="nav-label">${escapeHtml(label)}</span>
        <span class="count">${count}</span>
      </button>
    </div>`;
  };

  CatalogPanel.prototype.renderNavNodes = function renderNavNodes(nodes, depth, pathPrefix) {
    const parts = [];
    (nodes || []).forEach((node, index) => {
      const pathKey = `${pathPrefix}:${index}`;
      if (node.kind === 'cap') {
        parts.push(this.renderNavCapFromNode(node, depth, pathKey));
        return;
      }
      if (node.kind === 'playbookItem') {
        const row = this.renderNavPlaybookItemFromNode(node, depth, pathKey);
        if (row) parts.push(row);
        return;
      }
      if (node.kind === 'pbStep') {
        return;
      }
      parts.push(this.renderNavRow(node, depth, pathKey));
      const collapseKey = this.navCollapseKey(node);
      const branch = this.navRowIsBranch(node);
      if (branch && collapseKey && !this.collapsed.has(collapseKey)) {
        const childDepth = depth + 1;
        const treeInner = this.renderNavNodes(node.children || [], childDepth, `${pathKey}:c`);
        if (treeInner) {
          parts.push(`<div class="nav-children nav-children-mixed">${treeInner}</div>`);
        }
      }
    });
    return parts.join('');
  };

  CatalogPanel.prototype.renderNav = function renderNav(opts) {
    const nav = this.navEl;
    const preserveScroll = !!(opts && opts.preserveScroll);
    const prevScrollTop = preserveScroll && nav ? nav.scrollTop : 0;
    nav.classList.toggle('catalog-nav-tree', true);
    nav.innerHTML = `<div class="nav-tree">${this.renderNavNodes(this.navTree, 0, 'r')}</div>`;
    this.bindNavEvents(nav);
    if (preserveScroll && nav) {
      nav.scrollTop = prevScrollTop;
    } else {
      const activeRow = nav.querySelector('.nav-row.active');
      if (activeRow) activeRow.scrollIntoView({ inline: 'nearest', block: 'nearest' });
    }
  };

  CatalogPanel.prototype.ensureNavMenu = function ensureNavMenu() {
    if (this._navMenuEl) return this._navMenuEl;
    const menu = document.createElement('div');
    menu.className = 'catalog-nav-menu';
    menu.hidden = true;
    menu.innerHTML = `
      <button type="button" data-action="add">添加子分组</button>
      <button type="button" data-action="rename">重命名</button>
      <button type="button" data-action="delete">删除</button>
    `;
    menu.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn || !this._navMenuTarget) return;
      e.preventDefault();
      const action = btn.getAttribute('data-action');
      const target = this._navMenuTarget;
      this.hideNavMenu();
      if (action === 'add') {
        if (target.key === 'all') this.addRootFolder();
        else this.addSubFolder(target.key);
      }
      else if (action === 'rename') this.renameNavNode(target.key);
      else if (action === 'delete') this.deleteNavNode(target.key);
    });
    document.body.appendChild(menu);
    this._navMenuEl = menu;
    return menu;
  };

  CatalogPanel.prototype.hideNavMenu = function hideNavMenu() {
    if (this._navMenuEl) {
      this._navMenuEl.hidden = true;
      this._navMenuEl.classList.remove('is-open');
    }
    this._navMenuTarget = null;
  };

  CatalogPanel.prototype.showNavContextMenu = function showNavContextMenu(clientX, clientY, key) {
    const menu = this.ensureNavMenu();
    if (menu.parentElement !== document.body) document.body.appendChild(menu);
    const nodePath = this.findNodePath(key);
    const node = nodePath ? this.getNodeAtPath(nodePath) : null;
    if (!node) return;
    const addBtn = menu.querySelector('[data-action="add"]');
    const renameBtn = menu.querySelector('[data-action="rename"]');
    const deleteBtn = menu.querySelector('[data-action="delete"]');
    const isAll = node.kind === 'all';
    const isCap = node.kind === 'cap' || node.kind === 'playbookItem';
    const depth = this.navNodeDepth(nodePath);
    const canRename = this.navNodeSupportsRename(node, depth) && this.canEditNav;
    const canDeleteFolder = node.kind === 'folder' && this.canDeleteNav;
    const canDeleteNavRow = (node.kind === 'module' || node.kind === 'playbook')
      && depth === 0
      && this.canEditNav;
    if (addBtn) {
      addBtn.hidden = isCap || !this.canEditNav;
      addBtn.textContent = isAll ? '新建分组' : '添加子分组';
    }
    if (renameBtn) {
      renameBtn.hidden = isAll || !canRename;
      renameBtn.textContent = '重命名';
    }
    if (deleteBtn) {
      deleteBtn.hidden = isAll || isCap || !(canDeleteFolder || canDeleteNavRow);
      deleteBtn.textContent = node.kind === 'folder' ? '删除' : '从目录移除';
    }
    this._navMenuTarget = { key, nodePath };
    menu.hidden = false;
    menu.classList.add('is-open');
    menu.style.visibility = 'hidden';
    menu.style.left = '0px';
    menu.style.top = '0px';
    const menuRect = menu.getBoundingClientRect();
    const left = Math.min(Math.max(8, clientX), window.innerWidth - menuRect.width - 8);
    const top = Math.min(Math.max(8, clientY), window.innerHeight - menuRect.height - 8);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.visibility = '';
  };

  CatalogPanel.prototype.selectNavKey = function selectNavKey(key) {
    this.activeKey = key || 'all';
    this.renderNav();
    this.render();
    if (key.startsWith('module:')) {
      const el = document.getElementById('catalog-mod-' + key.slice(7));
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  CatalogPanel.prototype.addRootFolder = async function addRootFolder() {
    if (!this.canEditNav) return;
    const label = await openNavTextPrompt('分组名称');
    if (!label || !String(label).trim()) return;
    const folder = {
      kind: 'folder',
      id: newFolderId(),
      label: String(label).trim(),
      children: [],
    };
    this.navTree.push(folder);
    this.ensureFolderChildren(this.navTree);
    const newKey = this.navNodeKey(folder);
    this.activeKey = newKey;
    try {
      await this.persistNav();
      this.renderNav();
      this.render();
      this.scrollNavRowIntoView(newKey);
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.addSubFolder = async function addSubFolder(parentKey) {
    if (!this.canEditNav) return;
    const label = await openNavTextPrompt('子分组名称');
    if (!label || !String(label).trim()) return;
    const folder = {
      kind: 'folder',
      id: newFolderId(),
      label: String(label).trim(),
      children: [],
      subfolder: true,
    };
    const path = this.findNodePath(parentKey);
    const parent = path ? this.getNodeAtPath(path) : null;
    if (!this.isNavContainer(parent)) return;
    if (!Array.isArray(parent.children)) parent.children = [];
    parent.children.push(folder);
    this.expandNavAncestors(path);
    const parentCollapseKey = this.navCollapseKey(parent);
    if (parentCollapseKey) this.collapsed.delete(parentCollapseKey);
    this.persistNavCollapsed();
    this.ensureFolderChildren(this.navTree);
    const newKey = this.navNodeKey(folder);
    this.activeKey = newKey;
    try {
      await this.persistNav();
      this.renderNav();
      this.render();
      this.scrollNavRowIntoView(newKey);
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.renameNavNode = async function renameNavNode(key) {
    if (!this.canEditNav) return;
    const path = this.findNodePath(key);
    const node = path ? this.getNodeAtPath(path) : null;
    const depth = path ? this.navNodeDepth(path) : 0;
    if (!node || !this.navNodeSupportsRename(node, depth)) return;
    if (node.kind === 'folder') {
      const next = await openNavTextPrompt('分组名称', node.label || '');
      if (!next || !String(next).trim() || String(next).trim() === node.label) return;
      node.label = String(next).trim();
    } else if (node.kind === 'cap') {
      const current = this.navNodeLabel(node);
      const next = await openNavTextPrompt('能力接口名称', current);
      if (!next || !String(next).trim() || String(next).trim() === current) return;
      node.label = String(next).trim();
    } else {
      const current = this.navNodeLabel(node);
      const next = await openNavTextPrompt('目录显示名称', current);
      if (!next || !String(next).trim() || String(next).trim() === current) return;
      node.navLabel = String(next).trim();
    }
    try {
      await this.persistNav();
      this.renderNav();
      this.render();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.deleteNavNode = async function deleteNavNode(key) {
    const path = this.findNodePath(key);
    const node = path ? this.getNodeAtPath(path) : null;
    const depth = path ? this.navNodeDepth(path) : 0;
    if (!node || !this.navNodeSupportsDelete(node, depth)) return;
    if (node.kind === 'folder' && !this.canDeleteNav) {
      await openNavAlert('仅超级管理员可删除分组');
      return;
    }
    if ((node.kind === 'module' || node.kind === 'playbook') && !this.canEditNav) return;
    const label = this.navNodeLabel(node);
    const childCount = (node.children || []).length;
    const parentPath = this.parentFolderPath(path);
    const destLabel = parentPath ? (this.getNodeAtPath(parentPath)?.label || '上级分组') : '全部';
    const ok = await openNavConfirm(
      node.kind === 'folder'
        ? (childCount
          ? `删除「${label}」？子项将归属到「${destLabel}」。`
          : `删除「${label}」？`)
        : (childCount
          ? `从目录移除「${label}」？子项将归属到「${destLabel}」。`
          : `从目录移除「${label}」？`),
    );
    if (!ok) return;
    const list = this.getParentListForPath(path);
    const idx = path[path.length - 1];
    if (typeof idx !== 'number' || !Array.isArray(list)) return;
    const children = (node.children || []).slice();
    list.splice(idx, 1, ...children);
    if (this.activeKey === key) this.activeKey = 'all';
    try {
      await this.persistNav();
      this.renderNav({ preserveScroll: true });
      this.render();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.moveNavNode = async function moveNavNode(fromPath, toParentPath, toIndex) {
    if (!this.canEditNav) return;
    if (this.cannotDropInside(fromPath, toParentPath)) return;
    const fromParent = this.parentFolderPath(fromPath);
    const fromIndex = fromPath[fromPath.length - 1];
    const sameParent = JSON.stringify(fromParent || null) === JSON.stringify(toParentPath || null);
    let insertAt = toIndex;
    if (sameParent && fromIndex < toIndex) insertAt -= 1;
    const node = this.removeNodeAtPath(fromPath);
    if (!node) return;
    let destParentPath = toParentPath;
    let destIndex = insertAt;
    if (!sameParent) {
      if (toParentPath && toParentPath.length) {
        destParentPath = this.adjustNavItemPathAfterRemoval(fromPath, toParentPath);
      } else if (fromPath.length === 1 && typeof destIndex === 'number' && fromPath[0] < destIndex) {
        destIndex -= 1;
      }
    }
    if (node.kind === 'folder') {
      if (!destParentPath || !destParentPath.length) {
        delete node.subfolder;
      } else {
        node.subfolder = true;
      }
    }
    if (!this.insertNode(destParentPath, destIndex, node)) {
      this.insertNode(fromParent, fromIndex, node);
      return;
    }
    const toParent = destParentPath && destParentPath.length
      ? this.getNodeAtPath(destParentPath)
      : null;
    if (toParent && this.isNavContainer(toParent)) this.sortNavContainerChildren(toParent);
    if (fromParent && fromParent.length) {
      const fromParentNode = this.getNodeAtPath(
        this.adjustNavItemPathAfterRemoval(fromPath, fromParent),
      );
      if (fromParentNode && this.isNavContainer(fromParentNode)) {
        this.sortNavContainerChildren(fromParentNode);
      }
    }
    if (destParentPath && destParentPath.length) {
      this.expandNavAncestors(destParentPath);
      const parent = this.getNodeAtPath(destParentPath);
      const ck = this.navCollapseKey(parent);
      if (ck) this.collapsed.delete(ck);
      this.persistNavCollapsed();
    }
    try {
      await this.persistNav();
      this.renderNav({ preserveScroll: true });
      this.render();
    } catch (err) {
      this.removeNodeAtPath(this.findNodePath(this.navNodeKey(node)));
      this.insertNode(fromParent, fromIndex, node);
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.bindNavEvents = function bindNavEvents(nav) {
    nav.querySelectorAll('.nav-select').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        const row = e.target.closest('.nav-row');
        if (!row) return;
        this.selectNavKey(row.getAttribute('data-nav-key'));
      });
    });
    nav.querySelectorAll('.nav-fold').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const collapseKey = btn.getAttribute('data-collapse-key');
        if (!collapseKey) return;
        if (this.collapsed.has(collapseKey)) this.collapsed.delete(collapseKey);
        else this.collapsed.add(collapseKey);
        this.persistNavCollapsed();
        this.renderNav({ preserveScroll: true });
      });
    });
    if (!nav._catalogNavContextBound) {
      nav._catalogNavContextBound = true;
      nav.addEventListener('contextmenu', async (e) => {
        const row = e.target.closest('.nav-row');
        if (!row || !nav.contains(row)) return;
        const key = row.getAttribute('data-nav-key') || '';
        const nodePath = this.findNodePath(key);
        const node = nodePath ? this.getNodeAtPath(nodePath) : null;
        if (!node) return;
        e.preventDefault();
        e.stopPropagation();
        this.hideNavMenu();
        if (node.kind === 'cap') {
          if (!this.canEditNav) {
            await openNavAlert('仅管理员可编辑能力分组');
            return;
          }
        } else if (!this.canEditNav && !this.canDeleteNav) {
          await openNavAlert('仅管理员可编辑能力分组');
          return;
        } else if (!this.canEditNav && node.kind !== 'folder') return;
        if (!this.canEditNav && node.kind === 'all') return;
        this.showNavContextMenu(e.clientX, e.clientY, key);
      }, true);
    }

    if (!this.canEditNav) return;

    if (!this._navDragDocBound) {
      this._navDragDocBound = true;
      const blockNavDragNavigate = (e) => {
        if (!this._navDragActive && !this._dragNodePath) return;
        e.preventDefault();
      };
      ['dragenter', 'dragover', 'drop'].forEach((type) => {
        document.addEventListener(type, blockNavDragNavigate, true);
      });
    }

    const onNavTreeDragOver = (e) => {
      if (!this._dragNodePath) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    };
    nav.addEventListener('dragover', onNavTreeDragOver);
    nav.addEventListener('drop', (e) => {
      if (!this._dragNodePath) return;
      e.preventDefault();
      e.stopPropagation();
    });

    const bindNavRowDropTarget = (row) => {
      row.addEventListener('dragover', (e) => {
        if (!this._dragNodePath) return;
        e.preventDefault();
        const key = row.getAttribute('data-nav-key') || '';
        const rect = row.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const targetPath = this.navItemPathFromRow(row);
        if (!targetPath) return;
        this.applyNavDropIndicator(nav, row, this._dragNodePath, targetPath, y, rect.height);
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = this.isNavDropPlacementAllowed(
            this._dragNodePath,
            this.resolveNavDropTarget(targetPath, y, rect.height, this._dragNodePath),
          ) ? 'move' : 'none';
        }
      });
      row.addEventListener('dragleave', (e) => {
        const related = e.relatedTarget;
        if (related && row.contains(related)) return;
        if (related && typeof related.closest === 'function' && related.closest('.nav-row')) return;
      });
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!this._dragNodePath) return;
        const fromPath = this._dragNodePath.slice();
        const fromNode = this.getNodeAtPath(fromPath);
        if (fromNode && fromNode.kind === 'all') return;
        const targetPath = this.navItemPathFromRow(row);
        if (!targetPath) return;
        const targetNode = this.getNodeAtPath(targetPath);
        const fromKey = this.navNodeKey(fromNode);
        if (fromKey && fromKey === this.navNodeKey(targetNode)) {
          if (JSON.stringify(fromPath) === JSON.stringify(targetPath)) return;
        }
        const rect = row.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const drop = this.resolveNavDropTarget(targetPath, y, rect.height, fromPath);
        if (!this.isNavDropPlacementAllowed(fromPath, drop)) return;
        this._pendingNavMove = {
          fromPath,
          toParentPath: drop.toParentPath,
          toIndex: drop.toIndex,
        };
      });
    };

    nav.querySelectorAll('.nav-row[draggable="true"]').forEach((row) => {
      row.addEventListener('dragstart', (e) => {
        const key = row.getAttribute('data-nav-key');
        const path = this.navItemPathFromRow(row);
        this._dragNodePath = path;
        this._navDragActive = true;
        this._pendingNavMove = null;
        row.classList.add('is-dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          // 勿写入 cat: / folder: 等可被 WebKit 当作 URL 导航的 text/plain
          e.dataTransfer.setData('text/plain', 'catalog-nav-reorder');
          e.dataTransfer.setData('application/x-catalog-nav-drag', key || '');
        }
      });
      row.addEventListener('dragend', () => {
        row.classList.remove('is-dragging');
        this.clearNavDropIndicators(nav);
        const pending = this._pendingNavMove;
        this._pendingNavMove = null;
        this._dragNodePath = null;
        this._navDragActive = false;
        if (pending) {
          this.moveNavNode(pending.fromPath, pending.toParentPath, pending.toIndex);
        }
      });
      bindNavRowDropTarget(row);
    });

    const allRow = nav.querySelector('.nav-row[data-nav-key="all"]');
    if (allRow) bindNavRowDropTarget(allRow);

    if (!this._navMenuDocBound) {
      this._navMenuDocBound = true;
      const dismissMenu = (e) => {
        if (this._navMenuEl && !this._navMenuEl.hidden && !this._navMenuEl.contains(e.target)) {
          this.hideNavMenu();
        }
      };
      document.addEventListener('click', dismissMenu);
      document.addEventListener('scroll', () => this.hideNavMenu(), true);
    }
  };

  CatalogPanel.prototype.promptEditRefs = function promptEditRefs() {
    return {
      modal: document.getElementById('catalog-prompt-edit-modal'),
      title: document.getElementById('catalog-prompt-edit-title'),
      hint: document.getElementById('catalog-prompt-edit-hint'),
      textarea: document.getElementById('catalog-prompt-edit-textarea'),
      insertBtn: document.getElementById('catalog-prompt-edit-insert'),
      cancel: document.getElementById('catalog-prompt-edit-cancel'),
      submit: document.getElementById('catalog-prompt-edit-submit'),
    };
  };

  CatalogPanel.prototype.ensurePromptMenu = function ensurePromptMenu() {
    if (this._promptMenuEl) return this._promptMenuEl;
    const menu = document.createElement('div');
    menu.className = 'catalog-prompt-menu';
    menu.hidden = true;
    menu.innerHTML =
      '<button type="button" data-action="edit">编辑</button>' +
      '<button type="button" data-action="add">添加快捷提示</button>' +
      '<button type="button" data-action="delete-cap">删除能力</button>' +
      '<button type="button" data-action="delete">删除</button>';
    menu.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn || !this._promptMenuTarget) return;
      const action = btn.getAttribute('data-action');
      const target = this._promptMenuTarget;
      this.hidePromptMenu();
      if (action === 'edit') {
        if (target.contextKind === 'header') this.editCapName(target);
        else this.openPromptEditDialog(target);
      } else if (action === 'add') {
        this.openPromptEditDialog({ ...target, mode: 'append' });
      } else if (action === 'delete-cap') {
        this.deleteRegistryCapability(target);
      } else if (action === 'delete') {
        this.deletePromptLine(target);
      }
    });
    document.body.appendChild(menu);
    this._promptMenuEl = menu;
    return menu;
  };

  CatalogPanel.prototype.hidePromptMenu = function hidePromptMenu() {
    if (this._promptMenuEl) {
      this._promptMenuEl.hidden = true;
      this._promptMenuEl.classList.remove('is-open');
    }
    this._promptMenuTarget = null;
  };

  CatalogPanel.prototype.showPromptContextMenu = function showPromptContextMenu(clientX, clientY, target) {
    const menu = this.ensurePromptMenu();
    const editBtn = menu.querySelector('[data-action="edit"]');
    const addBtn = menu.querySelector('[data-action="add"]');
    const deleteCapBtn = menu.querySelector('[data-action="delete-cap"]');
    const deleteBtn = menu.querySelector('[data-action="delete"]');
    const isHeader = target.contextKind === 'header';
    if (editBtn) editBtn.hidden = false;
    if (addBtn) addBtn.hidden = !isHeader;
    if (deleteCapBtn) deleteCapBtn.hidden = !isHeader || !this.canDeleteNav;
    if (deleteBtn) deleteBtn.hidden = isHeader;
    this._promptMenuTarget = target;
    menu.hidden = false;
    menu.classList.add('is-open');
    menu.style.visibility = 'hidden';
    menu.style.left = '0px';
    menu.style.top = '0px';
    const menuRect = menu.getBoundingClientRect();
    const left = Math.min(Math.max(8, clientX), window.innerWidth - menuRect.width - 8);
    const top = Math.min(Math.max(8, clientY), window.innerHeight - menuRect.height - 8);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.visibility = '';
  };

  CatalogPanel.prototype.insertPromptPlaceholderAtCursor = function insertPromptPlaceholderAtCursor(textarea) {
    if (!textarea) return;
    const snippet = '<param|说明>';
    const start = textarea.selectionStart ?? textarea.value.length;
    const end = textarea.selectionEnd ?? start;
    const before = textarea.value.slice(0, start);
    const after = textarea.value.slice(end);
    textarea.value = before + snippet + after;
    const pos = start + snippet.length;
    textarea.focus();
    textarea.setSelectionRange(pos, pos);
  };

  CatalogPanel.prototype.openPromptEditDialog = function openPromptEditDialog(target) {
    const refs = this.promptEditRefs();
    if (!refs.modal || !refs.textarea) {
      window.prompt('快捷提示语', target.promptRaw || '');
      return;
    }
    const isAppend = target.mode === 'append';
    this._promptEditTarget = target;
    refs.title.textContent = isAppend ? '添加快捷提示' : '编辑快捷提示';
    if (refs.hint) refs.hint.hidden = false;
    refs.textarea.value = isAppend ? '' : (target.promptRaw || '');
    refs.modal.hidden = false;
    requestAnimationFrame(() => refs.modal.classList.add('open'));
    refs.textarea.focus();
    if (!isAppend) refs.textarea.select();
  };

  CatalogPanel.prototype.closePromptEditDialog = function closePromptEditDialog() {
    const refs = this.promptEditRefs();
    this._promptEditTarget = null;
    if (!refs.modal) return;
    refs.modal.classList.remove('open');
    window.setTimeout(() => {
      if (refs.modal) refs.modal.hidden = true;
    }, 200);
  };

  CatalogPanel.prototype.editCapName = async function editCapName(target) {
    if (!target || !this.savePrompt) return;
    const current = String(target.capName || '').trim();
    const currentTagId = String(target.sourceTagId || target.sourceId || '').trim();
    const sources = this.collectAllRegistrySources();
    if (!sources.length) {
      await openNavAlert('无可用来源模块');
      return;
    }
    const picked = await openNavAddCapabilityPrompt({
      title: '编辑能力名称',
      sources,
      defaultValue: current,
      defaultSourceId: currentTagId,
    });
    if (picked == null) return;
    const name = String(picked.name || '').trim();
    const sourceTagId = String(picked.sourceId || '').trim();
    if (!name) {
      await openNavAlert('能力名称不能为空');
      return;
    }
    if (!sourceTagId) {
      await openNavAlert('请选择来源标签');
      return;
    }
    if (name === current && sourceTagId === currentTagId) return;
    const payload = {
      source_id: target.sourceId,
      registry_id: target.registryId,
      name,
      source_tag: sourceTagId,
    };
    try {
      await this.savePrompt(payload);
      if (this.onPromptsSaved) await this.onPromptsSaved();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.ensureModuleMenu = function ensureModuleMenu() {
    if (this._moduleMenuEl) return this._moduleMenuEl;
    const menu = document.createElement('div');
    menu.className = 'catalog-prompt-menu catalog-module-menu';
    menu.hidden = true;
    menu.innerHTML =
      '<button type="button" data-action="add-cap">添加能力</button>' +
      '<button type="button" data-action="add-moa">添加 MOA 能力</button>';
    menu.addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn || !this._moduleMenuTarget) return;
      const action = btn.getAttribute('data-action');
      const target = this._moduleMenuTarget;
      this.hideModuleMenu();
      if (action === 'add-cap') this.addRegistryCapability(target);
      else if (action === 'add-moa') this.startMoaGenerativeAdd(target);
    });
    document.body.appendChild(menu);
    this._moduleMenuEl = menu;
    return menu;
  };

  CatalogPanel.prototype.hideModuleMenu = function hideModuleMenu() {
    if (this._moduleMenuEl) {
      this._moduleMenuEl.hidden = true;
      this._moduleMenuEl.classList.remove('is-open');
    }
    this._moduleMenuTarget = null;
  };

  CatalogPanel.prototype.showModuleContextMenu = function showModuleContextMenu(clientX, clientY, target) {
    const menu = this.ensureModuleMenu();
    const addMoaBtn = menu.querySelector('[data-action="add-moa"]');
    const isMoa = target.moduleId === 'moa';
    if (addMoaBtn) addMoaBtn.hidden = !isMoa;
    this._moduleMenuTarget = target;
    menu.hidden = false;
    menu.classList.add('is-open');
    menu.style.visibility = 'hidden';
    menu.style.left = '0px';
    menu.style.top = '0px';
    const menuRect = menu.getBoundingClientRect();
    const left = Math.min(Math.max(8, clientX), window.innerWidth - menuRect.width - 8);
    const top = Math.min(Math.max(8, clientY), window.innerHeight - menuRect.height - 8);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.style.visibility = '';
  };

  CatalogPanel.prototype.addRegistryCapability = async function addRegistryCapability(target) {
    if (!target || !this.savePrompt) return;
    let { moduleId, category } = target;
    if (!moduleId) {
      await openNavAlert('无法确定所属模块');
      return;
    }
    if (!category) {
      const picked = await openNavTextPrompt('registry 分类名（category）');
      if (picked == null) return;
      category = String(picked).trim();
      if (!category) {
        await openNavAlert('分类不能为空');
        return;
      }
    }
    const categorySources = this.collectRegistrySourcesForCategory(category);
    const sources = this.collectAllRegistrySources();
    if (!sources.length) {
      await openNavAlert('无可用来源模块');
      return;
    }
    const ownerSourceId = categorySources[0]?.id || sources[0]?.id || '';
    const defaultSourceId = ownerSourceId;
    const picked = await openNavAddCapabilityPrompt({
      title: '新能力名称',
      sources,
      defaultSourceId,
    });
    if (picked == null) return;
    const name = String(picked.name || '').trim();
    const sourceTagId = String(picked.sourceId || '').trim();
    if (!name) {
      await openNavAlert('能力名称不能为空');
      return;
    }
    if (!sourceTagId) {
      await openNavAlert('请选择来源标签');
      return;
    }
    if (!ownerSourceId) {
      await openNavAlert('无法确定 registry 所属模块');
      return;
    }
    try {
      await this.savePrompt({
        source_id: ownerSourceId,
        add_item: { category, name, source_tag: sourceTagId },
      });
      if (this.onPromptsSaved) await this.onPromptsSaved();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '添加失败');
    }
  };

  CatalogPanel.prototype.startMoaGenerativeAdd = function startMoaGenerativeAdd(target) {
    const category = String(target?.category || '').trim() || 'MOA';
    const text =
      `请按 MOA-generative / Tunnel 抓包入库流程，在 registry 分类「${category}」下新增一条 MOA 能力：` +
      '（补充接口场景、抓包 userId、期望 method/serviceUrl）';
    if (typeof this.onRunPrompt === 'function') this.onRunPrompt(text);
  };

  CatalogPanel.prototype.deleteRegistryCapability = async function deleteRegistryCapability(target) {
    if (!target || !this.savePrompt) return;
    if (!this.canDeleteNav) {
      await openNavAlert('仅超级管理员可删除能力');
      return;
    }
    const label = String(target.capName || target.registryId || '该能力').trim();
    const moaHint = target.isMoa ? '将同时移除 registry 与 MOA 模板文件。' : '将从 registry 中移除该能力。';
    const ok = await openNavConfirm(`确定删除能力「${label}」？${moaHint}`);
    if (!ok) return;
    try {
      await this.savePrompt({
        source_id: target.sourceId,
        registry_id: target.registryId,
        delete_item: true,
      });
      if (this.onPromptsSaved) await this.onPromptsSaved();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '删除失败');
    }
  };

  CatalogPanel.prototype.deletePromptLine = async function deletePromptLine(target) {
    if (!target || !this.savePrompt) return;
    const ok = await openNavConfirm('确定删除这条快捷提示？');
    if (!ok) return;
    try {
      await this.savePrompt({
        source_id: target.sourceId,
        registry_id: target.registryId,
        delete_prompt_index: target.promptIndex,
      });
      if (this.onPromptsSaved) await this.onPromptsSaved();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '删除失败');
    }
  };

  CatalogPanel.prototype.savePromptEditDialog = async function savePromptEditDialog() {
    const target = this._promptEditTarget;
    const refs = this.promptEditRefs();
    if (!target || !refs.textarea) return;
    const text = String(refs.textarea.value || '').trim();
    if (!text) {
      await openNavAlert('快捷提示语不能为空');
      return;
    }
    if (!this.savePrompt) {
      await openNavAlert('当前环境无法保存');
      return;
    }
    const payload = {
      source_id: target.sourceId,
      registry_id: target.registryId,
    };
    if (target.mode === 'append') payload.append_prompt = text;
    else {
      payload.prompt_index = target.promptIndex;
      payload.prompt = text;
    }
    try {
      await this.savePrompt(payload);
      this.closePromptEditDialog();
      if (this.onPromptsSaved) await this.onPromptsSaved();
    } catch (err) {
      await openNavAlert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.bindPromptEditDialog = function bindPromptEditDialog() {
    if (this._promptEditBound) return;
    this._promptEditBound = true;
    const refs = this.promptEditRefs();
    refs.cancel?.addEventListener('click', () => this.closePromptEditDialog());
    refs.submit?.addEventListener('click', () => this.savePromptEditDialog());
    refs.insertBtn?.addEventListener('click', () => {
      this.insertPromptPlaceholderAtCursor(refs.textarea);
    });
    refs.modal?.addEventListener('click', (e) => {
      if (e.target === refs.modal) this.closePromptEditDialog();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const refsNow = this.promptEditRefs();
      if (refsNow.modal && !refsNow.modal.hidden) this.closePromptEditDialog();
    });
  };

  CatalogPanel.prototype.bindPromptContextMenus = function bindPromptContextMenus() {
    if (this._promptMenuDocBound) return;
    this._promptMenuDocBound = true;
    document.addEventListener('click', (e) => {
      if (this._promptMenuEl && !this._promptMenuEl.hidden && !this._promptMenuEl.contains(e.target)) {
        this.hidePromptMenu();
      }
      if (this._moduleMenuEl && !this._moduleMenuEl.hidden && !this._moduleMenuEl.contains(e.target)) {
        this.hideModuleMenu();
      }
    });
    document.addEventListener('scroll', () => {
      this.hidePromptMenu();
      this.hideModuleMenu();
    }, true);
  };

  CatalogPanel.prototype.bindEvents = function bindEvents() {
    this.bindPromptEditDialog();
    this.bindPromptContextMenus();
    if (this.searchEl) {
      this.searchEl.addEventListener('input', e => {
        this.query = e.target.value;
        this.render();
      });
    }
    this.root.addEventListener('click', e => {
      const runBtn = e.target.closest('.prompt-run');
      if (runBtn) {
        e.preventDefault();
        const line = runBtn.closest('.prompt-line');
        if (line) this.onRunPrompt(assemblePromptLine(line));
      }
    });
    this.root.addEventListener('contextmenu', async (e) => {
      const moduleHead = e.target.closest('.module-head[data-module-head]');
      const line = e.target.closest('.prompt-line');
      const head = e.target.closest('.cap[data-registry-id] .cap-head');
      if (moduleHead && !line && !head) {
        const categoryOnHead = String(moduleHead.getAttribute('data-category') || '').trim();
        if (!categoryOnHead) return;
        e.preventDefault();
        if (!this.canEditNav) {
          await openNavAlert('仅管理员可编辑能力');
          return;
        }
        const ctx = this.resolveModuleHeadContext(moduleHead);
        if (!ctx.moduleId) {
          await openNavAlert('当前视图未绑定单一模块，请进入具体分类后再添加');
          return;
        }
        if (!ctx.category) ctx.category = categoryOnHead;
        this.showModuleContextMenu(e.clientX, e.clientY, ctx);
        return;
      }
      if (!line && !head) return;
      e.preventDefault();
      if (!this.canEditNav) {
        await openNavAlert('仅管理员可编辑快捷提示语');
        return;
      }
      let sourceId = '';
      let registryId = '';
      if (line) {
        sourceId = line.getAttribute('data-source-id') || '';
        registryId = line.getAttribute('data-registry-id') || '';
        const promptIndex = Number.parseInt(line.getAttribute('data-prompt-index') || '0', 10);
        const promptRaw = line.getAttribute('data-prompt-raw') || '';
        if (!sourceId || !registryId) return;
        this.showPromptContextMenu(e.clientX, e.clientY, {
          sourceId,
          registryId,
          promptIndex,
          promptRaw,
          contextKind: 'line',
        });
        return;
      }
      const cap = head.closest('.cap[data-registry-id]');
      sourceId = cap?.getAttribute('data-source-id') || head.getAttribute('data-source-id') || '';
      registryId = cap?.getAttribute('data-registry-id') || head.getAttribute('data-registry-id') || '';
      const capName = head.getAttribute('data-cap-name') || '';
      const sourceTagId = cap?.getAttribute('data-source-tag-id') || sourceId;
      if (!sourceId || !registryId) return;
      this.showPromptContextMenu(e.clientX, e.clientY, {
        sourceId,
        sourceTagId,
        registryId,
        capName,
        isMoa: sourceId === 'moa',
        contextKind: 'header',
      });
    });
  };

  CatalogPanel.prototype.init = async function init(fetchData) {
    this.bindEvents();
    await this.load(fetchData);
  };

  global.CatalogPanel = CatalogPanel;
})(window);
