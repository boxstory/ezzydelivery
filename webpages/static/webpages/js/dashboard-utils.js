/**
 * Dashboard Utilities - Helper Functions
 * EzzyDelivery Qatar
 */

/**
 * Format currency (QAR)
 */
function formatCurrency(amount, decimals = 2) {
  return `QAR ${parseFloat(amount).toFixed(decimals).replace(/\d(?=(\d{3})+\.)/g, '$&,')}`;
}

/**
 * Format number with commas
 */
function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Format date (YYYY-MM-DD to readable format)
 */
function formatDate(dateString, format = 'full') {
  const date = new Date(dateString);
  const options = {
    full: { year: 'numeric', month: 'long', day: 'numeric' },
    short: { year: 'numeric', month: 'short', day: 'numeric' },
    time: { hour: '2-digit', minute: '2-digit' }
  };

  return date.toLocaleDateString('en-QA', options[format] || options.full);
}

/**
 * Calculate percentage
 */
function calculatePercentage(value, total) {
  if (total === 0) return 0;
  return ((value / total) * 100).toFixed(1);
}

/**
 * Debounce function (for search inputs)
 */
function debounce(func, wait = 300) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      showSuccess('Copied to clipboard!');
    }).catch(() => {
      showError('Failed to copy');
    });
  } else {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showSuccess('Copied to clipboard!');
  }
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
  const statusMap = {
    // Order statuses
    'pending': { color: 'warning', icon: 'clock', text: 'Pending' },
    'published': { color: 'info', icon: 'cloud', text: 'Published' },
    'assigned': { color: 'primary', icon: 'user-check', text: 'Assigned' },
    'in_transit': { color: 'primary', icon: 'truck', text: 'In Transit' },
    'delivered': { color: 'success', icon: 'check-circle', text: 'Delivered' },
    'failed': { color: 'danger', icon: 'times-circle', text: 'Failed' },
    'cancelled': { color: 'danger', icon: 'ban', text: 'Cancelled' },

    // Driver statuses
    'Approved': { color: 'success', icon: 'check', text: 'Approved' },
    'Pending': { color: 'warning', icon: 'hourglass', text: 'Pending' },
    'Suspended': { color: 'danger', icon: 'pause', text: 'Suspended' },

    // Payment statuses
    'paid': { color: 'success', icon: 'check-double', text: 'Paid' },
    'unpaid': { color: 'warning', icon: 'exclamation', text: 'Unpaid' }
  };

  const config = statusMap[status] || { color: 'secondary', icon: 'question', text: status };

  return `<span class="badge bg-${config.color}">
    <i class="fa-solid fa-${config.icon} me-1"></i> ${config.text}
  </span>`;
}

/**
 * Confirm dialog with custom styling
 */
function confirmDialog(title, message, callback) {
  if (confirm(`${title}\n\n${message}`)) {
    callback();
    return true;
  }
  return false;
}

/**
 * Loading overlay
 */
const loadingOverlay = {
  show: function(message = 'Loading...') {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
      overlay.querySelector('.loading-text').textContent = message;
      overlay.classList.remove('d-none');
    }
  },
  hide: function() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
      overlay.classList.add('d-none');
    }
  }
};

/**
 * Auto-refresh for real-time dashboards
 */
let refreshInterval = null;

function startAutoRefresh(callback, interval = 30000) {
  stopAutoRefresh();
  refreshInterval = setInterval(callback, interval);
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval);
    refreshInterval = null;
  }
}

/**
 * Mobile detection
 */
function isMobile() {
  return window.innerWidth <= 768;
}

/**
 * Scroll to top
 */
function scrollToTop(smooth = true) {
  window.scrollTo({
    top: 0,
    behavior: smooth ? 'smooth' : 'auto'
  });
}

/**
 * Print element
 */
function printElement(elementId) {
  const element = document.getElementById(elementId);
  if (!element) return;

  const printWindow = window.open('', '', 'height=600,width=800');
  printWindow.document.write('<html><head><title>Print</title>');
  printWindow.document.write('<link rel="stylesheet" href="/static/webpages/css/brandkit.css">');
  printWindow.document.write('</head><body>');
  printWindow.document.write(element.innerHTML);
  printWindow.document.write('</body></html>');
  printWindow.document.close();
  printWindow.print();
}

/**
 * Export table to CSV
 */
function exportToCSV(tableId, filename = 'export.csv') {
  const table = document.getElementById(tableId);
  if (!table) return;

  let csv = [];
  const rows = table.querySelectorAll('tr');

  rows.forEach(row => {
    const cols = row.querySelectorAll('td, th');
    const rowData = [];
    cols.forEach(col => {
      rowData.push('"' + col.textContent.trim().replace(/"/g, '""') + '"');
    });
    csv.push(rowData.join(','));
  });

  const csvContent = csv.join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  window.URL.revokeObjectURL(url);
  showSuccess('Exported to CSV');
}

/**
 * Get CSRF Token
 */
function getCSRFToken() {
  return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
         document.querySelector('meta[name=csrf-token]')?.content ||
         getCookie('csrftoken');
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

/**
 * AJAX helper with CSRF
 */
function ajaxRequest(url, options = {}) {
  const defaultOptions = {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCSRFToken()
    }
  };

  return fetch(url, { ...defaultOptions, ...options })
    .then(response => {
      if (!response.ok) throw new Error('Network response was not ok');
      return response.json();
    });
}

// Export functions for global use
window.DashboardUtils = {
  formatCurrency,
  formatNumber,
  formatDate,
  calculatePercentage,
  debounce,
  copyToClipboard,
  getStatusBadge,
  confirmDialog,
  loadingOverlay,
  startAutoRefresh,
  stopAutoRefresh,
  isMobile,
  scrollToTop,
  printElement,
  exportToCSV,
  getCSRFToken,
  ajaxRequest
};
