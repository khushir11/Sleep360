// Reusable UI pieces shared by several pages.
import { esc, h, icon, setVar } from "./core.js";

const COMP_LABEL = { duration: "Duration", regularity: "Regularity", quality: "Quality", timing: "Timing" };

export function scoreBlock(a, change) {
  if (!a) {
    return h(`<div class="empty"><div class="ic">${icon("moon")}</div><h3>No score yet</h3>
      <p class="small">Log last night's sleep to get your first score.</p><a class="btn primary" href="/sleep#log">Log sleep</a></div>`);
  }
  const score = a.score.total;
  const color = score >= 75 ? "var(--good)" : score >= 55 ? "var(--accent)" : score >= 40 ? "var(--warn)" : "var(--bad)";
  const el = h(`<div>
    <div class="score-wrap">
      <div class="ring" role="img" aria-label="Sleep score ${Math.round(score)} out of 100"><div class="ring-inner"><div><strong>${Math.round(score)}</strong><span>of 100</span></div></div></div>
      <div class="components"></div>
    </div>
    <div class="callout mt-2">${icon("info")}<div class="change"></div></div>
  </div>`);
  const ring = el.querySelector(".ring");
  setVar(ring, "--c", color);
  requestAnimationFrame(() => setVar(ring, "--p", score));
  const comps = el.querySelector(".components");
  for (const [key, c] of Object.entries(a.score.components)) {
    const ratio = c.points / c.max;
    const row = h(`<div class="bar-row"><span class="muted">${COMP_LABEL[key]}</span><div class="bar ${ratio >= .8 ? "good" : ratio >= .5 ? "" : ratio >= .3 ? "warn" : "bad"}"><i></i></div><span class="num small">${c.points.toFixed(0)}/${c.max}</span></div>`);
    requestAnimationFrame(() => setVar(row.querySelector("i"), "--w", ratio * 100));
    comps.append(row);
  }
  const ch = el.querySelector(".change");
  ch.textContent = change?.summary || "";
  if (change?.risk) {
    const r = document.createElement("div");
    r.className = "small mt-1";
    r.textContent = change.risk.text + (change.risk.top_factors?.length ? ` Main factor: ${change.risk.top_factors.join(", ")}.` : "");
    ch.append(r);
  }
  return el;
}

export function recCard(r, compact = false) {
  const el = h(`<details class="rec ${esc(r.tone)}" ${compact ? "" : "open"}>
    <summary><h3>${esc(r.title)}</h3><p></p></summary>
    <ul></ul><div class="why"></div></details>`);
  el.querySelector("summary p").textContent = r.body;
  const ul = el.querySelector("ul");
  r.actions.forEach((a) => { const li = document.createElement("li"); li.textContent = a; ul.append(li); });
  el.querySelector(".why").textContent = `Why you're seeing this: ${r.why}${r.evidence ? ` · Source: ${r.evidence}` : ""}`;
  return el;
}
