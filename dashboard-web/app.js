let machinesCache = [];
let currentFilter = "active";
let currentMachine = "";
let historyPage = 0;
const HISTORY_PAGE_SIZE = 20;

function $(id) { return document.getElementById(id); }

function toast(msg, type = "success") {
  const t = document.createElement("div");
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

async function api(path, opts = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`HTTP ${res.status}: ${err}`);
  }
  return res.json();
}

function severityClass(s) {
  if (!s) return "";
  return s === "high" ? "severity-high" : s === "medium" ? "severity-medium" : "severity-low";
}

function badgeStatus(s) {
  if (s === "active") return "badge-active";
  if (s === "resolved") return "badge-resolved";
  return "badge-fp";
}

function statusLabel(s) {
  if (s === "active") return "Active";
  if (s === "resolved") return "Résolue";
  return "Faux positif";
}

function formatTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// ── Sidebar ──
function toggleSidebar() {
  $("sidebar").classList.toggle("open");
  $("overlay").classList.toggle("active");
}

$("menuBtn").addEventListener("click", toggleSidebar);

document.querySelectorAll(".nav-item").forEach(item => {
  item.addEventListener("click", function () {
    document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
    document.querySelectorAll(".section").forEach(s => s.classList.remove("active"));
    this.classList.add("active");
    const sec = $("section-" + this.dataset.section);
    if (sec) {
      sec.classList.add("active");
      if (this.dataset.section === "machines") renderMachines();
      if (this.dataset.section === "history") fetchHistory(0);
      if (this.dataset.section === "analytics") loadAnalytics();
      if (this.dataset.section === "alerts") fetchAlerts();
    }
    if (window.innerWidth <= 768) toggleSidebar();
  });
});

setInterval(() => {
  $("liveTime").textContent = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}, 1000);

// ── KPI ──
const KPI_META = [
  { icon: "fa-bell", bg: "#dbeafe", color: "#3b82f6", label: "Alertes actives", key: "active_alerts", suffix: "" },
  { icon: "fa-exclamation-triangle", bg: "#fce4ec", color: "#ef4444", label: "Machines critiques", key: "critical_machines", suffix: "" },
  { icon: "fa-heartbeat", bg: "#dcfce7", color: "#16a34a", label: "Health Score moyen", key: "avg_health", suffix: "%" },
  { icon: "fa-gauge-high", bg: "#fef3c7", color: "#d97706", label: "Faux positifs (7j)", key: "fp_rate", suffix: "%" },
  { icon: "fa-clock", bg: "#f3e8ff", color: "#8b5cf6", label: "RUL min (jours)", key: "min_rul", suffix: " j" },
];

function renderKPI(d) {
  if (!d) {
    $("kpiGrid").innerHTML = KPI_META.map(m => `
      <div class="kpi-card">
        <div class="kpi-header">
          <div class="kpi-label">${m.label}</div>
          <div class="kpi-icon" style="background:${m.bg};color:${m.color}"><i class="fas ${m.icon}"></i></div>
        </div>
        <div class="kpi-value" style="color:${m.color}">—</div>
      </div>`).join("");
    return;
  }
  $("kpiGrid").innerHTML = KPI_META.map(m => {
    let v = d[m.key];
    if (v === undefined || v === null) v = "—";
    else if (typeof v === "number") v = m.suffix ? v + m.suffix : v;
    return `
      <div class="kpi-card">
        <div class="kpi-header">
          <div class="kpi-label">${m.label}</div>
          <div class="kpi-icon" style="background:${m.bg};color:${m.color}"><i class="fas ${m.icon}"></i></div>
        </div>
        <div class="kpi-value" style="color:${m.color}">${v}</div>
      </div>`;
  }).join("");
}

// ── Machines ──
async function loadMachines() {
  try {
    const d = await api("/machines");
    machinesCache = d.machines || [];
    updateStatus();
    populateMachineFilter();
    renderKPI(computeKPI());
    return machinesCache;
  } catch (e) {
    console.warn("Machines error", e);
    return [];
  }
}

function computeKPI() {
  const m = machinesCache;
  if (!m.length) return {};
  const rulValues = m.map(x => x.rul_days || 0).filter(v => v > 0);
  return {
    active_alerts: m.filter(x => x.status === "critical" || x.status === "warning").length,
    critical_machines: m.filter(x => x.status === "critical").length,
    avg_health: Math.round(m.reduce((a, x) => a + (x.health_score || 0), 0) / m.length),
    fp_rate: 0,
    min_rul: rulValues.length ? Math.min(...rulValues) : 0,
  };
}

