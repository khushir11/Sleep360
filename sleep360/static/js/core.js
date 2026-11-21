// Sleep360 frontend core: API client, DOM helpers, charts, notifications.
// ES module, no build step. All user-supplied text is inserted via textContent or esc().

const CSRF = document.querySelector('meta[name="csrf-token"]')?.content || "";

export class ApiError extends Error {
  constructor(status, body) {
    super(body?.error?.message || `Request failed (${status})`);
    this.status = status;
    this.code = body?.error?.code;
    this.details = body?.error?.details;
  }
}

export async function api(path, { method = "GET", body, form, raw } = {}) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRFToken"] = CSRF;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: "same-origin" });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    throw new ApiError(401, {});
  }
  if (raw) { if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => ({}))); return res; }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, data);
  return data;
}

// ── DOM helpers ────────────────────────────────────────────────
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
export const icon = (name, cls = "i") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

export function h(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

export function setVar(el, name, value) { el?.style.setProperty(name, value); }

export function toast(msg, type = "info") {
  const el = h(`<div class="toast ${type === "error" ? "error" : ""}"></div>`);
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), 4200);
}

export function showError(err, fallback = "Something went wrong") {
  console.error(err);
  toast(err?.message || fallback, "error");
}

export function empty({ iconName = "info", title, text = "", action = "" }) {
  return `<div class="empty"><div class="ic">${icon(iconName)}</div><h3>${esc(title)}</h3><p class="small">${esc(text)}</p>${action}</div>`;
}

export function busy(btn, on = true) {
  if (!btn) return;
  if (on) { btn.dataset.label = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>`; }
  else { btn.disabled = false; if (btn.dataset.label) btn.innerHTML = btn.dataset.label; }
}

/** Serialise a form to an object; numbers/booleans coerced via data-type. Empty optional fields are omitted. */
export function formData(form) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    const t = el.dataset.type;
    if (el.type === "checkbox") { out[el.name] = el.checked; continue; }
    if (el.value === "") { if (el.dataset.nullable !== undefined) out[el.name] = null; continue; }
    out[el.name] = t === "int" ? parseInt(el.value, 10) : t === "float" ? parseFloat(el.value) : el.value;
  }
  return out;
}

export function fieldErrors(form, err) {
  $$("[aria-invalid]", form).forEach((el) => el.removeAttribute("aria-invalid"));
  const box = $(".form-error", form);
  if (box) box.textContent = err?.message || "";
  for (const d of err?.details || []) {
    const el = d.field && form.elements[d.field.split(".")[0]];
    if (el?.setAttribute) el.setAttribute("aria-invalid", "true");
  }
}

// ── formatting ─────────────────────────────────────────────────
export const fmt = {
  h: (v, d = 1) => (v == null ? "—" : `${Number(v).toFixed(d)}h`),
  hm(v) { if (v == null) return "—"; const m = Math.round(v * 60); return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`; },
  pct: (v, d = 1) => (v == null ? "—" : `${Number(v).toFixed(d)}%`),
  n: (v, d = 0) => (v == null ? "—" : Number(v).toFixed(d)),
  day: (iso) => new Date(`${iso}T00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }),
  dow: (iso) => new Date(`${iso}T00:00`).toLocaleDateString(undefined, { weekday: "short" }),
  dm: (iso) => new Date(`${iso}T00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" }),
  dt: (iso) => new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }),
  rel(iso) {
    const diff = (new Date(iso) - new Date()) / 36e5;
    if (diff < 0) return "overdue";
    if (diff < 12) return `in ${Math.max(1, Math.round(diff))}h`;
    const a = new Date(); a.setHours(0, 0, 0, 0);
    const b = new Date(iso); b.setHours(0, 0, 0, 0);
    const days = Math.round((b - a) / 864e5);
    return days === 0 ? "today" : days === 1 ? "tomorrow" : `in ${days}d`;
  },
};

export const STATUS = {
  safe: ["good", "On track"], warning: ["warn", "Close to limit"], shortage: ["bad", "Shortage"],
  critical: ["bad", "Target unreachable"], no_data: ["", "No classes yet"],
};
export const LEVEL = { low: "good", moderate: "warn", high: "bad" };

export function localISO(d = new Date()) {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 16);
}

