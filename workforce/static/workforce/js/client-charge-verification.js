/* Purpose: Client delivery-charge console behaviour — row selection, bulk amount, verify/publish/reject. */
/* Used by: workforce/templates/workforce/client_charge_verification.html */
/* Notes: Every figure is re-validated server-side; the tape total is display only. Published rows are locked
   in the markup and are also skipped by the server, so a stale page can never rewrite an agreed charge. */

(function () {
  'use strict';

  function csrf() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function selected() {
    return Array.prototype.slice.call(
      document.querySelectorAll('.workforce_charges_task:checked'));
  }

  function init() {
    const boxes = Array.prototype.slice.call(
      document.querySelectorAll('.workforce_charges_task'));
    const selectAll = document.getElementById('workforce_charges_select_all');
    const count = document.getElementById('workforce_charges_selected_count');
    const bulkAmount = document.getElementById('workforce_charges_bulk_amount');
    const btnSet = document.getElementById('workforce_charges_btn_set');
    const btnVerify = document.getElementById('workforce_charges_btn_verify');
    const btnPublish = document.getElementById('workforce_charges_btn_publish');
    const btnReject = document.getElementById('workforce_charges_btn_reject');
    const tape = document.getElementById('workforce_charges_tape');
    const tapeCount = document.getElementById('workforce_charges_tape_count');
    const tapeTotal = document.getElementById('workforce_charges_tape_total');

    if (!boxes.length) return;

    function update() {
      const checked = selected();
      let total = 0;
      checked.forEach(function (cb) {
        const input = document.getElementById('workforce_charges_input_' + cb.value);
        const raw = input ? input.value : cb.dataset.charge;
        total += parseFloat(raw) || 0;
      });

      if (count) count.textContent = checked.length + ' selected';
      if (tapeCount) tapeCount.textContent = checked.length;
      if (tapeTotal) tapeTotal.textContent = total.toFixed(2);
      if (tape) tape.hidden = checked.length === 0;

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

    document.querySelectorAll('.ccv__amount-input').forEach(function (input) {
      input.addEventListener('input', function () {
        const original = parseFloat(this.dataset.original) || 0;
        const current = parseFloat(this.value) || 0;
        this.classList.toggle('ccv__amount-input--modified', original !== current);
        update();
      });
    });

    function post(body, buttons) {
      buttons.forEach(function (b) { if (b) b.disabled = true; });
      fetch(workforceChargeActionUrl, { method: 'POST', body: body })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.success) {
            if (data.errors && data.errors.length) {
              alert(data.message + '\n\n' + data.errors.slice(0, 10).join('\n'));
            }
            location.reload();
          } else {
            alert('Error: ' + (data.error || 'Unknown error'));
            buttons.forEach(function (b) { if (b) b.disabled = false; });
          }
        })
        .catch(function (e) {
          alert('Error: ' + e.message);
          buttons.forEach(function (b) { if (b) b.disabled = false; });
        });
    }

    function bulkAction(action, label, button) {
      const checked = selected();
      if (!checked.length) return;
      const locked = checked.filter(function (cb) { return cb.dataset.locked === '1'; }).length;
      let msg = label.charAt(0).toUpperCase() + label.slice(1) +
                ' ' + checked.length + ' delivery charge(s)?';
      if (locked) msg += '\n\n' + locked + ' already published and will be skipped.';
      if (!confirm(msg)) return;

      const updates = {};
      const body = new FormData();
      body.append('action', action);
      checked.forEach(function (cb) {
        body.append('task_ids[]', cb.value);
        const input = document.getElementById('workforce_charges_input_' + cb.value);
        if (input && !input.readOnly) updates[cb.value] = input.value;
      });
      body.append('charge_updates', JSON.stringify(updates));
      body.append('csrfmiddlewaretoken', csrf());
      post(body, [button]);
    }

    if (btnVerify) {
      btnVerify.addEventListener('click', function () {
        bulkAction('verify', 'verify', btnVerify);
      });
    }
    if (btnPublish) {
      btnPublish.addEventListener('click', function () {
        bulkAction('publish', 'verify and publish', btnPublish);
      });
    }
    if (btnReject) {
      btnReject.addEventListener('click', function () {
        bulkAction('reject', 'reject', btnReject);
      });
    }

    if (btnSet) {
      btnSet.addEventListener('click', function () {
        const checked = selected();
        if (!checked.length) return;
        const raw = (bulkAmount.value || '').trim();
        const amount = parseFloat(raw);
        if (raw === '' || isNaN(amount) || amount < 0) {
          alert('Enter an amount of 0 or more.');
          bulkAmount.focus();
          return;
        }
        if (!confirm('Set the client charge to ' + amount.toFixed(2) + ' QAR on ' +
                     checked.length + ' delivery(ies)?\n\nAlready-published rows are skipped.')) {
          return;
        }
        const body = new FormData();
        body.append('action', 'set_amount');
        body.append('bulk_amount', amount.toFixed(2));
        checked.forEach(function (cb) { body.append('task_ids[]', cb.value); });
        body.append('csrfmiddlewaretoken', csrf());
        post(body, [btnSet]);
      });
    }

    update();
  }

  function initMisc() {
    document.querySelectorAll('.ccv__log-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const row = document.getElementById('workforce_charges_log_' + btn.dataset.logFor);
        if (!row) return;
        const open = !row.hidden;
        row.hidden = open;
        btn.setAttribute('aria-expanded', String(!open));
        btn.classList.toggle('ccv__log-btn--open', !open);
      });
    });

    // Filters re-query on change — no separate Apply button to forget.
    const form = document.getElementById('workforce_charges_filter_form');
    if (form) {
      form.querySelectorAll('select').forEach(function (sel) {
        sel.addEventListener('change', function () { form.submit(); });
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    init();
    initMisc();
  });
})();
