import { $, api, busy, esc, fieldErrors, formData, showError, toast } from "../core.js";

const form = $("#settingsForm");

const ZONES = (Intl.supportedValuesOf?.("timeZone") || ["Asia/Kolkata", "UTC", "Europe/London", "America/New_York", "America/Los_Angeles", "Asia/Singapore", "Australia/Sydney"]);

async function load() {
  try {
    const { user: u } = await api("/account");
    const tz = $("#timezone");
    const zones = ZONES.includes(u.timezone) ? ZONES : [u.timezone, ...ZONES];
    tz.innerHTML = zones.map((z) => `<option value="${esc(z)}">${esc(z.replaceAll("_", " "))}</option>`).join("");
    for (const k of ["name", "sleep_goal_hours", "target_wake_time", "attendance_target", "study_goal_hours_week", "timezone"]) form[k].value = u[k];
    form.ai_assistant_enabled.checked = u.ai_assistant_enabled;
  } catch (e) { showError(e); }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter; busy(btn);
  try { await api("/account", { method: "PATCH", body: formData(form) }); fieldErrors(form, null); toast("Settings saved. Scores recalculated."); }
  catch (err) { fieldErrors(form, err); } finally { busy(btn, false); }
});

$("#pwForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target, btn = e.submitter; busy(btn);
  try { await api("/account/password", { method: "POST", body: formData(f) }); f.reset(); fieldErrors(f, null); toast("Password updated"); }
  catch (err) { fieldErrors(f, err); } finally { busy(btn, false); }
});

$("#delForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!confirm("This permanently deletes your account and all data. Continue?")) return;
  const f = e.target, btn = e.submitter; busy(btn);
  try { await api("/account", { method: "DELETE", body: formData(f) }); location.href = "/"; }
  catch (err) { fieldErrors(f, err); busy(btn, false); }
});

load();
