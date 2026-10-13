/**
 * 工具台能力目录面板（Web Agent 深色主题版）
 * onRunPrompt(text) — 填参后点击「执行」时回调（填入提问栏，不自动发送）
 */
(function (global) {
  'use strict';

  const PROMPT_PLACEHOLDER_RE = /<([^>|]+)(?:\|([^>]+))?>/g;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
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

  function navChevronSvg(collapsed) {
    if (collapsed) {
      return `<svg class="nav-chevron-svg" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.25 2.25 8 6l-3.75 3.75"/></svg>`;
    }
    return `<svg class="nav-chevron-svg" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.25 4.25 6 8l3.75-3.75"/></svg>`;
  }

  function defaultNavTree(data) {
    const tree = [{ kind: 'all' }];
    const playbooks = data?.playbooks || [];
    if (playbooks.length) tree.push({ kind: 'playbook' });
    for (const mod of data?.modules || []) {
      if (mod?.id) tree.push({ kind: 'module', moduleId: mod.id });
    }
    return tree;
  }

  function CatalogPanel(options) {
    this.onRunPrompt = options.onRunPrompt || function () {};
    this.root = options.root;
    this.metaEl = options.metaEl;
    this.searchEl = options.searchEl;
    this.navEl = options.navEl;
    this.mainEl = options.mainEl;
    this.envCheckBtn = options.envCheckBtn || null;
    this.canEditNav = !!options.canEditNav;
    this.canDeleteNav = !!options.canDeleteNav;
    this.saveNav = options.saveNav || null;
    this.DATA = null;
    this.activeKey = 'all';
    this.navTree = [];
    this.collapsed = new Set();
    this.query = '';
    this._navMenuEl = null;
    this._navMenuTarget = null;
    this._dragNodePath = null;
  }

  CatalogPanel.prototype.load = async function load(fetchData) {
    this.DATA = typeof fetchData === 'function' ? await fetchData() : fetchData;
    if (this.metaEl && this.DATA) {
      this.metaEl.textContent = `${this.DATA.module_count} 模块 · ${this.DATA.total_items} 能力`;
    }
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
    this.resetNavCollapsedAll();
    this.renderNav();
    this.render();
  };

  CatalogPanel.prototype.navCollapseKey = function navCollapseKey(node) {
    if (!node) return '';
    if (node.kind === 'folder') return String(node.id || '');
    if (node.kind === 'module') return `module:${node.moduleId}`;
    if (node.kind === 'playbook') return 'playbook';
    return '';
  };

  CatalogPanel.prototype.isNavContainer = function isNavContainer(node) {
    return !!node && (node.kind === 'folder' || node.kind === 'module' || node.kind === 'playbook');
  };

  CatalogPanel.prototype.hasFolderChildren = function hasFolderChildren(node) {
    return (node?.children || []).some((child) => child && child.kind === 'folder');
  };

  CatalogPanel.prototype.navRowIsBranch = function navRowIsBranch(node) {
    if (!this.isNavContainer(node)) return false;
    if (node.kind === 'folder' || node.kind === 'module' || node.kind === 'playbook') return true;
    return this.hasFolderChildren(node);
  };

  CatalogPanel.prototype.navRowShowsFolderIcon = function navRowShowsFolderIcon(node) {
    if (!node) return false;
    return node.kind === 'folder' || node.kind === 'module' || node.kind === 'playbook';
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
    if (node.kind === 'folder') return true;
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

  CatalogPanel.prototype.navNodeKey = function navNodeKey(node) {
    if (!node || !node.kind) return '';
    if (node.kind === 'all') return 'all';
    if (node.kind === 'playbook') return 'playbook';
    if (node.kind === 'module') return `module:${node.moduleId}`;
    if (node.kind === 'folder') return `folder:${node.id}`;
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
    return '';
  };

  CatalogPanel.prototype.navNodeCount = function navNodeCount(node) {
    if (!node) return 0;
    if (node.kind === 'all') return this.DATA?.total_items || 0;
    if (node.kind === 'playbook') return this.playbookCount();
    if (node.kind === 'module') {
      let sum = 0;
      for (const child of node.children || []) sum += this.navNodeCount(child);
      if (sum > 0) return sum;
      const mod = this.moduleById(node.moduleId);
      return mod?.item_count || 0;
    }
    if (node.kind === 'folder') {
      let sum = 0;
      for (const child of node.children || []) sum += this.navNodeCount(child);
      return sum;
    }
    return 0;
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
    if (key.startsWith('module:')) return { mode: 'modules', moduleIds: new Set([key.slice(7)]) };
    if (key.startsWith('folder:')) {
      const folderId = key.slice(7);
      const folder = this.findFolderById(folderId);
      const moduleIds = folder ? this.collectModuleIds(folder) : new Set();
      return { mode: 'modules', moduleIds };
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
      if (this.isNavContainer(node)) {
        const nested = this.findNodePath(key, node.children || [], pathPrefix.concat([i, 'children']));
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

  CatalogPanel.prototype.resolveNavDropTarget = function resolveNavDropTarget(targetPath, y, rectHeight) {
    const targetNode = this.getNodeAtPath(targetPath);
    if (this.isDropInsideZone(targetNode, y, rectHeight)) {
      if (!Array.isArray(targetNode.children)) targetNode.children = [];
      return { toParentPath: targetPath, toIndex: targetNode.children.length };
    }
    return {
      toParentPath: this.parentFolderPath(targetPath),
      toIndex: targetPath[targetPath.length - 1] + (y >= rectHeight / 2 ? 1 : 0),
    };
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

  CatalogPanel.prototype.renderPromptLine = function renderPromptLine(text) {
    const spanParts = [];
    let last = 0;
    let m;
    const re = new RegExp(PROMPT_PLACEHOLDER_RE.source, 'g');
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) spanParts.push(escapeHtml(text.slice(last, m.index)));
      const key = m[1];
      const label = (m[2] || key).trim();
      const width = Math.min(12, Math.max(4, label.length + 1));
      spanParts.push(
        `<input type="text" class="prompt-field" data-key="${escapeHtml(key)}" ` +
        `placeholder="${escapeHtml(label)}" aria-label="${escapeHtml(label)}" ` +
        `style="width:${width}em">`
      );
      last = re.lastIndex;
    }
    if (last < text.length) spanParts.push(escapeHtml(text.slice(last)));
    return `<div class="prompt-line">
      <span class="prompt-text">${spanParts.join('')}</span>
      <div class="prompt-line-footer">
        <button type="button" class="prompt-run" title="填入提问栏">执行</button>
      </div>
    </div>`;
  };

  CatalogPanel.prototype.renderCapItem = function renderCapItem(item) {
    const prompts = item.prompts || [];
    const hasPrompts = prompts.length > 0;
    const promptHtml = prompts.map(t => this.renderPromptLine(t)).join('');
    const headToggle = hasPrompts ? ' is-toggle' : '';
    const headAria = hasPrompts ? ' aria-expanded="false"' : '';
    const source = item.source
      ? `<span class="source-badge" data-env="${escapeHtml(item.env || '')}" data-source-id="${escapeHtml(item.source_id || '')}">${escapeHtml(item.source)}</span>`
      : '';
    const chevron = hasPrompts ? '<span class="cap-chevron" aria-hidden="true">▸</span>' : '';
    return `<li class="cap">
      <div class="cap-head${headToggle}"${headAria}>
        ${chevron}
        <span class="cap-icon" aria-hidden="true">${smallIcon('spark')}</span>
        <div class="cap-main">
          <span class="cap-name">${escapeHtml(item.name)}</span>
          ${source}
        </div>
      </div>
      <div class="prompt-panel" hidden>${hasPrompts ? `<div class="prompt-list">${promptHtml}</div>` : ''}</div>
    </li>`;
  };

  CatalogPanel.prototype.bindPromptToggles = function bindPromptToggles(root) {
    root.querySelectorAll('.cap-head.is-toggle').forEach(head => {
      head.addEventListener('click', () => {
        const panel = head.closest('.cap').querySelector('.prompt-panel');
        const open = head.getAttribute('aria-expanded') === 'true';
        head.setAttribute('aria-expanded', open ? 'false' : 'true');
        panel.hidden = open;
      });
    });
  };

  CatalogPanel.prototype.bindPromptPanels = function bindPromptPanels(root) {
    this.bindPromptToggles(root);
  };

  CatalogPanel.prototype.renderPlaybookStep = function renderPlaybookStep(step) {
    const ops = (step.operations || []).map(op => `<li>${escapeHtml(op)}</li>`).join('');
    const prompts = (step.prompts || []).map(t => this.renderPromptLine(t)).join('');
    const title = step.workflowName || step.workflowId || step.note || `步骤 ${step.order}`;
    const subParts = [];
    if (step.workflowId && step.workflowName) subParts.push(`<code>${escapeHtml(step.workflowId)}</code>`);
    if (step.sheet) subParts.push(`Sheet「${escapeHtml(step.sheet)}」`);
    const sub = subParts.join(' · ');
    const noteBlock = (step.note && title !== step.note)
      ? `<div class="playbook-step-note">${escapeHtml(step.note)}</div>` : '';
    return `<div class="playbook-step">
      <div class="playbook-step-head" aria-expanded="false">
        <span class="playbook-step-num">${step.order}</span>
        <div>
          <div class="playbook-step-title">${escapeHtml(title)}</div>
          ${sub ? `<div class="playbook-step-sub">${sub}</div>` : ''}
        </div>
      </div>
      <div class="playbook-step-body" hidden>
        ${noteBlock}
        ${ops ? `<ol class="playbook-ops">${ops}</ol>` : ''}
        ${prompts ? `<div class="prompt-list">${prompts}</div>` : ''}
      </div>
    </div>`;
  };

  CatalogPanel.prototype.renderPlaybook = function renderPlaybook(pb) {
    const defaults = Object.entries(pb.defaults || {})
      .map(([k, v]) => `<span class="default-chip"><code>${escapeHtml(k)}</code> ${escapeHtml(v)}</span>`)
      .join('');
    const steps = (pb.steps || []).map(s => this.renderPlaybookStep(s)).join('');
    const topPrompts = (pb.prompts || []).map(t => this.renderPromptLine(t)).join('');
    const stepCount = (pb.steps || []).length;
    return `<section class="playbook-section" id="playbook-${escapeHtml(pb.id)}">
      <div class="playbook-head">
        <h3>${escapeHtml(pb.title)}</h3>
        <p class="playbook-summary">${escapeHtml(pb.summary || '')}</p>
        <div class="playbook-tag-row">
          <span class="playbook-tag">${escapeHtml(pb.category || '工作流')}</span>
          <span class="playbook-tag">${stepCount} 步</span>
        </div>
        ${defaults ? `<div class="playbook-defaults">${defaults}</div>` : ''}
        ${topPrompts ? `<div class="prompt-list" style="margin-top:10px">${topPrompts}</div>` : ''}
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

  CatalogPanel.prototype.renderPlaybooks = function renderPlaybooks(container) {
    const playbooks = this.DATA.playbooks || [];
    if (!playbooks.length) return;
    const filter = this.activeFilter();
    if (filter.mode !== 'all' && filter.mode !== 'playbook') return;
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
    if ((this.DATA.playbooks || []).length && (filter.mode === 'all' || filter.mode === 'playbook')) {
      any = true;
    }

    for (const mod of this.DATA.modules) {
      if (filter.mode === 'playbook') continue;
      if (filter.mode === 'modules' && !filter.moduleIds.has(mod.id)) continue;

      let catsHtml = '';
      let visibleCount = 0;
      for (const cat of mod.categories) {
        const filtered = cat.items.filter(it => this.matches(it, mod.label, cat.name, q));
        if (!filtered.length) continue;
        visibleCount += filtered.length;
        const items = filtered.map(it => this.renderCapItem(it)).join('');
        catsHtml += `<li><span class="cat-name">${escapeHtml(cat.name)}</span><ul class="items">${items}</ul></li>`;
      }
      if (!visibleCount) continue;
      any = true;

      const section = document.createElement('section');
      section.className = 'catalog-module';
      section.id = 'catalog-mod-' + mod.id;
      section.innerHTML = `
        <div class="module-head">
          <span class="module-icon" aria-hidden="true">${smallIcon('module')}</span>
          <div>
            <h3>${escapeHtml(mod.label)}</h3>
            <div class="sub">${visibleCount} 项能力</div>
          </div>
        </div>
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
    const folderMark = showsFolderIcon
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

  CatalogPanel.prototype.renderNavNodes = function renderNavNodes(nodes, depth, pathPrefix) {
    const parts = [];
    (nodes || []).forEach((node, index) => {
      const pathKey = `${pathPrefix}:${index}`;
      parts.push(this.renderNavRow(node, depth, pathKey));
      const collapseKey = this.navCollapseKey(node);
      const branch = this.navRowIsBranch(node);
      if (branch && collapseKey && !this.collapsed.has(collapseKey)) {
        parts.push(`<div class="nav-children">${this.renderNavNodes(node.children || [], depth + 1, `${pathKey}:c`)}</div>`);
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
    const depth = this.navNodeDepth(nodePath);
    const canRename = this.navNodeSupportsRename(node, depth) && this.canEditNav;
    const canDeleteFolder = node.kind === 'folder' && this.canDeleteNav;
    const canDeleteNavRow = (node.kind === 'module' || node.kind === 'playbook')
      && depth === 0
      && this.canEditNav;
    if (addBtn) {
      addBtn.hidden = !this.canEditNav;
      addBtn.textContent = isAll ? '新建分组' : '添加子分组';
    }
    if (renameBtn) renameBtn.hidden = isAll || !canRename;
    if (deleteBtn) {
      deleteBtn.hidden = isAll || !(canDeleteFolder || canDeleteNavRow);
      if (deleteBtn) {
        deleteBtn.textContent = node.kind === 'folder' ? '删除' : '从目录移除';
      }
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
    const label = window.prompt('分组名称');
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
      window.alert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.addSubFolder = async function addSubFolder(parentKey) {
    if (!this.canEditNav) return;
    const label = window.prompt('子分组名称');
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
    this.ensureFolderChildren(this.navTree);
    const newKey = this.navNodeKey(folder);
    this.activeKey = newKey;
    try {
      await this.persistNav();
      this.renderNav();
      this.render();
      this.scrollNavRowIntoView(newKey);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.renameNavNode = async function renameNavNode(key) {
    if (!this.canEditNav) return;
    const path = this.findNodePath(key);
    const node = path ? this.getNodeAtPath(path) : null;
    const depth = path ? this.navNodeDepth(path) : 0;
    if (!node || !this.navNodeSupportsRename(node, depth)) return;
    if (node.kind === 'folder') {
      const next = window.prompt('分组名称', node.label || '');
      if (!next || !String(next).trim() || String(next).trim() === node.label) return;
      node.label = String(next).trim();
    } else {
      const current = this.navNodeLabel(node);
      const next = window.prompt('目录显示名称', current);
      if (!next || !String(next).trim() || String(next).trim() === current) return;
      node.navLabel = String(next).trim();
    }
    try {
      await this.persistNav();
      this.renderNav();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '保存失败');
    }
  };

  CatalogPanel.prototype.deleteNavNode = async function deleteNavNode(key) {
    const path = this.findNodePath(key);
    const node = path ? this.getNodeAtPath(path) : null;
    const depth = path ? this.navNodeDepth(path) : 0;
    if (!node || !this.navNodeSupportsDelete(node, depth)) return;
    if (node.kind === 'folder' && !this.canDeleteNav) {
      window.alert('仅超级管理员可删除分组');
      return;
    }
    if ((node.kind === 'module' || node.kind === 'playbook') && !this.canEditNav) return;
    const label = this.navNodeLabel(node);
    const childCount = (node.children || []).length;
    const parentPath = this.parentFolderPath(path);
    const destLabel = parentPath ? (this.getNodeAtPath(parentPath)?.label || '上级分组') : '全部';
    const ok = window.confirm(
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
      window.alert(err instanceof Error ? err.message : '保存失败');
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
    if (node.kind === 'folder') {
      if (!toParentPath || !toParentPath.length) {
        if (fromParent) node.subfolder = true;
      } else {
        node.subfolder = true;
      }
    }
    if (!this.insertNode(toParentPath, insertAt, node)) {
      this.insertNode(fromParent, fromIndex, node);
      return;
    }
    if (toParentPath && toParentPath.length) {
      this.expandNavAncestors(toParentPath);
      const parent = this.getNodeAtPath(toParentPath);
      const ck = this.navCollapseKey(parent);
      if (ck) this.collapsed.delete(ck);
    }
    try {
      await this.persistNav();
      this.renderNav();
    } catch (err) {
      this.removeNodeAtPath(this.findNodePath(this.navNodeKey(node)));
      this.insertNode(fromParent, fromIndex, node);
      window.alert(err instanceof Error ? err.message : '保存失败');
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
        this.renderNav({ preserveScroll: true });
      });
    });
    if (!nav._catalogNavContextBound) {
      nav._catalogNavContextBound = true;
      nav.addEventListener('contextmenu', (e) => {
        const row = e.target.closest('.nav-row');
        if (!row || !nav.contains(row)) return;
        const key = row.getAttribute('data-nav-key') || '';
        const nodePath = this.findNodePath(key);
        const node = nodePath ? this.getNodeAtPath(nodePath) : null;
        if (!node) return;
        e.preventDefault();
        e.stopPropagation();
        this.hideNavMenu();
        if (!this.canEditNav && !this.canDeleteNav) {
          window.alert('仅管理员可编辑能力分组');
          return;
        }
        if (!this.canEditNav && node.kind !== 'folder') return;
        if (!this.canEditNav && node.kind === 'all') return;
        this.showNavContextMenu(e.clientX, e.clientY, key);
      }, true);
    }

    if (!this.canEditNav) return;

    nav.querySelectorAll('.nav-row[draggable="true"]').forEach((row) => {
      row.addEventListener('dragstart', (e) => {
        const key = row.getAttribute('data-nav-key');
        const path = this.findNodePath(key);
        this._dragNodePath = path;
        row.classList.add('is-dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', key || '');
        }
      });
      row.addEventListener('dragend', () => {
        row.classList.remove('is-dragging');
        nav.querySelectorAll('.nav-row.drop-before, .nav-row.drop-after, .nav-row.drop-inside')
          .forEach((el) => el.classList.remove('drop-before', 'drop-after', 'drop-inside'));
        this._dragNodePath = null;
      });
      row.addEventListener('dragover', (e) => {
        if (!this._dragNodePath) return;
        const key = row.getAttribute('data-nav-key') || '';
        if (key === 'all') return;
        e.preventDefault();
        const rect = row.getBoundingClientRect();
        const y = e.clientY - rect.top;
        row.classList.remove('drop-before', 'drop-after', 'drop-inside');
        const targetPath = this.findNodePath(key);
        const targetNode = targetPath ? this.getNodeAtPath(targetPath) : null;
        if (this.isDropInsideZone(targetNode, y, rect.height)) {
          row.classList.add('drop-inside');
        } else if (y < rect.height / 2) {
          row.classList.add('drop-before');
        } else {
          row.classList.add('drop-after');
        }
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      });
      row.addEventListener('dragleave', () => {
        row.classList.remove('drop-before', 'drop-after', 'drop-inside');
      });
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        if (!this._dragNodePath) return;
        const fromPath = this._dragNodePath.slice();
        const fromNode = this.getNodeAtPath(fromPath);
        if (fromNode && fromNode.kind === 'all') return;
        const targetKey = row.getAttribute('data-nav-key') || '';
        if (targetKey === 'all') return;
        const targetPath = this.findNodePath(targetKey);
        if (!targetPath) return;
        const fromKey = this.navNodeKey(fromNode);
        if (fromKey === targetKey) return;
        const rect = row.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const drop = this.resolveNavDropTarget(targetPath, y, rect.height);
        this.moveNavNode(fromPath, drop.toParentPath, drop.toIndex);
      });
    });

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

  CatalogPanel.prototype.bindEvents = function bindEvents() {
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
  };

  CatalogPanel.prototype.init = async function init(fetchData) {
    this.bindEvents();
    await this.load(fetchData);
  };

  global.CatalogPanel = CatalogPanel;
})(window);