function updateStatus() {
  const badge = $("statusBadge");
  const critical = machinesCache.filter(m => m.status === "critical").length;
  const warning = machinesCache.filter(m => m.status === "warning").length;
  if (critical > 0) {
    badge.className = "badge-live bad";
    badge.innerHTML = `<span class="dot"></span> ${critical} critique(s)`;
  } else if (warning > 0) {
    badge.className = "badge-live warning";
    badge.innerHTML = `<span class="dot"></span> ${warning} warning(s)`;
  } else {
    badge.className = "badge-live good";
    badge.innerHTML = `<span class="dot"></span> Normal`;
  }
}

function populateMachineFilter() {
  const sel = $("filter-machine");
  sel.innerHTML = '<option value="">Toutes les machines</option>';
  for (const m of machinesCache) {
    sel.innerHTML += `<option value="${m.machine_id}">${m.machine_id} - ${m.label}</option>`;
  }
}

function renderMachines() {
  const grid = $("machineGrid");
  if (!machinesCache.length) {
    grid.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted)">Aucune machine</div>';
    return;
  }
  grid.innerHTML = machinesCache.map(m => {
    const hs = m.health_score || 0;
    const cls = hs < 30 ? "badge-red" : hs < 70 ? "badge-orange" : "badge-green";
    const label = hs < 30 ? "Critique" : hs < 70 ? "Warning" : "Normal";
    const color = hs < 30 ? "#ef4444" : hs < 70 ? "#d97706" : "#16a34a";
    return `
      <div class="machine-card" onclick="openMachineDetail('${m.machine_id}')">
        <div class="mc-header">
          <div>
            <div class="mc-id">${m.machine_id}</div>
            <div class="mc-type">${m.machine_type} · ${m.label}</div>
          </div>
          <div style="text-align:right">
            <div class="mc-score" style="color:${color}">${hs}</div>
            <div class="mc-status"><span class="badge ${cls}">${label}</span></div>
          </div>
        </div>
        <div class="mc-rul"><i class="fas fa-clock" style="margin-right:4px"></i>RUL: ${m.rul_days > 0 ? m.rul_days + ' jours' : '—'}</div>
      </div>`;
  }).join("");
}

// ── Machine Detail (modal) ──
async function openMachineDetail(machineId) {
  $("modalOverlay").classList.add("show");
  $("modalTitle").textContent = `Machine ${machineId}`;
  $("modalContent").innerHTML = '<div class="loading">Chargement</div>';

  try {
    const [health, history] = await Promise.all([
      api(`/machine/${machineId}/health`),
      api(`/machine/${machineId}/history?hours=24`),
    ]);

    const hs = health.health_score || 0;
    const color = hs < 30 ? "#ef4444" : hs < 70 ? "#d97706" : "#16a34a";
    const label = hs < 30 ? "CRITIQUE" : hs < 70 ? "WARNING" : "NORMAL";

    $("modalContent").innerHTML = `
      <div class="modal-grid">
        <div class="item"><div class="lbl">Health Score</div><div class="val" style="color:${color}">${hs}</div></div>
        <div class="item"><div class="lbl">Statut</div><div class="val" style="font-size:20px;color:${color}">${label}</div></div>
        <div class="item"><div class="lbl">RUL estimé</div><div class="val">${health.rul_days > 0 ? health.rul_days : '—'} ${health.rul_days > 0 ? '<span style="font-size:14px;font-weight:400">jours</span>' : ''}</div></div>        <div class="item"><div class="lbl">Score anomalie</div><div class="val">${health.anomaly_score || 0}</div></div>
        <div class="item"><div class="lbl">Type</div><div class="val" style="font-size:20px">${health.machine_type || "?"}</div></div>
        <div class="item"><div class="lbl">Dernières valeurs</div>
          <div class="val sub">
            T: ${health.last_values?.temperature || "—"}°C /
            V: ${health.last_values?.vibration || "—"} /
            P: ${health.last_values?.pressure || "—"} bar /
            C: ${health.last_values?.courant_moteur || "—"} A
          </div>
        </div>
      </div>
      <div class="chart-container">
        <canvas id="modalChart"></canvas>
      </div>
    `;

    renderModalChart(history.records || [], machineId, hs);
  } catch (e) {
    $("modalContent").innerHTML = `<p style="color:#ef4444">Erreur: ${e.message}</p>`;
  }
}

