import { $, $$, api, busy, chart, empty, esc, fieldErrors, fmt, formData, h, icon, modal, palette, setVar, showError, STATUS, toast, whenCharts } from "../core.js";

const root = $("#att");
let state = null;
let semesterId = null;
let editing = null;
const semDlg = modal("semModal");
const subDlg = modal("subModal");

async function load() {
  try {
    const [att, sems] = await Promise.all([api(`/attendance${semesterId ? `?semester_id=${semesterId}` : ""}`), api("/semesters")]);
    state = att;
    renderSemesters(sems.items);
    render();
  } catch (e) { root.innerHTML = empty({ iconName: "alert", title: "Couldn't load attendance", text: e.message }); showError(e); }
}

function renderSemesters(items) {
  const sel = $("#semSelect");
  sel.classList.toggle("hidden", items.length < 2);
  sel.innerHTML = items.map((s) => `<option value="${s.id}">${esc(s.name)}${s.is_active ? " (active)" : ""}</option>`).join("");
  if (state.semester) sel.value = state.semester.id;
  $("#addSubjectBtn").classList.toggle("hidden", !state.semester);
}

function render() {
  if (!state.semester) {
    root.innerHTML = `<div class="card">${empty({ iconName: "calendar", title: "Set up your semester", text: "Create a semester, add your subjects, then mark classes as you go. Takes about two minutes.", action: '<button class="btn primary" data-act="new-sem">Create semester</button>' })}</div>`;
    $('[data-act="new-sem"]', root).addEventListener("click", openSem);
    return;
  }
  const s = state.semester, ov = state.overall;
  $("#semLabel").textContent = `${s.name} · ${fmt.dm(s.start_date)} – ${fmt.dm(s.end_date)} · default target ${state.default_target}%`;
  root.innerHTML = `
    <div class="grid g-4">
      <div class="card kpi"><div class="label">Overall</div><div class="value">${ov.percentage != null ? `${fmt.n(ov.percentage, 1)}<small>%</small>` : "—"}</div><div class="meta">${ov.attended}/${ov.conducted} classes</div></div>
      <div class="card kpi"><div class="label">Below target</div><div class="value">${ov.subjects_at_risk}</div><div class="meta">subject(s)</div></div>
      <div class="card kpi"><div class="label">Close to limit</div><div class="value">${ov.subjects_warning}</div><div class="meta">within 5 points</div></div>
      <div class="card kpi"><div class="label">Semester ends</div><div class="value">${Math.max(0, Math.round((new Date(`${s.end_date}T00:00`) - new Date()) / 864e5))}<small>days</small></div><div class="meta">${fmt.day(s.end_date)}</div></div>
    </div>
    <section class="card"><div class="card-head"><div><h2>Mark today</h2><p>${esc(fmt.day(state.today))}. Tap again to change. Cancelled classes don't count.</p></div>
      <input class="input" type="date" id="markDate" value="${state.today}" max="${state.today}" aria-label="Date to mark"></div>
      <div id="subjects" class="grid g-3"></div></section>
    <div class="grid g-2">
      <section class="card"><div class="card-head"><div><h2>Weekly attendance</h2><p>Share of classes attended each week</p></div></div><div class="chart-box"><canvas id="weeklyChart" role="img" aria-label="Weekly attendance percentage"></canvas></div></section>
      <section class="card"><div class="card-head"><div><h2>What if…</h2><p>Simulate attending or missing upcoming classes</p></div></div>
        <form id="simForm" class="form-grid">
          <div class="field full"><label for="simSubject">Subject</label><select class="input" id="simSubject"></select></div>
          <div class="field"><label for="simAttend">Attend next</label><input class="input" type="number" id="simAttend" min="0" max="200" value="5"></div>
          <div class="field"><label for="simMiss">Miss next</label><input class="input" type="number" id="simMiss" min="0" max="200" value="0"></div>
        </form>
        <div id="simOut" class="mt-2"></div></section>
    </div>
    <section class="card"><div class="card-head"><h2>Monthly history</h2></div><div class="table-wrap" id="monthly"></div></section>`;

  renderSubjects();
  $("#markDate").addEventListener("change", () => renderSubjects());

  const simSel = $("#simSubject");
  simSel.innerHTML = state.subjects.map((x) => `<option value="${x.id}">${esc(x.name)}</option>`).join("");
  const runSim = debounce(simulate, 250);
  $("#simForm").addEventListener("input", runSim);
  if (state.subjects.length) simulate();

  $("#monthly").innerHTML = state.monthly.length ? `<table class="table"><thead><tr><th>Month</th><th>Attended</th><th>Held</th><th>%</th></tr></thead><tbody>
    ${state.monthly.map((m) => `<tr><td>${esc(new Date(`${m.month}-01T00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" }))}</td><td>${m.attended}</td><td>${m.conducted}</td><td><strong>${fmt.pct(m.percentage)}</strong></td></tr>`).join("")}</tbody></table>`
    : `<p class="muted small">Marked classes will be summarised here by month.</p>`;

  whenCharts(() => {
    const p = palette();
    chart($("#weeklyChart"), {
      type: "line",
      data: { labels: state.weekly.map((w) => fmt.dm(w.week_start)), datasets: [
        { label: "Attendance %", data: state.weekly.map((w) => w.percentage), borderColor: p.accent, backgroundColor: p.accent, tension: .3, spanGaps: true, pointRadius: 3 },
        { label: "Target", data: state.weekly.map(() => state.default_target), borderColor: p.bad, borderDash: [4, 4], borderWidth: 1, pointRadius: 0 },
      ] },
      options: { scales: { y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } } } },
    });
  });
}

function renderSubjects() {
  const box = $("#subjects");
  const date = $("#markDate").value;
  if (!state.subjects.length) {
    box.outerHTML = `<div id="subjects">${empty({ iconName: "book", title: "No subjects yet", text: "Add the subjects you're taking this semester.", action: '<button class="btn primary" data-act="add-sub">Add subject</button>' })}</div>`;
    $('[data-act="add-sub"]').addEventListener("click", () => openSubject());
    return;
  }
  const marked = date === state.today ? Object.fromEntries(state.marked_today.filter((r) => r.period === 1).map((r) => [r.subject_id, r.status])) : {};
  box.innerHTML = "";
  for (const s of state.subjects) {
    const [cls, label] = STATUS[s.status];
    const advice = s.status === "critical" ? `Max reachable this semester is ${fmt.pct(s.max_achievable)}. Talk to your faculty advisor.`
      : s.status === "shortage" ? `Attend the next <strong>${s.classes_needed}</strong> classes in a row to reach ${s.target}%.`
      : s.percentage == null ? "Mark your first class below." : `You can miss <strong>${s.safe_skips}</strong> class${s.safe_skips === 1 ? "" : "es"} and stay at ${s.target}%.`;
    const card = h(`<article class="subject" aria-label="${esc(s.name)}">
      <div class="row-between"><div class="row"><span class="dot"></span><div><h3>${esc(s.name)}</h3><div class="tiny muted">${esc(s.code || "")} ${s.code ? "·" : ""} target ${s.target}%</div></div></div>
        <button class="btn sm ghost" data-edit aria-label="Edit ${esc(s.name)}">Edit</button></div>
      <div class="row-between"><span class="pct num">${fmt.pct(s.percentage)}</span><span class="pill ${cls}">${label}</span></div>
      <div class="progress ${s.status}"><i></i><b title="Target ${s.target}%"></b></div>
      <div class="small muted">${s.attended}/${s.conducted} attended · ~${s.remaining_classes} classes left · projected ${fmt.pct(s.projected_end, 0)}${s.recent_rate != null ? ` · last 4 weeks ${fmt.pct(s.recent_rate, 0)}` : ""}</div>
      <p class="small">${advice}</p>
      <div class="mark-buttons" role="group" aria-label="Mark ${esc(s.name)} for ${esc(date)}">
        <button class="btn sm present" data-mark="present" aria-pressed="${marked[s.id] === "present"}">${icon("check")}Present</button>
        <button class="btn sm absent" data-mark="absent" aria-pressed="${marked[s.id] === "absent"}">Absent</button>
        <button class="btn sm cancelled" data-mark="cancelled" aria-pressed="${marked[s.id] === "cancelled"}">Cancelled</button>
      </div></article>`);
    setVar($(".dot", card), "--c", s.color);
    setVar($(".progress i", card), "--w", s.percentage ?? 0);
    setVar($(".progress b", card), "--t", s.target);
    $("[data-edit]", card).addEventListener("click", () => openSubject(s));
    $$("[data-mark]", card).forEach((b) => b.addEventListener("click", () => mark(s, b.dataset.mark, date, b)));
    box.append(card);
  }
}

async function mark(s, status, date, btn) {
  busy(btn);
  try {
    await api("/attendance", { method: "POST", body: { subject_id: s.id, date, status } });
    toast(`${s.name}: marked ${status}`);
    await load();
  } catch (e) { showError(e); busy(btn, false); }
}

async function simulate() {
  const id = $("#simSubject")?.value;
  if (!id) return;
  const a = Math.max(0, parseInt($("#simAttend").value || "0", 10)), m = Math.max(0, parseInt($("#simMiss").value || "0", 10));
  try {
    const r = await api(`/attendance/simulate?subject_id=${id}&attend=${a}&miss=${m}`);
    $("#simOut").innerHTML = `<div class="callout ${r.meets_target ? "good" : "bad"}">${icon(r.meets_target ? "check" : "alert")}<div>You'd be at <strong>${fmt.pct(r.percentage)}</strong> (${r.attended}/${r.conducted}). ${r.meets_target ? "Above" : "Below"} the ${r.target}% target.</div></div>`;
  } catch (e) { showError(e); }
}

