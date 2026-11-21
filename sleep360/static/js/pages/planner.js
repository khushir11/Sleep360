import { $, $$, api, busy, chart, empty, esc, fieldErrors, fmt, formData, h, icon, localISO, modal, palette, showError, toast, whenCharts } from "../core.js";

const dlg = modal("taskModal");
let filter = "open";
let tasks = [];
let editing = null;

// ── plan ───────────────────────────────────────────────────────
async function loadPlan() {
  const start = $("#planStart").value;
  try {
    const p = await api(`/planner${start ? `?start=${start}` : ""}`);
    if (!start) $("#planStart").value = p.window.start;
    $("#planMeta").textContent = `${fmt.n(p.planned_minutes / 60, 1)}h planned · study until ${p.window.cutoff} · bed ${p.bedtime}`;
    $("#planNotes").innerHTML = p.notes.map((n) => `<div class="callout small">${icon("info")}<div></div></div>`).join("");
    $$("#planNotes .callout div").forEach((el, i) => { el.textContent = p.notes[i]; });
    const box = $("#plan");
    if (!p.blocks.length) {
      box.innerHTML = empty({ iconName: "list", title: p.window.minutes <= 0 ? "Past your study cutoff" : "Nothing to plan", text: p.window.minutes <= 0 ? "It's wind-down time. Tomorrow's plan will be ready in the morning." : "Add assignments or exams with due dates and estimates." });
    } else {
      box.innerHTML = "";
      for (const b of p.blocks) {
        const el = h(`<div class="block ${b.type}"><span class="time">${esc(b.start)}–${esc(b.end)}</span><div><div class="title"></div><div class="tiny muted"></div></div><span></span></div>`);
        $(".title", el).textContent = b.title;
        if (b.type === "focus") {
          $(".tiny", el).textContent = [b.subject, b.kind, b.due_in_days != null ? (b.due_in_days <= 0 ? "due today/overdue" : `due in ${b.due_in_days}d`) : null].filter(Boolean).join(" · ");
          el.lastElementChild.outerHTML = `<button class="btn sm" data-focus="${b.task_id}">${icon("play")}Focus</button>`;
        }
        box.append(el);
      }
      $$("[data-focus]", box).forEach((btn) => btn.addEventListener("click", () => { $("#timerTask").value = btn.dataset.focus; startTimer(); }));
    }
    if (p.unscheduled.length) {
      $("#plan").append(h(`<p class="small muted mt-2">Didn't fit today: ${p.unscheduled.map((u) => `${esc(u.title)} (${u.minutes} min)`).join(", ")}</p>`));
    }
  } catch (e) { $("#plan").innerHTML = empty({ iconName: "alert", title: "Couldn't build plan", text: e.message }); }
}
$("#planStart").addEventListener("change", loadPlan);

