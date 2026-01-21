/**
 * Orders Main JavaScript
 * Handles view toggle between grid and table views
 */

document.addEventListener('DOMContentLoaded', function() {
  initViewToggle();
});

/**
 * Initialize the view toggle functionality
 */
function initViewToggle() {
  const toggleContainer = document.getElementById('orders_all_list_view_toggle');
  if (!toggleContainer) return;

  const toggleButtons = toggleContainer.querySelectorAll('.view-toggle-btn');
  const gridView = document.getElementById('orders_grid_view');
  const tableView = document.getElementById('orders_table_view');

  if (!gridView || !tableView) return;

  // Load saved preference
  const savedView = localStorage.getItem('orders_view_preference') || 'grid';
  setActiveView(savedView, toggleButtons, gridView, tableView);

  // Add click handlers
  toggleButtons.forEach(function(btn) {
    btn.addEventListener('click', function() {
      const view = this.getAttribute('data-view');
      setActiveView(view, toggleButtons, gridView, tableView);
      localStorage.setItem('orders_view_preference', view);
    });
  });
}

/**
 * Set the active view
 * @param {string} view - 'grid' or 'table'
 * @param {NodeList} buttons - Toggle buttons
 * @param {HTMLElement} gridView - Grid view container
 * @param {HTMLElement} tableView - Table view container
 */
function setActiveView(view, buttons, gridView, tableView) {
  // Update button states
  buttons.forEach(function(btn) {
    if (btn.getAttribute('data-view') === view) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Show/hide views
  if (view === 'table') {
    gridView.style.display = 'none';
    tableView.style.display = 'block';
  } else {
    gridView.style.display = 'block';
    tableView.style.display = 'none';
  }
}
