const TOKEN_KEY = "yaahlan_dashboard_token";
let pollTimer = null;
let activeJobId = null;

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function setToken(value) {
  localStorage.setItem(TOKEN_KEY, value.trim());
}

function authHeaders() {
  const token = getToken();
  return token ? { "X-Dashboard-Token": token } : {};
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch (_) {}
    throw new Error(`${res.status}: ${detail}`);
  }
  if (res.headers.get("content-type")?.includes("application/json")) {
    return res.json();
  }
  return res.text();
}

function showToast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3500);
}

function statusBadge(status) {
  const map = {
    passed: "badge-ok",
    failed: "badge-fail",
    running: "badge-run",
    pending: "badge-pending",
    error: "badge-fail",
  };
  return `<span class="badge ${map[status] || "badge-pending"}">${status}</span>`;
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function shortCaseId(caseName) {
  const name = String(caseName || "");
  if (name.length <= 28) return name;
  const prefix = name.slice(0, 14);
  const suffix = name.slice(-12);
  return `${prefix}…${suffix}`;
}

function suiteBrief(description, fallback) {
  const text = String(description || fallback || "").trim();
  if (!text) return fallback || "";
  const firstLine = text.split("\n").find((line) => line.trim()) || text;
  return firstLine.length > 160 ? `${firstLine.slice(0, 159)}…` : firstLine;
}

function updateSelectedCount() {
  const count = document.querySelectorAll(".case-check:checked").length;
  const el = document.getElementById("selectedCount");
  if (el) el.textContent = `已选 ${count} 条`;
  document.querySelectorAll(".case-card").forEach((card) => {
    const checkbox = card.querySelector(".case-check");
    card.classList.toggle("is-selected", Boolean(checkbox?.checked));
  });
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${name}`);
  });
}

async function loadHealth() {
  const badge = document.getElementById("healthBadge");
  try {
    const health = await api("/api/health");
    const running = health.running_job_id ? ` · 运行中 ${health.running_job_id}` : "";
    badge.textContent = `在线 · ${health.auth_mode}${running}`;
    badge.className = "badge badge-ok";
  } catch (err) {
    badge.textContent = `离线 · ${err.message}`;
    badge.className = "badge badge-fail";
  }
}

async function loadSuites() {
  const suites = await api("/api/suites");
  const suiteSelect = document.getElementById("suiteSelect");
  const reportFilter = document.getElementById("reportSuiteFilter");
  suiteSelect.innerHTML = "";
  reportFilter.innerHTML = '<option value="">全部</option>';
  suites.forEach((suite) => {
    const opt = document.createElement("option");
    opt.value = suite.id;
    opt.textContent = `${suite.name} (${suite.case_count})`;
    suiteSelect.appendChild(opt);

    const opt2 = document.createElement("option");
    opt2.value = suite.id;
    opt2.textContent = suite.name;
    reportFilter.appendChild(opt2);
  });
  if (suites.length) {
    await loadCases(suites[0].id);
  }
}

async function loadCases(suiteId) {
  const detail = await api(`/api/suites/${suiteId}`);
  const meta = document.getElementById("suiteMeta");
  meta.textContent = suiteBrief(
    detail.description,
    `${detail.name} · 共 ${detail.case_count} 条用例`
  );
  meta.title = detail.description || "";

  const list = document.getElementById("casesList");
  list.innerHTML = "";
  detail.cases.forEach((item, index) => {
    const card = document.createElement("article");
    card.className = "case-card";
    const title = item.case_name_cn || item.case_name_en || `用例 ${index + 1}`;
    const desc = item.scenario_desc || item.case_purpose || "暂无场景说明";
    const tags = [];
    if (item.anchor_id) tags.push(`主播 ${item.anchor_id}`);
    if (item.period_start) tags.push(`周期 ${item.period_start}`);
    card.innerHTML = `
      <div class="case-check-wrap">
        <input type="checkbox" class="case-check" value="${escapeHtml(item.case_name)}" aria-label="选择用例" />
      </div>
      <div class="case-main">
        <h3 class="case-title">${escapeHtml(title)}</h3>
        <p class="case-desc" title="${escapeHtml(desc)}">${escapeHtml(desc)}</p>
        <div class="case-meta">
          ${tags.map((tag) => `<span class="case-tag">${escapeHtml(tag)}</span>`).join("")}
          <button class="case-id-btn case-id" type="button" data-case-id="${escapeHtml(item.case_name)}" title="${escapeHtml(item.case_name)}">
            ID: ${escapeHtml(shortCaseId(item.case_name))}
          </button>
        </div>
      </div>
      <div class="case-actions">
        <button class="btn btn-primary btn-sm run-one-btn" data-case="${escapeHtml(item.case_name)}" type="button">执行</button>
      </div>
    `;
    list.appendChild(card);
  });

  document.querySelectorAll(".case-check").forEach((el) => {
    el.addEventListener("change", updateSelectedCount);
  });
  document.querySelectorAll(".case-id-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const fullId = btn.dataset.caseId || "";
      try {
        await navigator.clipboard.writeText(fullId);
        showToast(`已复制用例 ID: ${shortCaseId(fullId)}`);
      } catch (_) {
        showToast(fullId);
      }
    });
  });
  document.querySelectorAll(".run-one-btn").forEach((btn) => {
    btn.addEventListener("click", () => runCases([btn.dataset.case]));
  });
  document.getElementById("selectAllCases").checked = false;
  updateSelectedCount();
}

function selectedCaseNames() {
  return [...document.querySelectorAll(".case-check:checked")].map((el) => el.value);
}

async function runCases(caseNames = []) {
  const suiteId = document.getElementById("suiteSelect").value;
  if (!suiteId) return;
  try {
    const job = await api("/api/jobs/run", {
      method: "POST",
      body: JSON.stringify({
        suite_id: suiteId,
        case_names: caseNames,
        generate_report: true,
      }),
    });
    showToast(`任务已提交: ${job.job_id}`);
    activeJobId = job.job_id;
    switchTab("jobs");
    await refreshJobs();
    startPolling(job.job_id);
  } catch (err) {
    showToast(err.message);
  }
}

async function refreshJobs() {
  const jobs = await api("/api/jobs");
  const tbody = document.getElementById("jobsTableBody");
  tbody.innerHTML = "";
  jobs.forEach((job) => {
    const tr = document.createElement("tr");
    const caseHint = job.case_names?.length
      ? `${job.case_names.length} 条用例`
      : "全量执行";
    tr.innerHTML = `
      <td>
        <div class="cell-primary">${escapeHtml(caseHint)}</div>
        <div class="cell-mono-short" title="${escapeHtml(job.job_id)}">${escapeHtml(job.job_id)}</div>
      </td>
      <td>${escapeHtml(job.suite_name)}</td>
      <td>${statusBadge(job.status)}</td>
      <td>${job.duration_seconds != null ? `${job.duration_seconds}s` : "-"}</td>
      <td>${escapeHtml(job.started_at || "-")}</td>
      <td>
        <button class="btn btn-link view-log-btn" data-id="${escapeHtml(job.job_id)}" type="button">日志</button>
        ${job.report_html_url ? `<a class="btn btn-link" href="${job.report_html_url}" target="_blank" rel="noopener">报告</a>` : ""}
      </td>
    `;
    tbody.appendChild(tr);
  });

  const running = jobs.find((j) => j.status === "running" || j.status === "pending");
  const box = document.getElementById("currentJobBox");
  if (running) {
    box.classList.remove("hidden");
    box.textContent = `当前任务: ${running.job_id} · ${running.suite_name} · ${running.status}\n命令: ${running.command || "-"}`;
    if (!pollTimer) startPolling(running.job_id);
  } else {
    box.classList.add("hidden");
    stopPolling();
  }

  document.querySelectorAll(".view-log-btn").forEach((btn) => {
    btn.addEventListener("click", () => viewJobLog(btn.dataset.id));
  });
}

async function viewJobLog(jobId) {
  activeJobId = jobId;
  const logBox = document.getElementById("jobLog");
  logBox.classList.remove("hidden");
  try {
    const text = await api(`/api/jobs/${jobId}/log`);
    logBox.textContent = text || "(暂无日志)";
  } catch (err) {
    logBox.textContent = err.message;
  }
}

function startPolling(jobId) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      await refreshJobs();
      if (activeJobId === jobId) {
        await viewJobLog(jobId);
      }
      if (job.status === "passed" || job.status === "failed" || job.status === "error") {
        stopPolling();
        await loadReports();
        showToast(`任务 ${jobId} 结束: ${job.status}`);
      }
    } catch (_) {}
  }, 3000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function loadReports() {
  const suiteId = document.getElementById("reportSuiteFilter").value;
  const query = suiteId ? `?suite_id=${encodeURIComponent(suiteId)}` : "";
  const reports = await api(`/api/reports${query}`);
  const tbody = document.getElementById("reportsTableBody");
  tbody.innerHTML = "";
  reports.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${item.filename}</td>
      <td>${item.suite_name || "-"}</td>
      <td>${item.format}</td>
      <td>${formatBytes(item.size_bytes)}</td>
      <td>${item.modified_at}</td>
      <td><a class="btn btn-link" href="${item.url_path}" target="_blank" rel="noopener">打开</a></td>
    `;
    tbody.appendChild(tr);
  });
}