// ── tasks ──────────────────────────────────────────────────────
async function loadTasks() {
  const box = $("#tasks");
  try {
    ({ items: tasks } = await api(`/tasks?status=${filter}`));
    if (!tasks.length) { box.innerHTML = empty({ iconName: "list", title: filter === "open" ? "No open tasks" : "Nothing completed yet", text: filter === "open" ? "Add assignments and exams to get a study plan." : "" }); }
    else {
      box.innerHTML = `<div class="list"></div>`;
      for (const t of tasks) {
        const overdue = t.due_at && !t.done && new Date(t.due_at) < new Date();
        const el = h(`<div class="list-item">
          <label class="check"><input type="checkbox" ${t.done ? "checked" : ""} aria-label="Mark complete"></label>
          <div class="grow"><div class="title"></div><div class="small muted"></div></div>
          ${t.due_at ? `<span class="pill ${overdue ? "bad" : t.kind === "exam" ? "warn" : "accent"}">${t.done ? fmt.dm(t.due_at.slice(0, 10)) : fmt.rel(t.due_at)}</span>` : ""}
          <button class="btn sm ghost" data-edit>Edit</button></div>`);
        $(".title", el).textContent = t.title;
        $(".small", el).textContent = [t.subject_name, t.kind, t.due_at ? fmt.dt(t.due_at) : "no due date", !t.done ? `${t.remaining_minutes} of ${t.estimated_minutes} min left` : null, ["", "high priority", "", "low priority"][t.priority]].filter(Boolean).join(" · ");
        $("input", el).addEventListener("change", async (e) => {
          try { await api(`/tasks/${t.id}`, { method: "PATCH", body: { done: e.target.checked } }); toast(e.target.checked ? "Nice work!" : "Reopened"); refresh(); }
          catch (err) { showError(err); }
        });
        $("[data-edit]", el).addEventListener("click", () => openTask(t));
        $(".list", box).append(el);
      }
    }
    const sel = $("#timerTask"), cur = sel.value;
    sel.innerHTML = `<option value="">General study</option>` + (filter === "open" ? tasks : []).map((t) => `<option value="${t.id}">${esc(t.title)}</option>`).join("");
    sel.value = cur;
  } catch (e) { box.innerHTML = empty({ iconName: "alert", title: "Couldn't load tasks", text: e.message }); }
}

$$("[data-filter]").forEach((b) => b.addEventListener("click", () => {
  filter = b.dataset.filter;
  $$("[data-filter]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  loadTasks();
}));

async function loadSubjects() {
  try {
    const att = await api("/attendance");
    $("#tSubject").innerHTML = `<option value="">None</option>` + att.subjects.map((s) => `<option value="${s.id}">${esc(s.name)}</option>`).join("");
  } catch { /* subjects optional */ }
}

function openTask(t = null) {
  editing = t;
  const f = $("#taskForm"); f.reset(); fieldErrors(f, null);
  $("#taskH").textContent = t ? "Edit task" : "Add task";
  $("#taskDelete").classList.toggle("hidden", !t);
  if (t) {
    f.title.value = t.title; f.kind.value = t.kind; f.subject_id.value = t.subject_id ?? ""; f.due_at.value = t.due_at ? t.due_at.slice(0, 16) : "";
    f.estimated_minutes.value = t.estimated_minutes; f.priority.value = t.priority;
  } else {
    const d = new Date(); d.setDate(d.getDate() + 3); d.setHours(23, 59, 0, 0); f.due_at.value = localISO(d);
  }
  dlg.showModal();
}
$("#addTaskBtn").addEventListener("click", () => openTask());

$("#taskForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, btn = e.submitter; busy(btn);
  try {
    const body = formData(f);
    if (editing) await api(`/tasks/${editing.id}`, { method: "PATCH", body });
    else await api("/tasks", { method: "POST", body });
    dlg.close(); toast("Task saved"); refresh();
  } catch (err) { fieldErrors(f, err); } finally { busy(btn, false); }
});
$("#taskDelete").addEventListener("click", async () => {
  if (!editing || !confirm("Delete this task?")) return;
  try { await api(`/tasks/${editing.id}`, { method: "DELETE" }); dlg.close(); toast("Deleted"); refresh(); } catch (e) { showError(e); }
});

// ── focus timer (50/10) ────────────────────────────────────────
const FOCUS = 50 * 60, BREAK = 10 * 60;
let timer = null, mode = "focus", remaining = FOCUS, startedAt = null, focusedSec = 0;

function renderClock() {
  const m = Math.floor(remaining / 60), s = remaining % 60;
  $("#timerClock").textContent = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  $("#timerMode").textContent = mode === "focus" ? "Focus" : "Break";
  $("#timerMode").className = `pill ${mode === "focus" ? "accent" : "good"}`;
  document.title = timer ? `${$("#timerClock").textContent} · ${mode === "focus" ? "Focus" : "Break"} · Sleep360` : "Planner · Sleep360";
}

