/**
 * Session Timeout Monitor
 * Automatically logs out users after 1 hour of inactivity
 * Shows warning modal 5 minutes before logout
 */

(function() {
    'use strict';

    // Configuration
    var SESSION_TIMEOUT = window.SESSION_TIMEOUT || 3600; // 1 hour in seconds
    var WARNING_TIME = window.SESSION_WARNING_TIME || 300; // 5 minutes before timeout
    var CHECK_INTERVAL = 10000; // Check every 10 seconds

    var warningShown = false;
    var countdownInterval = null;
    var timeRemaining = SESSION_TIMEOUT;

    // Create warning modal HTML
    function createWarningModal() {
        var modalHTML = '<div id="sessionWarningModal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 10000; justify-content: center; align-items: center;"><div style="background: white; padding: 2rem; border-radius: 12px; max-width: 500px; box-shadow: 0 10px 40px rgba(0,0,0,0.3); text-align: center;"><div style="font-size: 3rem; color: #ff6b6b; margin-bottom: 1rem;"><i class="fas fa-exclamation-triangle"></i></div><h3 style="margin-bottom: 1rem; color: #333;">Session Expiring Soon!</h3><p style="margin-bottom: 1.5rem; color: #666;">Your session will expire in <strong id="sessionCountdown" style="color: #ff6b6b; font-size: 1.5rem;">5:00</strong> due to inactivity.</p><p style="margin-bottom: 2rem; color: #666;">Click "Stay Logged In" to continue working, or you will be automatically logged out.</p><div style="display: flex; gap: 1rem; justify-content: center;"><button id="stayLoggedInBtn" class="btn btn-primary" style="padding: 0.75rem 2rem;"><i class="fas fa-check-circle me-2"></i>Stay Logged In</button><button id="logoutNowBtn" class="btn btn-outline-secondary" style="padding: 0.75rem 2rem;"><i class="fas fa-sign-out-alt me-2"></i>Logout Now</button></div></div></div>';

        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Event listeners
        document.getElementById('stayLoggedInBtn').addEventListener('click', function() {
            // Make a request to refresh session
            fetch(window.location.href, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            }).then(function() {
                hideWarningModal();
                resetTimer();
            });
        });

        document.getElementById('logoutNowBtn').addEventListener('click', function() {
            window.location.href = '/accounts/logout/';
        });
    }

    // Show warning modal
    function showWarningModal() {
    var modal = document.getElementById('sessionWarningModal');
        if (modal) {
            modal.style.display = 'flex';
            warningShown = true;
            startCountdown();
        }
    }

    // Hide warning modal
    function hideWarningModal() {
    var modal = document.getElementById('sessionWarningModal');
        if (modal) {
            modal.style.display = 'none';
            warningShown = false;
            if (countdownInterval) {
                clearInterval(countdownInterval);
                countdownInterval = null;
            }
        }
    }

    // Start countdown in modal
    function startCountdown() {
        var secondsLeft = WARNING_TIME;
        var countdownElement = document.getElementById('sessionCountdown');

        if (countdownInterval) {
            clearInterval(countdownInterval);
        }

        countdownInterval = setInterval(function() {
            secondsLeft--;

            if (secondsLeft <= 0) {
                clearInterval(countdownInterval);
                // Redirect to logout
                window.location.href = '/accounts/logout/';
                return;
            }

            // Update countdown display
            var minutes = Math.floor(secondsLeft / 60);
            var seconds = secondsLeft % 60;
            if (countdownElement) {
                countdownElement.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            }
        }, 1000);
    }

    // Reset timer
    function resetTimer() {
        timeRemaining = SESSION_TIMEOUT;
        warningShown = false;
    }

    // Update activity on user interaction
    function updateActivity() {
        if (warningShown) {
            // If warning is shown and user is active, hide it and reset
            hideWarningModal();
        }
        resetTimer();
    }

    // Monitor session timeout
    function monitorSession() {
        setInterval(() => {
            timeRemaining -= CHECK_INTERVAL / 1000;

            // Show warning when 5 minutes remain
            if (timeRemaining <= WARNING_TIME && !warningShown) {
                showWarningModal();
            }

            // Auto logout when time is up
            if (timeRemaining <= 0) {
                window.location.href = '/accounts/logout/';
            }
        }, CHECK_INTERVAL);
    }

    // Initialize
    function init() {
        // Only run on dashboard pages for authenticated users
        if (!window.location.pathname.includes('dashboard') &&
            !window.location.pathname.includes('workforce') &&
            !window.location.pathname.includes('fleet') &&
            !window.location.pathname.includes('business')) {
            return;
        }

        // Create warning modal
        createWarningModal();

        // Start monitoring
        monitorSession();

        // Track user activity to reset timer
        var activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];

        // Throttle activity updates (max once per 30 seconds)
        var lastActivityUpdate = Date.now();
        var throttleDelay = 30000; // 30 seconds

        activityEvents.forEach(function(event) {
            document.addEventListener(event, function() {
                var now = Date.now();
                if (now - lastActivityUpdate > throttleDelay) {
                    updateActivity();
                    lastActivityUpdate = now;
                }
            }, true);
        });
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
