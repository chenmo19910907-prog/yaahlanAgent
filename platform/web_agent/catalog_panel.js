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
    this._navDragActive = false;
    this._pendingNavMove = null;
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
    this.hydrateNavCaps(this.navTree);
    this.sortNavTreeChildOrder(this.navTree);
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
    if (node.kind === 'cap' || node.kind === 'folder') return true;
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

  CatalogPanel.prototype.navSiblingSortRank = function navSiblingSortRank(node) {
    if (!node) return 2;
    if (node.kind === 'folder') return 0;
    if (node.kind === 'cap') return 1;
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
    if (node.kind === 'cap') return navCategoryKey(node.moduleId, node.catIndex);
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
    if (node.kind === 'all') return this.DATA?.total_items || 0;
    if (node.kind === 'playbook') return this.playbookCount();
    if (node.kind === 'cap') return this.capItemCount(node);
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
    if (
      before
      && fromPath
      && targetParentPath
      && y <= Math.max(10, rectHeight * 0.28)
    ) {
      const fromParent = this.parentFolderPath(fromPath);
      if (
        this.navParentPathKey(fromParent) === this.navParentPathKey(targetParentPath)
        && this.navParentPathKey(fromPath) !== this.navParentPathKey(targetPath)
      ) {
        const parentIdx = targetParentPath[targetParentPath.length - 1];
        return {
          kind: 'sibling',
          toParentPath: this.parentFolderPath(targetParentPath),
          toIndex: parentIdx + 1,
        };
      }
    }
    return {
      kind: 'sibling',
      toParentPath: targetParentPath,
      toIndex: targetIdx + (before ? 0 : 1),
    };
  };

  CatalogPanel.prototype.isNavDropPlacementAllowed = function isNavDropPlacementAllowed(fromPath, drop) {
    if (!drop || !fromPath) return false;
    if (drop.kind === 'inside') {
      return !this.cannotDropInside(fromPath, drop.toParentPath);
    }
    return !this.cannotDropInside(fromPath, drop.toParentPath);
  };

  CatalogPanel.prototype.applyNavDropIndicator = function applyNavDropIndicator(nav, row, fromPath, targetPath, y, rectHeight) {
    nav.querySelectorAll('.nav-row.drop-before, .nav-row.drop-after, .nav-row.drop-inside')
      .forEach((el) => el.classList.remove('drop-before', 'drop-after', 'drop-inside'));
    const drop = this.resolveNavDropTarget(targetPath, y, rectHeight, fromPath);
    if (!this.isNavDropPlacementAllowed(fromPath, drop)) return;
    if (drop.kind === 'inside') row.classList.add('drop-inside');
    else if (y < rectHeight / 2) row.classList.add('drop-before');
    else row.classList.add('drop-after');
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

  CatalogPanel.prototype.renderCapCategoryBlock = function renderCapCategoryBlock(capNode, q) {
    const mod = this.moduleById(capNode.moduleId);
    const cat = mod?.categories?.[capNode.catIndex];
    if (!cat) return { html: '', count: 0 };
    const catLabel = this.navNodeLabel(capNode);
    const filtered = cat.items.filter((it) => this.matches(it, mod.label, cat.name, q));
    if (!filtered.length) return { html: '', count: 0 };
    const items = filtered.map((it) => this.renderCapItem(it)).join('');
    return {
      count: filtered.length,
      html: `<li><span class="cat-name">${escapeHtml(catLabel)}</span><ul class="items">${items}</ul></li>`,
    };
  };

  CatalogPanel.prototype.renderNavScopeBody = function renderNavScopeBody(node, q) {
    let catsHtml = '';
    let visibleCount = 0;
    const parts = [];
    const scopeChildren = (node.children || []).slice().sort((a, b) => {
      const ra = this.navSiblingSortRank(a);
      const rb = this.navSiblingSortRank(b);
      return ra !== rb ? ra - rb : 0;
    });
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
      }
    });
    return { catsHtml, partsHtml: parts.join(''), visibleCount };
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

    if (filter.mode === 'navScope') {
      const body = this.renderNavScopeBody(filter.node, q);
      if (body.visibleCount) {
        any = true;
        const icon = filter.icon === 'module' ? smallIcon('module') : smallIcon('spark');
        const section = document.createElement('section');
        section.className = 'catalog-module catalog-module-scope';
        section.innerHTML = `
          <div class="module-head">
            <span class="module-icon" aria-hidden="true">${icon}</span>
            <div>
              <h3>${escapeHtml(filter.title)}</h3>
              <div class="sub">${body.visibleCount} 项能力</div>
            </div>
          </div>
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

    if (filter.mode === 'category') {
      const mod = this.DATA.modules.find((m) => m.id === filter.moduleId);
      const cat = mod?.categories?.[filter.catIndex];
      if (cat) {
        const filtered = cat.items.filter((it) => this.matches(it, mod.label, cat.name, q));
        if (filtered.length) {
          any = true;
          const items = filtered.map((it) => this.renderCapItem(it)).join('');
          const section = document.createElement('section');
          section.className = 'catalog-module catalog-module-category';
          section.innerHTML = `
            <div class="module-head">
              <span class="module-icon" aria-hidden="true">${smallIcon('spark')}</span>
              <div>
                <h3>${escapeHtml(collapseNavDisplayLabel(cat.name))}</h3>
                <div class="sub">${filtered.length} 项 MOA 能力</div>
              </div>
            </div>
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
        catsHtml += `<li><span class="cat-name">${escapeHtml(collapseNavDisplayLabel(cat.name))}</span><ul class="items">${items}</ul></li>`;
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
    const isCap = node.kind === 'cap';
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
    } else if (node.kind === 'cap') {
      const current = this.navNodeLabel(node);
      const next = window.prompt('能力接口名称', current);
      if (!next || !String(next).trim() || String(next).trim() === current) return;
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
        if (fromParent) node.subfolder = true;
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
    }
    try {
      await this.persistNav();
      this.renderNav({ preserveScroll: true });
      this.render();
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
        if (node.kind === 'cap') {
          if (!this.canEditNav) {
            window.alert('仅管理员可编辑能力分组');
            return;
          }
        } else if (!this.canEditNav && !this.canDeleteNav) {
          window.alert('仅管理员可编辑能力分组');
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

    nav.querySelectorAll('.nav-row[draggable="true"]').forEach((row) => {
      row.addEventListener('dragstart', (e) => {
        const key = row.getAttribute('data-nav-key');
        const path = this.findNodePath(key);
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
        nav.querySelectorAll('.nav-row.drop-before, .nav-row.drop-after, .nav-row.drop-inside')
          .forEach((el) => el.classList.remove('drop-before', 'drop-after', 'drop-inside'));
        const pending = this._pendingNavMove;
        this._pendingNavMove = null;
        this._dragNodePath = null;
        this._navDragActive = false;
        if (pending) {
          this.moveNavNode(pending.fromPath, pending.toParentPath, pending.toIndex);
        }
      });
      row.addEventListener('dragover', (e) => {
        if (!this._dragNodePath) return;
        const key = row.getAttribute('data-nav-key') || '';
        if (key === 'all') return;
        e.preventDefault();
        const rect = row.getBoundingClientRect();
        const y = e.clientY - rect.top;
        const targetPath = this.findNodePath(key);
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
        row.classList.remove('drop-before', 'drop-after', 'drop-inside');
      });
      row.addEventListener('drop', (e) => {
        e.preventDefault();
        e.stopPropagation();
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
        const drop = this.resolveNavDropTarget(targetPath, y, rect.height, fromPath);
        if (!this.isNavDropPlacementAllowed(fromPath, drop)) return;
        this._pendingNavMove = {
          fromPath,
          toParentPath: drop.toParentPath,
          toIndex: drop.toIndex,
        };
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
