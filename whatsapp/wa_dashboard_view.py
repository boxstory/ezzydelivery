"""
WAHA session-health ops dashboard.

A single self-contained HTML page that polls /waha/api/sessions/<session>
every 5 seconds and surfaces session status, linked phone, and a QR pane.

Auth: htpasswd-gated by nginx upstream of /waha/wa-dashboard/. Do NOT add
Django auth here.

The browser talks to /waha/api/... directly; nginx reverse-proxies to the
WAHA container with X-Api-Key injected, so the API key never reaches the
client.
"""
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache


@never_cache
def wa_dashboard(request):
    session = settings.WAHA_DEFAULT_SESSION
    html = _DASHBOARD_HTML.replace('%SESSION%', session)
    return HttpResponse(html, content_type='text/html; charset=utf-8')


# WhatsApp-parity colors, intentional. This ops page deliberately uses the
# WhatsApp brand green (#00a884) and matching neutral palette rather than the
# project Brand Kit, so operators recognise it as a WhatsApp tool at a glance.
_DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WAHA Session — EzzyDelivery</title>
<style>
  :root {
    --wa-green: #00a884;
    --wa-green-hover: #008f6f;
    --wa-red: #dc2626;
    --wa-red-hover: #b91c1c;
    --wa-text: #111b21;
    --wa-muted: #667781;
    --wa-border: #e9edef;
    --wa-bg: #f0f2f5;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: var(--wa-bg);
    color: var(--wa-text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      "Helvetica Neue", Arial, sans-serif;
    font-size: 0.9375rem;
    line-height: 1.4;
  }
  .wa-wrap {
    min-height: 100vh;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 2.5rem 1rem;
  }
  .wa-card {
    width: 100%;
    max-width: 32rem;
    background: #ffffff;
    border: 0.0625rem solid var(--wa-border);
    border-radius: 0.75rem;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }
  .wa-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }
  .wa-title {
    font-size: 1rem;
    font-weight: 600;
  }
  .wa-status {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 0.8125rem;
    text-transform: uppercase;
    color: var(--wa-text);
  }
  .wa-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    background: #6b7280;
    display: inline-block;
  }
  .wa-desc {
    color: var(--wa-muted);
    font-size: 0.875rem;
    margin: 0 0 1.25rem 0;
  }
  .wa-actions {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
    padding-top: 0.5rem;
    border-top: 0.0625rem solid var(--wa-border);
    margin-top: 0.75rem;
  }
  .wa-btn {
    appearance: none;
    border: none;
    cursor: pointer;
    background: var(--wa-green);
    color: #ffffff;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    transition: background 0.15s ease;
  }
  .wa-btn:hover:not(:disabled) { background: var(--wa-green-hover); }
  .wa-btn:disabled { opacity: 0.7; cursor: not-allowed; }
  .wa-btn--danger { background: var(--wa-red); }
  .wa-btn--danger:hover:not(:disabled) { background: var(--wa-red-hover); }
  .wa-qr {
    display: none;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }
  .wa-qr img {
    display: block;
    max-width: 16rem;
    width: 100%;
    height: auto;
    background: #ffffff;
    padding: 0.75rem;
    border: 0.0625rem solid var(--wa-border);
    border-radius: 0.5rem;
  }
  .wa-qr-hint {
    font-size: 0.75rem;
    color: var(--wa-muted);
  }
  .wa-foot {
    margin-top: 1.25rem;
    padding-top: 0.875rem;
    border-top: 0.0625rem solid var(--wa-border);
    text-align: center;
    font-size: 0.75rem;
    color: var(--wa-muted);
  }
  .wa-foot a {
    color: var(--wa-muted);
    text-decoration: none;
  }
  .wa-foot a:hover { text-decoration: underline; }
  .wa-foot .sep { margin: 0 0.5rem; opacity: 0.6; }
