/* =============================================================================
   Pricing Inquiry Detail — CRM interactions
   Config via window.PID_CONFIG (set inline in template, inside #main-content)
   Safe to call initPricingDetail() multiple times — uses scoped DOM queries.
   ============================================================================= */

function initPricingDetail() {
  'use strict';

  var cfg = window.PID_CONFIG;
  if (!cfg) return;  // not on this page

  // Scope all queries to the page container so re-init is safe
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

  // ── STATUS SELECTOR (Offcanvas) ────────────────────────────────────────────

  function getSelectedStatus() {
    var active = page.querySelector('.pid__status-opt.active');
    return active ? active.dataset.status : null;
  }

  qsa('.pid__status-opt').forEach(function (btn) {
    // Prevent duplicate listeners
    if (btn._pidBound) return;
    btn._pidBound = true;

    btn.addEventListener('click', function () {
      qsa('.pid__status-opt').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
    });
  });

  // ── SAVE STATUS ────────────────────────────────────────────────────────────

  var saveBtn = qs('#save-status-btn');
  var saveFeedback = qs('#save-status-feedback');

  if (saveBtn && !saveBtn._pidBound) {
    saveBtn._pidBound = true;

    saveBtn.addEventListener('click', function () {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving…';

      var data = {
        crm_status: getSelectedStatus() || '',
        assigned_to: (qs('#assigned-to-select') || {}).value || '',
        staff_notes: (qs('#staff-notes-input') || {}).value || '',
      };

      csrfPost(cfg.urlUpdateStatus, data)
        .then(function (res) {
          if (res.success) {
            // Update hero badge
            var heroBadge = qs('#crm-status-badge');
            if (heroBadge) {
              heroBadge.className.split(' ').forEach(function (c) {
                if (c.startsWith('pid__badge--')) heroBadge.classList.remove(c);
              });
              heroBadge.classList.add('pid__badge--status', 'pid__badge--' + res.crm_status);
              heroBadge.innerHTML = '<i class="fa-solid fa-circle"></i>' + res.crm_status_display;
            }

            // Update right-column status pill
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

            // Update notes block
            var notesInput = qs('#staff-notes-input');
            var notesBlock = qs('#staff-notes-block');
            var crmPanel = qs('.pid__panel--crm .pid__panel__body');
            if (notesInput) {
              var notesVal = notesInput.value.trim();
              if (notesBlock) {
                var notesDisplay = notesBlock.querySelector('#staff-notes-display');
                if (notesDisplay) notesDisplay.textContent = notesVal;
                notesBlock.style.display = notesVal ? '' : 'none';
              } else if (notesVal && crmPanel) {
                // Notes block didn't exist (no notes before) — inject it
                var nb = document.createElement('div');
                nb.className = 'pid__notes-block';
                nb.id = 'staff-notes-block';
                nb.innerHTML = '<div class="pid__notes-label"><i class="fa-solid fa-clipboard me-1"></i>Internal Notes</div>' +
                  '<p class="pid__notes-text" id="staff-notes-display">' + escHtml(notesVal) + '</p>';
                crmPanel.appendChild(nb);
              }
            }

            saveFeedback.className = 'mt-2 pid__feedback';
            saveFeedback.style.color = '#16a34a';
            saveFeedback.textContent = 'Saved successfully.';
            setTimeout(function () { saveFeedback.className = 'd-none mt-2 pid__feedback'; }, 2500);
          } else {
            saveFeedback.className = 'mt-2 pid__feedback';
            saveFeedback.style.color = '#dc2626';
            saveFeedback.textContent = res.error || 'Save failed.';
          }
        })
        .catch(function () {
          saveFeedback.className = 'mt-2 pid__feedback';
          saveFeedback.style.color = '#dc2626';
          saveFeedback.textContent = 'Network error.';
        })
        .finally(function () {
          saveBtn.disabled = false;
          saveBtn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Save Changes';
        });
    });
  }

  // ── ADD ACTIVITY ───────────────────────────────────────────────────────────

  var submitBtn = qs('#submit-activity-btn');
  var bodyEl = qs('#activity-body');
  var errorEl = qs('#activity-error');
  var timeline = qs('#activity-timeline');
  var countBadge = qs('#activity-count-badge');

  function escHtml(str) {
    return String(str)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function updateCount(delta) {
    if (countBadge) countBadge.textContent = (parseInt(countBadge.textContent, 10) || 0) + delta;
  }

  var ICONS = {
    note: '<i class="fa-solid fa-sticky-note"></i>',
    followup: '<i class="fa-solid fa-phone-flip"></i>',
    status_change: '<i class="fa-solid fa-arrow-right-arrow-left"></i>',
  };

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

  if (submitBtn && !submitBtn._pidBound) {
    submitBtn._pidBound = true;

    submitBtn.addEventListener('click', function () {
      var body = bodyEl ? bodyEl.value.trim() : '';
      if (!body) {
        if (errorEl) { errorEl.textContent = 'Please enter a note or follow-up.'; errorEl.classList.remove('d-none'); }
        return;
      }
      if (errorEl) errorEl.classList.add('d-none');

      var typeInput = page.querySelector('input[name="activity_type_sel"]:checked');
      var activityType = typeInput ? typeInput.value : 'note';

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting…';

      csrfPost(cfg.urlAddActivity, { activity_type: activityType, body: body })
        .then(function (res) {
          if (res.success) {
            if (bodyEl) bodyEl.value = '';
            var empty = qs('#timeline-empty-state');
            if (empty) empty.remove();
            if (timeline) timeline.insertAdjacentHTML('afterbegin', buildItem(res.activity));
            updateCount(1);
            bindDeleteHandlers();
          } else {
            if (errorEl) { errorEl.textContent = res.error || 'Failed.'; errorEl.classList.remove('d-none'); }
          }
        })
        .catch(function () {
          if (errorEl) { errorEl.textContent = 'Network error.'; errorEl.classList.remove('d-none'); }
        })
        .finally(function () {
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit';
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

// Auto-init when script tag executes (inline in swapped content)
initPricingDetail();

// Re-init on every HTMX swap (covers back-navigation and re-loads)
document.body.addEventListener('htmx:afterSettle', function (e) {
  if (window.PID_CONFIG && document.getElementById('pricing-inquiry-detail')) {
    initPricingDetail();
  }
});