function closeModal() {
  $("modalOverlay").classList.remove("show");
}

$("modalOverlay").addEventListener("click", e => {
  if (e.target === $("modalOverlay")) closeModal();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") closeModal();
});

let modalChart = null;

function renderModalChart(records, machineId, healthScore) {
  if (!records || !records.length || typeof Chart === "undefined") return;

  const times = records.map(r => r.time);
  const temps = records.map(r => r.temperature);
  const vibs = records.map(r => r.vibration);

  if (modalChart) modalChart.destroy();

  modalChart = new Chart($("modalChart"), {
    type: "line",
    data: {
      labels: times,
      datasets: [
        {
          label: "Température (°C)",
          data: temps,
          borderColor: "#ef4444",
          backgroundColor: "rgba(239,68,68,0.1)",
          yAxisID: "y",
          tension: 0.3,
          pointRadius: 0,
        },
        {
          label: "Vibration",
          data: vibs,
          borderColor: "#3b82f6",
          backgroundColor: "rgba(59,130,246,0.1)",
          yAxisID: "y1",
          tension: 0.3,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { position: "bottom", labels: { color: "#64748b", font: { size: 11 } } },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 10, maxRotation: 0, color: "#94a3b8", font: { size: 10 } } },
        y: { type: "linear", display: true, position: "left", title: { display: true, text: "Température (°C)", color: "#64748b" }, grid: { color: "#f1f5f9" }, ticks: { color: "#94a3b8" } },
        y1: { type: "linear", display: true, position: "right", title: { display: true, text: "Vibration", color: "#64748b" }, grid: { drawOnChartArea: false }, ticks: { color: "#94a3b8" } },
      },
    },
  });
}

// ── Dashboard alerts table ──
async function fetchRecentAlerts() {
  try {
    const d = await api("/alerts?status=all");
    renderEventsTable((d.alerts || []).slice(0, 10));
  } catch (e) {
    $("eventsBody").innerHTML = `<tr><td colspan="6" style="text-align:center;padding:30px;color:var(--text-muted)">Erreur: ${e.message}</td></tr>`;
  }
}

function renderEventsTable(alerts) {
  const tbody = $("eventsBody");
  if (!alerts.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:30px;color:var(--text-muted)">Aucune alerte</td></tr>';
    return;
  }
  tbody.innerHTML = alerts.map(a => {
    const cls = a.severity === "high" ? "badge-red" : a.severity === "medium" ? "badge-orange" : "badge-blue";
    return `<tr>
      <td><span class="machine-link" onclick="openMachineDetail('${a.machine_id}')">${a.machine_id}</span></td>
      <td>${a.capteur || "—"}</td>
      <td class="${severityClass(a.severity)}">${a.anomaly_score || 0}</td>
      <td><span class="badge ${cls}">${a.severity || "low"}</span></td>
      <td style="color:var(--text-muted);font-size:12px">${formatTime(a.timestamp)}</td>
      <td><span class="badge ${badgeStatus(a.status)}">${statusLabel(a.status)}</span></td>
    </tr>`;
  }).join("");
}

// ── Alertes (full) ──
async function fetchAlerts() {
  try {
    const status = currentFilter === "all" ? "all" : currentFilter;
    const d = await api(`/alerts?status=${status}`);
    let alerts = d.alerts || [];
    if (currentMachine) {
      alerts = alerts.filter(a => a.machine_id === currentMachine);
    }
    renderAlertsTable(alerts);
    $("alertsCount").textContent = alerts.length;
    updateAlertCount(alerts);
  } catch (e) {
    $("alertsBody").innerHTML = `<tr><td colspan="7" style="text-align:center;padding:30px;color:#ef4444">Erreur: ${e.message}</td></tr>`;
  }
}

