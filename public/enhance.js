// Small progressive-enhancement layer: visual preferences are local to this browser.
const preferenceKey = 'foodflow-display-preferences';
const defaults = { theme: 'light', density: 'comfortable', contrast: 'normal' };
let prefs = { ...defaults, ...JSON.parse(localStorage.getItem(preferenceKey) || '{}') };

function applyPreferences() {
  const root = document.documentElement;
  root.dataset.theme = prefs.theme;
  root.dataset.density = prefs.density;
  root.dataset.contrast = prefs.contrast;
  localStorage.setItem(preferenceKey, JSON.stringify(prefs));
  document.querySelectorAll('[data-preference]').forEach(button => {
    const [key, value] = button.dataset.preference.split(':');
    button.classList.toggle('active', prefs[key] === value);
  });
}

function preferencePanel() {
  if (document.querySelector('.appearance-trigger')) return;
  const panel = document.createElement('section');
  panel.className = 'appearance-panel'; panel.hidden = true;
  panel.innerHTML = `<h3>Make it yours</h3><p>These display choices are saved in this browser.</p>
    <div class="appearance-row"><span>Colour mode</span><span><button data-preference="theme:light">Light</button> <button data-preference="theme:dark">Dark</button></span></div>
    <div class="appearance-row"><span>Layout density</span><span><button data-preference="density:comfortable">Easy</button> <button data-preference="density:compact">Compact</button></span></div>
    <div class="appearance-row"><span>Visibility</span><span><button data-preference="contrast:normal">Standard</button> <button data-preference="contrast:high">High contrast</button></span></div>`;
  const trigger = document.createElement('button');
  trigger.className = 'appearance-trigger'; trigger.type = 'button'; trigger.title = 'Display preferences'; trigger.setAttribute('aria-label', 'Display preferences'); trigger.textContent = '◐';
  trigger.onclick = () => { panel.hidden = !panel.hidden; trigger.setAttribute('aria-expanded', String(!panel.hidden)); };
  panel.onclick = event => {
    const button = event.target.closest('[data-preference]'); if (!button) return;
    const [key, value] = button.dataset.preference.split(':'); prefs[key] = value; applyPreferences();
  };
  document.body.append(panel, trigger); applyPreferences();
}

function loginVisual() {
  const login = document.querySelector('.login');
  if (!login || login.querySelector('.login-visual')) return;
  const visual = document.createElement('aside');
  visual.className = 'login-visual';
  visual.innerHTML = `<span class="eyebrow">● Operations, connected</span><h2>Every packet has a story.</h2><p>Orders, production, stock and audit evidence move as one clear flow.</p><div class="mini-chart"><span>Today’s production visibility</span><strong>94%</strong><div class="mini-bars"><i></i><i></i><i></i><i></i><i></i><i></i></div></div>`;
  login.append(visual);
}

function dashboardPolish() {
  const icons = { dashboard: '⌂', orders: '▣', production: '◉', inventory: '▤', reports: '◫', audit: '✓' };
  document.querySelectorAll('.side button[data-page]').forEach(button => { button.dataset.icon = icons[button.dataset.page] || '•'; });
  const signout = document.querySelector('.side #logout'); if (signout) signout.dataset.icon = '↪';
}

function decorate() { loginVisual(); dashboardPolish(); preferencePanel(); }
new MutationObserver(decorate).observe(document.body, { childList: true, subtree: true });
document.addEventListener('DOMContentLoaded', decorate);
applyPreferences();
