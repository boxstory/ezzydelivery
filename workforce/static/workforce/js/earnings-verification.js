/* ============================================
   EARNINGS VERIFICATION - INTERACTIVE BEHAVIORS
   ============================================ */

document.addEventListener('DOMContentLoaded', function() {
  // Element references
  const selectAll = document.getElementById('workforce_earnings_select_all');
  const checkboxes = document.querySelectorAll('.workforce_earnings_task_checkbox');
  const selectedCount = document.getElementById('workforce_earnings_selected_count');
  const barSelectedCount = document.getElementById('workforce_earnings_bar_selected_count');
  const barTotalEarnings = document.getElementById('workforce_earnings_bar_total_earnings');
  const bulkActionBar = document.getElementById('workforce_earnings_bulk_action_bar');
  const btnVerify = document.getElementById('workforce_earnings_btn_verify');
  const btnPublish = document.getElementById('workforce_earnings_btn_publish');
  const btnReject = document.getElementById('workforce_earnings_btn_reject');
  const bulkAmount = document.getElementById('workforce_earnings_bulk_amount');
  const btnSetAmount = document.getElementById('workforce_earnings_btn_set_amount');
  const barBtnVerify = document.getElementById('workforce_earnings_bar_btn_verify');
  const barBtnPublish = document.getElementById('workforce_earnings_bar_btn_publish');

  /**
   * Update selection state and totals
   */
  function updateSelection() {
    const checked = document.querySelectorAll('.workforce_earnings_task_checkbox:checked');
    const count = checked.length;
    let total = 0;

    checked.forEach(function(cb) {
      const input = document.getElementById('workforce_earnings_input_' + cb.value);
      total += parseFloat(input.value) || 0;
    });

    selectedCount.textContent = count + ' selected';
    barSelectedCount.textContent = count;
    barTotalEarnings.textContent = total.toFixed(0);

    // Show/hide bulk action bar
    bulkActionBar.classList.toggle('show', count > 0);

    // Enable/disable buttons
    btnVerify.disabled = count === 0;
    btnPublish.disabled = count === 0;
    btnReject.disabled = count === 0;
    if (btnSetAmount) btnSetAmount.disabled = count === 0;

    // Update select all state
    selectAll.checked = count === checkboxes.length && count > 0;
    selectAll.indeterminate = count > 0 && count < checkboxes.length;
  }

  /**
   * Select all checkbox handler
   */
  selectAll.addEventListener('change', function() {
    checkboxes.forEach(function(cb) {
      cb.checked = selectAll.checked;
    });
    updateSelection();
  });

  /**
   * Individual checkbox handlers
   */
  checkboxes.forEach(function(cb) {
    cb.addEventListener('change', updateSelection);
  });

  /**
   * Track modified earnings inputs
   */
  document.querySelectorAll('.workforce_earnings_input').forEach(function(input) {
    input.addEventListener('input', function() {
      const original = parseFloat(this.dataset.original) || 0;
      const current = parseFloat(this.value) || 0;
      this.classList.toggle('modified', original !== current);
      updateSelection();
    });
  });

  /**
   * Attach click handlers to action buttons
   */
  btnVerify.addEventListener('click', function() { workforceEarningsBulkAction('verify'); });
  btnPublish.addEventListener('click', function() { workforceEarningsBulkAction('publish'); });
  btnReject.addEventListener('click', function() { workforceEarningsBulkAction('reject'); });
  barBtnVerify.addEventListener('click', function() { workforceEarningsBulkAction('verify'); });
  barBtnPublish.addEventListener('click', function() { workforceEarningsBulkAction('publish'); });

  /**
   * Auto-submit filter form on dropdown change
   */
  document.getElementById('workforce_earnings_filter_driver').addEventListener('change', function() {
    document.getElementById('workforce_earnings_filter_form').submit();
  });
  document.getElementById('workforce_earnings_filter_status').addEventListener('change', function() {
    document.getElementById('workforce_earnings_filter_form').submit();
  });
  document.getElementById('workforce_earnings_filter_days').addEventListener('change', function() {
    document.getElementById('workforce_earnings_filter_form').submit();
  });
});

/**
 * Execute bulk action
 * @param {string} action - Action type: verify, publish, reject
 */
function workforceEarningsBulkAction(action) {
  const checked = document.querySelectorAll('.workforce_earnings_task_checkbox:checked');

  if (checked.length === 0) {
    alert('Please select at least one task');
    return;
  }

  const actionLabels = {
    'verify': 'verify',
    'publish': 'verify and publish',
    'reject': 'reject'
  };

  if (!confirm(`Are you sure you want to ${actionLabels[action]} ${checked.length} task(s)?`)) {
    return;
  }

  const taskIds = [];
  const earningsUpdates = {};

  checked.forEach(function(cb) {
    taskIds.push(cb.value);
    const input = document.getElementById('workforce_earnings_input_' + cb.value);
    earningsUpdates[cb.value] = input.value;
  });

  const formData = new FormData();
  formData.append('action', action);
  taskIds.forEach(id => formData.append('task_ids[]', id));
  formData.append('earnings_updates', JSON.stringify(earningsUpdates));
  formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

  fetch(workforceEarningsVerificationActionUrl, {
    method: 'POST',
    body: formData
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      alert(data.message);
      location.reload();
    } else {
      alert('Error: ' + (data.error || 'Unknown error'));
    }
  })
  .catch(error => {
    alert('Error: ' + error.message);
  });
}


/**
 * Apply one amount to every selected delivery.
 */
function workforceEarningsSetAmount() {
  const checked = document.querySelectorAll('.workforce_earnings_task_checkbox:checked');
  const field = document.getElementById('workforce_earnings_bulk_amount');
  if (checked.length === 0) { alert('Select at least one delivery first.'); return; }

  const raw = (field.value || '').trim();
  const amount = parseFloat(raw);
  if (raw === '' || isNaN(amount) || amount < 0) {
    alert('Enter an amount of 0 or more.');
    field.focus();
    return;
  }
  if (!confirm('Set earnings to ' + amount.toFixed(2) + ' QAR on ' + checked.length +
               ' delivery(ies)?\n\nAlready-published rows are skipped.')) {
    return;
  }

  const formData = new FormData();
  formData.append('action', 'set_amount');
  formData.append('bulk_amount', amount.toFixed(2));
  checked.forEach(function (cb) { formData.append('task_ids[]', cb.value); });
  formData.append('csrfmiddlewaretoken',
                  document.querySelector('[name=csrfmiddlewaretoken]').value);

  fetch(workforceEarningsVerificationActionUrl, { method: 'POST', body: formData })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success) { alert(data.message); location.reload(); }
      else { alert('Error: ' + (data.error || 'Unknown error')); }
    })
    .catch(function (e) { alert('Error: ' + e.message); });
}

document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('workforce_earnings_btn_set_amount');
  if (btn) btn.addEventListener('click', workforceEarningsSetAmount);
});

/* Per-task activity trail. The log row sits directly under its task row and is
   collapsed by default so the console stays a dense list until staff ask. */
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.evr__log-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const row = document.getElementById('workforce_earnings_log_' + btn.dataset.logFor);
      if (!row) return;
      const open = !row.hidden;
      row.hidden = open;
      btn.setAttribute('aria-expanded', String(!open));
      btn.classList.toggle('evr__log-btn--open', !open);
    });
  });
});
