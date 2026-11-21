import { $, $$, api, busy, empty, esc, fieldErrors, fmt, h, icon, modal, showError, toast } from "../core.js";
import { scoreBlock } from "../widgets.js";

const form = $("#logForm");
const touched = new Set();

function iso(d) { const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000); return z.toISOString().slice(0, 16); }

function defaults() {
  const wake = new Date(); wake.setHours(7, 0, 0, 0);
  if (new Date() < wake) wake.setDate(wake.getDate()); // still valid: this morning
  const bed = new Date(wake); bed.setDate(bed.getDate() - 1); bed.setHours(23, 30, 0, 0);
  form.bedtime.value = iso(bed);
  form.wake_time.value = iso(wake);
}

function preview() {
  const b = new Date(form.bedtime.value), w = new Date(form.wake_time.value);
  const box = $("#durationPreview div");
  const hrs = (w - b) / 36e5;
  if (!form.bedtime.value || !form.wake_time.value || Number.isNaN(hrs)) { box.textContent = "Enter both times"; return; }
  if (hrs <= 0) { box.textContent = "Wake time must be after bedtime"; return; }
  box.innerHTML = `<strong>${fmt.hm(hrs)}</strong> of sleep, logged for the morning of ${esc(fmt.day(form.wake_time.value.slice(0, 10)))}`;
}

function bindRange(id, out) {
  const el = $(`#${id}`);
  const o = $(`#${out}`);
  const optional = el.dataset.optional !== undefined;
  const upd = () => { o.textContent = optional && !touched.has(id) ? "—" : el.value; };
  el.addEventListener("input", () => { touched.add(id); upd(); });
  upd();
}

let caffeine = "";
$$("#caffeineSeg button").forEach((b) => b.addEventListener("click", () => {
  caffeine = b.dataset.v;
  $$("#caffeineSeg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
}));

form.addEventListener("input", (e) => { if (["bedtime", "wake_time"].includes(e.target.name)) preview(); });

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    bedtime: form.bedtime.value, wake_time: form.wake_time.value, quality: parseInt(form.quality.value, 10),
  };
  for (const id of ["daytime_sleepiness", "stress"]) if (touched.has(id)) body[id] = parseInt(form[id].value, 10);
  if (form.screen_minutes_before_bed.value !== "") body.screen_minutes_before_bed = parseInt(form.screen_minutes_before_bed.value, 10);
  if (form.exercise_minutes.value !== "") body.exercise_minutes = parseInt(form.exercise_minutes.value, 10);
  if (caffeine !== "") body.caffeine_after_2pm = caffeine === "true";
  if (form.notes.value.trim()) body.notes = form.notes.value.trim();

  const btn = $("#saveBtn");
  busy(btn);
  try {
    const res = await api("/sleep", { method: "POST", body });
    fieldErrors(form, null);
    toast(res.created ? "Night saved" : "Night updated");
    const r = $("#result");
    r.classList.remove("hidden");
    r.replaceChildren(h(`<div class="card-head"><h2>Your score for ${esc(fmt.day(res.log.date))}</h2><a class="btn sm" href="/dashboard">Go to dashboard ${icon("arrow-right")}</a></div>`), scoreBlock(res.assessment, res.change));
    r.scrollIntoView({ behavior: "smooth", block: "nearest" });
    loadHistory();
  } catch (err) { fieldErrors(form, err); showError(err); } finally { busy(btn, false); }
});

