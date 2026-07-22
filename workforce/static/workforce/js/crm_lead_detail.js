/* Purpose: CRM lead detail page actions — stage change, save assignee/follow-up/notes, contact edit, add/delete activity, AI summary.
   Used by: workforce/templates/workforce/crm/lead_detail.html (reads window.CRMD_CONFIG for URLs + CSRF).
   Notes: All writes are fetch POST → JSON endpoints in workforce/crm_views.py; re-runs safely after HTMX swaps because it re-reads CRMD_CONFIG per action. */

(function () {
  'use strict';

  function cfg() { return window.CRMD_CONFIG || {}; }

  function post(url, fields) {
    var fd = new FormData();
    Object.keys(fields).forEach(function (k) { fd.append(k, fields[k]); });
    fd.append('csrfmiddlewaretoken', cfg().csrfToken || '');
    return fetch(url, { method: 'POST', body: fd }).then(function (r) { return r.json(); });
  }

  function flash(id, message, isError) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = message;
    el.style.color = isError ? '#b3462f' : '';
    setTimeout(function () { el.textContent = ''; }, 3500);
  }

  function scrollChatToEnd() {
    var chat = document.getElementById('workforce_crm_detail_div_chat');
    if (chat) chat.scrollTop = chat.scrollHeight;
  }
  scrollChatToEnd();

  if (window.__crmdInit) return;
  window.__crmdInit = true;
  document.addEventListener('htmx:afterSettle', scrollChatToEnd);

  document.addEventListener('click', function (e) {
    // Stage buttons
    var stageBtn = e.target.closest && e.target.closest('.crmd__stage-opt');
    if (stageBtn) {
      var stage = stageBtn.getAttribute('data-stage');
      post(cfg().urlUpdateStage, { stage: stage }).then(function (data) {
        if (data.success) {
          document.querySelectorAll('.crmd__stage-opt').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-stage') === data.stage);
          });
          var badge = document.getElementById('workforce_crm_detail_span_stage');
          if (badge) {
            badge.className = 'crm__stage crm__stage--' + data.stage;
            badge.innerHTML = '<i class="fa-solid fa-circle"></i>' + data.stage_display;
          }
          flash('workforce_crm_detail_div_feedback', 'Stage updated to ' + data.stage_display);
        } else {
          flash('workforce_crm_detail_div_feedback', data.error || 'Failed to update stage', true);
        }
      });
      return;
    }

    // Save manage panel
    if (e.target.closest && e.target.closest('#workforce_crm_detail_btn_save')) {
      var assignee = document.getElementById('workforce_crm_detail_select_assignee');
      var followup = document.getElementById('workforce_crm_detail_input_followup');
      var notes = document.getElementById('workforce_crm_detail_textarea_notes');
      post(cfg().urlUpdate, {
        assigned_to: assignee ? assignee.value : '',
        next_followup_at: followup ? followup.value : '',
        notes: notes ? notes.value : ''
      }).then(function (data) {
        if (data.success) {
          var label = document.getElementById('workforce_crm_detail_span_assignee');
          if (label) label.textContent = data.assigned_to || 'Unassigned';
          flash('workforce_crm_detail_div_feedback',
                data.changes > 0 ? 'Saved.' : 'No changes detected.');
        } else {
          flash('workforce_crm_detail_div_feedback', data.error || 'Save failed', true);
        }
      });
      return;
    }

    // Add activity
    if (e.target.closest && e.target.closest('#workforce_crm_detail_btn_add_activity')) {
      var body = document.getElementById('workforce_crm_detail_textarea_activity');
      var typeInput = document.querySelector('input[name="workforce_crm_detail_radio_activity"]:checked');
      if (!body || !body.value.trim()) {
        flash('workforce_crm_detail_span_activity_feedback', 'Write something first', true);
        return;
      }
      post(cfg().urlAddActivity, {
        body: body.value.trim(),
        activity_type: typeInput ? typeInput.value : 'note'
      }).then(function (data) {
        if (data.success) {
          body.value = '';
          prependActivity(data.activity);
          flash('workforce_crm_detail_span_activity_feedback', 'Added.');
        } else {
          flash('workforce_crm_detail_span_activity_feedback', data.error || 'Failed', true);
        }
      });
      return;
    }

    // Delete activity
    var delBtn = e.target.closest && e.target.closest('[data-delete-activity]');
    if (delBtn) {
      if (!window.confirm('Delete this activity?')) return;
      var activityId = delBtn.getAttribute('data-delete-activity');
      post(cfg().urlDeleteBase + activityId + '/', {}).then(function (data) {
        if (data.success) {
          var item = document.querySelector('[data-activity-id="' + activityId + '"]');
          if (item) item.remove();
          bumpCount(-1);
        } else {
          alert(data.error || 'Delete failed');
        }
      });
      return;
    }

    // AI summary
    if (e.target.closest && e.target.closest('#workforce_crm_detail_btn_ai_summary')) {
      var aiBtn = document.getElementById('workforce_crm_detail_btn_ai_summary');
      var aiBody = document.getElementById('workforce_crm_detail_div_ai_summary');
      if (!aiBody || aiBtn.disabled) return;
      var hadSummary = !aiBody.classList.contains('crmd__ai-body--empty');
      aiBtn.disabled = true;
      aiBtn.innerHTML = '<i class="fa-solid fa-rotate fa-spin"></i> Thinking…';
      aiBody.classList.remove('crmd__ai-body--empty');
      aiBody.textContent = 'Reading the conversation…';
      post(cfg().urlAiSummary, { force: hadSummary ? '1' : '0' }).then(function (data) {
        aiBtn.disabled = false;
        aiBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh';
        if (data.success) {
          aiBody.textContent = data.summary;
        } else {
          aiBody.classList.add('crmd__ai-body--empty');
          aiBody.textContent = data.error || 'AI summary failed.';
        }
      }).catch(function () {
        aiBtn.disabled = false;
        aiBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Retry';
        aiBody.classList.add('crmd__ai-body--empty');
        aiBody.textContent = 'AI summary failed — try again.';
      });
      return;
    }

    // Manual WA chat link — pick a search result
    var resultItem = e.target.closest && e.target.closest('.crmd__link-result-item');
    if (resultItem) {
      var phone = resultItem.getAttribute('data-phone');
      var searchInput = document.getElementById('workforce_crm_detail_input_wa_search');
      var linkResults = document.getElementById('workforce_crm_detail_div_wa_results');
      if (searchInput) searchInput.value = phone;
      if (linkResults) linkResults.classList.remove('show');
      flash('workforce_crm_detail_span_link_feedback', 'Linking…');
      post(cfg().urlLinkChat, { identifier: phone }).then(function (data) {
        if (data.success) {
          flash('workforce_crm_detail_span_link_feedback', data.message || 'Linked.');
          if (data.connected) setTimeout(function () { window.location.reload(); }, 900);
        } else {
          flash('workforce_crm_detail_span_link_feedback', data.error || 'Link failed', true);
        }
      });
      return;
    }

    // Click outside the WA search box closes its results dropdown
    var linkResultsEl = document.getElementById('workforce_crm_detail_div_wa_results');
    if (linkResultsEl && !(e.target.closest && e.target.closest('.crmd__link-search-wrap'))) {
      linkResultsEl.classList.remove('show');
    }
  });

  var waSearchTimer = null;
  document.addEventListener('input', function (e) {
    if (e.target.id !== 'workforce_crm_detail_input_wa_search') return;
    var q = e.target.value.trim();
    var resultsEl = document.getElementById('workforce_crm_detail_div_wa_results');
    if (!resultsEl) return;
    clearTimeout(waSearchTimer);
    if (q.length < 3) {
      resultsEl.classList.remove('show');
      resultsEl.innerHTML = '';
      return;
    }
    waSearchTimer = setTimeout(function () {
      fetch(cfg().urlWaSearch + '?q=' + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) { renderWaResults(data.results || []); });
    }, 300);
  });

  function renderWaResults(results) {
    var resultsEl = document.getElementById('workforce_crm_detail_div_wa_results');
    if (!resultsEl) return;
    if (!results.length) {
      resultsEl.innerHTML = '<div class="crmd__link-empty">No matching WhatsApp contacts</div>';
      resultsEl.classList.add('show');
      return;
    }
    resultsEl.innerHTML = results.map(function () {
      return '<div class="crmd__link-result-item" data-phone="">' +
        '<span class="crmd__link-result-name"></span>' +
        '<span class="crmd__link-result-phone"></span>' +
      '</div>';
    }).join('');
    resultsEl.querySelectorAll('.crmd__link-result-item').forEach(function (el, i) {
      el.setAttribute('data-phone', results[i].phone);
      el.querySelector('.crmd__link-result-name').textContent = results[i].name || results[i].phone;
      el.querySelector('.crmd__link-result-phone').textContent = results[i].phone;
    });
    resultsEl.classList.add('show');
  }

  document.addEventListener('submit', function (e) {
    var form = e.target.closest && e.target.closest('#workforce_crm_detail_form_contact');
    if (!form) return;
    e.preventDefault();
    var fields = {};
    new FormData(form).forEach(function (value, key) { fields[key] = value; });
    post(cfg().urlUpdate, fields).then(function (data) {
      flash('workforce_crm_detail_span_contact_feedback',
            data.success ? (data.changes > 0 ? 'Saved.' : 'No changes.') : (data.error || 'Failed'),
            !data.success);
    });
  });

  function prependActivity(activity) {
    var timeline = document.getElementById('workforce_crm_detail_div_timeline');
    if (!timeline) return;
    var empty = document.getElementById('workforce_crm_detail_div_timeline_empty');
    if (empty) empty.remove();
    var item = document.createElement('div');
    item.className = 'crmd__tl-item crmd__tl-item--' + activity.type;
    item.setAttribute('data-activity-id', activity.id);
    item.innerHTML =
      '<div class="crmd__tl-dot"></div>' +
      '<div class="crmd__tl-card">' +
        '<div class="crmd__tl-head">' +
          '<span class="crmd__tl-type"></span>' +
          '<span class="crmd__tl-time"></span>' +
          '<button class="crmd__tl-del" data-delete-activity="' + activity.id + '">' +
            '<i class="fa-solid fa-trash-can"></i></button>' +
        '</div>' +
        '<p class="crmd__tl-text"></p>' +
        '<div class="crmd__tl-by"></div>' +
      '</div>';
    item.querySelector('.crmd__tl-type').textContent = activity.type_display;
    item.querySelector('.crmd__tl-time').textContent = activity.created_at;
    item.querySelector('.crmd__tl-text').textContent = activity.body;
    item.querySelector('.crmd__tl-by').textContent = activity.created_by;
    timeline.prepend(item);
    bumpCount(1);
  }

  function bumpCount(delta) {
    var badge = document.getElementById('workforce_crm_detail_span_activity_count');
    if (badge) badge.textContent = Math.max(0, parseInt(badge.textContent || '0', 10) + delta);
  }
})();
