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

    const FilterManager = {
        filterLabels: {
            'dlCode': 'DL Code',
            'cCode': 'Client Code',
            'mobile': 'Mobile',
            'driverName': 'Driver',
            'cStatus': 'Client Status',
            'dmsStatus': 'DMS Status',
            'dateFrom': 'From',
            'dateTo': 'To',
            'business': 'Client'
        },

        init: function() {
            this.bindEvents();
            this.updateActiveFiltersDisplay();
        },

        bindEvents: function() {
            // Filter toggle animation
            const filterToggle = document.querySelector('.pg-filter__toggle');
            const filterCollapse = document.getElementById('filterCollapse');

            if (filterToggle && filterCollapse) {
                filterCollapse.addEventListener('show.bs.collapse', () => {
                    filterToggle.classList.add('active');
                });
                filterCollapse.addEventListener('hide.bs.collapse', () => {
                    filterToggle.classList.remove('active');
                });
            }

            // Clear filter button
            const clearFilter = document.getElementById('clearFilter');
            if (clearFilter) {
                clearFilter.addEventListener('click', () => this.clearAllFilters());
            }

            // Clear filter from empty state
            const clearFilterEmpty = document.getElementById('clearFilterEmpty');
            if (clearFilterEmpty) {
                clearFilterEmpty.addEventListener('click', () => this.clearAllFilters());
            }

            // Submit form on Enter key with debounce
            const filterInputs = document.querySelectorAll('#filterForm input[type="text"]');
            filterInputs.forEach(input => {
                input.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        htmx.trigger('#filterForm', 'submit');
                    }
                });

                // Optional: Auto-submit after typing stops (debounced)
                input.addEventListener('input', debounce(() => {
                    // Uncomment to enable auto-submit
                    // htmx.trigger('#filterForm', 'submit');
                }, 500));
            });

            // Save filter button
            const saveFilter = document.getElementById('saveFilter');
            if (saveFilter) {
                saveFilter.addEventListener('click', () => this.saveFilterPreset());
            }
        },

        getFilterValues: function() {
            return {
                dlCode: document.getElementById('dlCode')?.value || '',
                cCode: document.getElementById('cCode')?.value || '',
                mobile: document.getElementById('mobile')?.value || '',
                driverName: document.getElementById('driverName')?.value || '',
                cStatus: document.getElementById('cStatus')?.value || '',
                dmsStatus: document.getElementById('dmsStatus')?.value || '',
                dateFrom: document.getElementById('dateFrom')?.value || '',
                dateTo: document.getElementById('dateTo')?.value || '',
                business: document.getElementById('business')?.value || ''
            };
        },

        clearAllFilters: function() {
            const filters = this.getFilterValues();
            Object.keys(filters).forEach(key => {
                const element = document.getElementById(key);
                if (element) element.value = '';
            });

            // Use HTMX to navigate
            htmx.ajax('GET', window.location.pathname, {
                target: '#main-content',
                select: '#main-content',
                swap: 'outerHTML'
            });
            history.pushState({}, '', window.location.pathname);
        },

        removeFilter: function(filterKey) {
            const element = document.getElementById(filterKey);
            if (element) element.value = '';
            htmx.trigger('#filterForm', 'submit');
        },

        updateActiveFiltersDisplay: function() {
            const filters = this.getFilterValues();
            const activeFilters = Object.entries(filters).filter(([key, value]) => value !== '');
            const filterCount = activeFilters.length;

            // Update count badge
            const countDisplay = document.getElementById('activeFiltersCount');
            const countBadge = document.getElementById('filterCountBadge');
            if (countDisplay && countBadge) {
                if (filterCount > 0) {
                    countDisplay.classList.add('show');
                    countBadge.textContent = filterCount;
                } else {
                    countDisplay.classList.remove('show');
                }
            }

            // Update filter tags
            const tagsContainer = document.getElementById('filterTagsContainer');
            const tagsDisplay = document.getElementById('activeFilterTags');

            if (tagsContainer && tagsDisplay) {
                if (filterCount > 0) {
                    tagsDisplay.classList.add('show');
                    tagsContainer.innerHTML = '';

                    activeFilters.forEach(([key, value]) => {
                        let displayValue = value;
                        // For select elements, show the selected option text
                        if (['business', 'cStatus', 'dmsStatus'].includes(key)) {
                            const selectEl = document.getElementById(key);
                            if (selectEl && selectEl.selectedIndex >= 0) {
                                displayValue = selectEl.options[selectEl.selectedIndex].text;
                            }
                        }
                        const tag = document.createElement('span');
                        tag.className = 'pg-filter__tag';
                        tag.innerHTML = `
                            <strong>${this.filterLabels[key]}:</strong> ${displayValue}
                            <button type="button" class="btn-close btn-close-sm ms-1"
                                    onclick="window.FilterManager.removeFilter('${key}')"
                                    title="Remove filter"
                                    aria-label="Remove ${this.filterLabels[key]} filter"></button>
                        `;
                        tagsContainer.appendChild(tag);
                    });
                } else {
                    tagsDisplay.classList.remove('show');
                }
            }
        },

        quickFilter: function(type) {
            // Clear all fields first
            const filters = this.getFilterValues();
            Object.keys(filters).forEach(key => {
                const element = document.getElementById(key);
                if (element) element.value = '';
            });

            switch(type) {
                case 'today':
                    const today = new Date().toISOString().split('T')[0];
                    const dateFrom = document.getElementById('dateFrom');
                    const dateTo = document.getElementById('dateTo');
                    if (dateFrom) dateFrom.value = today;
                    if (dateTo) dateTo.value = today;
                    break;
                case 'pending':
                    const cStatus = document.getElementById('cStatus');
                    if (cStatus) cStatus.value = 'for_review';
                    break;
                case 'in_transit':
                    const dmsStatus = document.getElementById('dmsStatus');
                    if (dmsStatus) dmsStatus.value = '4';
                    break;
                case 'week':
                    const weekStart = new Date();
                    weekStart.setDate(weekStart.getDate() - 7);
                    const dateFromWeek = document.getElementById('dateFrom');
                    const dateToWeek = document.getElementById('dateTo');
                    if (dateFromWeek) dateFromWeek.value = weekStart.toISOString().split('T')[0];
                    if (dateToWeek) dateToWeek.value = new Date().toISOString().split('T')[0];
                    break;
                case 'month':
                    const monthStart = new Date();
                    monthStart.setDate(1);
                    const dateFromMonth = document.getElementById('dateFrom');
                    const dateToMonth = document.getElementById('dateTo');
                    if (dateFromMonth) dateFromMonth.value = monthStart.toISOString().split('T')[0];
                    if (dateToMonth) dateToMonth.value = new Date().toISOString().split('T')[0];
                    break;
            }

            htmx.trigger('#filterForm', 'submit');
        },

        saveFilterPreset: function() {
            const filterName = prompt('Enter a name for this filter preset:');
            if (filterName) {
                const filters = {
                    name: filterName,
                    ...this.getFilterValues(),
                    createdAt: new Date().toISOString()
                };

                // Save to localStorage
                let savedFilters = JSON.parse(localStorage.getItem('taskFilters') || '[]');
                savedFilters.push(filters);
                localStorage.setItem('taskFilters', JSON.stringify(savedFilters));

                showToast('Filter preset saved successfully!', 'success');
            }
        },

        loadFilterPresets: function() {
            return JSON.parse(localStorage.getItem('taskFilters') || '[]');
        },

        applyFilterPreset: function(preset) {
            Object.keys(preset).forEach(key => {
                if (key !== 'name' && key !== 'createdAt') {
                    const element = document.getElementById(key);
                    if (element) element.value = preset[key];
                }
            });
            htmx.trigger('#filterForm', 'submit');
        },

        deleteFilterPreset: function(index) {
            let savedFilters = this.loadFilterPresets();
            savedFilters.splice(index, 1);
            localStorage.setItem('taskFilters', JSON.stringify(savedFilters));
            showToast('Filter preset deleted', 'info');
        }
    };

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

            // Pre-select current status
            var selectEl = document.getElementById('statusSelect');
            selectEl.value = currentStatus || '';

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
                showToast('An error occurred while updating status', 'danger');
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
        FilterManager.init();
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
    window.FilterManager = FilterManager;
    window.TaskActions = TaskActions;
    window.OrderDetailPanel = OrderDetailPanel;
    window.OrderActions = OrderActions;
    window.publishToDMS = TaskActions.publishToDMS.bind(TaskActions);
    window.publishToDriverApp = TaskActions.publishToDriverApp.bind(TaskActions);
    window.setStatusModalTask = TaskActions.setStatusModalTask.bind(TaskActions);
    window.submitStatusUpdate = TaskActions.submitStatusUpdate.bind(TaskActions);
    window.quickFilter = FilterManager.quickFilter.bind(FilterManager);
    window.removeFilter = FilterManager.removeFilter.bind(FilterManager);
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

            // Determine if this collapse should be open
            let shouldBeOpen = false;

            // Priority 1: Contains active page
            if (collapseId === activeCollapseId) {
                shouldBeOpen = true;
            }
            // Priority 2: Saved state (if not the active page's section)
            else if (savedState[collapseId] !== undefined) {
                shouldBeOpen = savedState[collapseId];
            }

            // Apply state
            if (shouldBeOpen) {
                collapse.classList.add('show');
                if (chevron) {
                    chevron.style.transform = 'rotate(180deg)';
                }
                if (toggle) {
                    toggle.setAttribute('aria-expanded', 'true');
                    // Only add active class to parent nav-item if this collapse contains the active page
                    if (collapseId === activeCollapseId) {
                        const parentNavItem = toggle.closest('.nav-item');
                        if (parentNavItem) {
                            parentNavItem.classList.add('active');
                        }
                    }
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