async function loadPlan() {
  try {
    const p = await api("/sleep/bedtime-plan");
    $("#plan").innerHTML = `
      <div class="kpi"><div class="label">Lights out</div><div class="value">${esc(p.bedtime)}</div><div class="meta">for ${p.goal_hours}h before a ${esc(p.target_wake_time)} alarm (incl. ~${p.latency_minutes} min to fall asleep)</div></div>
      <div class="list mt-2">
        <div class="list-item"><span class="grow">Start winding down</span><strong class="num">${esc(p.wind_down_start)}</strong></div>
        <div class="list-item"><span class="grow">Screens off</span><strong class="num">${esc(p.screens_off)}</strong></div>
        <div class="list-item"><span class="grow">Last caffeine</span><strong class="num">${esc(p.last_caffeine)}</strong></div>
      </div>
      <p class="small muted mt-2">Prefer sleep cycles? ${p.cycle_options.map((c) => `<strong>${esc(c.bedtime)}</strong> (${c.cycles} cycles, ${c.sleep_hours}h)`).join(" or ")}. Cycle length varies, so treat these as approximate.</p>
      <a class="small" href="/settings">Change goal or wake time</a>`;
  } catch (e) { $("#plan").innerHTML = empty({ iconName: "alert", title: "Couldn't load", text: e.message }); }
}

async function loadHistory() {
  const box = $("#history");
  try {
    const { items } = await api("/sleep");
    if (!items.length) { box.innerHTML = empty({ iconName: "moon", title: "No nights logged yet", text: "Your history will appear here." }); return; }
    box.innerHTML = `<table class="table"><thead><tr><th>Night</th><th>Bed → wake</th><th>Duration</th><th>Quality</th><th>Stress</th><th>Sleepiness</th><th>Source</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody></tbody></table>`;
    const tb = $("tbody", box);
    for (const x of items) {
      const tr = h(`<table><tr>
        <td>${esc(fmt.day(x.date))}</td><td class="num">${esc(x.bedtime.slice(11))} → ${esc(x.wake_time.slice(11))}</td>
        <td><strong>${fmt.hm(x.duration_hours)}</strong></td><td>${x.quality}/10</td><td>${x.stress ?? "—"}</td><td>${x.daytime_sleepiness ?? "—"}</td>
        <td><span class="pill">${esc(x.source)}</span></td>
        <td><button class="btn sm ghost danger" data-del="${x.id}" aria-label="Delete night of ${esc(x.date)}">${icon("trash")}</button></td></tr></table>`).querySelector("tr");
      tb.append(tr);
    }
    $$("[data-del]", box).forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("Delete this night? Your scores will be recalculated.")) return;
      try { await api(`/sleep/${b.dataset.del}`, { method: "DELETE" }); toast("Deleted"); loadHistory(); } catch (e) { showError(e); }
    }));
  } catch (e) { box.innerHTML = empty({ iconName: "alert", title: "Couldn't load history", text: e.message }); }
}

// CSV import
const dlg = modal("importModal");
$("#importBtn").addEventListener("click", () => { $("#importResult").innerHTML = ""; dlg.showModal(); });
$("#importForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  if (!fd.get("file")?.size) return toast("Choose a CSV file first", "error");
  const btn = e.submitter; busy(btn);
  try {
    const { report: r } = await api("/sleep/import", { method: "POST", form: fd });
    $("#importResult").innerHTML = `<div class="callout ${r.error_count ? "warn" : "good"}">${icon(r.error_count ? "alert" : "check")}<div>
      <strong>${r.created} added, ${r.updated} updated</strong> from ${r.rows} rows.
      ${r.skipped_existing ? `${r.skipped_existing} already logged (skipped). ` : ""}${r.duplicates_in_file ? `${r.duplicates_in_file} duplicate dates in file (last kept). ` : ""}
      ${r.error_count ? `<ul class="small">${r.errors.slice(0, 8).map((x) => `<li>Line ${x.line}: ${esc(x.error)}</li>`).join("")}</ul>` : ""}</div></div>`;
    if (r.created || r.updated) loadHistory();
  } catch (err) { showError(err); } finally { busy(btn, false); }
});

defaults(); preview();
bindRange("quality", "qualityOut"); bindRange("daytime_sleepiness", "sleepyOut"); bindRange("stress", "stressOut");
loadPlan(); loadHistory();
if (location.hash === "#log") form.bedtime.focus();
