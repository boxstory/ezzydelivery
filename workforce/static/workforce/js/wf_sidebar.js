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
        const submenuLinks = document.querySelectorAll('.submenu-link');
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
        const allCollapses = document.querySelectorAll('.sidebar-nav .collapse');

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
                    const parentNavItem = toggle.closest('.nav-item');
                    if (parentNavItem) {
                        parentNavItem.classList.add('active');
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

        const navLinks = sidebar.querySelectorAll('.nav-link, .submenu-link');

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
