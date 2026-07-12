/* =============================================================================
   Pricing Inquiry Detail — CRM interactions
   Config via window.PID_CONFIG (set inline in template, inside #main-content)
   Safe to call initPricingDetail() multiple times — uses scoped DOM queries.
   ============================================================================= */

function initPricingDetail() {
  'use strict';

  var cfg = window.PID_CONFIG;
  if (!cfg) return;

  var page = document.getElementById('pricing-inquiry-detail');
  if (!page) return;

  // ── Helpers ────────────────────────────────────────────────────────────────

  function csrfPost(url, data) {
    data.csrfmiddlewaretoken = cfg.csrfToken;
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams(data),
    }).then(function (r) { return r.json(); });
  }

  function qs(sel) { return page.querySelector(sel); }
  function qsa(sel) { return page.querySelectorAll(sel); }

  function escHtml(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── STATUS SELECTOR ──────────────────────────────────────────────────────

  function getSelectedStatus() {
    var active = page.querySelector('.pid__status-opt.active');
    return active ? active.dataset.status : null;
  }

  qsa('.pid__status-opt').forEach(function (btn) {
    if (btn._pidBound) return;
    btn._pidBound = true;
    btn.addEventListener('click', function () {
      qsa('.pid__status-opt').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
    });
  });

  // ── TIMELINE HELPERS ─────────────────────────────────────────────────────

  var timeline = qs('#activity-timeline');
  var countBadge = qs('#activity-count-badge');

  function updateCount(delta) {
    if (countBadge) countBadge.textContent = (parseInt(countBadge.textContent, 10) || 0) + delta;
  }

  function buildItem(a) {
    return (
      '<div class="pid__tl-item pid__tl-item--' + a.activity_type + '" data-activity-id="' + a.id + '">' +
        '<div class="pid__tl-dot"></div>' +
        '<div class="pid__tl-card">' +
          '<div class="pid__tl-head">' +
            '<span class="pid__tl-type">' + escHtml(a.activity_type_display) + '</span>' +
            '<span class="pid__tl-time">' + escHtml(a.created_at) + '</span>' +
            '<button class="pid__tl-del pid__delete-activity" data-activity-id="' + a.id + '">' +
              '<i class="fa-solid fa-trash-can"></i>' +
            '</button>' +
          '</div>' +
          '<p class="pid__tl-text">' + escHtml(a.body) + '</p>' +
          '<div class="pid__tl-by">' + escHtml(a.created_by) + '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function addToTimeline(activity) {
    var empty = qs('#timeline-empty-state');
    if (empty) empty.remove();
    if (timeline) timeline.insertAdjacentHTML('afterbegin', buildItem(activity));
    updateCount(1);
    bindDeleteHandlers();
  }

  // ── UNIFIED SAVE (status + activity) ─────────────────────────────────────

  var saveBtn = qs('#save-status-btn');
  var saveFeedback = qs('#save-status-feedback');
  var bodyEl = qs('#activity-body');
  var errorEl = qs('#activity-error');

  if (saveBtn && !saveBtn._pidBound) {
    saveBtn._pidBound = true;

    saveBtn.addEventListener('click', function () {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…';
      if (errorEl) errorEl.classList.add('d-none');

      var notesEl = qs('#staff-notes-input');
      var statusData = {
        crm_status: getSelectedStatus() || '',
        assigned_to: (qs('#assigned-to-select') || {}).value || '',
        staff_notes: notesEl ? notesEl.value.trim() : '',
      };

      var activityBody = bodyEl ? bodyEl.value.trim() : '';
      var typeInput = page.querySelector('input[name="activity_type_sel"]:checked');
      var activityType = typeInput ? typeInput.value : 'note';

      // 1. Save status
      csrfPost(cfg.urlUpdateStatus, statusData)
        .then(function (res) {
          if (!res.success) {
            throw new Error(res.error || 'Save failed.');
          }

          // Update hero badge
          var heroBadge = qs('#crm-status-badge');
          if (heroBadge) {
            heroBadge.className.split(' ').forEach(function (c) {
              if (c.startsWith('pid__badge--')) heroBadge.classList.remove(c);
            });
            heroBadge.classList.add('pid__badge--status', 'pid__badge--' + res.crm_status);
            heroBadge.innerHTML = '<i class="fa-solid fa-circle"></i>' + res.crm_status_display;
          }

          // Update status pill
          var crmDisplay = qs('#crm-status-display');
          if (crmDisplay) {
            crmDisplay.innerHTML =
              '<span class="pid__crm-pill pid__crm-pill--' + res.crm_status + '">' +
              '<i class="fa-solid fa-circle"></i>' + res.crm_status_display + '</span>';
          }

          // Update assigned-to displays
          var heroAssigned = qs('#assigned-to-display');
          var panelAssigned = qs('#assigned-to-panel');
          var assignedText = res.assigned_to || 'Unassigned';
          if (heroAssigned) heroAssigned.textContent = assignedText;
          if (panelAssigned) panelAssigned.innerHTML = res.assigned_to
            ? res.assigned_to
            : '<span class="pid__muted">Unassigned</span>';

          // 2. Add activity if text was entered
          if (activityBody) {
            return csrfPost(cfg.urlAddActivity, { activity_type: activityType, body: activityBody })
              .then(function (actRes) {
                if (actRes.success) {
                  addToTimeline(actRes.activity);
                  if (bodyEl) bodyEl.value = '';
                }
              });
          }
        })
        .then(function () {
          if (saveFeedback) {
            saveFeedback.className = 'mt-2 pid__feedback';
            saveFeedback.style.color = '#16a34a';
            saveFeedback.textContent = 'Saved successfully.';
            setTimeout(function () { saveFeedback.className = 'd-none mt-2 pid__feedback'; }, 2500);
          }
        })
        .catch(function (err) {
          var target = saveFeedback || errorEl;
          if (target) {
            target.className = 'mt-2 pid__feedback';
            target.style.color = '#dc2626';
            target.textContent = err.message || 'Network error.';
          }
        })
        .finally(function () {
          saveBtn.disabled = false;
          saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Changes';
        });
    });
  }

  // ── DELETE ACTIVITY ────────────────────────────────────────────────────────

  function bindDeleteHandlers() {
    qsa('.pid__delete-activity').forEach(function (btn) {
      if (btn._pidBound) return;
      btn._pidBound = true;

      btn.addEventListener('click', function () {
        if (!confirm('Delete this activity?')) return;
        var actId = btn.dataset.activityId;
        csrfPost(cfg.urlDeleteBase + actId + '/', {})
          .then(function (res) {
            if (res.success) {
              var item = timeline && timeline.querySelector('[data-activity-id="' + actId + '"]');
              if (item) item.remove();
              updateCount(-1);
              if (timeline && !timeline.querySelector('.pid__tl-item')) {
                timeline.innerHTML =
                  '<div class="pid__tl-empty" id="timeline-empty-state">' +
                  '<i class="fa-solid fa-clock-rotate-left"></i>' +
                  '<p>No activity yet</p></div>';
              }
            }
          });
      });
    });
  }

  bindDeleteHandlers();
}

// Auto-init when script tag executes
initPricingDetail();

// Re-init on every HTMX swap
document.body.addEventListener('htmx:afterSettle', function (e) {
  if (window.PID_CONFIG && document.getElementById('pricing-inquiry-detail')) {
    initPricingDetail();
  }
});