// tiny, safe markdown: escape first, then **bold**, *italic*, lists, paragraphs
export function md(text) {
  const lines = esc(text).split("\n");
  let html = "", inList = false;
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|\W)\*(?!\s)(.+?)\*(?=\W|$)/g, "$1<em>$2</em>");
    const m = line.match(/^\s*(?:[-•]|\d+\.)\s+(.*)/);
    if (m) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${m[1]}</li>`; continue; }
    if (inList) { html += "</ul>"; inList = false; }
    if (line.trim()) html += `<p>${line}</p>`;
  }
  return html + (inList ? "</ul>" : "");
}

// ── charts (Chart.js, vendored) ────────────────────────────────
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
export const palette = () => ({
  accent: cssVar("--chart-1"), good: cssVar("--chart-2"), warn: cssVar("--chart-3"), bad: cssVar("--bad"),
  grid: cssVar("--chart-grid"), text: cssVar("--text-2"), surface: cssVar("--surface"),
});

const charts = new Map();
export function chart(canvas, config) {
  if (!canvas || !window.Chart) return null;
  charts.get(canvas)?.destroy();
  const p = palette();
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.color = p.text;
  const base = {
    responsive: true, maintainAspectRatio: false, animation: { duration: 450 },
    interaction: { mode: "index", intersect: false },
    plugins: { legend: { display: false, labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
      tooltip: { backgroundColor: cssVar("--text"), titleColor: p.surface, bodyColor: p.surface, padding: 10, cornerRadius: 8, displayColors: true, boxPadding: 4 } },
    scales: {
      x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
      y: { grid: { color: p.grid }, border: { display: false }, ticks: { padding: 6 } },
    },
  };
  const merged = deepMerge(base, config.options || {});
  const c = new Chart(canvas, { ...config, options: merged });
  charts.set(canvas, c);
  return c;
}
function deepMerge(a, b) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b)) out[k] = v && typeof v === "object" && !Array.isArray(v) && typeof a[k] === "object" ? deepMerge(a[k], v) : v;
  return out;
}
export function whenCharts(fn) {
  if (window.Chart) return fn();
  window.addEventListener("load", fn, { once: true });
}

// ── shell: logout, notifications ───────────────────────────────
async function initShell() {
  document.addEventListener("click", (e) => { if (e.target.closest('[data-action="reload"]')) location.reload(); });
  $$('[data-action="logout"]').forEach((b) => b.addEventListener("click", async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    location.href = "/";
  }));

  const btn = $("#notifBtn");
  if (!btn) return;
  let pop = null;
  const seen = new Set(JSON.parse(sessionStorageSafe("get", "s360_seen") || "[]"));

  async function refresh() {
    try {
      const data = await api("/notifications");
      const unread = data.items.filter((n) => !n.read);
      const count = $("#notifCount");
      count.textContent = unread.length > 9 ? "9+" : unread.length;
      count.classList.toggle("hidden", unread.length === 0);
      btn.setAttribute("aria-label", `Notifications (${unread.length} unread)`);
      // optional browser notifications for new items
      if ("Notification" in window && Notification.permission === "granted") {
        for (const n of unread) if (!seen.has(n.id)) { new Notification(n.title, { body: n.body, tag: `s360-${n.id}` }); seen.add(n.id); }
        sessionStorageSafe("set", "s360_seen", JSON.stringify([...seen].slice(-100)));
      } else unread.forEach((n) => seen.add(n.id));
      if (pop) render(data.items);
    } catch { /* offline: keep last state */ }
  }

  function render(items) {
    const body = $(".popover-body", pop);
    body.innerHTML = items.length ? "" : empty({ iconName: "bell", title: "You're all caught up", text: "Reminders and alerts will show up here." });
    for (const n of items) {
      const a = h(`<a class="notif ${n.read ? "" : "unread"}"><strong></strong><span></span></a>`);
      a.href = n.link || "#";
      a.querySelector("strong").textContent = n.title;
      a.querySelector("span").textContent = n.body;
      body.append(a);
    }
  }

  btn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (pop) { pop.remove(); pop = null; btn.setAttribute("aria-expanded", "false"); return; }
    pop = h(`<div class="popover" role="dialog" aria-label="Notifications">
      <div class="popover-head"><h3>Notifications</h3><div class="row">
        ${"Notification" in window && Notification.permission === "default" ? '<button class="btn sm ghost" data-enable>Enable alerts</button>' : ""}
        <button class="btn sm ghost" data-readall>Mark all read</button></div></div>
      <div class="popover-body"><div class="skeleton h-md"></div></div></div>`);
    $("#notifWrap").append(pop);
    btn.setAttribute("aria-expanded", "true");
    $("[data-readall]", pop).addEventListener("click", async () => { await api("/notifications/read", { method: "POST", body: {} }); refresh(); });
    $("[data-enable]", pop)?.addEventListener("click", async (ev) => { await Notification.requestPermission(); ev.target.remove(); });
    await refresh();
  });
  document.addEventListener("click", (e) => { if (pop && !pop.contains(e.target)) { pop.remove(); pop = null; btn.setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && pop) { pop.remove(); pop = null; btn.focus(); } });
  refresh();
  setInterval(refresh, 60000);
}

function sessionStorageSafe(op, k, v) {
  try { return op === "get" ? sessionStorage.getItem(k) : sessionStorage.setItem(k, v); } catch { return null; }
}

export function modal(id) {
  const d = document.getElementById(id);
  $$("[data-close]", d).forEach((b) => b.addEventListener("click", () => d.close()));
  return d;
}

initShell();
