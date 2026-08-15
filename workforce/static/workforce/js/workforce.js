/* ============================================
   WORKFORCE APP - MERGED JAVASCRIPT
   ============================================ */

/* ---------- WF LISTS ---------- */
/**
 * Workforce Lists JavaScript
 * Handles filtering, task actions, and UI interactions for task/order lists
 */

(function() {
    'use strict';

    // ==================== UTILITY FUNCTIONS ====================

    /**
     * Get CSRF token from cookies
     */
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

    function getCSRFToken() {
        // 1. Try meta tag
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        // 2. Try hidden input from any form
        var input = document.querySelector('[name=csrfmiddlewaretoken]');
        if (input) return input.value;
        // 3. Fallback to cookie (works when CSRF_COOKIE_HTTPONLY=False)
        return getCookie('csrftoken');
    }

    /**
     * Show toast notification
     */
    function showToast(message, type = 'info') {
        const toastContainer = document.getElementById('toast-container') || createToastContainer();
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        toastContainer.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast, { delay: 4000 });
        bsToast.show();
        toast.addEventListener('hidden.bs.toast', () => toast.remove());
    }

    function createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '11000';
        document.body.appendChild(container);
        return container;
    }

    /**
     * Debounce function for input handlers
     */
    function debounce(func, wait) {
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

    // ==================== FILTER FUNCTIONALITY ====================

    /* FilterManager removed 2026-07-29.
       It was a second, orphaned filter engine: initialised on every page but
       keyed on ids (dlCode, cCode, mobile, driverName, cStatus, dmsStatus,
       dateFrom, dateTo, business) that no template has rendered for a long time
       — every list uses the pgf_* set. So getFilterValues() always returned
       empty, its active-filter chips never drew, and its localStorage presets
       were unreachable with no button bound to them.

       It also bound a SECOND Enter handler on '#filterForm input[type=text]'.
       Both that and the pg-filter handler fired on one keypress and happened to
       navigate to the same URL — coincidence, not design. Chips now come from
       the server (see _page_filter.html applied_chips). */

    // ==================== TASK ACTIONS ====================

    const TaskActions = {
        publishToDMS: function(taskId) {
            if (confirm('Publish this task to the Delivery Management System?')) {
                fetch(`/workforce/delivery-task/${taskId}/publish-dms/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast('Task published to DMS successfully!', 'success');
                        // Refresh the task card
                        htmx.ajax('GET', window.location.href, {
                            target: '#main-content',
                            select: '#main-content',
                            swap: 'outerHTML'
                        });
                    } else {
                        showToast('Error: ' + (data.error || 'Failed to publish to DMS'), 'danger');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    showToast('An error occurred while publishing to DMS', 'danger');
                });
            }
        },

        publishToDriverApp: function(taskId) {
            if (confirm('Publish this task to the Driver Mobile App?')) {
                fetch(`/workforce/delivery-task/${taskId}/publish-driver-app/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        showToast('Task published to Driver App successfully!', 'success');
                        htmx.ajax('GET', window.location.href, {
                            target: '#main-content',
                            select: '#main-content',
                            swap: 'outerHTML'
                        });
                    } else {
                        showToast('Error: ' + (data.error || 'Failed to publish to Driver App'), 'danger');
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    showToast('An error occurred while publishing to Driver App', 'danger');
                });
            }
        },

        setStatusModalTask: function(btn) {
            var taskId = btn.getAttribute('data-task-id');
            var taskNumber = btn.getAttribute('data-task-number');
            var statusType = btn.getAttribute('data-status-type') || 'task';
            var currentStatus = btn.getAttribute('data-current-status') || '';
            var currentDms = btn.getAttribute('data-current-dms') || '';
            var driverId = btn.getAttribute('data-driver-id') || '';
            var driverName = btn.getAttribute('data-driver-name') || '';
            var customerName = btn.getAttribute('data-customer-name') || '';

            document.getElementById('statusModalTaskId').value = taskId;
            document.getElementById('statusModalStatusType').value = statusType;
            document.getElementById('statusModalTaskNumber').textContent = taskNumber;

            // Customer name
            var custEl = document.getElementById('statusModalCustomer');
            if (custEl) custEl.textContent = customerName || '—';

            // Current status badge
            var badgeEl = document.getElementById('statusModalCurrentBadge');
            if (badgeEl) {
                var display = currentStatus ? currentStatus.replace(/_/g, ' ') : currentDms;
                badgeEl.textContent = display || '—';
                badgeEl.className = 'dl-badge dl-badge--' + (currentStatus || 'dms-' + currentDms);
            }

            // Rebuild status options from model choices and pre-select current status
            var selectEl = document.getElementById('statusSelect');
            var taskStatuses = window.TASK_STATUS_CHOICES || [];
            var optionsHtml = '<option value="">-- Select Status --</option>';
            taskStatuses.forEach(function(s) {
                var selected = (s.value === currentStatus) ? ' selected' : '';
                optionsHtml += '<option value="' + s.value + '"' + selected + '>' + s.label + '</option>';
            });
            selectEl.innerHTML = optionsHtml;

            // Set current time
            var timeEl = document.getElementById('statusModalTime');
            if (timeEl) {
                var now = new Date();
                var offset = now.getTimezoneOffset();
                var local = new Date(now.getTime() - offset * 60000);
                timeEl.value = local.toISOString().slice(0, 16);
            }

            // Clear notes
            var notesEl = document.getElementById('statusModalNotes');
            if (notesEl) notesEl.value = '';

            // Driver info
            var driverInfoEl = document.getElementById('statusModalDriverInfo');
            var driverNameEl = document.getElementById('statusModalDriverName');
            if (driverId && driverName) {
                if (driverInfoEl) driverInfoEl.style.display = 'block';
                if (driverNameEl) driverNameEl.textContent = driverName;
            } else {
                if (driverInfoEl) driverInfoEl.style.display = 'none';
            }

            // Load drivers list
            this._loadDriversList(driverId);
        },

        _loadDriversList: function(currentDriverId) {
            var driverSelect = document.getElementById('statusModalDriver');
            if (!driverSelect) return;

            // Reset to loading state
            driverSelect.innerHTML = '<option value="">Loading drivers...</option>';
            driverSelect.disabled = true;

            fetch('/workforce/api/drivers-list/', {
                headers: { 'Accept': 'application/json' }
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                driverSelect.innerHTML = '<option value="">-- No Driver --</option>';
                if (data.drivers && data.drivers.length) {
                    data.drivers.forEach(function(d) {
                        var opt = document.createElement('option');
                        opt.value = d.id;
                        opt.textContent = d.name;
                        if (String(d.id) === String(currentDriverId)) {
                            opt.selected = true;
                        }
                        driverSelect.appendChild(opt);
                    });
                }
                driverSelect.disabled = false;
            })
            .catch(function() {
                driverSelect.innerHTML = '<option value="">-- No Driver --</option>';
                driverSelect.disabled = false;
            });
        },

        submitStatusUpdate: function() {
            var taskId = document.getElementById('statusModalTaskId').value;
            var status = document.getElementById('statusSelect').value;
            var driverId = document.getElementById('statusModalDriver').value;
            var time = document.getElementById('statusModalTime').value;
            var notes = document.getElementById('statusModalNotes').value;

            if (!status) {
                showToast('Please select a status', 'warning');
                return;
            }

            var submitBtn = document.getElementById('statusModalSubmitBtn');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-1"></i>Updating...';
            }

            // Special action: Publish to Fleets (sets dl_task_publish=True + status=pending)
            if (status === 'publish_to_fleets') {
                fetch('/workforce/delivery-task/' + taskId + '/publish-fleets/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    }
                })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i>Update Status';
                    }
                    if (data.success) {
                        var modal = bootstrap.Modal.getInstance(document.getElementById('statusModal'));
                        if (modal) modal.hide();
                        showToast('Task published to Fleet drivers!', 'success');
                        if (typeof htmx !== 'undefined') {
                            htmx.ajax('GET', window.location.href, { target: '#main-content', select: '#main-content', swap: 'outerHTML' });
                        } else {
                            location.reload();
                        }
                    } else {
                        showToast('Error: ' + (data.error || 'Failed to publish'), 'danger');
                    }
                })
                .catch(function() {
                    if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i>Update Status'; }
                    showToast('An error occurred', 'danger');
                });
                return;
            }

            var payload = { status: status };
            if (driverId) payload.driver_id = driverId;
            if (time) payload.time = time;
            if (notes) payload.notes = notes;

            fetch('/workforce/delivery-task/' + taskId + '/update-status/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify(payload)
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i>Update Status';
                }
                if (data.success) {
                    var modal = bootstrap.Modal.getInstance(document.getElementById('statusModal'));
                    modal.hide();
                    showToast('Task status updated successfully!', 'success');
                    if (typeof htmx !== 'undefined') {
                        htmx.ajax('GET', window.location.href, {
                            target: '#main-content',
                            select: '#main-content',
                            swap: 'outerHTML'
                        });
                    } else {
                        location.reload();
                    }
                } else {
                    showToast('Error: ' + (data.error || 'Failed to update status'), 'danger');
                }
            })
            .catch(function(error) {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fa-solid fa-check me-1"></i>Update Status';
                }
                console.error('Error:', error);
                showToast('Error: ' + (error.message || 'An error occurred while updating status'), 'danger');
            });
        }
    };

    // ==================== KEYBOARD SHORTCUTS ====================

    const KeyboardShortcuts = {
        init: function() {
            document.addEventListener('keydown', (e) => {
                // Skip if user is typing in an input
                if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
                    return;
                }

                // Ctrl/Cmd + F: Focus filter
                if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
                    e.preventDefault();
                    const filterCollapse = document.getElementById('filterCollapse');
                    if (filterCollapse && !filterCollapse.classList.contains('show')) {
                        new bootstrap.Collapse(filterCollapse, { show: true });
                    }
                    const firstInput = document.querySelector('#filterForm input[type="text"]');
                    if (firstInput) firstInput.focus();
                }

                // Escape: Clear filters or close modal
                if (e.key === 'Escape') {
                    const modal = document.querySelector('.modal.show');
                    if (!modal) {
                        const filterCollapse = document.getElementById('filterCollapse');
                        if (filterCollapse && filterCollapse.classList.contains('show')) {
                            new bootstrap.Collapse(filterCollapse, { hide: true });
                        }
                    }
                }

                // R: Refresh list
                if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
                    htmx.ajax('GET', window.location.href, {
                        target: '#main-content',
                        select: '#main-content',
                        swap: 'outerHTML'
                    });
                }
            });
        }
    };

    // ==================== INITIALIZATION ====================

    function init() {
        KeyboardShortcuts.init();
    }

    // Run on DOM ready and after HTMX swaps
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Re-initialize after HTMX content swap
    document.body.addEventListener('htmx:afterSwap', function(event) {
        if (event.detail.target.id === 'main-content') {
            init();
        }
    });

    // ==================== ORDER DETAIL PANEL ====================

    const OrderDetailPanel = {
        open: function(orderId) {
            const panel = document.getElementById('orderDetailPanel');
            const content = document.getElementById('orderDetailContent');

            if (!panel) {
                console.warn('Order detail panel not found');
                return;
            }

            // Show panel with animation
            panel.classList.add('active');
            document.body.style.overflow = 'hidden'; // Prevent background scrolling

            // Load order details via HTMX
            if (typeof htmx !== 'undefined') {
                htmx.ajax('GET', '/workforce/orders/' + orderId + '/', {
                    target: '#orderDetailContent',
                    swap: 'innerHTML'
                });
            }
        },

        close: function() {
            const panel = document.getElementById('orderDetailPanel');
            if (panel) {
                panel.classList.remove('active');
                document.body.style.overflow = ''; // Restore scrolling
            }
        },

        init: function() {
            // Close panel with Escape key
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') {
                    const panel = document.getElementById('orderDetailPanel');
                    if (panel && panel.classList.contains('active')) {
                        OrderDetailPanel.close();
                    }
                }
            });

            // Close on overlay click
            const overlay = document.querySelector('.order-detail-panel-overlay');
            if (overlay) {
                overlay.addEventListener('click', function() {
                    OrderDetailPanel.close();
                });
            }
        }
    };

    // ==================== ORDER ACTIONS ====================

    const OrderActions = {
        publishToDelivery: function(orderId) {
            if (confirm('Are you sure you want to publish this order to delivery?')) {
                fetch('/workforce/orders/' + orderId + '/publish/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRFToken()
                    },
                    body: JSON.stringify({ action: 'publish' })
                })
                .then(function(response) { return response.json(); })
                .then(function(data) {
                    if (data.success) {
                        showToast('Order published successfully!', 'success');
                        // Refresh via HTMX
                        htmx.ajax('GET', window.location.href, {
                            target: '#main-content',
                            select: '#main-content',
                            swap: 'outerHTML'
                        });
                    } else {
                        showToast('Error: ' + (data.error || 'Failed to publish order'), 'danger');
                    }
                })
                .catch(function(error) {
                    console.error('Error:', error);
                    showToast('An error occurred while publishing the order', 'danger');
                });
            }
        },

        submitStatusUpdate: function(orderId) {
            var statusSelect = document.getElementById('statusSelect' + orderId);
            var status = statusSelect ? statusSelect.value : null;

            if (!status) {
                showToast('Please select a status', 'warning');
                return;
            }

            fetch('/workforce/orders/' + orderId + '/update-status/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ status: status })
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.success) {
                    // Close the modal
                    var modal = bootstrap.Modal.getInstance(document.getElementById('statusModal' + orderId));
                    if (modal) modal.hide();
                    showToast('Status updated successfully!', 'success');
                    // Refresh via HTMX
                    htmx.ajax('GET', window.location.href, {
                        target: '#main-content',
                        select: '#main-content',
                        swap: 'outerHTML'
                    });
                } else {
                    showToast('Error: ' + (data.error || 'Failed to update status'), 'danger');
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
                showToast('An error occurred while updating status', 'danger');
            });
        },

        addComment: function(event, orderId) {
            event.preventDefault();
            const commentInput = document.getElementById('commentInput' + orderId);
            const comment = commentInput ? commentInput.value.trim() : '';

            if (!comment) return;

            fetch('/workforce/orders/' + orderId + '/add-comment/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCSRFToken()
                },
                body: JSON.stringify({ comment: comment })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    commentInput.value = '';
                    showToast('Comment added successfully!', 'success');
                    // Refresh via HTMX
                    htmx.ajax('GET', window.location.href, {
                        target: '#main-content',
                        select: '#main-content',
                        swap: 'outerHTML'
                    });
                } else {
                    showToast('Error: ' + (data.error || 'Failed to add comment'), 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('An error occurred while adding comment', 'danger');
            });
        }
    };

    // Expose to global scope for inline handlers
    window.TaskActions = TaskActions;
    window.OrderDetailPanel = OrderDetailPanel;
    window.OrderActions = OrderActions;
    window.publishToDMS = TaskActions.publishToDMS.bind(TaskActions);
    window.publishToDriverApp = TaskActions.publishToDriverApp.bind(TaskActions);
    window.setStatusModalTask = TaskActions.setStatusModalTask.bind(TaskActions);
    window.submitStatusUpdate = TaskActions.submitStatusUpdate.bind(TaskActions);
    // Order detail panel functions
    window.openOrderDetailPanel = OrderDetailPanel.open.bind(OrderDetailPanel);
    window.closeOrderDetailPanel = OrderDetailPanel.close.bind(OrderDetailPanel);
    window.publishToDelivery = OrderActions.publishToDelivery.bind(OrderActions);
    window.addComment = OrderActions.addComment.bind(OrderActions);

})();

