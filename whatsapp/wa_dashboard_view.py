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
from django.http import HttpResponse
from django.utils.html import escape
from django.views.decorators.cache import never_cache

from . import sessions as wa_sessions


@never_cache
def wa_dashboard(request):
    session = wa_sessions.from_request(request)
    html = (
        _DASHBOARD_HTML
        .replace('%SESSION_TABS%', wa_sessions.render_tabs(
            session, request.path, always=True, add_button=True,
        ))
        .replace('%SESSION_ROUTES%', _routes_html(session))
        .replace('%SESSION%', session)
    )
    return HttpResponse(html, content_type='text/html; charset=utf-8')


def _routes_html(active):
    """Read-only 'what sends from this number' panel.

    Ops keep asking which number a given section actually uses; without this the
    answer lives on a different page under a different login. Rows for the
    session on screen are marked, so switching tabs answers "what is this number
    responsible for?" directly.
    """
    routes = wa_sessions.section_routes()
    if not routes:
        return ''
    parts = [
        '<div class="wa-routes">',
        '<div class="wa-routes__hd">'
        '<span>Sections sending from this number</span>'
        # This page can't write the setting (htpasswd only, no staff session),
        # so the primary action here is "go where you can" — hence a real,
        # visible link rather than a footnote.
        '<a class="wa-routes__edit" href="/workforce/auto-triggers/whatsapp-instances/"'
        ' target="_blank" rel="noopener"'
        ' title="Set each number\'s WAHA session (opens in a new tab, staff login)">'
        'Edit settings <span aria-hidden="true">&#8599;</span></a>'
        '</div>',
    ]
    unmapped = 0
    for r in routes:
        mine = r['session'] == active
        if not r['enabled']:
            # No route row, or the toggle is off — falls back to the default.
            target, detail, warn = 'default sender', 'unrouted', False
        elif r['mapped'] and not r['live']:
            # Mapped, but that session has no device on it (QR screen, stopped,
            # failed). Sends will fail — not the same as "configured".
            unmapped += 1
            target = escape(r['instance_label'] or r['session'])
            detail = f'session {escape(r["status"].lower())}'
            warn = True
        elif r['mapped']:
            target = escape(r['instance_label'] or r['session'])
            detail = f'+{escape(r["phone"])}' if r['phone'] else escape(r['session'])
            warn = False
        else:
            # Routed on the Evolution side, but no WAHA session behind it —
            # say so plainly rather than implying that number is live on WAHA.
            unmapped += 1
            target = escape(r['instance_label'] or r['session'])
            detail = 'no WAHA session → default'
            warn = True
        parts.append(
            '<div class="wa-routes__row{on}">'
            '<span class="wa-routes__sec">{label}</span>'
            '<span class="wa-routes__to">{target}'
            '<span class="wa-routes__num{wcls}">{detail}</span></span>'
            '</div>'.format(
                on=' wa-routes__row--mine' if mine else '',
                label=escape(r['label']), target=target, detail=detail,
                wcls=' wa-routes__num--warn' if warn else '',
            )
        )
    note = (
        f'{unmapped} section(s) are not sending from the number they name — either '
        'no WAHA session is set (so they fall back to the default session) or that '
        'session has no device connected. '
        if unmapped else 'Rows on this number are highlighted. '
    )
    parts.append(
        '<div class="wa-routes__ft">' + note +
        'Fill <b>WAHA Session</b> on the number\'s row via <b>Edit settings</b> above. '
        'To change which section uses which number instead, open '
        '<a href="/workforce/auto-triggers/" target="_blank" rel="noopener">Auto Triggers '
        '<span aria-hidden="true">&#8599;</span></a>. Both need a staff login.</div></div>'
    )
    return ''.join(parts)


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
  .wa-qr-wait {
    display: none;
    width: 100%;
    max-width: 16rem;
    padding: 2rem 0.75rem;
    text-align: center;
    font-size: 0.8125rem;
    color: var(--wa-muted);
    background: #ffffff;
    border: 0.0625rem dashed var(--wa-border);
    border-radius: 0.5rem;
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

  /* One tab per WhatsApp number linked to WAHA. Every control on this page
     already targets SESSION, so switching tabs is a plain page navigation.
     Rendered as nothing when only one session exists. */
  .wa-sess {
    display: flex;
    gap: 0.375rem;
    margin: 0 0 0.875rem;
    padding: 0.25rem;
    background: var(--wa-bg, #f0f2f5);
    border-radius: 0.5rem;
  }
  .wa-sess__tab {
    flex: 1 1 0;
    min-width: 0;
    padding: 0.4375rem 0.5rem;
    border-radius: 0.375rem;
    text-align: center;
    text-decoration: none;
    font-size: 0.75rem;
    line-height: 1.3;
    color: var(--wa-muted);
  }
  .wa-sess__tab:hover { background: rgba(0, 0, 0, 0.04); }
  .wa-sess__tab--on {
    background: #ffffff;
    color: var(--wa-green);
    font-weight: 600;
    box-shadow: 0 0.0625rem 0.125rem rgba(0, 0, 0, 0.08);
  }
  .wa-sess__name { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .wa-sess__num { display: block; font-size: 0.6875rem; opacity: 0.75; font-variant-numeric: tabular-nums; }
  .wa-sess__dot {
    display: inline-block;
    width: 0.4375rem;
    height: 0.4375rem;
    border-radius: 50%;
    margin-right: 0.25rem;
    background: #b9b9b9;
  }
  .wa-sess__dot--on { background: var(--wa-green); }
  /* "+ Add number" sits in the tab strip as a button, not a link — it POSTs. */
  .wa-sess__tab--add {
    border: 0.0625rem dashed var(--wa-border);
    background: transparent;
    cursor: pointer;
    font: inherit;
    color: var(--wa-muted);
  }
  .wa-sess__tab--add:hover { border-color: var(--wa-green); color: var(--wa-green); }

  /* Section routing — read-only mirror of the Auto Triggers config. */
  .wa-routes {
    margin-top: 1.25rem;
    border: 0.0625rem solid var(--wa-border);
    border-radius: 0.5rem;
    overflow: hidden;
  }
  .wa-routes__hd {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--wa-muted);
    background: var(--wa-bg, #f0f2f5);
    border-bottom: 0.0625rem solid var(--wa-border);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .wa-routes__edit {
    flex: none;
    padding: 0.1875rem 0.5rem;
    border: 0.0625rem solid var(--wa-green);
    border-radius: 0.25rem;
    color: var(--wa-green);
    text-decoration: none;
    text-transform: none;
    letter-spacing: 0;
    font-size: 0.6875rem;
    white-space: nowrap;
  }
  .wa-routes__edit:hover { background: var(--wa-green); color: #fff; }
  .wa-routes__row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.8125rem;
    border-bottom: 0.0625rem solid var(--wa-border);
  }
  .wa-routes__row:last-of-type { border-bottom: 0; }
  .wa-routes__row--mine { background: rgba(0, 168, 132, 0.06); }
  .wa-routes__row--mine .wa-routes__to { color: var(--wa-green); font-weight: 600; }
  .wa-routes__sec { color: var(--wa-muted); }
  .wa-routes__to { text-align: right; }
  .wa-routes__num {
    display: block;
    font-size: 0.6875rem;
    font-weight: 400;
    color: var(--wa-muted);
    font-variant-numeric: tabular-nums;
  }
  .wa-routes__ft {
    padding: 0.5rem 0.75rem;
    font-size: 0.6875rem;
    color: var(--wa-muted);
    border-top: 0.0625rem solid var(--wa-border);
    background: var(--wa-bg, #f0f2f5);
  }
  .wa-routes__ft a { color: var(--wa-green); }
  /* Routed on Evolution but with no WAHA session behind it — an actionable
     gap, not an error, so amber rather than the destructive red. */
  .wa-routes__num--warn { color: #b45309; }
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
    %SESSION_TABS%
    <p class="wa-desc" id="wa-desc">Loading…</p>
    <div class="wa-actions" id="wa-actions"></div>
    <div class="wa-qr" id="wa-qr">
      <img id="wa-qr-img" alt="WhatsApp QR code">
      <div class="wa-qr-wait" id="wa-qr-wait">QR not ready yet — waiting for session…</div>
      <div class="wa-qr-hint">Open WhatsApp → Linked devices → Link a device</div>
    </div>
    %SESSION_ROUTES%
    <div class="wa-foot">
      <a href="/waha/wa-chats/?session=%SESSION%" target="_blank" rel="noopener">Chat Dashboard</a>
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
  const qrWaitEl = document.getElementById('wa-qr-wait');

  const QR_URL = '/waha/api/' + SESSION + '/auth/qr?format=image';
  const QR_RETRY_MS = 4000;
  let qrRetryTimer = null;

  // WAHA 422s on the QR endpoint unless the session is in SCAN_QR_CODE, so a
  // too-early click shows a broken image. Swap it for a waiting note and keep
  // retrying while the pane is open — the QR appears as soon as WAHA has one.
  qrImgEl.addEventListener('load', function () {
    qrImgEl.style.display = 'block';
    qrWaitEl.style.display = 'none';
  });
  qrImgEl.addEventListener('error', function () {
    if (!qrImgEl.getAttribute('src')) return;  // ignore src removal on hideQr
    qrImgEl.style.display = 'none';
    qrWaitEl.style.display = 'block';
    clearTimeout(qrRetryTimer);
    qrRetryTimer = setTimeout(function () {
      if (qrEl.style.display !== 'flex') return;
      qrImgEl.src = QR_URL + '&t=' + Date.now();
    }, QR_RETRY_MS);
  });

  // Link another WhatsApp number. Creating the session is all this needs —
  // navigating to its tab then shows the QR pane for the actual pairing.
  const addBtn = document.getElementById('wa-add-session');
  if (addBtn) {
    addBtn.addEventListener('click', async function () {
      const raw = window.prompt(
        'Name for the new number\'s session (letters, digits, - and _ only).\n'
        + 'Use something that says what the number is for, e.g. "fleet" or "marketing".'
      );
      if (raw === null) return;
      const name = raw.trim();
      if (!/^[a-zA-Z0-9_-]{1,64}$/.test(name)) {
        window.alert('Invalid name. Use only letters, digits, hyphen and underscore.');
        return;
      }
      addBtn.disabled = true;
      try {
        const res = await fetch('/waha/api/sessions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ name: name, start: true })
        });
        if (!res.ok) {
          const detail = await res.text();
          window.alert('Could not create the session (HTTP ' + res.status + ').\n'
            + (detail || '').slice(0, 300));
          addBtn.disabled = false;
          return;
        }
      } catch (e) {
        window.alert('Could not reach WAHA: ' + e);
        addBtn.disabled = false;
        return;
      }
      // Land on the new session's tab so the QR pane is one click away.
      window.location.search = '?session=' + encodeURIComponent(name);
    });
  }

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
    clearTimeout(qrRetryTimer);
    qrEl.style.display = 'none';
    qrImgEl.removeAttribute('src');
    qrImgEl.style.display = 'block';
    qrWaitEl.style.display = 'none';
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
