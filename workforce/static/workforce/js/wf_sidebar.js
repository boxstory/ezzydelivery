/**
 * Workforce Dashboard Sidebar Active State Management
 * Automatically expands submenus and highlights active links based on current URL
 */

document.addEventListener('DOMContentLoaded', function() {
    // Get current URL path
    const currentPath = window.location.pathname;

    // Find all submenu links
    const submenuLinks = document.querySelectorAll('.submenu-link');

    submenuLinks.forEach(link => {
        const linkHref = link.getAttribute('href');

        // Check if this link matches the current path
        if (linkHref === currentPath) {
            // Add active class to the link
            link.classList.add('active');

            // Find the parent collapse div
            const parentCollapse = link.closest('.collapse');

            if (parentCollapse) {
                // Show the collapse using Bootstrap's Collapse API
                const bsCollapse = new bootstrap.Collapse(parentCollapse, {
                    toggle: false
                });
                bsCollapse.show();

                // Find the toggle button for this collapse
                const collapseId = parentCollapse.getAttribute('id');
                const collapseToggle = document.querySelector(`[data-bs-target="#${collapseId}"]`);

                if (collapseToggle) {
                    // Add active class to parent nav item
                    const parentNavItem = collapseToggle.closest('.nav-item');
                    if (parentNavItem) {
                        parentNavItem.classList.add('active');
                    }

                    // Rotate chevron icon
                    const chevron = collapseToggle.querySelector('.fa-chevron-down');
                    if (chevron) {
                        chevron.style.transition = 'transform 0.3s ease';
                        chevron.style.transform = 'rotate(180deg)';
                    }
                }
            }
        }
    });

    // Add event listeners to all collapse toggles for chevron rotation
    const collapseToggles = document.querySelectorAll('[data-bs-toggle="collapse"]');

    collapseToggles.forEach(toggle => {
        const chevron = toggle.querySelector('.fa-chevron-down');

        if (chevron) {
            toggle.addEventListener('click', function() {
                // Toggle chevron rotation
                const currentRotation = chevron.style.transform;
                chevron.style.transition = 'transform 0.3s ease';
                chevron.style.transform = currentRotation === 'rotate(180deg)' ? 'rotate(0deg)' : 'rotate(180deg)';
            });

            // Listen for Bootstrap collapse events to sync chevron state
            const targetId = toggle.getAttribute('data-bs-target');
            if (targetId) {
                const targetElement = document.querySelector(targetId);

                if (targetElement) {
                    targetElement.addEventListener('show.bs.collapse', function() {
                        chevron.style.transition = 'transform 0.3s ease';
                        chevron.style.transform = 'rotate(180deg)';
                    });

                    targetElement.addEventListener('hide.bs.collapse', function() {
                        chevron.style.transition = 'transform 0.3s ease';
                        chevron.style.transform = 'rotate(0deg)';
                    });
                }
            }
        }
    });
});
