/* Purpose: Driver payout worksheet behaviour — payable-line selection, payout submit, verification bulk edits. */
/* Used by: workforce/templates/workforce/driver_payout_worksheet.html */
/* Notes: Verification actions reuse the existing earnings_verification_action endpoint; the payout submit
   posts the plain form so the server recomputes totals from locked rows rather than trusting the page. */

(function () {
  'use strict';

  /* The hidden input only exists inside the payout form, which is rendered only
     when the driver has payable lines. On a driver with nothing to pay the input
     is absent, so the token has to come from the base template's meta tag —
     otherwise every queue action posts an empty token and dies on a CSRF 403. */
  function csrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute('content')) return meta.getAttribute('content');
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el && el.value) return el.value;
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]*)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  /* Shift-click range select — 50 rows a page, so picking a run by hand is the
     difference between one click and fifty. */
  function rangeSelect(boxes, onChange) {
    let anchor = null;
    boxes.forEach(function (cb, i) {
      cb.addEventListener('click', function (e) {
        if (e.shiftKey && anchor !== null) {
          const [from, to] = anchor < i ? [anchor, i] : [i, anchor];
          for (let j = from; j <= to; j++) { boxes[j].checked = cb.checked; }
          onChange();
        }
        anchor = i;
      });
    });
  }

  /* ── Section A: payable lines ─────────────────────────────── */
  function initPayable() {
    const selectAll = document.getElementById('workforce_payout_select_all');
    const lines = document.querySelectorAll('.workforce_payout_line');
    const count = document.getElementById('workforce_payout_selected_count');
    const tape = document.getElementById('workforce_payout_tape');
    const tapeCount = document.getElementById('workforce_payout_tape_count');
    const tapeTotal = document.getElementById('workforce_payout_tape_total');
    const createBtn = document.getElementById('workforce_payout_btn_create');
    const form = document.getElementById('workforce_payout_form');

    if (!lines.length || !form) return;

    function update() {
      const checked = document.querySelectorAll('.workforce_payout_line:checked');
      // Deductions carry a negative amount, so a plain sum is the net payout.
      let total = 0;
      checked.forEach(function (cb) { total += parseFloat(cb.dataset.amount) || 0; });

      if (count) count.textContent = checked.length + ' selected';
      if (tapeCount) tapeCount.textContent = checked.length;
      if (tapeTotal) tapeTotal.textContent = total.toFixed(2);
      if (tape) tape.hidden = checked.length === 0;
      // The page carries no bottom padding until the tape is there to need it.
      const root = document.getElementById('workforce_payout_root');
      if (root) root.classList.toggle('dpw--tape-open', checked.length > 0);
      if (createBtn) createBtn.disabled = checked.length === 0 || total < 0;

      if (selectAll) {
        selectAll.checked = checked.length === lines.length && checked.length > 0;
        selectAll.indeterminate = checked.length > 0 && checked.length < lines.length;
      }
    }

    if (selectAll) {
      selectAll.addEventListener('change', function () {
        lines.forEach(function (cb) { cb.checked = selectAll.checked; });
        update();
      });
    }
    lines.forEach(function (cb) { cb.addEventListener('change', update); });
    rangeSelect(Array.prototype.slice.call(lines), update);

    if (createBtn) {
      createBtn.addEventListener('click', function () {
        const checked = document.querySelectorAll('.workforce_payout_line:checked');
        if (!checked.length) { return; }
        let total = 0;
        checked.forEach(function (cb) { total += parseFloat(cb.dataset.amount) || 0; });
        if (total < 0) {
          alert('Deductions exceed the earnings selected. Adjust the selection.');
          return;
        }
        if (!confirm('Create a payout of QAR ' + total.toFixed(2) + ' from ' +
                     checked.length + ' line(s)?\n\nThis marks them paid and opens the invoice.')) {
          return;
        }
        createBtn.disabled = true;
        form.submit();
      });
    }

    update();
  }

  /* ── Section B: verification queue ────────────────────────── */
  function initVerification() {
    const selectAll = document.getElementById('workforce_verify_select_all');
    const boxes = document.querySelectorAll('.workforce_verify_task');
    const count = document.getElementById('workforce_verify_selected_count');
    const btnSet = document.getElementById('workforce_verify_btn_set');
    const btnVerify = document.getElementById('workforce_verify_btn_verify');
    const btnPublish = document.getElementById('workforce_verify_btn_publish');
    const btnReject = document.getElementById('workforce_verify_btn_reject');
    const bulkAmount = document.getElementById('workforce_verify_bulk_amount');
    const tools = document.querySelector('.dpw__tools');
    const allPagesBar = document.getElementById('workforce_verify_allpages');
    const allPagesMsg = document.getElementById('workforce_verify_allpages_msg');
    const allPagesBtn = document.getElementById('workforce_verify_btn_allpages');

    if (!boxes.length) return;

    /* Whole-filter selection is a claim about rows this page never rendered, so
       it is only ever a flag — the server resolves the actual ids from the same
       filter. It survives nothing: any change to the checkboxes drops it. */
    const matchCount = tools ? (parseInt(tools.dataset.matchCount, 10) || 0) : 0;
    let allPages = false;

    /* Rows on this page that are selected and priced at nothing. Read off the
       fee box, not the server figure, so a zero typed a second ago counts. */
    function zeroSelected() {
      let n = 0;
      document.querySelectorAll('.workforce_verify_task:checked').forEach(function (cb) {
        const input = document.getElementById('workforce_verify_input_' + cb.value);
        if (input && parseFloat(input.value || '0') === 0) n++;
      });
      return n;
    }

    function selectedCount() {
      return allPages ? matchCount
                      : document.querySelectorAll('.workforce_verify_task:checked').length;
    }

    function renderAllPages(pageChecked) {
      if (!allPagesBar || !allPagesBtn) return;
      // Offer it only once the page itself is fully selected, and only when
      // there is genuinely more behind it.
      const offer = pageChecked === boxes.length && boxes.length > 0 && matchCount > boxes.length;
      allPagesBar.hidden = !(offer || allPages);
      if (allPages) {
        allPagesMsg.textContent = 'All ' + matchCount + ' deliveries in this filter are selected.';
        allPagesBtn.textContent = 'Select this page only';
      } else if (offer) {
        allPagesMsg.textContent = 'All ' + boxes.length + ' on this page selected.';
        allPagesBtn.textContent = 'Select all ' + matchCount + ' across every page';
      }
    }

    function update() {
      const checked = document.querySelectorAll('.workforce_verify_task:checked');
      if (count) {
        count.textContent = allPages ? matchCount + ' selected (all pages)'
                                     : checked.length + ' selected';
      }
      [btnSet, btnVerify, btnPublish, btnReject].forEach(function (b) {
        if (b) b.disabled = selectedCount() === 0;
      });
      if (selectAll) {
        selectAll.checked = checked.length === boxes.length && checked.length > 0;
        selectAll.indeterminate = checked.length > 0 && checked.length < boxes.length;
      }
      renderAllPages(checked.length);
    }

    if (allPagesBtn) {
      allPagesBtn.addEventListener('click', function () {
        allPages = !allPages;
        if (allPages) { boxes.forEach(function (cb) { cb.checked = true; }); }
        update();
      });
    }

    if (selectAll) {
      selectAll.addEventListener('change', function () {
        allPages = false;
        boxes.forEach(function (cb) { cb.checked = selectAll.checked; });
        update();
      });
    }
    boxes.forEach(function (cb) {
      cb.addEventListener('change', function () { allPages = false; update(); });
    });
    rangeSelect(Array.prototype.slice.call(boxes), function () { allPages = false; update(); });

    const fees = Array.prototype.slice.call(document.querySelectorAll('.dpw__fee-input'));
    fees.forEach(function (input, i) {
      input.addEventListener('input', function () {
        const original = parseFloat(this.dataset.original) || 0;
        const current = parseFloat(this.value) || 0;
        this.classList.toggle('dpw__fee-input--modified', original !== current);
      });
      // Typing down a column beats reaching for the mouse on every row.
      input.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const next = fees[e.shiftKey ? i - 1 : i + 1];
        if (next) { next.focus(); next.select(); }
      });
    });

    /* X-Requested-With makes core.views_csrf return JSON instead of the HTML
       expired-page, and the content-type guard turns any other HTML error
       (login redirect, 500) into a readable message rather than a JSON
       parse error about "<!DOCTYPE". */
    function post(body) {
      fetch(workforceEarningsActionUrl, {
        method: 'POST',
        body: body,
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
      })
        .then(function (r) {
          const type = r.headers.get('content-type') || '';
          if (type.indexOf('application/json') === -1) {
            throw new Error(r.status === 403
              ? 'Your session expired. Refresh the page and try again.'
              : 'Server error (' + r.status + '). Refresh the page and try again.');
          }
          return r.json();
        })
        .then(function (data) {
          if (data.success) { location.reload(); }
          else { alert('Error: ' + (data.error || 'Unknown error')); }
        })
        .catch(function (e) { alert('Error: ' + e.message); });
    }

    /* In all-pages mode the ids are left to the server; only the filter and any
       fee the staff member actually typed on a visible row travel with it. */
    function addScope(body) {
      if (!allPages || !tools) return false;
      body.append('scope', 'filtered');
      body.append('driver_id', tools.dataset.driverId || '');
      body.append('only', tools.dataset.only || '');
      (tools.dataset.range || '').split('&').forEach(function (pair) {
        const [k, v] = pair.split('=');
        if (k && v) body.append(k, decodeURIComponent(v));
      });
      return true;
    }

    function bulkAction(action, label) {
      const checked = document.querySelectorAll('.workforce_verify_task:checked');
      const n = selectedCount();
      if (!n) { return; }
      // Publishing is where a salary silently swallows a delivery, so say so
      // before the click, not in the alert afterwards.
      let salaryNote = '';
      if (action === 'publish') {
        const n2 = allPages
          ? (tools ? parseInt(tools.dataset.salaryCount, 10) || 0 : 0)
          : document.querySelectorAll('.workforce_verify_task:checked[data-salary]').length;
        if (n2) {
          salaryNote = '\n\n' + n2 + ' of these are covered by the driver\u2019s salary ' +
                       'and will NOT create an earning.';
        }
        // A fee left at 0.00 pays the driver nothing and cannot be taken back
        // once published, so it is named before the click too.
        const n3 = allPages
          ? (tools ? parseInt(tools.dataset.zeroCount, 10) || 0 : 0)
          : zeroSelected();
        if (n3) {
          salaryNote += '\n\n' + n3 + ' of these have a fee of 0.00 and would pay ' +
                        'the driver nothing.';
        }
      }
      if (!confirm('Are you sure you want to ' + label + ' ' + n + ' delivery(ies)?' +
                   (allPages ? '\n\nThis covers every page of the current filter.' : '') +
                   salaryNote)) {
        return;
      }
      const updates = {};
      const body = new FormData();
      body.append('action', action);
      const scoped = addScope(body);
      checked.forEach(function (cb) {
        if (!scoped) body.append('task_ids[]', cb.value);
        const input = document.getElementById('workforce_verify_input_' + cb.value);
        if (input) updates[cb.value] = input.value;
      });
      body.append('earnings_updates', JSON.stringify(updates));
      body.append('csrfmiddlewaretoken', csrf());
      post(body);
    }

    if (btnVerify) btnVerify.addEventListener('click', function () { bulkAction('verify', 'verify'); });
    if (btnPublish) btnPublish.addEventListener('click', function () { bulkAction('publish', 'verify and publish'); });
    if (btnReject) btnReject.addEventListener('click', function () { bulkAction('reject', 'reject'); });

    if (btnSet) {
      btnSet.addEventListener('click', function () {
        const checked = document.querySelectorAll('.workforce_verify_task:checked');
        const n = selectedCount();
        if (!n) { return; }
        const raw = (bulkAmount.value || '').trim();
        const amount = parseFloat(raw);
        if (raw === '' || isNaN(amount) || amount < 0) {
          alert('Enter an amount of 0 or more.');
          bulkAmount.focus();
          return;
        }
        if (!confirm('Set earnings to ' + amount.toFixed(2) + ' QAR on ' + n +
                     ' delivery(ies)?\n\nAlready-published rows are skipped.' +
                     (allPages ? '\n\nThis covers every page of the current filter.' : ''))) {
          return;
        }
        const body = new FormData();
        body.append('action', 'set_amount');
        body.append('bulk_amount', amount.toFixed(2));
        if (!addScope(body)) {
          checked.forEach(function (cb) { body.append('task_ids[]', cb.value); });
        }
        body.append('csrfmiddlewaretoken', csrf());
        post(body);
      });
    }

    update();
  }

  /* ── Activity trail + period filter ───────────────────────── */
  function initMisc() {
    document.querySelectorAll('.dpw__log-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const row = document.getElementById('workforce_verify_log_' + btn.dataset.logFor);
        if (!row) return;
        const open = !row.hidden;
        row.hidden = open;
        btn.setAttribute('aria-expanded', String(!open));
        btn.classList.toggle('dpw__log-btn--open', !open);
      });
    });

    /* Preset and custom range are two answers to one question, so picking a
       preset drops the From/To boxes — otherwise the server would keep taking
       the range and the dropdown would look broken. */
    const days = document.getElementById('workforce_payout_days');
    const filterForm = document.getElementById('workforce_payout_filter_form');
    const from = document.getElementById('workforce_payout_from');
    const to = document.getElementById('workforce_payout_to');
    if (days && filterForm) {
      days.addEventListener('change', function () {
        if (!days.value) return;  // the "Custom range" placeholder
        if (from) from.value = '';
        if (to) to.value = '';
        filterForm.submit();
      });
    }
    /* Typing a range is the explicit act, so it clears the preset on submit
       and an empty To is read as "up to today". */
    if (filterForm && (from || to)) {
      filterForm.addEventListener('submit', function () {
        if (days && ((from && from.value) || (to && to.value))) days.disabled = true;
        // An empty box would otherwise serialise as `from=&to=`, which is noise
        // in a URL staff copy to each other.
        [from, to].forEach(function (el) { if (el && !el.value) el.disabled = true; });
      });
      [from, to].forEach(function (el) {
        if (!el) return;
        el.addEventListener('change', function () {
          if (from && to && from.value && to.value && from.value > to.value) {
            const swap = from.value; from.value = to.value; to.value = swap;
          }
        });
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initPayable();
    initVerification();
    initMisc();
  });
})();
