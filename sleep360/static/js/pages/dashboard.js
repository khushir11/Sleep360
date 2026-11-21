import { $, $$, api, chart, empty, esc, fmt, icon, LEVEL, palette, setVar, showError, STATUS, whenCharts } from "../core.js";
import { recCard, scoreBlock } from "../widgets.js";

const root = $("#dash");

function k(name) { return root.querySelector(`[data-k="${name}"]`); }

async function load() {
  let d;
  try { d = await api("/dashboard"); } catch (e) {
    root.innerHTML = empty({ iconName: "alert", title: "Couldn't load your dashboard", text: e.message, action: '<button class="btn" data-action="reload">Retry</button>' });
    return showError(e);
  }
  root.replaceChildren($("#dashTpl").content.cloneNode(true));
  root.setAttribute("aria-busy", "false");

  const hour = new Date().getHours();
  $("#greeting").textContent = `${hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"}, ${d.user.name.split(" ")[0]}`;
  $("#todayLabel").textContent = new Date(`${d.today}T00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  const a = d.assessment, w = d.week;
  const last = d.series.at(-1);
  if (last?.duration != null) {
    k("last").innerHTML = `${fmt.hm(last.duration)}`;
    k("lastMeta").textContent = `${last.bedtime} → ${last.wake_time} · quality ${last.quality}/10`;
  } else {
    k("last").innerHTML = `<small>Not logged</small>`;
    k("lastMeta").innerHTML = `<a href="/sleep#log">Log last night</a>`;
  }
  k("avg").innerHTML = w.nights ? `${fmt.n(w.avg_duration, 1)}<small>h</small>` : "—";
  k("avgMeta").textContent = w.nights ? `Goal ${d.user.sleep_goal_hours}h · ${w.sleep_debt_hours}h sleep debt` : "No nights this week";

  const ov = d.attendance.overall;
  k("att").innerHTML = ov.percentage != null ? `${fmt.n(ov.percentage, 1)}<small>%</small>` : "—";
  k("attMeta").innerHTML = ov.percentage == null ? '<a href="/attendance">Add your subjects</a>'
    : ov.subjects_at_risk ? `<span class="pill bad">${ov.subjects_at_risk} subject(s) below target</span>`
    : ov.subjects_warning ? `<span class="pill warn">${ov.subjects_warning} close to limit</span>` : `<span class="pill good">All subjects on track</span>`;

  if (a?.fatigue_level) {
    k("fat").innerHTML = `<span class="pill ${LEVEL[a.fatigue_level]}">${esc(a.fatigue_level)}</span>`;
    k("fatMeta").innerHTML = `${Math.round(a.fatigue_probability * 100)}% estimated · <a href="/model">simulated-data model</a>`;
  } else { k("fat").innerHTML = "—"; k("fatMeta").textContent = "Log sleep to get an estimate"; }

  // score
  k("scoreDate").textContent = a ? `Night ending ${fmt.day(a.date)}` : "";
  k("scoreBody").replaceChildren(scoreBlock(a, d.change));

  // goals + bedtime
  const goals = k("goals");
  goals.innerHTML = d.daily_goals.map((g) => `<div class="goal ${g.done ? "done" : ""}"><span class="tick">${icon("check")}</span><span>${esc(g.label)}</span></div>`).join("");
  k("streakPill").textContent = `${d.achievements.streaks.logging}-day streak`;
  const bp = d.bedtime_plan;
  k("bedtime").innerHTML = `${icon("moon")}<div><strong>Tonight: lights out by ${esc(bp.bedtime)}</strong><div class="small">Wind down from ${esc(bp.wind_down_start)} · screens off ${esc(bp.screens_off)} · for a ${esc(bp.target_wake_time)} wake-up</div></div>`;

  // recommendations
  const recs = k("recs");
  if (!d.recommendations.length) recs.innerHTML = empty({ iconName: "check", title: "Nothing urgent", text: "Keep logging and we'll flag anything worth your attention." });
  else d.recommendations.forEach((r) => recs.append(recCard(r, true)));

  // subjects
  const subs = d.attendance.subjects;
  k("subjects").innerHTML = !subs.length ? empty({ iconName: "calendar", title: "No subjects yet", text: "Add your subjects to track attendance and get shortage alerts.", action: '<a class="btn primary sm" href="/attendance">Add subjects</a>' })
    : `<div class="list">${subs.map((s) => {
      const [cls, label] = STATUS[s.status];
      return `<div class="list-item"><span class="dot" data-color="${esc(s.color)}"></span><div class="grow"><div class="title">${esc(s.name)}</div>
        <div class="small muted">${s.attended}/${s.conducted} classes${s.status === "shortage" ? ` · attend next ${s.classes_needed}` : s.percentage != null ? ` · ${s.safe_skips} safe skip${s.safe_skips === 1 ? "" : "s"}` : ""}</div></div>
        <div class="num"><strong>${fmt.pct(s.percentage)}</strong></div><span class="pill ${cls}">${label}</span></div>`;
    }).join("")}</div>`;
  $$("[data-color]", root).forEach((el) => setVar(el, "--c", el.dataset.color));

  // tasks
  const tasks = d.upcoming_tasks;
  k("tasks").innerHTML = !tasks.length ? `<p class="muted small">Nothing due in the next 7 days.</p>`
    : `<div class="list">${tasks.map((t) => `<div class="list-item"><div class="grow"><div class="title">${esc(t.title)}</div><div class="small muted">${esc(t.subject_name || t.kind)} · ${fmt.dt(t.due_at)}</div></div><span class="pill ${t.kind === "exam" ? "bad" : "accent"}">${fmt.rel(t.due_at)}</span></div>`).join("")}</div>`;

  // achievements
  const ach = d.achievements;
  k("logStreak").textContent = ach.streaks.logging;
  k("goalStreak").textContent = ach.streaks.sleep_goal;
  k("challengeCount").textContent = `${ach.challenge.nights}/7`;
  k("challengeText").textContent = `Consistency challenge: be in bed ${ach.challenge.window} for 7 nights in a row.`;
  k("challengeDots").innerHTML = Array.from({ length: 7 }, (_, i) => `<i class="${i < ach.challenge.nights ? "on" : ""}"></i>`).join("");
  k("badges").innerHTML = ach.badges.map((b) => `<div class="badge ${b.earned ? "earned" : ""}" title="${esc(b.description)}"><div class="ic">${icon(b.icon)}</div><strong>${esc(b.name)}</strong>${b.earned ? "Earned" : "Locked"}</div>`).join("");

  whenCharts(() => drawTrend(d.series, d.user.sleep_goal_hours));
}

function drawTrend(series, goal) {
  const p = palette();
  chart($("#trendChart"), {
    data: {
      labels: series.map((s) => fmt.dow(s.date)),
      datasets: [
        { type: "bar", label: "Hours slept", data: series.map((s) => s.duration), backgroundColor: series.map((s) => (s.duration != null && s.duration < goal - 1 ? p.warn : p.accent)), borderRadius: 6, maxBarThickness: 26, yAxisID: "y" },
        { type: "line", label: "Sleep score", data: series.map((s) => s.score), borderColor: p.good, backgroundColor: p.good, tension: .35, pointRadius: 3, spanGaps: true, yAxisID: "y2" },
        { type: "line", label: "Goal", data: series.map(() => goal), borderColor: p.text, borderDash: [4, 4], borderWidth: 1, pointRadius: 0, yAxisID: "y" },
      ],
    },
    options: {
      plugins: { legend: { display: true, position: "bottom" } },
      scales: { y: { min: 0, max: 12, title: { display: true, text: "hours" } }, y2: { position: "right", min: 0, max: 100, grid: { display: false }, border: { display: false } } },
    },
  });
}

load();
