import { $, $$, api, esc, h, md, showError, toast } from "../core.js";

const log = $("#log");
const form = $("#chatForm");
const input = $("#msg");

const PROVIDER = { anthropic: "Claude", fallback: "Sleep360 built-in guide", safety: "Safety response" };

function bubble(m) {
  const el = h(`<div class="msg ${m.role}"></div>`);
  if (m.role === "assistant") {
    el.innerHTML = md(m.content) + (m.provider ? `<div class="meta">${esc(PROVIDER[m.provider] || m.provider)}</div>` : "");
  } else el.textContent = m.content;
  return el;
}

function scroll() { log.scrollTop = log.scrollHeight; }

async function load() {
  try {
    const d = await api("/assistant/messages");
    $("#aiStatus").textContent = d.ai_configured && d.ai_enabled ? "Powered by Claude, grounded in your own data."
      : d.ai_enabled ? "Running in built-in mode (no AI key configured). Answers still use your real data."
      : "AI is turned off in Settings. Using the built-in guide.";
    log.innerHTML = "";
    if (!d.items.length) {
      log.append(bubble({ role: "assistant", content: "Hi! I can see your recent sleep, attendance and tasks. Ask me anything, or pick a suggestion below." }));
    }
    d.items.forEach((m) => log.append(bubble(m)));
    scroll();
  } catch (e) { showError(e); }
}

async function send(text) {
  text = text.trim();
  if (!text) return;
  log.append(bubble({ role: "user", content: text }));
  const typing = h(`<div class="msg assistant" aria-label="Assistant is typing"><span class="typing"><i></i><i></i><i></i></span></div>`);
  log.append(typing); scroll();
  input.value = ""; input.disabled = true;
  try {
    const { message } = await api("/assistant/messages", { method: "POST", body: { message: text } });
    typing.replaceWith(bubble(message));
  } catch (e) {
    typing.remove();
    showError(e);
    input.value = text;
  } finally { input.disabled = false; input.focus(); scroll(); }
}

form.addEventListener("submit", (e) => { e.preventDefault(); send(input.value); });
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); } });
$$("#suggestions button").forEach((b) => b.addEventListener("click", () => send(b.textContent)));
$("#clearBtn").addEventListener("click", async () => {
  if (!confirm("Clear your chat history?")) return;
  try { await api("/assistant/messages", { method: "DELETE" }); toast("Chat cleared"); load(); } catch (e) { showError(e); }
});

load();