function renderAlertsTable(alerts) {
  const tbody = $("alertsBody");
  if (!alerts.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:32px;color:var(--text-muted)">Aucune alerte ${currentFilter !== "all" ? currentFilter : ""}</td></tr>`;
    return;
  }
  tbody.innerHTML = alerts.map(a => {
    const mid = a.machine_id || "?";
    const machine = machinesCache.find(m => m.machine_id === mid);
    const typeLabel = machine ? machine.machine_type : "?";
    const cls = a.severity === "high" ? "badge-red" : a.severity === "medium" ? "badge-orange" : "badge-blue";
    return `<tr>
      <td><span class="machine-link" onclick="openMachineDetail('${mid}')">${mid}</span></td>
      <td>${typeLabel}</td>
      <td>${a.capteur || "—"}</td>
      <td class="${severityClass(a.severity)}">${a.anomaly_score || 0}</td>
      <td><span class="badge ${cls}">${a.severity || "low"}</span></td>
      <td style="color:var(--text-muted);font-size:12px">${formatTime(a.timestamp)}</td>
      <td style="white-space:nowrap">
        ${a.status === "active" ? `
          <button class="btn btn-confirm btn-sm" onclick="handleFeedback('${a.alert_id}','confirmed')">Confirmer</button>
          <button class="btn btn-fp btn-sm" onclick="handleFeedback('${a.alert_id}','false_positive')">Faux positif</button>
        ` : `<span class="badge ${badgeStatus(a.status)}">${statusLabel(a.status)}</span>`}
      </td>
    </tr>`;
  }).join("");
}

function updateAlertCount(alerts) {
  const active = alerts.filter(a => a.status === "active").length;
  $("alertCount").textContent = active;
}

// ── Feedback ──
async function handleFeedback(alertId, decision) {
  try {
    await api(`/alerts/${encodeURIComponent(alertId)}/feedback`, {
      method: "POST",
      body: JSON.stringify({ decision, comment: "" }),
    });
    toast(decision === "confirmed" ? "Anomalie confirmée" : "Marquée comme faux positif");
    fetchAlerts();
    fetchHistory(0);
    loadStats();
  } catch (e) {
    toast("Erreur: " + e.message, "error");
  }
}

// ── Filters ──
function setFilter(status, btn) {
  currentFilter = status;
  document.querySelectorAll(".btn-group button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  fetchAlerts();
}

function onMachineFilterChange() {
  currentMachine = $("filter-machine").value;
  fetchAlerts();
}

// ── History ──
async function fetchHistory(page = 0) {
  historyPage = page;
  try {
    const d = await api("/alerts?status=all");
    let alerts = (d.alerts || []).filter(a => a.status !== "active");
    const total = alerts.length;
    const start = page * HISTORY_PAGE_SIZE;
    const pageItems = alerts.slice(start, start + HISTORY_PAGE_SIZE);
    renderHistoryTable(pageItems, total);
  } catch (e) {
    $("historyBody").innerHTML = `<tr><td colspan="7" style="text-align:center;color:#ef4444">Erreur: ${e.message}</td></tr>`;
  }
}

function renderHistoryTable(alerts, total) {
  const tbody = $("historyBody");
  const totalPages = Math.ceil(total / HISTORY_PAGE_SIZE);
  if (!alerts.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-muted)">Aucune validation enregistrée</td></tr>';
  } else {
    tbody.innerHTML = alerts.map(a => {
      const cls = a.severity === "high" ? "badge-red" : a.severity === "medium" ? "badge-orange" : "badge-blue";
      return `<tr>
        <td>${a.machine_id || "?"}</td>
        <td>${a.capteur || "—"}</td>
        <td class="${severityClass(a.severity)}">${a.anomaly_score || 0}</td>
        <td><span class="badge ${cls}">${a.severity || "low"}</span></td>
        <td style="color:var(--text-muted);font-size:12px">${formatTime(a.timestamp)}</td>
        <td><span class="badge ${badgeStatus(a.status)}">${statusLabel(a.status)}</span></td>
        <td>${a.comment || "—"}</td>
      </tr>`;
    }).join("");
  }
  $("historyPageInfo").textContent = `Page ${historyPage + 1}/${totalPages || 1} (${total} total)`;
  $("historyPrev").disabled = historyPage <= 0;
  $("historyNext").disabled = historyPage >= totalPages - 1;
}

function historyPrev() { if (historyPage > 0) fetchHistory(historyPage - 1); }
function historyNext() { fetchHistory(historyPage + 1); }

// ── Charts (Dashboard) ──
let pieChart, healthChart, timelineChart;

