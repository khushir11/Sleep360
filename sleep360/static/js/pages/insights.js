import { $, $$, api, chart, empty, esc, fmt, icon, LEVEL, palette, showError, whenCharts } from "../core.js";
import { recCard } from "../widgets.js";

let days = 30;

// convert "HH:MM" to hours on an evening-anchored axis (18:00 = 0 → 14:00 next day = 20)
const evening = (t) => { if (!t) return null; const [hh, mm] = t.split(":").map(Number); let v = hh + mm / 60; if (v < 18) v += 24; return v - 18; };
const clock = (v) => { const t = (v + 18) % 24; const hh = Math.floor(t), mm = Math.round((t - hh) * 60); return `${String(hh).padStart(2, "0")}:${String(mm % 60).padStart(2, "0")}`; };

async function load() {
  try {
    const [a, recs, latest] = await Promise.all([api(`/analytics?days=${days}`), api("/recommendations"), api("/assessment/latest")]);
    renderSummary(a); renderRecs(recs.items); renderFatigue(latest.assessment); renderWeeks(a.weeks);
    whenCharts(() => drawCharts(a));
  } catch (e) { showError(e); $("#summary").innerHTML = `<div class="card span-2">${empty({ iconName: "alert", title: "Couldn't load analytics", text: e.message })}</div>`; }
}

function renderSummary(a) {
  const s = a.summary;
  if (!s.nights) { $("#summary").innerHTML = `<div class="card">${empty({ iconName: "moon", title: "No data in this period", text: "Log some nights to see your trends.", action: '<a class="btn primary" href="/sleep#log">Log sleep</a>' })}</div>`; return; }
  $("#summary").innerHTML = `
    <div class="card kpi"><div class="label">Average sleep</div><div class="value">${fmt.n(s.avg_duration, 1)}<small>h</small></div><div class="meta">${s.nights} nights logged · shortest ${fmt.h(s.min_duration)}</div></div>
    <div class="card kpi"><div class="label">Nights at goal</div><div class="value">${Math.round((s.nights_meeting_goal / s.nights) * 100)}<small>%</small></div><div class="meta">${s.nights_meeting_goal} of ${s.nights}</div></div>
    <div class="card kpi"><div class="label">Typical bedtime</div><div class="value">${esc(s.avg_bedtime)}</div><div class="meta">±${fmt.n(s.bedtime_sd_minutes)} min variation</div></div>
    <div class="card kpi"><div class="label">Weekend shift</div><div class="value">${s.social_jetlag_minutes != null ? `${fmt.n(s.social_jetlag_minutes)}<small>min</small>` : "—"}</div><div class="meta">sleep midpoint, weekends vs weekdays</div></div>`;
}

function renderRecs(items) {
  const box = $("#recList");
  box.innerHTML = "";
  if (!items.length) { box.innerHTML = empty({ iconName: "check", title: "No recommendations right now", text: "You're on track." }); return; }
  items.forEach((r) => box.append(recCard(r)));
}

const r1 = (v) => (Number.isInteger(v) ? v : Number(v).toFixed(1));
const unit = (u) => (!u ? "" : u.startsWith("/") ? esc(u) : ` ${esc(u)}`);

function renderFatigue(a) {
  const box = $("#fatigue");
  const p = a?.prediction;
  if (!p) { box.innerHTML = empty({ iconName: "battery", title: "No estimate yet", text: "Log a night (and ideally a week) to see what's driving your estimate." }); return; }
  $("#fatMeta").textContent = `Night ending ${fmt.day(a.date)} · model ${p.model_version}`;
  const top = p.contributions.slice(0, 6);
  const max = Math.max(0.01, ...top.map((c) => Math.abs(c.impact)));
  box.innerHTML = `
    <div class="row wrap"><span class="pill ${LEVEL[p.level]}">${esc(p.level)} · ${Math.round(p.probability * 100)}%</span>
    ${p.low_confidence ? '<span class="pill warn">Low confidence: fewer than 3 nights in the last week</span>' : ""}
    ${p.data_source === "synthetic" ? '<span class="pill">Trained on simulated data</span>' : ""}</div>
    <div class="stack mt-2">${top.map((c) => {
      const up = c.impact > 0;
      return `<div class="bar-row wide" title="Your value ${c.value}${c.unit ? ` ${c.unit}` : ""} vs typical ${c.reference}">
        <span class="small">${esc(c.label)}</span>
        <div class="bar ${up ? "bad" : "good"}"><i data-w="${(Math.abs(c.impact) / max) * 100}"></i></div>
        <span class="num small ${up ? "delta-down" : "delta-up"}">${up ? "+" : "−"}${Math.abs(c.impact * 100).toFixed(0)}</span></div>
        <div class="tiny faint">You: ${r1(c.value)}${unit(c.unit)} · typical: ${r1(c.reference)}${unit(c.unit)}</div>`;
    }).join("")}</div>
    <p class="small muted mt-2">${icon("info", "i")} Each bar shows roughly how many percentage points that factor adds (red) or removes (green) compared with a typical value. These are approximate "what-if" effects from a model trained on simulated data, not a diagnosis.</p>`;
  $$("[data-w]", box).forEach((el) => requestAnimationFrame(() => el.style.setProperty("--w", el.dataset.w)));
}

