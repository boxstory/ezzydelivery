/* Purpose: CRM lead detail page actions — stage change, save assignee/follow-up/notes, contact edit, add/delete activity, AI summary, driver-document Add form (the viewer popup is doc_viewer.js).
   Used by: workforce/templates/workforce/crm/lead_detail.html (reads window.CRMD_CONFIG for URLs + CSRF).
   Notes: All writes are fetch POST → JSON endpoints in workforce/crm_views.py; re-runs safely after HTMX swaps because it re-reads CRMD_CONFIG per action.
          The document dialogs post instead to the fleet endpoints in workforce/views.py (driver_document_save) — the same ones the driver record uses. */

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
      // Same guard as the board: a column that rewrites the driver's real status (and
      // WhatsApps them) must confirm first. This grid used to post straight through, so
      // a mis-clicked "Rejected" chip messaged the applicant with no dialog.
      var confirmText = stageBtn.getAttribute('data-confirm') || '';
      var needsReason = stageBtn.getAttribute('data-needs-reason') === '1';
      var who = (cfg().leadName || 'this lead');
      var rejectionReason = '';
      if (needsReason) {
        var reason = prompt('This will ' + (confirmText || 'change this driver\'s status') +
          ' (' + who + ') and update their real application status.\n\nReason (optional):', '');
        if (reason === null) return;
        rejectionReason = reason;
      } else if (confirmText) {
        if (!confirm('This will ' + confirmText + ' (' + who + ') and update their real application status. Continue?')) {
          return;
        }
      }

      post(cfg().urlUpdateStage, { stage: stage, rejection_reason: rejectionReason }).then(function (data) {
        if (data.success) {
          document.querySelectorAll('.crmd__stage-opt').forEach(function (b) {
            b.classList.toggle('active', b.getAttribute('data-stage') === data.stage);
          });
          var badge = document.getElementById('workforce_crm_detail_span_stage');
          if (badge) {
            // Swap only the swatch modifier. Rewriting className wholesale used to
            // drop crmd__hero-plate, which is what makes the badge legible on the
            // navy band — the stage went dark-on-dark until the next page load.
            badge.className = badge.className
              .split(/\s+/)
              .filter(function (c) { return c && c.indexOf('crm__stage--sw-') !== 0; })
              .join(' ');
            badge.classList.add('crm__stage', 'crm__stage--sw-' + (data.stage_swatch || 'grey'));
            // textContent, not innerHTML: stage_display is a staff-editable column label.
            badge.textContent = '';
            var icon = document.createElement('i');
            icon.className = 'fa-solid fa-circle';
            badge.appendChild(icon);
            badge.appendChild(document.createTextNode(data.stage_display));
          }
          var pinbar = document.getElementById('workforce_crm_detail_div_pinbar');
          if (pinbar) pinbar.hidden = !data.pinned;
          if (data.warning) {
            // The card was accepted but pinned — staff must know it has stopped
            // tracking the application, so this cannot be a fading flash.
            alert(data.warning);
          }
          flash('workforce_crm_detail_div_feedback', 'Stage updated to ' + data.stage_display);
        } else {
          alert(data.error || 'Failed to update stage');
          flash('workforce_crm_detail_div_feedback', data.error || 'Failed to update stage', true);
        }
      });
      return;
    }

    // Merge a same-number duplicate into this card (both rows survive)
    var mergeBtn = e.target.closest && e.target.closest('[data-merge-duplicate]');
    if (mergeBtn) {
      var label = mergeBtn.getAttribute('data-merge-label') || 'that lead';
      if (!confirm('Merge ' + label + ' into this card? Both cards are kept — the other one '
                   + 'will show inside this card instead of on the board. You can un-merge later.')) {
        return;
      }
      post(mergeBtn.getAttribute('data-merge-url'),
           { duplicate_id: mergeBtn.getAttribute('data-merge-duplicate') }).then(function (data) {
        if (!data.success) { alert(data.error || 'Could not merge'); return; }
        flash('workforce_crm_detail_div_feedback', 'Merged — reloading');
        setTimeout(function () { window.location.reload(); }, 700);
      });
      return;
    }

    // Take one value from an absorbed card where it disagrees with this one
    var adoptBtn = e.target.closest && e.target.closest('[data-adopt-field]');
    if (adoptBtn) {
      var fieldLabel = adoptBtn.getAttribute('data-adopt-label') || 'this field';
      if (!confirm('Replace this card\'s ' + fieldLabel + ' with the value from #'
                   + adoptBtn.getAttribute('data-adopt-child') + '?')) return;
      post(adoptBtn.getAttribute('data-adopt-url'), {
        child_id: adoptBtn.getAttribute('data-adopt-child'),
        field: adoptBtn.getAttribute('data-adopt-field')
      }).then(function (data) {
        if (!data.success) { alert(data.error || 'Could not update'); return; }
        flash('workforce_crm_detail_div_feedback', fieldLabel + ' updated — reloading');
        setTimeout(function () { window.location.reload(); }, 700);
      });
      return;
    }

    // Put an absorbed card back on the board on its own
    var unmergeBtn = e.target.closest && e.target.closest('[data-unmerge-child]');
    if (unmergeBtn) {
      if (!confirm('Un-merge this card? It goes back on the board as its own lead. Anything the '
                   + 'merge filled in here (and WhatsApp numbers it added) is taken back, unless '
                   + 'it has been changed since.')) return;
      post(unmergeBtn.getAttribute('data-unmerge-url'),
           { child_id: unmergeBtn.getAttribute('data-unmerge-child') }).then(function (data) {
        if (!data.success) { alert(data.error || 'Could not un-merge'); return; }
        flash('workforce_crm_detail_div_feedback', 'Un-merged — reloading');
        setTimeout(function () { window.location.reload(); }, 700);
      });
      return;
    }

    // Re-file this card on the other pipeline (Business <-> Driver)
    var moveBoardBtn = e.target.closest && e.target.closest('[data-move-board]');
    if (moveBoardBtn) {
      var boardLabel = moveBoardBtn.getAttribute('data-move-label') || 'the other';
      if (!confirm('Move this card to the ' + boardLabel + ' board?\n\n'
                   + 'The two pipelines have separate columns, so it starts again at the '
                   + boardLabel + ' board\'s first column. Nothing is sent to the lead.')) {
        return;
      }
      post(cfg().urlMoveBoard, { category: moveBoardBtn.getAttribute('data-move-board') })
        .then(function (data) {
          if (!data.success) { alert(data.error || 'Could not move this card'); return; }
          // Full reload, not a patch: the board this page belongs to decides the back
          // link, the driver panel, the stage grid and which WhatsApp line sends.
          flash('workforce_crm_detail_div_feedback', 'Moved to the ' + boardLabel + ' board — reloading');
          setTimeout(function () { window.location.reload(); }, 700);
        });
      return;
    }

    // Resume automatic filing for a pinned driver card
    var unpinBtn = e.target.closest && e.target.closest('#workforce_crm_detail_btn_unpin');
    if (unpinBtn) {
      if (!confirm('Hand this card back to automatic filing? It will move to whatever the driver\'s application status says, which may not be the current column.')) {
        return;
      }
      post(unpinBtn.getAttribute('data-unpin-url'), {}).then(function (data) {
        if (!data.success) {
          alert(data.error || 'Could not resume auto-filing');
          return;
        }
        var pinbar = document.getElementById('workforce_crm_detail_div_pinbar');
        if (pinbar) pinbar.hidden = true;
        flash('workforce_crm_detail_div_feedback',
          data.moves_to ? 'Auto-filing resumed — moving to ' + data.moves_to : 'Auto-filing resumed');
        setTimeout(function () { window.location.reload(); }, 900);
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

    // Refresh the WhatsApp thread — pulls this chat from WAHA server-side, then
    // swaps in the re-rendered bubbles. No page reload: staff lose the scroll
    // position, the open linker and any half-typed note on a full reload.
    if (e.target.closest && e.target.closest('#workforce_crm_detail_btn_chat_refresh')) {
      var refBtn = document.getElementById('workforce_crm_detail_btn_chat_refresh');
      var chatBox = document.getElementById('workforce_crm_detail_div_chat');
      if (!refBtn || !chatBox || refBtn.disabled) return;
      var refLabel = refBtn.innerHTML;
      refBtn.disabled = true;
      refBtn.innerHTML = '<i class="fa-solid fa-rotate fa-spin"></i> Refreshing…';
      post(cfg().urlChatRefresh, { session: refBtn.getAttribute('data-session') || '' })
        .then(function (data) {
          refBtn.disabled = false;
          if (!data || !data.success) {
            refBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Retry';
            flash('workforce_crm_detail_span_chat_feedback',
                  (data && data.error) || 'Refresh failed', true);
            return;
          }
          chatBox.innerHTML = data.html || '';
          chatBox.classList.toggle('d-none', !data.count);
          var countEl = document.getElementById('workforce_crm_detail_span_chat_count');
          if (countEl) countEl.textContent = data.count;
          var emptyNote = document.getElementById('workforce_crm_detail_div_chat_empty');
          if (emptyNote) emptyNote.classList.toggle('d-none', !!data.count);
          scrollChatToEnd();
          // Say what the pull actually did: "nothing new" and "the bridge is
          // down" look identical on a silent button.
          if (data.error) {
            refBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Refresh';
            flash('workforce_crm_detail_span_chat_feedback', data.error, true);
          } else {
            refBtn.innerHTML = '<i class="fa-solid fa-check"></i> ' +
              (data.new ? data.new + ' new' : 'Up to date');
            setTimeout(function () { refBtn.innerHTML = refLabel; }, 2500);
          }
        })
        .catch(function () {
          refBtn.disabled = false;
          refBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Retry';
          flash('workforce_crm_detail_span_chat_feedback', 'Refresh failed — try again', true);
        });
      return;
    }

    // Show/hide the manual chat linker. It lives inside the conversation panel and
    // starts open only when there is no matched chat to read.
    var linkToggle = e.target.closest && e.target.closest('[data-chatlink-toggle]');
    if (linkToggle) {
      var linkerBox = document.getElementById('workforce_crm_detail_div_chat_link');
      if (linkerBox) {
        var nowOpen = linkerBox.classList.toggle('d-none') === false;
        linkToggle.setAttribute('aria-expanded', nowOpen ? 'true' : 'false');
        if (nowOpen) {
          var boxInput = document.getElementById('workforce_crm_detail_input_wa_search');
          if (boxInput) boxInput.focus();
        }
      }
      return;
    }

    // Manual WA chat link — pick a search result
    var resultItem = e.target.closest && e.target.closest('.crmd__link-result-item');
    if (resultItem) {
      var phone = resultItem.getAttribute('data-phone');
      // Which WhatsApp number this contact was found on — the lid only
      // resolves against that session.
      var waSession = resultItem.getAttribute('data-session') || '';
      var searchInput = document.getElementById('workforce_crm_detail_input_wa_search');
      var linkResults = document.getElementById('workforce_crm_detail_div_wa_results');
      if (searchInput) searchInput.value = phone;
      if (linkResults) linkResults.classList.remove('show');
      flash('workforce_crm_detail_span_link_feedback', 'Linking…');
      var labelInput = document.getElementById('workforce_crm_detail_input_wa_label');
      var waLabel = labelInput ? labelInput.value.trim() : '';
      post(cfg().urlLinkChat, { identifier: phone, session: waSession, label: waLabel }).then(function (data) {
        if (data.success) {
          flash('workforce_crm_detail_span_link_feedback', data.message || 'Linked.');
          // Reload either way: the number is linked even when no messages exist yet,
          // and the Numbers list has to show it.
          setTimeout(function () { window.location.reload(); }, 900);
        } else {
          flash('workforce_crm_detail_span_link_feedback', data.error || 'Link failed', true);
        }
      });
      return;
    }

    // Unlink one of the lead's extra WhatsApp numbers
    var unlinkBtn = e.target.closest && e.target.closest('[data-unlink-number]');
    if (unlinkBtn) {
      var num = unlinkBtn.getAttribute('data-unlink-number');
      if (!window.confirm('Unlink ' + num + ' from this lead? Its chat will no longer show here.')) return;
      unlinkBtn.disabled = true;
      post(cfg().urlUnlinkChat, { identifier: num }).then(function (data) {
        if (data.success) { window.location.reload(); }
        else { unlinkBtn.disabled = false; window.alert(data.error || 'Could not unlink'); }
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
      return '<div class="crmd__link-result-item" data-phone="" data-session="">' +
        '<span class="crmd__link-result-name"></span>' +
        '<span class="crmd__link-result-phone"></span>' +
      '</div>';
    }).join('');
    resultsEl.querySelectorAll('.crmd__link-result-item').forEach(function (el, i) {
      el.setAttribute('data-phone', results[i].phone);
      el.setAttribute('data-session', results[i].session || '');
      el.querySelector('.crmd__link-result-name').textContent = results[i].name || results[i].phone;
      el.querySelector('.crmd__link-result-phone').textContent = results[i].phone;
    });
    resultsEl.classList.add('show');
  }

  // ── CONTACT CARD ───────────────────────────────────────────────────────────
  // The panel shows a read record by default; Edit swaps in the form, Cancel puts
  // the inputs back to what is on screen, and a successful save repaints the read
  // rows from the server's values (the phone is normalised there).
  function contactPanel() { return document.getElementById('workforce_crm_detail_div_contact'); }

  function setContactMode(editing) {
    var panel = contactPanel();
    if (!panel) return;
    var form = document.getElementById('workforce_crm_detail_form_contact');
    var read = document.getElementById('workforce_crm_detail_div_contact_read');
    var btn = document.getElementById('workforce_crm_detail_btn_contact_edit');
    panel.classList.toggle('is-editing', editing);
    if (form) form.hidden = !editing;
    if (read) read.hidden = editing;
    if (btn) btn.setAttribute('aria-expanded', editing ? 'true' : 'false');
    if (editing && form) {
      var first = form.querySelector('input');
      if (first) first.focus();
    } else if (btn) {
      btn.focus();
    }
  }

  // Cancel restores the inputs from the read rows, so reopening Edit never shows
  // an abandoned edit as if it had been saved.
  function resetContactInputs() {
    var form = document.getElementById('workforce_crm_detail_form_contact');
    if (!form) return;
    form.querySelectorAll('input[name]').forEach(function (input) {
      var cell = document.querySelector('[data-contact-read="' + input.name + '"]');
      if (!cell) return;
      var text = (cell.textContent || '').trim();
      input.value = cell.classList.contains('crmd__crow-val--empty') || text === 'Not set' ? '' : text;
    });
  }

  function paintContactRead(contact) {
    if (!contact) return;
    ['company_name', 'contact_name', 'product_category'].forEach(function (name) {
      var cell = document.querySelector('[data-contact-read="' + name + '"]');
      if (!cell) return;
      var value = contact[name] || '';
      cell.textContent = value || 'Not set';
      cell.classList.toggle('crmd__crow-val--empty', !value);
    });
    ['phone', 'phone_2'].forEach(function (name) {
      var wrap = document.querySelector('[data-contact-read-phone="' + name + '"]');
      if (!wrap) return;
      var phone = contact[name] || '';
      wrap.textContent = '';
      var el;
      if (phone) {
        el = document.createElement('a');
        el.className = 'crmd__crow-tel';
        el.href = 'tel:' + phone;
      } else {
        el = document.createElement('span');
        el.className = 'crmd__crow-val--empty';
      }
      el.setAttribute('data-contact-read', name);
      el.textContent = phone || 'Not set';
      wrap.appendChild(el);
      var input = document.querySelector('#workforce_crm_detail_form_contact input[name="' + name + '"]');
      if (input) input.value = phone;
    });
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('[data-contact-edit]')) { setContactMode(true); return; }
    if (e.target.closest('[data-contact-cancel]')) { resetContactInputs(); setContactMode(false); }
  });

  document.addEventListener('submit', function (e) {
    var form = e.target.closest && e.target.closest('#workforce_crm_detail_form_contact');
    if (!form) return;
    e.preventDefault();
    var fields = {};
    new FormData(form).forEach(function (value, key) { fields[key] = value; });
    post(cfg().urlUpdate, fields).then(function (data) {
      if (data.success) {
        paintContactRead(data.contact);
        setContactMode(false);
      }
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


  // ─── DRIVER DOCUMENTS ───────────────────────────────────────────────────────
  // Every row carries its own facts in data-*, so opening the viewer — and
  // pre-filling the edit form from it — costs no second request. Elements are
  // looked up at click time, never cached: HTMX replaces this markup on every
  // navigation and a cached node would point at a detached dialog.
  // The scan viewer itself (crop/rotate, fields, Verify) lives in doc_viewer.js,
  // shared with the driver record page. This file keeps only the Add form.
  function docModal(id) {
    var el = document.getElementById(id);
    if (!el || !window.bootstrap) return null;
    return bootstrap.Modal.getOrCreateInstance(el);
  }

  // `row` null = adding a document rather than editing one.
  function docOpenEditor(row) {
    var title = document.getElementById('workforce_crm_detail_h_docedit_title');
    var err = document.getElementById('workforce_crm_detail_p_docedit_err');
    var form = document.getElementById('workforce_crm_detail_form_docedit');
    if (form) form.reset();
    if (err) { err.hidden = true; err.textContent = ''; }
    if (title) title.textContent = row ? 'Edit document' : 'Add document';

    var set = function (id, value) {
      var el = document.getElementById(id);
      if (el) el.value = value || '';
    };
    set('workforce_crm_detail_input_docedit_id', row ? row.docId : '');
    set('workforce_crm_detail_select_docedit_type', row ? row.docType : '');
    set('workforce_crm_detail_input_docedit_no', row ? row.docNo : '');
    set('workforce_crm_detail_input_docedit_issued', row ? row.docIssued : '');
    set('workforce_crm_detail_input_docedit_expiry', row ? row.docExpiry : '');

    var modal = docModal('workforce_crm_detail_modal_docedit');
    if (modal) modal.show();
  }

  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('#workforce_crm_detail_btn_docadd')) { docOpenEditor(null); return; }
  });

  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form || form.id !== 'workforce_crm_detail_form_docedit') return;
    e.preventDefault();

    var idEl = document.getElementById('workforce_crm_detail_input_docedit_id');
    var id = idEl ? idEl.value : '';
    var url = id ? (cfg().urlDocEditBase || '') + id + '/edit/' : (cfg().urlDocAdd || '');
    if (!url) return;

    var err = document.getElementById('workforce_crm_detail_p_docedit_err');
    var save = document.getElementById('workforce_crm_detail_btn_docsave');
    if (err) { err.hidden = true; err.textContent = ''; }
    if (save) save.disabled = true;

    var fd = new FormData(form);
    fd.append('csrfmiddlewaretoken', cfg().csrfToken || '');
    fetch(url, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) { window.location.reload(); return; }
        if (save) save.disabled = false;
        if (err) { err.textContent = data.error || 'Could not save this document.'; err.hidden = false; }
      })
      .catch(function () {
        if (save) save.disabled = false;
        if (err) { err.textContent = 'Could not reach the server. Try again.'; err.hidden = false; }
      });
  });

  function bumpCount(delta) {
    var badge = document.getElementById('workforce_crm_detail_span_activity_count');
    if (badge) badge.textContent = Math.max(0, parseInt(badge.textContent || '0', 10) + delta);
  }
})();
