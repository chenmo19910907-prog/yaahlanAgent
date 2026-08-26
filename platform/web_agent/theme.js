/** Web Agent 主题：自动模式按北京时间切换（08:00 白天，17:00 夜间）；设置内可选自动/白天/夜间。 */
(function (global) {
  const BEIJING_OFFSET_MIN = 8 * 60;
  const DAY_START_MIN = 8 * 60;
  const NIGHT_START_MIN = 17 * 60;
  const STORAGE_KEY = 'webAgentThemeManual';
  const THEME_CYCLE = ['auto', 'light', 'dark'];

  let autoTimer = null;
  let themePreference = 'auto';
  let initialized = false;

  function readStoredThemePreference() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      if (value === 'light' || value === 'dark' || value === 'auto') {
        return value;
      }
    } catch (_err) {
      // localStorage 不可用时忽略
    }
    return 'auto';
  }

  function writeStoredThemePreference(preference) {
    try {
      if (preference === 'light' || preference === 'dark' || preference === 'auto') {
        localStorage.setItem(STORAGE_KEY, preference);
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
    if (themePreference === 'light' || themePreference === 'dark') {
      return themePreference;
    }
    return resolveAutoTheme();
  }

  function updateThemeButtons(preference) {
    document.querySelectorAll('.theme-option[data-theme]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.theme === preference);
    });
    updateThemeQuickToggle(preference);
  }

  function updateThemeQuickToggle(preference) {
    const effective = getEffectiveTheme();
    document.querySelectorAll('#btn-theme-toggle').forEach((btn) => {
      const isAuto = preference === 'auto';
      const isLight = preference === 'light' || (isAuto && effective === 'light');
      const isDark = preference === 'dark' || (isAuto && effective === 'dark');
      btn.classList.toggle('is-auto', isAuto);
      btn.classList.toggle('is-light', isLight);
      btn.classList.toggle('is-dark', isDark);
      if (isAuto) {
        btn.title = `自动模式（当前${effective === 'light' ? '白天' : '夜间'}）· 点击切换`;
      } else {
        btn.title = isLight ? '切换到夜间模式' : '切换到白天模式';
      }
      btn.setAttribute('aria-label', btn.title);
    });
  }

  function cycleThemePreference() {
    const idx = THEME_CYCLE.indexOf(themePreference);
    const nextIdx = ((idx >= 0 ? idx : 0) + 1) % THEME_CYCLE.length;
    setThemePreference(THEME_CYCLE[nextIdx]);
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
    if (themePreference !== 'auto') return;
    autoTimer = setTimeout(() => {
      applyCurrentTheme();
      scheduleAutoThemeCheck();
    }, msUntilNextBoundary());
  }

  function syncThemeFromStorage() {
    themePreference = readStoredThemePreference();
    return applyCurrentTheme();
  }

  function applyCurrentTheme() {
    const effective = getEffectiveTheme();
    document.documentElement.setAttribute('data-theme', effective);
    updateThemeButtons(themePreference);
    scheduleAutoThemeCheck();
    return effective;
  }

  function applyThemeEarly() {
    themePreference = readStoredThemePreference();
    document.documentElement.setAttribute('data-theme', getEffectiveTheme());
  }

  function setThemePreference(preference) {
    themePreference = preference === 'light' ? 'light' : preference === 'dark' ? 'dark' : 'auto';
    writeStoredThemePreference(themePreference);
    applyCurrentTheme();
  }

  function bindThemeControls() {
    document.getElementById('theme-dark')?.addEventListener('click', () => setThemePreference('dark'));
    document.getElementById('theme-light')?.addEventListener('click', () => setThemePreference('light'));
    document.getElementById('theme-auto')?.addEventListener('click', () => setThemePreference('auto'));
    document.querySelectorAll('#btn-theme-toggle').forEach((btn) => {
      btn.addEventListener('click', () => cycleThemePreference());
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
    getThemePreference: () => themePreference,
    applyThemeEarly: applyThemeEarly,
    applyCurrentTheme: applyCurrentTheme,
    setThemePreference: setThemePreference,
    setManualTheme: setThemePreference,
    cycleThemePreference: cycleThemePreference,
    toggleManualTheme: cycleThemePreference,
    initThemeSettings: initThemeSettings,
    syncThemeFromStorage: syncThemeFromStorage,
  };
})(typeof window !== 'undefined' ? window : globalThis);