function notify(title, body) {
  toast(`${title}: ${body}`);
  if ("Notification" in window && Notification.permission === "granted") new Notification(title, { body });
}

function startTimer() {
  if (timer) return;
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  startedAt = startedAt || new Date();
  timer = setInterval(tick, 1000);
  $("#timerStart").disabled = true; $("#timerStop").disabled = false;
  $("#timerMeta").textContent = "Phone face down. You've got this.";
  renderClock();
}

function tick() {
  remaining -= 1;
  if (mode === "focus") focusedSec += 1;
  if (remaining <= 0) {
    if (mode === "focus") { mode = "break"; remaining = BREAK; notify("Break time", "Stand up, stretch, drink water. Back in 10 minutes."); }
    else { mode = "focus"; remaining = FOCUS; notify("Break over", "Ready for another focus block?"); }
  }
  renderClock();
}

async function stopTimer() {
  clearInterval(timer); timer = null;
  $("#timerStart").disabled = false; $("#timerStop").disabled = true;
  const minutes = Math.round(focusedSec / 60);
  const taskId = $("#timerTask").value ? parseInt($("#timerTask").value, 10) : null;
  const started = startedAt;
  mode = "focus"; remaining = FOCUS; focusedSec = 0; startedAt = null;
  renderClock();
  $("#timerMeta").textContent = "50 min focus, then a 10 min break";
  if (minutes < 1) return toast("Session too short to save");
  const focus = parseInt(prompt("How focused were you? (1 = distracted, 5 = deep focus)", "4") || "", 10);
  try {
    await api("/study-sessions", { method: "POST", body: { started_at: localISO(started), duration_minutes: minutes, task_id: taskId, ...(focus >= 1 && focus <= 5 ? { focus } : {}) } });
    toast(`Saved ${minutes} min of study`);
    refresh();
  } catch (e) { showError(e); }
}
$("#timerStart").addEventListener("click", startTimer);
$("#timerStop").addEventListener("click", stopTimer);
window.addEventListener("beforeunload", (e) => { if (timer) { e.preventDefault(); e.returnValue = ""; } });

// ── productivity ───────────────────────────────────────────────
async function loadProductivity() {
  try {
    const p = await api("/productivity?days=14");
    const pct = Math.min(100, (p.week_hours / (p.week_goal_hours || 1)) * 100);
    $("#weekStudy").innerHTML = `<div class="kpi"><div class="value">${p.week_hours}<small>h</small></div><div class="meta">of ${p.week_goal_hours}h weekly goal${p.avg_focus ? ` · avg focus ${p.avg_focus}/5` : ""}</div></div><div class="bar mt-2"><i></i></div>`;
    $("#weekStudy .bar i").style.setProperty("--w", pct);
    $("#bySubject").innerHTML = p.by_subject.length ? `<div class="list">${p.by_subject.map((s) => `<div class="list-item"><span class="grow">${esc(s.subject)}</span><strong class="num">${fmt.n(s.minutes / 60, 1)}h</strong></div>`).join("")}</div>` : `<p class="small muted">Use the focus timer to track study time.</p>`;
    const c = p.sleep_study_correlation;
    $("#corr").innerHTML = c ? `<div class="callout small">${icon("chart")}<div>Nights you slept longer were followed by ${c.r > 0.1 ? "more" : c.r < -0.1 ? "less" : "about the same amount of"} study time (r = ${c.r}, ${c.n} days). ${esc(c.note)}</div></div>` : "";
    whenCharts(() => {
      const pal = palette();
      chart($("#studyChart"), { type: "bar", data: { labels: p.daily.map((d) => fmt.dow(d.date)), datasets: [{ label: "Minutes", data: p.daily.map((d) => d.minutes), backgroundColor: pal.accent, borderRadius: 5, maxBarThickness: 22 }] } });
    });
  } catch (e) { showError(e); }
}

function refresh() { loadPlan(); loadTasks(); loadProductivity(); }
renderClock();
loadSubjects();
refresh();
