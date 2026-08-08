/** Web Agent 主题：打开页面按北京时间默认（08:00 白天，17:00 夜间）；设置内可临时切换。 */
(function (global) {
  const BEIJING_OFFSET_MIN = 8 * 60;
  const DAY_START_MIN = 8 * 60;
  const NIGHT_START_MIN = 17 * 60;
  const STORAGE_KEY = 'webAgentThemeManual';

  let autoTimer = null;
  let manualOverride = null;
  let initialized = false;

  function readStoredManualTheme() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      if (value === 'light' || value === 'dark') {
        return value;
      }
    } catch (_err) {
      // localStorage 不可用时忽略
    }
    return null;
  }

  function writeStoredManualTheme(theme) {
    try {
      if (theme === 'light' || theme === 'dark') {
        localStorage.setItem(STORAGE_KEY, theme);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch (_err) {
      // localStorage 不可用时忽略
    }
  }

  function getBeijingTotalMinutes() {
    const now = new Date();
    const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
    const bj = new Date(utcMs + BEIJING_OFFSET_MIN * 60000);
    return bj.getHours() * 60 + bj.getMinutes();
  }

  function resolveAutoTheme() {
    const totalMinutes = getBeijingTotalMinutes();
    return totalMinutes >= DAY_START_MIN && totalMinutes < NIGHT_START_MIN ? 'light' : 'dark';
  }

  function getEffectiveTheme() {
    return manualOverride || resolveAutoTheme();
  }

  function updateThemeButtons(effective) {
    document.querySelectorAll('.theme-option[data-theme]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.theme === effective);
    });
    updateThemeQuickToggle(effective);
  }

  function updateThemeQuickToggle(effective) {
    document.querySelectorAll('#btn-theme-toggle').forEach((btn) => {
      const isLight = effective === 'light';
      btn.title = isLight ? '切换到夜间模式' : '切换到白天模式';
      btn.setAttribute('aria-label', btn.title);
      btn.classList.toggle('is-light', isLight);
      btn.classList.toggle('is-dark', !isLight);
    });
  }

  function toggleManualTheme() {
    setManualTheme(getEffectiveTheme() === 'light' ? 'dark' : 'light');
  }

  function clearAutoTimer() {
    if (autoTimer != null) {
      clearTimeout(autoTimer);
      autoTimer = null;
    }
  }

  function msUntilNextBoundary() {
    const totalMinutes = getBeijingTotalMinutes();
    let minsToBoundary;
    if (totalMinutes < DAY_START_MIN) {
      minsToBoundary = DAY_START_MIN - totalMinutes;
    } else if (totalMinutes < NIGHT_START_MIN) {
      minsToBoundary = NIGHT_START_MIN - totalMinutes;
    } else {
      minsToBoundary = (24 * 60 - totalMinutes) + DAY_START_MIN;
    }
    return Math.max(minsToBoundary * 60 * 1000, 60000);
  }

  function scheduleAutoThemeCheck() {
    clearAutoTimer();
    if (manualOverride) return;
    autoTimer = setTimeout(() => {
      applyCurrentTheme();
      scheduleAutoThemeCheck();
    }, msUntilNextBoundary());
  }

  function syncThemeFromStorage() {
    manualOverride = readStoredManualTheme();
    return applyCurrentTheme();
  }

  function applyCurrentTheme() {
    const effective = getEffectiveTheme();
    document.documentElement.setAttribute('data-theme', effective);
    updateThemeButtons(effective);
    scheduleAutoThemeCheck();
    return effective;
  }

  function applyThemeEarly() {
    manualOverride = readStoredManualTheme();
    document.documentElement.setAttribute('data-theme', getEffectiveTheme());
  }

  function setManualTheme(theme) {
    manualOverride = theme === 'light' ? 'light' : 'dark';
    writeStoredManualTheme(manualOverride);
    applyCurrentTheme();
  }

  function bindThemeControls() {
    document.getElementById('theme-dark')?.addEventListener('click', () => setManualTheme('dark'));
    document.getElementById('theme-light')?.addEventListener('click', () => setManualTheme('light'));
    document.querySelectorAll('#btn-theme-toggle').forEach((btn) => {
      btn.addEventListener('click', () => toggleManualTheme());
    });
  }

  function initThemeSettings() {
    syncThemeFromStorage();
    if (initialized) return;
    initialized = true;
    bindThemeControls();
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        syncThemeFromStorage();
      }
    });
    global.addEventListener('storage', (event) => {
      if (event.key !== STORAGE_KEY) return;
      syncThemeFromStorage();
    });
    global.addEventListener('pageshow', (event) => {
      if (event.persisted) syncThemeFromStorage();
    });
  }

  function bootThemeWhenDomReady() {
    if (!global.document || !global.document.documentElement) return;
    initThemeSettings();
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', bootThemeWhenDomReady);
    } else {
      bootThemeWhenDomReady();
    }
  }

  global.WebAgentTheme = {
    resolveAutoTheme: resolveAutoTheme,
    getEffectiveTheme: getEffectiveTheme,
    applyThemeEarly: applyThemeEarly,
    applyCurrentTheme: applyCurrentTheme,
    setManualTheme: setManualTheme,
    toggleManualTheme: toggleManualTheme,
    initThemeSettings: initThemeSettings,
    syncThemeFromStorage: syncThemeFromStorage,
  };
})(typeof window !== 'undefined' ? window : globalThis);