/* ---------- WF SIDEBAR ---------- */
/**
 * Workforce Dashboard Sidebar Management
 * - Active state management based on current URL
 * - Collapse state persistence in localStorage
 * - Chevron rotation animations
 */

(function() {
    'use strict';

    const STORAGE_KEY = 'wf_sidebar_state';

    /**
     * Get saved sidebar state from localStorage
     */
    function getSavedState() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            return saved ? JSON.parse(saved) : {};
        } catch (e) {
            console.warn('Failed to load sidebar state:', e);
            return {};
        }
    }

    /**
     * Save sidebar state to localStorage
     */
    function saveState(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (e) {
            console.warn('Failed to save sidebar state:', e);
        }
    }

    /**
     * Update saved state for a specific collapse
     */
    function updateCollapseState(collapseId, isOpen) {
        const state = getSavedState();
        state[collapseId] = isOpen;
        saveState(state);
    }

    /**
     * Initialize sidebar functionality
     */
    function initSidebar() {
        const currentPath = window.location.pathname;
        const savedState = getSavedState();
        const submenuLinks = document.querySelectorAll('.wf-sidebar__submenu-link');
        let activeCollapseId = null;

        // Clear all existing active states first (stale from template rendering or previous nav)
        document.querySelectorAll('.wf-sidebar__submenu-link.active, .nav-link-single.active').forEach(el => {
            el.classList.remove('active');
            el.removeAttribute('aria-current');
        });
        document.querySelectorAll('.wf-sidebar__nav .nav-item.active').forEach(el => {
            el.classList.remove('active');
        });

        // Find active link and mark it
        submenuLinks.forEach(link => {
            const linkHref = link.getAttribute('href');

            if (linkHref === currentPath) {
                link.classList.add('active');
                link.setAttribute('aria-current', 'page');

                const parentCollapse = link.closest('.collapse');
                if (parentCollapse) {
                    activeCollapseId = parentCollapse.getAttribute('id');
                }
            }
        });

        // Also check single nav links (non-collapsible)
        const singleLinks = document.querySelectorAll('.nav-link-single');
        singleLinks.forEach(link => {
            const linkHref = link.getAttribute('href');
            if (linkHref === currentPath) {
                link.classList.add('active');
                link.setAttribute('aria-current', 'page');
            }
        });

        // Initialize collapse states
        const allCollapses = document.querySelectorAll('.wf-sidebar__nav .collapse');

        allCollapses.forEach(collapse => {
            const collapseId = collapse.getAttribute('id');
            const toggle = document.querySelector(`[data-bs-target="#${collapseId}"]`);
            const chevron = toggle?.querySelector('.fa-chevron-down');

            // Only open the submenu that contains the active page
            let shouldBeOpen = (collapseId === activeCollapseId);

            // Apply state — always set both cases to override server-rendered show class
            if (shouldBeOpen) {
                collapse.classList.add('show');
                if (chevron) {
                    chevron.style.transform = 'rotate(180deg)';
                }
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'true');
                    const parentNavItem = toggle.closest('.nav-item');
                    if (parentNavItem) {
                        parentNavItem.classList.add('active');
                    }
                }
            } else {
                collapse.classList.remove('show');
                if (chevron) {
                    chevron.style.transform = 'rotate(0deg)';
                }
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'false');
                }
            }

            // Listen for collapse events to persist state
            collapse.addEventListener('show.bs.collapse', function() {
                updateCollapseState(collapseId, true);
                if (chevron) {
                    chevron.style.transition = 'transform 0.3s ease';
                    chevron.style.transform = 'rotate(180deg)';
                }
            });

            collapse.addEventListener('hide.bs.collapse', function() {
                updateCollapseState(collapseId, false);
                if (chevron) {
                    chevron.style.transition = 'transform 0.3s ease';
                    chevron.style.transform = 'rotate(0deg)';
                }
            });
        });

        // Accordion: collapse others when one opens
        const sidebarNav = document.getElementById('workforce_sidebar_nav');
        if (sidebarNav) {
            sidebarNav.addEventListener('show.bs.collapse', function(e) {
                allCollapses.forEach(function(other) {
                    if (other !== e.target && other.classList.contains('show')) {
                        const otherId = other.getAttribute('id');
                        const bsOther = bootstrap.Collapse.getOrCreateInstance(other, { toggle: false });
                        bsOther.hide();
                        updateCollapseState(otherId, false);
                    }
                });
            });
        }

        // Add keyboard navigation
        initKeyboardNav();
    }

    /**
     * Initialize keyboard navigation for sidebar
     */
    function initKeyboardNav() {
        const sidebar = document.getElementById('workforce_sidebar_main');
        if (!sidebar) return;

        const navLinks = sidebar.querySelectorAll('.nav-link, .wf-sidebar__submenu-link');

        navLinks.forEach((link, index) => {
            link.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    const nextLink = navLinks[index + 1] || navLinks[0];
                    nextLink.focus();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    const prevLink = navLinks[index - 1] || navLinks[navLinks.length - 1];
                    prevLink.focus();
                }
            });
        });
    }

    /**
     * Update notification badges via AJAX
     */
    function updateBadges() {
        fetch('/workforce/api/sidebar-counts/', {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (response.ok) return response.json();
            throw new Error('Failed to fetch badge counts');
        })
        .then(data => {
            // Update badge elements
            Object.keys(data).forEach(key => {
                const badge = document.querySelector(`[data-badge="${key}"]`);
                if (badge) {
                    const count = data[key];
                    if (count > 0) {
                        badge.textContent = count > 99 ? '99+' : count;
                        badge.classList.remove('d-none');
                    } else {
                        badge.classList.add('d-none');
                    }
                }
            });
        })
        .catch(error => {
            console.warn('Failed to update sidebar badges:', error);
        });
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSidebar);
    } else {
        initSidebar();
    }

    // Re-initialize after HTMX swaps (for SPA-like navigation)
    document.body.addEventListener('htmx:afterSwap', function(event) {
        // Only re-init if the sidebar might have changed
        if (event.detail.target.id === 'main-content') {
            // Re-check active states after navigation
            setTimeout(initSidebar, 50);
        }
    });

    // Update badges periodically (every 60 seconds)
    // Uncomment when API endpoint is available
    // setInterval(updateBadges, 60000);
    // updateBadges(); // Initial load

})();