function renderPieChart() {
  const m = machinesCache;
  if (!m.length) return;
  const counts = { normal: 0, warning: 0, critical: 0 };
  m.forEach(x => {
    const hs = x.health_score || 0;
    if (hs < 30) counts.critical++;
    else if (hs < 70) counts.warning++;
    else counts.normal++;
  });
  const data = [counts.normal, counts.warning, counts.critical];
  const labels = [`Normal (${counts.normal})`, `Warning (${counts.warning})`, `Critique (${counts.critical})`];
  if (pieChart) {
    pieChart.data.labels = labels;
    pieChart.data.datasets[0].data = data;
    pieChart.update("default");
    return;
  }
  pieChart = new Chart($("pieChart"), {
    type: "doughnut",
    data: { labels, datasets: [{ data, backgroundColor: ["#22c55e", "#eab308", "#ef4444"], borderWidth: 0 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "60%",
      animation: { animateRotate: true, duration: 800, easing: "easeOutQuart" },
        plugins: { legend: { position: "bottom", labels: { color: "#64748b", font: { size: 11, family: "Inter" }, boxWidth: 12, padding: 14 } } },
    },
  });
}

function renderHealthChart() {
  const m = machinesCache;
  if (!m.length) return;
  const labels = m.map(x => x.machine_id);
  const scores = m.map(x => x.health_score || 0);
  const colors = scores.map(s => s < 30 ? "#ef4444" : s < 70 ? "#eab308" : "#22c55e");
  if (healthChart) {
    healthChart.data.labels = labels;
    healthChart.data.datasets[0].data = scores;
    healthChart.data.datasets[0].backgroundColor = colors;
    healthChart.update("default");
    return;
  }
  healthChart = new Chart($("healthChart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Health Score", data: scores, backgroundColor: colors, borderRadius: 6, borderSkipped: false }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 600, easing: "easeOutQuart" },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ctx.raw + "%" } } },
      scales: {
        y: { beginAtZero: true, max: 100, grid: { color: "#f1f5f9" }, ticks: { color: "#94a3b8", font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 11 } } },
      },
    },
  });
}

// ── Stats / Analytics ──
async function loadStats() {
  try {
    const d = await api("/stats/model-performance");
    return d;
  } catch (e) {
    return null;
  }
}

async function loadAnalytics() {
  // FP Chart
  loadStats().then(d => {
    if (d && d.weekly) renderFPChart(d.weekly);
    if (d) {
      $("anomalyStats").innerHTML = `
        <div style="font-size:36px;font-weight:700;color:var(--accent)">${d.total_validations || 0}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px">validations totales</div>`;
      $("modelStats").innerHTML = `
        <div style="font-size:36px;font-weight:700;color:#16a34a">${100 - (d.false_positive_rate || 0)}%</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px">précision (FP: ${d.false_positive_rate || 0}%)</div>`;
    }
  });

  // RUL stats
  const m = machinesCache;
  if (m.length) {
    const rulValues = m.map(x => x.rul_days || 0).filter(v => v > 0);
    const minRul = rulValues.length ? Math.min(...rulValues) : 0;
    const worst = m.find(x => (x.rul_days || 0) === minRul && minRul > 0);
    $("rulStats").innerHTML = `
      <div style="font-size:36px;font-weight:700;color:#8b5cf6">${minRul > 0 ? minRul : '—'}</div>
      <div style="font-size:12px;color:var(--text-muted);margin-top:4px">${minRul > 0 ? 'jours (' + (worst ? worst.machine_id : '—') + ')' : 'En attente de données'}</div>`;
  }

  // Temp chart
  renderTempChart();
}

let fpChart = null;

function renderFPChart(weekly) {
  if (!weekly || !weekly.length || typeof Chart === "undefined") return;
  if (fpChart) fpChart.destroy();
  fpChart = new Chart($("fpChart"), {
    type: "bar",
    data: {
      labels: weekly.map(w => w.week),
      datasets: [
        { label: "Faux positifs", data: weekly.map(w => w.false_positive), backgroundColor: "#ef4444", borderRadius: 4 },
        { label: "Total validations", data: weekly.map(w => w.total), backgroundColor: "#3b82f6", borderRadius: 4 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { color: "#64748b", font: { size: 11 } } },
        tooltip: { callbacks: { afterLabel: ctx => { const w = weekly[ctx.dataIndex]; return `Taux FP: ${w.fp_rate}%`; } } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { stepSize: 1, color: "#94a3b8" }, grid: { color: "#f1f5f9" } },
        x: { ticks: { color: "#94a3b8" }, grid: { display: false } },
      },
    },
  });
}

