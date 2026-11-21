import { $, api, chart, empty, esc, palette, whenCharts } from "../core.js";

const NAMES = {
  logistic_regression: "Logistic regression", random_forest: "Random forest", gradient_boosting: "Gradient boosting (hist)",
  baseline_base_rate: "Baseline: base rate", baseline_rule_sleep_lt_6h: "Baseline: \"slept < 6h\" rule",
};

async function load() {
  const box = $("#card");
  let c;
  try { c = await api("/model"); } catch (e) { box.innerHTML = `<div class="card">${empty({ iconName: "alert", title: "Model not loaded", text: e.message })}</div>`; return; }
  const m = (k, v) => `${v[k].mean.toFixed(3)} <span class="faint">± ${v[k].std.toFixed(3)}</span>`;
  box.innerHTML = `
    <div class="grid g-4">
      <div class="card kpi"><div class="label">Selected model</div><div class="value small">${esc(NAMES[c.selected_model])}</div><div class="meta">${esc(c.selection_rule)}</div></div>
      <div class="card kpi"><div class="label">Training rows</div><div class="value">${c.n_rows.toLocaleString()}</div><div class="meta">${c.n_groups} ${c.data_source === "synthetic" ? "simulated students" : "users"}</div></div>
      <div class="card kpi"><div class="label">Positive rate</div><div class="value">${(c.positive_rate * 100).toFixed(1)}<small>%</small></div><div class="meta">${esc(c.target)}</div></div>
      <div class="card kpi"><div class="label">Data</div><div class="value"><span class="pill ${c.data_source === "synthetic" ? "warn" : "good"}">${esc(c.data_source)}</span></div><div class="meta">version ${esc(c.version)}</div></div>
    </div>
    <section class="card"><div class="card-head"><div><h2>Model comparison</h2><p>${esc(c.cv)}. Higher ROC-AUC and average precision are better; lower Brier is better (calibration).</p></div></div>
      <div class="table-wrap"><table class="table"><thead><tr><th>Model</th><th>ROC-AUC</th><th>Avg precision</th><th>Brier</th><th>F1 @0.5</th><th>Accuracy</th></tr></thead><tbody>
      ${Object.entries(c.comparison).map(([k, v]) => `<tr${k === c.selected_model ? ' class="selected"' : ""}><td>${esc(NAMES[k] || k)} ${k === c.selected_model ? '<span class="pill accent">selected</span>' : ""}</td><td>${m("roc_auc", v)}</td><td>${m("avg_precision", v)}</td><td>${m("brier", v)}</td><td>${m("f1", v)}</td><td>${m("accuracy", v)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="small muted mt-2">${esc(c.data_disclaimer)}</p></section>
    <section class="card"><div class="card-head"><div><h2>Global feature importance</h2><p>Permutation importance: drop in ROC-AUC on held-out students when a feature is shuffled.</p></div></div>
      <div class="chart-box tall"><canvas id="impChart" role="img" aria-label="Feature importance"></canvas></div></section>`;
  whenCharts(() => {
    const p = palette();
    chart($("#impChart"), {
      type: "bar",
      data: { labels: c.permutation_importance.map((f) => f.label), datasets: [{ label: "ROC-AUC drop", data: c.permutation_importance.map((f) => f.importance), backgroundColor: p.accent, borderRadius: 4 }] },
      options: { indexAxis: "y", scales: { x: { grid: { color: p.grid } }, y: { grid: { display: false } } } },
    });
  });
}
load();
