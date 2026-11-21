import { $, $$, api, busy, fieldErrors, formData, showError } from "../core.js";

function nextUrl() {
  const n = new URLSearchParams(location.search).get("next");
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/dashboard"; // only same-site redirects
}

const form = $("#authForm");
form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.submitter; busy(btn);
  try {
    await api(`/auth/${form.dataset.mode}`, { method: "POST", body: formData(form) });
    location.href = nextUrl();
  } catch (err) { fieldErrors(form, err); busy(btn, false); }
});

$$("[data-demo]").forEach((b) => b.addEventListener("click", async () => {
  busy(b);
  try { await api("/auth/demo", { method: "POST" }); location.href = "/dashboard"; }
  catch (err) { showError(err); busy(b, false); }
}));
