/* Purpose: Driver payout worksheet behaviour — payable-line selection, payout submit, verification bulk edits. */
/* Used by: workforce/templates/workforce/driver_payout_worksheet.html */
/* Notes: Verification actions reuse the existing earnings_verification_action endpoint; the payout submit
   posts the plain form so the server recomputes totals from locked rows rather than trusting the page. */

(function () {
  'use strict';

  function csrf() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
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

    if (!boxes.length) return;

    function update() {
      const checked = document.querySelectorAll('.workforce_verify_task:checked');
      if (count) count.textContent = checked.length + ' selected';
      [btnSet, btnVerify, btnPublish, btnReject].forEach(function (b) {
        if (b) b.disabled = checked.length === 0;
      });
      if (selectAll) {
        selectAll.checked = checked.length === boxes.length && checked.length > 0;
        selectAll.indeterminate = checked.length > 0 && checked.length < boxes.length;
      }
    }

    if (selectAll) {
      selectAll.addEventListener('change', function () {
        boxes.forEach(function (cb) { cb.checked = selectAll.checked; });
        update();
      });
    }
    boxes.forEach(function (cb) { cb.addEventListener('change', update); });
    rangeSelect(Array.prototype.slice.call(boxes), update);

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

    function post(body) {
      fetch(workforceEarningsActionUrl, { method: 'POST', body: body })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.success) { location.reload(); }
          else { alert('Error: ' + (data.error || 'Unknown error')); }
        })
        .catch(function (e) { alert('Error: ' + e.message); });
    }

    function bulkAction(action, label) {
      const checked = document.querySelectorAll('.workforce_verify_task:checked');
      if (!checked.length) { return; }
      if (!confirm('Are you sure you want to ' + label + ' ' + checked.length + ' delivery(ies)?')) {
        return;
      }
      const updates = {};
      const body = new FormData();
      body.append('action', action);
      checked.forEach(function (cb) {
        body.append('task_ids[]', cb.value);
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
        if (!checked.length) { return; }
        const raw = (bulkAmount.value || '').trim();
        const amount = parseFloat(raw);
        if (raw === '' || isNaN(amount) || amount < 0) {
          alert('Enter an amount of 0 or more.');
          bulkAmount.focus();
          return;
        }
        if (!confirm('Set earnings to ' + amount.toFixed(2) + ' QAR on ' + checked.length +
                     ' delivery(ies)?\n\nAlready-published rows are skipped.')) {
          return;
        }
        const body = new FormData();
        body.append('action', 'set_amount');
        body.append('bulk_amount', amount.toFixed(2));
        checked.forEach(function (cb) { body.append('task_ids[]', cb.value); });
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

    const days = document.getElementById('workforce_payout_days');
    const filterForm = document.getElementById('workforce_payout_filter_form');
    if (days && filterForm) {
      days.addEventListener('change', function () { filterForm.submit(); });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initPayable();
    initVerification();
    initMisc();
  });
})();