let tempChart = null;

function renderTempChart() {
  const m = machinesCache;
  if (!m.length || typeof Chart === "undefined") return;
  if (tempChart) tempChart.destroy();
  const labels = m.map(x => x.machine_id);
  const temps = m.map(x => x.last_temperature || Math.random() * 20 + 60);
  tempChart = new Chart($("tempChart"), {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Température (°C)", data: temps, backgroundColor: temps.map(t => t > 75 ? "#ef4444" : t > 65 ? "#eab308" : "#22c55e"), borderRadius: 6, borderSkipped: false }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { color: "#94a3b8" } },
        x: { grid: { display: false }, ticks: { color: "#94a3b8" } },
      },
    },
  });
}

// ── Timeline (FP evolution) ──
function renderTimeline() {
  loadStats().then(d => {
    if (!d || !d.weekly || !d.weekly.length || typeof Chart === "undefined") return;
    if (timelineChart) timelineChart.destroy();
    timelineChart = new Chart($("timelineChart"), {
      type: "line",
      data: {
        labels: d.weekly.map(w => w.week),
        datasets: [
          {
            label: "Taux FP (%)",
            data: d.weekly.map(w => w.fp_rate),
            borderColor: "#f59e0b",
            backgroundColor: "rgba(245,158,11,0.08)",
            fill: true,
            tension: 0.4,
            pointRadius: 4,
            pointBackgroundColor: "#f59e0b",
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: { duration: 500, easing: "easeOutQuart" },
        plugins: { legend: { labels: { color: "#64748b", font: { size: 11 } } } },
        scales: {
          x: { grid: { color: "#f1f5f9" }, ticks: { color: "#94a3b8" } },
          y: { beginAtZero: true, grid: { color: "#f1f5f9" }, ticks: { color: "#94a3b8" } },
        },
      },
    });
  });
}

// ── Reports ──
let reportCount = 0;
const reportLabels = { summary: "Résumé", alerts: "Alertes", machines: "Machines", anomalies: "Anomalies", complet: "Complet (graphiques)" };

function downloadCSV() {
  const type = $("csvType").value;
  const a = document.createElement("a");
  a.href = API_BASE + `/report/csv?type=${type}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
  reportCount++;
  addReportHistory("CSV", type);
}

function downloadPDF() {
  const type = $("pdfType").value;
  const a = document.createElement("a");
  a.href = API_BASE + `/report/pdf?type=${type}`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
  reportCount++;
  addReportHistory("PDF", type);
}

function addReportHistory(format, type) {
  const container = $("reportHistory");
  const label = reportLabels[type] || type;
  const ts = new Date().toLocaleTimeString("fr-FR");
  if (reportCount === 1) container.innerHTML = "";
  const item = document.createElement("div");
  item.style.cssText = "display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:4px;background:#f8fafc;border:1px solid var(--border);border-radius:var(--radius-sm);font-size:13px";
  item.innerHTML = `
    <span style="background:${format === "PDF" ? "#ef4444" : "#10b981"};color:#fff;border-radius:4px;padding:3px 8px;font-size:10px;font-weight:700">${format}</span>
    <span style="flex:1;font-weight:500">${label}</span>
    <span style="color:var(--text-muted);font-size:11px">${ts}</span>
    <i class="fas fa-check-circle" style="color:#16a34a;font-size:14px"></i>`;
  container.prepend(item);
  if (container.children.length > 5) container.lastChild.remove();
}

// ── Polling ──
async function pollAll() {
  await loadMachines();
  fetchRecentAlerts();
  renderPieChart();
  renderHealthChart();
  renderTimeline();
}

function startPolling() {
  pollAll();
  setInterval(pollAll, POLL_INTERVAL);
  setInterval(fetchAlerts, POLL_INTERVAL);
}

// ── Init ──
document.addEventListener("DOMContentLoaded", async () => {
  await loadMachines();
  renderMachines();
  fetchRecentAlerts();
  fetchAlerts();
  fetchHistory(0);
  renderPieChart();
  renderHealthChart();
  startPolling();
});
