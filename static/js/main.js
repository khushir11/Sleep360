// Sleep360 – Main JavaScript

// ── Navbar scroll ──
window.addEventListener('scroll', () => {
  document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 20);
});

// ── Session ──
async function initSession() {
  try {
    const r = await fetch('/api/user-data');
    const d = await r.json();
    if (d.ok && d.student) setUser(d.student);
  } catch(e) {}
}

function setUser(student) {
  document.getElementById('navUser').style.display = 'flex';
  document.getElementById('navUserName').textContent = student.name;
  const lb = document.getElementById('navLoginBtn');
  if (lb) lb.style.display = 'none';
  window._currentUser = student;
}

async function doLogin() {
  const email = document.getElementById('loginEmail').value.trim();
  if (!email) return toast('Please enter your email', true);
  const r = await fetch('/api/login', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ email })
  });
  const d = await r.json();
  if (d.ok) {
    setUser(d.student);
    closeModal('loginModal');
    toast(`Welcome back, ${d.student.name}! 🌙`);
    setTimeout(() => location.reload(), 800);
  } else {
    toast('Email not found. Please register.', true);
  }
}

async function doRegister() {
  const name  = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const age   = parseInt(document.getElementById('regAge').value) || 20;
  if (!name || !email) return toast('Please fill Name and Email', true);
  const r = await fetch('/api/register', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ name, email, age })
  });
  const d = await r.json();
  if (d.ok) {
    setUser(d.student);
    closeModal('loginModal');
    toast(`Account created! Welcome, ${d.student.name}! 🎉`);
    setTimeout(() => location.reload(), 800);
  } else {
    toast('Registration failed', true);
  }
}

async function logout() {
  await fetch('/api/logout', { method: 'POST' });
  toast('Logged out. See you soon! 👋');
  setTimeout(() => location.reload(), 800);
}

// ── Modals ──
function openModal(id) {
  document.getElementById(id).classList.add('open');
}
function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}
function switchTab(tab) {
  document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tabLogin').style.display   = tab === 'login'    ? '' : 'none';
  document.getElementById('tabRegister').style.display = tab === 'register' ? '' : 'none';
  event.target.classList.add('active');
}

// ── Mobile menu ──
function toggleMobile() {
  document.getElementById('mobileMenu').classList.toggle('open');
}

// ── Toast ──
function toast(msg, error = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast' + (error ? ' error' : '');
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3200);
}

// ── Slider value display ──
function updateSlider(inputId, displayId, suffix='') {
  const v = parseFloat(document.getElementById(inputId).value).toFixed(1);
  document.getElementById(displayId).textContent = v + suffix;
}

// ── Bar chart renderer ──
function renderBarChart(containerId, data, colorFn) {
  const c = document.getElementById(containerId);
  if (!c) return;
  const max = Math.max(...data.map(d => d.v), 1);
  c.innerHTML = data.map(d => {
    const pct = Math.round((d.v / max) * 100);
    const color = colorFn ? colorFn(d) : 'bar-default';
    return `
      <div class="bar-group">
        <span class="bar-num">${typeof d.v === 'number' ? d.v.toFixed(d.dec||0) : d.v}</span>
        <div class="bar ${color}" style="height:${pct}%"></div>
        <span class="bar-lbl">${d.l}</span>
      </div>`;
  }).join('');
}

// ── Number animation ──
function animateNumber(el, target, duration=1200, suffix='') {
  const start = 0;
  const step = (target - start) / (duration / 16);
  let current = start;
  const tick = () => {
    current = Math.min(current + step, target);
    el.textContent = typeof target === 'float'
      ? current.toFixed(1) + suffix
      : Math.round(current) + suffix;
    if (current < target) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

// ── Intersection observer for animations ──
const observer = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
    }
  });
}, { threshold: 0.1 });
document.querySelectorAll('.fade-in-up').forEach(el => observer.observe(el));

// ── Init ──
document.addEventListener('DOMContentLoaded', initSession);