async function bootstrap() {
  document.getElementById("tokenInput").value = getToken();

  document.getElementById("saveTokenBtn").addEventListener("click", async () => {
    setToken(document.getElementById("tokenInput").value);
    showToast("Token 已保存");
    await initData();
  });

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("suiteSelect").addEventListener("change", (e) => loadCases(e.target.value));
  document.getElementById("runSelectedBtn").addEventListener("click", () => {
    const names = selectedCaseNames();
    if (!names.length) {
      showToast("请先选择至少一条用例");
      return;
    }
    runCases(names);
  });
  document.getElementById("runAllBtn").addEventListener("click", () => runCases([]));
  document.getElementById("selectAllCases").addEventListener("change", (e) => {
    document.querySelectorAll(".case-check").forEach((el) => {
      el.checked = e.target.checked;
    });
    updateSelectedCount();
  });

  document.getElementById("refreshBtn").addEventListener("click", initData);
  document.getElementById("refreshJobsBtn").addEventListener("click", refreshJobs);
  document.getElementById("refreshReportsBtn").addEventListener("click", loadReports);
  document.getElementById("reportSuiteFilter").addEventListener("change", loadReports);

  await initData();
}

async function initData() {
  await loadHealth();
  await loadSuites();
  await refreshJobs();
  await loadReports();
}

bootstrap().catch((err) => showToast(`初始化失败: ${err.message}`));
