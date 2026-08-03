/**
 * Web Agent · 工具台 MOA 录制面板
 * onSubmit({ text, attachments }) — 填完表单后写入提问栏，不自动发送
 */
(function (global) {
  'use strict';

  const MODES = [
    {
      id: 'screenshot',
      label: 'MOA 截图',
      desc: '上传 MOA 后台截图并说明功能',
      fields: [
        {
          id: 'intro',
          type: 'textarea',
          label: 'MOA 介绍',
          placeholder: '说明该 MOA 的用途、参数含义、注意事项…',
          required: true,
        },
        {
          id: 'screenshot',
          type: 'file',
          label: 'MOA 截图',
          accept: 'image/*',
          required: true,
        },
      ],
      buildPrompt(data) {
        return [
          '根据附件 MOA 后台截图录制 MOA。',
          '',
          `功能说明：${data.intro}`,
          '',
          '请解析截图中的 ServiceUrl、Method、参数结构，生成 MOA template 并登记 MOA/config/registry.json，调通后返回可执行命令。',
        ].join('\n');
      },
      collectAttachments(data) {
        const file = data.screenshot;
        if (!file) return [];
        return [{ file }];
      },
    },
    {
      id: 'full_request',
      label: '完整请求',
      desc: '粘贴网页检查器或抓包的完整请求',
      fields: [
        {
          id: 'intro',
          type: 'textarea',
          label: 'MOA 介绍',
          placeholder: '说明该 MOA 的用途、关键参数…',
          required: true,
        },
        {
          id: 'request',
          type: 'textarea',
          label: '完整请求',
          placeholder: '粘贴 Request URL、Headers、Body…',
          required: true,
          rows: 12,
          mono: true,
        },
      ],
      buildPrompt(data) {
        return [
          '根据以下完整 HTTP 请求录制 MOA。',
          '',
          `功能说明：${data.intro}`,
          '',
          '```',
          data.request,
          '```',
          '',
          '请解析请求生成 MOA payload/template，登记 MOA/config/registry.json 并调通验收。',
        ].join('\n');
      },
    },
    {
      id: 'tunnel_capture',
      label: '抓包账号行为',
      desc: '指定账号与操作，从 Tunnel 抓包生成 MOA',
      fields: [
        {
          id: 'account',
          type: 'text',
          label: '账号',
          placeholder: '手机号或 userId',
          required: true,
        },
        {
          id: 'behavior',
          type: 'textarea',
          label: '行为描述',
          placeholder: '如：邀请 80949067 跨房 PK',
          required: true,
        },
        {
          id: 'since',
          type: 'text',
          label: '抓包时间范围（秒）',
          placeholder: '默认 3600',
          value: '3600',
        },
      ],
      buildPrompt(data) {
        const since = String(data.since || '').trim() || '3600';
        return [
          `抓包${data.account}${data.behavior}的 tunnel（since ${since}s），并记录到 MOA。`,
          '',
          '请：1) Tunnel 拉取对应请求；2) 提取 body + 调用链 ServiceUrl/Method；',
          '3) 生成 MOA template 并登记 MOA/config/registry.json 与 MOA-generative/mappings.md；4) 调通验收。',
        ].join('\n');
      },
    },
    {
      id: 'server_code',
      label: '服务端代码',
      desc: '描述需要的 MOA，由服务端 Agent 查代码实现',
      fields: [
        {
          id: 'operation',
          type: 'textarea',
          label: '操作描述',
          placeholder: '如：录制跨房 PK 邀请 MOA，需 targetUserId、roomId 等参数，调通后返回可执行命令',
          required: true,
          rows: 6,
        },
      ],
      buildPrompt(data) {
        return [
          '请调用服务端 Agent 查代码实现，根据以下需求直接录制 MOA 并调通：',
          '',
          data.operation,
          '',
          '请：1) 定位对应接口/方法实现；2) 生成 MOA payload/template；',
          '3) 登记 MOA/config/registry.json 与 MOA-generative/mappings.md；4) 调通验收并返回可执行命令。',
        ].join('\n');
      },
      suggestExternalAgents: ['yaahlan_service'],
    },
  ];

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  async function readFileAsBase64(file) {
    const dataUrl = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('读取文件失败'));
      reader.readAsDataURL(file);
    });
    const comma = dataUrl.indexOf(',');
    return comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
  }

  function MoaRecordPanel(options) {
    this.modalEl = options.modalEl;
    this.bubbleEl = options.bubbleEl;
    this.modeListEl = options.modeListEl;
    this.formEl = options.formEl;
    this.formFieldsEl = options.formFieldsEl;
    this.formTitleEl = options.formTitleEl;
    this.formDescEl = options.formDescEl;
    this.submitEl = options.submitEl;
    this.closeEl = options.closeEl;
    this.onSubmit = options.onSubmit || function () {};
    this.animateClose = options.animateClose || null;
    this.open = false;
    this.activeMode = null;
    this._fileMap = {};
  }

  MoaRecordPanel.prototype.getMode = function getMode(id) {
    return MODES.find((item) => item.id === id) || null;
  };

  MoaRecordPanel.prototype.renderModeList = function renderModeList() {
    if (!this.modeListEl) return;
    this.modeListEl.innerHTML = MODES.map((mode) => `
      <button type="button" class="moa-record-mode" data-mode="${escapeHtml(mode.id)}"
              aria-pressed="false">
        <span class="moa-record-mode-label">${escapeHtml(mode.label)}</span>
        <span class="moa-record-mode-desc">${escapeHtml(mode.desc)}</span>
      </button>
    `).join('');
    this.updateModeSelection();
  };

  MoaRecordPanel.prototype.updateModeSelection = function updateModeSelection() {
    if (!this.modeListEl) return;
    this.modeListEl.querySelectorAll('[data-mode]').forEach((btn) => {
      const selected = Boolean(this.activeMode && btn.dataset.mode === this.activeMode.id);
      btn.classList.toggle('is-selected', selected);
      btn.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
  };

  MoaRecordPanel.prototype.renderField = function renderField(field) {
    const id = escapeHtml(field.id);
    const label = escapeHtml(field.label);
    const requiredMark = field.required ? '<span class="moa-record-required">*</span>' : '';
    if (field.type === 'file') {
      return `
        <div class="moa-record-field">
          <label for="moa-record-${id}">${label}${requiredMark}</label>
          <div class="moa-record-dropzone" tabindex="0" role="button"
               aria-label="拖拽或选择${label}">
            <input type="file" id="moa-record-${id}" name="${id}"
                   accept="${escapeHtml(field.accept || '')}" hidden />
            <div class="moa-record-dropzone-body">
              <span class="moa-record-dropzone-prompt">拖拽图片到此处，或点击选择</span>
              <span class="moa-record-dropzone-name"></span>
            </div>
          </div>
          <p class="moa-record-field-hint">支持 PNG / JPG / WebP 截图</p>
        </div>`;
    }
    if (field.type === 'textarea') {
      const rows = field.rows || 4;
      const monoClass = field.mono ? ' is-mono' : '';
      return `
        <div class="moa-record-field">
          <label for="moa-record-${id}">${label}${requiredMark}</label>
          <textarea id="moa-record-${id}" name="${id}" rows="${rows}"
                    class="${monoClass.trim()}"
                    placeholder="${escapeHtml(field.placeholder || '')}"></textarea>
        </div>`;
    }
    return `
      <div class="moa-record-field">
        <label for="moa-record-${id}">${label}${requiredMark}</label>
        <input type="text" id="moa-record-${id}" name="${id}"
               placeholder="${escapeHtml(field.placeholder || '')}"
               value="${escapeHtml(field.value || '')}" />
      </div>`;
  };

  MoaRecordPanel.prototype.showModeList = function showModeList() {
    this.activeMode = null;
    this._fileMap = {};
    if (this.formEl) this.formEl.hidden = true;
    if (this.submitEl) this.submitEl.hidden = true;
    this.updateModeSelection();
  };

  MoaRecordPanel.prototype.showForm = function showForm(modeId) {
    const mode = this.getMode(modeId);
    if (!mode) return;
    this.activeMode = mode;
    this._fileMap = {};
    if (this.formTitleEl) this.formTitleEl.textContent = mode.label;
    if (this.formDescEl) this.formDescEl.textContent = mode.desc;
    if (this.formFieldsEl) {
      this.formFieldsEl.innerHTML = (mode.fields || []).map((field) => this.renderField(field)).join('');
      this.formFieldsEl.querySelectorAll('.moa-record-dropzone').forEach((zone) => {
        this.bindDropzone(zone);
      });
    }
    if (this.formEl) this.formEl.hidden = false;
    if (this.submitEl) this.submitEl.hidden = false;
    this.updateModeSelection();
    const firstInput = this.formFieldsEl?.querySelector('input:not([type="file"]), textarea');
    if (firstInput) firstInput.focus();
  };

  MoaRecordPanel.prototype.bindDropzone = function bindDropzone(zone) {
    const input = zone.querySelector('input[type="file"]');
    if (!input) return;
    const nameEl = zone.querySelector('.moa-record-dropzone-name');
    const fieldName = input.name;

    const setFile = (file) => {
      if (!file) return;
      if (!(file.type || '').startsWith('image/')) {
        alert('请上传图片文件（PNG / JPG / WebP）');
        return;
      }
      this._fileMap[fieldName] = file;
      zone.classList.add('has-file');
      if (nameEl) nameEl.textContent = file.name;
    };

    zone.addEventListener('click', () => input.click());
    zone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        input.click();
      }
    });
    input.addEventListener('change', () => {
      const file = input.files && input.files[0] ? input.files[0] : null;
      if (file) setFile(file);
    });

    zone.addEventListener('dragenter', (event) => {
      event.preventDefault();
      zone.classList.add('is-dragover');
    });
    zone.addEventListener('dragover', (event) => {
      event.preventDefault();
      zone.classList.add('is-dragover');
    });
    zone.addEventListener('dragleave', (event) => {
      if (!zone.contains(event.relatedTarget)) {
        zone.classList.remove('is-dragover');
      }
    });
    zone.addEventListener('drop', (event) => {
      event.preventDefault();
      zone.classList.remove('is-dragover');
      const file = event.dataTransfer?.files?.[0];
      if (file) setFile(file);
    });
  };

  MoaRecordPanel.prototype.collectFormData = function collectFormData() {
    const mode = this.activeMode;
    if (!mode) return null;
    const data = {};
    for (const field of mode.fields || []) {
      if (field.type === 'file') {
        const inputEl = this.formFieldsEl?.querySelector(`[name="${field.id}"]`);
        const file = this._fileMap[field.id] || (inputEl?.files && inputEl.files[0]) || null;
        if (field.required && !file) {
          alert(`请上传${field.label}`);
          return null;
        }
        data[field.id] = file;
        continue;
      }
      const el = this.formFieldsEl?.querySelector(`[name="${field.id}"]`);
      const value = el ? String(el.value || '').trim() : '';
      if (field.required && !value) {
        alert(`请填写${field.label}`);
        if (el) el.focus();
        return null;
      }
      data[field.id] = value;
    }
    return data;
  };

  MoaRecordPanel.prototype.buildAttachments = async function buildAttachments(data) {
    const mode = this.activeMode;
    if (!mode || typeof mode.collectAttachments !== 'function') return [];
    const raw = mode.collectAttachments(data);
    const attachments = [];
    for (const item of raw) {
      const file = item.file;
      if (!file) continue;
      const data_base64 = await readFileAsBase64(file);
      const isImage = (file.type || '').startsWith('image/');
      attachments.push({
        name: file.name || 'screenshot.png',
        mime: file.type || 'image/png',
        kind: isImage ? 'image' : 'file',
        data_base64,
      });
    }
    return attachments;
  };

  MoaRecordPanel.prototype.handleSubmit = async function handleSubmit() {
    const mode = this.activeMode;
    if (!mode) return;
    const data = this.collectFormData();
    if (!data) return;
    const text = mode.buildPrompt(data);
    if (!text) return;
    if (this.submitEl) this.submitEl.disabled = true;
    try {
      const attachments = await this.buildAttachments(data);
      await this.onSubmit({
        text,
        attachments,
        modeId: mode.id,
        suggestExternalAgents: mode.suggestExternalAgents || [],
      });
      await this.setOpen(false);
    } catch (err) {
      alert(err.message || '填入输入框失败');
    } finally {
      if (this.submitEl) this.submitEl.disabled = false;
    }
  };

  MoaRecordPanel.prototype.setOpen = async function setOpen(open, opts = {}) {
    if (!this.modalEl) return;
    if (!open && this.open && !opts.skipAnimation && this.animateClose) {
      await this.animateClose(this.modalEl);
    }
    this.open = open;
    this.modalEl.classList.toggle('open', open);
    this.modalEl.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (open) {
      this.showModeList();
      this.renderModeList();
    }
  };

  MoaRecordPanel.prototype.bind = function bind() {
    this.renderModeList();
    this.modeListEl?.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-mode]');
      if (!btn) return;
      this.showForm(btn.dataset.mode);
    });
    this.submitEl?.addEventListener('click', () => { void this.handleSubmit(); });
    this.closeEl?.addEventListener('click', () => { void this.setOpen(false); });
    this.modalEl?.addEventListener('click', (event) => {
      if (event.target === this.modalEl) void this.setOpen(false);
    });
  };

  global.MoaRecordPanel = MoaRecordPanel;
  global.MoaRecordModes = MODES;
})(window);