/* ---------- PG-FILTER (Orders list filter) ---------- */
(function() {
    function el(id) { return document.getElementById(id); }
    function isoDate(d) { return d.toISOString().split('T')[0]; }

    // Read a control only if this page has it. Print Labels shares this bar but
    // carries no DL-code or status filters, and reading .value off a missing
    // element threw before the URL was ever built.
    function val(id) { var e = el(id); return e ? e.value : ''; }

    // Repeated values (a multi-select client, checkbox status filters) have to
    // survive as repeated keys — .value on a <select multiple> returns only the
    // first option, which silently dropped every client but one.
    function addMulti(p, key, id) {
        var e = el(id);
        if (!e) return;
        if (e.multiple) {
            Array.prototype.forEach.call(e.selectedOptions, function (o) {
                if (o.value) p.append(key, o.value);
            });
        } else if (e.value) {
            p.set(key, e.value);
        }
    }

    // Checkbox-dropdown filters live outside the pgf_* set but inside the same
    // form, so they are read straight off the form.
    function addCheckboxFilters(p) {
        var form = document.getElementById('filterForm');
        if (!form) return;
        form.querySelectorAll('.msf input[type="checkbox"]:checked').forEach(function (c) {
            if (c.name && c.value) p.append(c.name, c.value);
        });
    }

    function pgFilterSubmit() {
        if (!el('pgf_business')) return;
        var basePath = window.location.pathname;
        var p = new URLSearchParams();
        function add(k, v) { if (v) p.set(k, v); }
        addMulti(p, 'business', 'pgf_business');
        addCheckboxFilters(p);
        add('sort',         val('pgf_sort'));
        add('per_page',     val('pgf_per_page'));
        add('dlCode',       val('pgf_dlCode'));
        add('search',       val('pgf_search'));
        add('cStatus',      val('pgf_cStatus'));
        add('dlTaskStatus', val('pgf_dlTaskStatus'));
        add('datePreset',   val('pgf_date_preset'));
        add('dateFrom',     val('pgf_dateFrom'));
        add('dateTo',       val('pgf_dateTo'));
        var qs = p.toString();
        window.location.href = basePath + (qs ? '?' + qs : '');
    }

    function pgApplyPreset(preset) {
        var today = new Date(); today.setHours(0,0,0,0);
        var from = '', to = '';
        if (preset === 'today')          { from = to = isoDate(today); }
        else if (preset === 'yesterday') { var y=new Date(today); y.setDate(y.getDate()-1); from=to=isoDate(y); }
        // Today + yesterday. "Yesterday" is that one day alone, which is not what
        // a packing bench wants when it is working through the overnight orders.
        else if (preset === '2days')     { var d2=new Date(today); d2.setDate(d2.getDate()-1); from=isoDate(d2); to=isoDate(today); }
        else if (preset === '3days')     { var d3=new Date(today); d3.setDate(d3.getDate()-2); from=isoDate(d3); to=isoDate(today); }
        else if (preset === 'week')      { var dw=new Date(today); dw.setDate(dw.getDate()-6); from=isoDate(dw); to=isoDate(today); }
        else if (preset === 'month')     { var dm=new Date(today); dm.setDate(dm.getDate()-29); from=isoDate(dm); to=isoDate(today); }
        else if (preset === 'custom')    { from = el('pgf_from_vis') ? el('pgf_from_vis').value : ''; to = el('pgf_to_vis') ? el('pgf_to_vis').value : ''; }
        if (el('pgf_dateFrom'))    el('pgf_dateFrom').value    = from;
        if (el('pgf_dateTo'))      el('pgf_dateTo').value      = to;
        if (el('pgf_date_preset')) el('pgf_date_preset').value = preset;
        if (el('pgf_from_vis'))    el('pgf_from_vis').classList.toggle('d-none', preset !== 'custom');
        if (el('pgf_to_vis'))      el('pgf_to_vis').classList.toggle('d-none',   preset !== 'custom');
        document.querySelectorAll('.pg-filter__date-btn').forEach(function(b) {
            b.classList.toggle('active', b.dataset.preset === preset);
        });
    }

    // Use event delegation on document — works regardless of when DOM is swapped
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.pg-filter__date-btn');
        if (!btn) return;
        var preset = btn.dataset.preset;
        pgApplyPreset(preset);
        if (preset !== 'custom') pgFilterSubmit();
    });

    document.addEventListener('change', function(e) {
        var id = e.target.id;
        if (id === 'pgf_business' || id === 'pgf_cStatus' || id === 'pgf_dlTaskStatus'
            || id === 'pgf_sort' || id === 'pgf_per_page') {
            pgFilterSubmit();
        }
        if (id === 'pgf_from_vis') {
            if (el('pgf_dateFrom')) el('pgf_dateFrom').value = e.target.value;
            if (e.target.value && el('pgf_to_vis') && el('pgf_to_vis').value) pgFilterSubmit();
        }
        if (id === 'pgf_to_vis') {
            if (el('pgf_dateTo')) el('pgf_dateTo').value = e.target.value;
            if (e.target.value && el('pgf_from_vis') && el('pgf_from_vis').value) pgFilterSubmit();
        }
    });

    document.addEventListener('keypress', function(e) {
        var id = e.target.id;
        if ((id === 'pgf_dlCode' || id === 'pgf_search') && e.key === 'Enter') {
            e.preventDefault();
            pgFilterSubmit();
        }
    });
})();

/* PAGE NOTES (wfnote) moved to webpages/js/wfnote.js — loaded for every
 * dashboard from includes/main_dashboard_scripts.html, so the warehouse and
 * delivery pages get the same help button without pulling in workforce.js. */