</style>
</head>
<body>
<div class="wa-wrap">
  <div class="wa-card" id="wa-card">
    <div class="wa-head">
      <div class="wa-title">WAHA Session</div>
      <div class="wa-status">
        <span class="wa-dot" id="wa-dot"></span>
        <span id="wa-status-text">LOADING</span>
      </div>
    </div>
    <p class="wa-desc" id="wa-desc">Loading…</p>
    <div class="wa-actions" id="wa-actions"></div>
    <div class="wa-qr" id="wa-qr">
      <img id="wa-qr-img" alt="WhatsApp QR code">
      <div class="wa-qr-hint">Open WhatsApp → Linked devices → Link a device</div>
    </div>
    <div class="wa-foot">
      <a href="/waha/wa-chats/" target="_blank" rel="noopener">Chat Dashboard</a>
      <span class="sep">·</span>
      <a href="/waha/" target="_blank" rel="noopener">WAHA Swagger</a>
      <span class="sep">·</span>
      <a href="/waha/api/sessions/%SESSION%" target="_blank" rel="noopener">Raw session JSON</a>
      <span class="sep">·</span>
      <a href="/waha/api/%SESSION%/auth/qr?format=image" target="_blank" rel="noopener">Raw QR image</a>
    </div>
  </div>
</div>
<script>
(function () {
  'use strict';
  const SESSION = '%SESSION%';
  const POLL_MS = 5000;
  const QR_REFRESH_MS = 55000;

  const dotEl = document.getElementById('wa-dot');
  const statusTextEl = document.getElementById('wa-status-text');
  const descEl = document.getElementById('wa-desc');
  const actionsEl = document.getElementById('wa-actions');
  const qrEl = document.getElementById('wa-qr');
  const qrImgEl = document.getElementById('wa-qr-img');

  const QR_URL = '/waha/api/' + SESSION + '/auth/qr?format=image';

  function setDot(color) { dotEl.style.background = color; }

  function clearActions() { actionsEl.innerHTML = ''; }

  function makeBtn(label, opts) {
    const b = document.createElement('button');
    b.className = 'wa-btn' + (opts && opts.danger ? ' wa-btn--danger' : '');
    b.textContent = label;
    b.type = 'button';
    return b;
  }

  function showQr() {
    qrImgEl.src = QR_URL + '&t=' + Date.now();
    qrEl.style.display = 'flex';
  }

  // Recover a session by stopping then starting it. A FAILED session is still
  // considered "started" by WAHA, so calling start alone returns 422
  // ("already started") and nothing happens — the stop first is required.
  async function restartSession() {
    try {
      await fetch('/waha/api/sessions/stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ name: SESSION })
      });
    } catch (e) {
      // best-effort; a not-yet-started session has nothing to stop
    }
    // small gap so WAHA settles into STOPPED before we start again
    await new Promise(function (r) { setTimeout(r, 1500); });
    try {
      await fetch('/waha/api/sessions/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ name: SESSION })
      });
    } catch (e) {
      // best-effort; status poll will reflect outcome
    }
  }

  function hideQr() {
    qrEl.style.display = 'none';
    qrImgEl.removeAttribute('src');
  }

  function formatPhone(me) {
    if (!me) return 'Unknown';
    if (me.id) {
      // strip @c.us suffix
      const id = String(me.id).split('@')[0];
      return '+' + id;
    }
    if (me.pushName) return me.pushName;
    return 'Unknown';
  }

  function renderWorking(data) {
    setDot('#16a34a');
    statusTextEl.textContent = 'WORKING';
    descEl.textContent = 'Connected as: ' + formatPhone(data && data.me);
    clearActions();
    hideQr();
    const btn = makeBtn('Logout (unlink this device)', { danger: true });
    btn.addEventListener('click', async function () {
      if (!window.confirm('Log out the WhatsApp session? This unlinks the '
        + 'device — you will need to re-scan a QR code to reconnect.')) {
        return;
      }
      btn.disabled = true;
      const originalLabel = btn.textContent;
      btn.textContent = 'Logging out…';
      try {
        await fetch('/waha/api/sessions/logout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ name: SESSION })
        });
      } catch (e) {
        // best-effort; status poll will reflect outcome
      }
      setTimeout(function () {
        btn.disabled = false;
        btn.textContent = originalLabel;
        fetchStatus();
      }, 2000);
    });
    actionsEl.appendChild(btn);
  }

  function renderScan() {
    setDot('#f59e0b');
    statusTextEl.textContent = 'SCAN_QR_CODE';
    descEl.textContent = 'Scan QR with WhatsApp on your phone.';
    clearActions();
    const btn = makeBtn('Show QR to connect');
    btn.addEventListener('click', showQr);
    actionsEl.appendChild(btn);
  }

  function renderStarting() {
    setDot('#f59e0b');
    statusTextEl.textContent = 'STARTING';
    descEl.textContent = 'Session is starting…';
    clearActions();
    const btn = makeBtn('Starting… Show QR');
    btn.addEventListener('click', showQr);
    actionsEl.appendChild(btn);
  }

  function renderStoppedOrFailed(label) {
    setDot('#dc2626');
    statusTextEl.textContent = label;
    descEl.textContent = label === 'FAILED'
      ? 'Session failed. Restart to recover.'
      : 'Session stopped.';
    clearActions();
    hideQr();
    const btn = makeBtn('Restart + show QR', { danger: true });
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      const originalLabel = btn.textContent;
      btn.textContent = 'Restarting…';
      await restartSession();
      setTimeout(function () {
        showQr();
        btn.disabled = false;
        btn.textContent = originalLabel;
        fetchStatus();
      }, 3000);
    });
    actionsEl.appendChild(btn);
  }

  function renderUnknown(rawStatus) {
    setDot('#6b7280');
    statusTextEl.textContent = rawStatus
      ? String(rawStatus).toUpperCase()
      : 'UNKNOWN';
    descEl.textContent = 'Unknown state';
    clearActions();
    hideQr();
  }

  function renderUnreachable() {
    setDot('#dc2626');
    statusTextEl.textContent = 'UNREACHABLE';
    descEl.textContent = 'WAHA unreachable';
    clearActions();
    hideQr();
    const btn = makeBtn('Restart + show QR', { danger: true });
    btn.addEventListener('click', async function () {
      btn.disabled = true;
      btn.textContent = 'Restarting…';
      await restartSession();
      setTimeout(function () {
        showQr();
        btn.disabled = false;
        btn.textContent = 'Restart + show QR';
        fetchStatus();
      }, 3000);
    });
    actionsEl.appendChild(btn);
  }

  async function fetchStatus() {
    try {
      const res = await fetch('/waha/api/sessions/' + SESSION, {
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
      });
      if (!res.ok) {
        renderUnreachable();
        return;
      }
      const data = await res.json();
      const status = data && data.status ? String(data.status).toUpperCase() : '';
      switch (status) {
        case 'WORKING':
          renderWorking(data);
          break;
        case 'SCAN_QR_CODE':
          renderScan();
          break;
        case 'STARTING':
          renderStarting();
          break;
        case 'STOPPED':
          renderStoppedOrFailed('STOPPED');
          break;
        case 'FAILED':
          renderStoppedOrFailed('FAILED');
          break;
        default:
          renderUnknown(status);
      }
    } catch (e) {
      renderUnreachable();
    }
  }

  // QR auto-refresh: only when the QR pane is visible AND tab is foregrounded.
  setInterval(function () {
    if (qrEl.style.display !== 'flex') return;
    if (document.visibilityState !== 'visible') return;
    qrImgEl.src = QR_URL + '&t=' + Date.now();
  }, QR_REFRESH_MS);

  // Initial fetch + poll.
  fetchStatus();
  setInterval(fetchStatus, POLL_MS);
})();
</script>
</body>
</html>
"""
