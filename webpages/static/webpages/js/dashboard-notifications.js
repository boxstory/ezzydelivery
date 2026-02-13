/**
 * Dashboard Notifications - Toastify Wrapper
 * EzzyDelivery Qatar
 */

// Toast notification wrapper
function showToast(message, type = 'success', duration = 3000) {
  const colors = {
    success: '#10B981',
    error: '#EF4444',
    warning: '#F59E0B',
    info: '#3B82F6',
    primary: '#f7c000'
  };

  const icons = {
    success: '✓',
    error: '✕',
    warning: '⚠',
    info: 'ℹ',
    primary: '★'
  };

  if (typeof Toastify === 'undefined') {
    console.warn('Toastify not loaded, using fallback');
    alert(`${icons[type] || ''} ${message}`);
    return;
  }

  Toastify({
    text: `${icons[type] || ''} ${message}`,
    duration: duration,
    gravity: "top",
    position: "right",
    backgroundColor: colors[type] || colors.success,
    stopOnFocus: true,
    className: `toast-${type}`,
    offset: {
      x: 10,
      y: 70
    },
    onClick: function() {
      this.hideToast();
    }
  }).showToast();
}

// Success toast
function showSuccess(message, duration = 3000) {
  showToast(message, 'success', duration);
}

// Error toast
function showError(message, duration = 5000) {
  showToast(message, 'error', duration);
}

// Warning toast
function showWarning(message, duration = 4000) {
  showToast(message, 'warning', duration);
}

// Info toast
function showInfo(message, duration = 3000) {
  showToast(message, 'info', duration);
}

// Convert Django messages to toasts
document.addEventListener('DOMContentLoaded', function() {
  const djangoMessages = document.querySelectorAll('.django-message');

  djangoMessages.forEach(function(msg) {
    const text = msg.textContent.trim();
    const messageType = msg.dataset.messageType || 'info';

    // Map Django message types to toast types
    const typeMap = {
      'success': 'success',
      'error': 'error',
      'warning': 'warning',
      'info': 'info',
      'debug': 'info'
    };

    showToast(text, typeMap[messageType] || 'info');

    // Hide the original Django message
    msg.style.display = 'none';
  });
});

// HTMX response toasts
document.body.addEventListener('htmx:afterSwap', function(evt) {
  // Check for toast data in response
  const toast = evt.detail.xhr.getResponseHeader('X-Toast-Message');
  const toastType = evt.detail.xhr.getResponseHeader('X-Toast-Type');

  if (toast) {
    showToast(toast, toastType || 'success');
  }
});

// Form validation toasts
function showValidationError(message) {
  showError(message || 'Please check the form for errors');
}

// Confirm action with toast
function confirmAction(message, callback) {
  const confirmed = confirm(message);
  if (confirmed) {
    callback();
    showInfo('Action in progress...');
  }
  return confirmed;
}