function openSem() {
  const f = $("#semForm"); f.reset(); fieldErrors(f, null);
  const t = new Date(); f.start_date.value = t.toISOString().slice(0, 10);
  const e = new Date(t); e.setDate(e.getDate() + 120); f.end_date.value = e.toISOString().slice(0, 10);
  semDlg.showModal();
}

function openSubject(s = null) {
  editing = s;
  const f = $("#subForm"); f.reset(); fieldErrors(f, null);
  $("#subH").textContent = s ? `Edit ${s.name}` : "Add subject";
  $("#subDelete").classList.toggle("hidden", !s);
  if (s) {
    f.name.value = s.name; f.code.value = s.code || ""; f.classes_per_week.value = s.classes_per_week; f.color.value = s.color;
    f.target_override.value = s.target !== state.default_target ? s.target : "";
    f.initial_conducted.value = s.initial_conducted;
    f.initial_attended.value = s.initial_attended;
  }
  subDlg.showModal();
}

$("#newSemBtn").addEventListener("click", openSem);
$("#addSubjectBtn").addEventListener("click", () => openSubject());
$("#semSelect").addEventListener("change", (e) => { semesterId = e.target.value; load(); });

$("#semForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, btn = e.submitter; busy(btn);
  try { const s = await api("/semesters", { method: "POST", body: formData(f) }); semesterId = s.id; semDlg.close(); toast("Semester created"); load(); }
  catch (err) { fieldErrors(f, err); } finally { busy(btn, false); }
});

$("#subForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, btn = e.submitter; busy(btn);
  const body = formData(f);
  try {
    if (editing) {
      await api(`/subjects/${editing.id}`, { method: "PATCH", body });
    } else await api("/subjects", { method: "POST", body: { ...body, semester_id: state.semester.id } });
    subDlg.close(); toast("Saved"); load();
  } catch (err) { fieldErrors(f, err); } finally { busy(btn, false); }
});

$("#subDelete").addEventListener("click", async () => {
  if (!editing || !confirm(`Delete ${editing.name} and all its attendance records?`)) return;
  try { await api(`/subjects/${editing.id}`, { method: "DELETE" }); subDlg.close(); toast("Subject deleted"); load(); } catch (e) { showError(e); }
});

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

load();
