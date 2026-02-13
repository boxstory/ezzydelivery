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