function renderWeeks(weeks) {
  const rows = weeks.filter((w) => w.nights);
  $("#weeks").innerHTML = rows.length ? `<table class="table"><thead><tr><th>Week ending</th><th>Nights</th><th>Avg sleep</th><th>Debt</th><th>Bedtime</th><th>Variation</th><th>Quality</th><th>Stress</th><th>Screens</th></tr></thead><tbody>
    ${rows.map((w) => `<tr><td>${esc(fmt.dm(w.week_ending))}</td><td>${w.nights}</td><td><strong>${fmt.h(w.avg_duration)}</strong></td><td>${fmt.h(w.sleep_debt_hours)}</td><td>${esc(w.avg_bedtime)}</td><td>±${fmt.n(w.bedtime_sd_minutes)}m</td><td>${fmt.n(w.avg_quality, 1)}</td><td>${w.avg_stress ?? "—"}</td><td>${w.avg_screen_minutes != null ? `${fmt.n(w.avg_screen_minutes)}m` : "—"}</td></tr>`).join("")}</tbody></table>`
    : `<p class="small muted">Not enough data yet.</p>`;
}

function drawCharts(a) {
  const p = palette();
  const labels = a.series.map((s) => (days > 30 ? fmt.dm(s.date) : fmt.dow(s.date)));
  chart($("#durChart"), {
    data: { labels, datasets: [
      { type: "bar", label: "Hours", data: a.series.map((s) => s.duration), backgroundColor: p.accent, borderRadius: 4, maxBarThickness: 18, yAxisID: "y" },
      { type: "line", label: "Score", data: a.series.map((s) => s.score), borderColor: p.good, backgroundColor: p.good, pointRadius: days > 30 ? 0 : 2, tension: .35, spanGaps: true, yAxisID: "y2" },
    ] },
    options: { plugins: { legend: { display: true, position: "bottom" } }, scales: { y: { min: 0, max: 12 }, y2: { position: "right", min: 0, max: 100, grid: { display: false }, border: { display: false } } } },
  });

  chart($("#windowChart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "Asleep", data: a.series.map((s) => (s.bedtime ? [evening(s.bedtime), evening(s.wake_time)] : null)), backgroundColor: p.accent, borderRadius: 4, borderSkipped: false, maxBarThickness: 14 }] },
    options: {
      scales: { y: { reverse: true, min: 2, max: 16, ticks: { stepSize: 2, callback: (v) => clock(v) } } },
      plugins: { tooltip: { callbacks: { label: (c) => (c.raw ? `${clock(c.raw[0])} → ${clock(c.raw[1])}` : "") } } },
    },
  });

  chart($("#weekdayChart"), {
    type: "bar",
    data: { labels: a.weekday_pattern.map((w) => w.weekday), datasets: [{ label: "Avg hours", data: a.weekday_pattern.map((w) => w.avg_duration), backgroundColor: a.weekday_pattern.map((w, i) => (i >= 5 ? p.warn : p.accent)), borderRadius: 6, maxBarThickness: 34 }] },
    options: { scales: { y: { min: 0, max: 11 } } },
  });

  chart($("#lifeChart"), {
    type: "line",
    data: { labels, datasets: [
      { label: "Stress (1–10)", data: a.series.map((s) => s.stress), borderColor: p.bad, backgroundColor: p.bad, spanGaps: true, tension: .3, pointRadius: 0, yAxisID: "y" },
      { label: "Sleepiness (1–10)", data: a.series.map((s) => s.sleepiness), borderColor: p.warn, backgroundColor: p.warn, spanGaps: true, tension: .3, pointRadius: 0, yAxisID: "y" },
      { label: "Screens (min)", data: a.series.map((s) => s.screen), borderColor: p.accent, backgroundColor: p.accent, spanGaps: true, tension: .3, pointRadius: 0, borderDash: [5, 3], yAxisID: "y2" },
    ] },
    options: { plugins: { legend: { display: true, position: "bottom" } }, scales: { y: { min: 0, max: 10 }, y2: { position: "right", min: 0, grid: { display: false }, border: { display: false } } } },
  });

  chart($("#attChart"), {
    type: "line",
    data: { labels: a.attendance_weekly.map((w) => fmt.dm(w.week_start)), datasets: [{ label: "Attendance %", data: a.attendance_weekly.map((w) => w.percentage), borderColor: p.good, backgroundColor: p.good, spanGaps: true, tension: .3 }] },
    options: { scales: { y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } } } },
  });
}

$$("[data-days]").forEach((b) => b.addEventListener("click", () => {
  days = parseInt(b.dataset.days, 10);
  $$("[data-days]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  load();
}));

load();
