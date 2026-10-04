/* Purpose: The driver app's location lock — a full-screen "turn on location" screen over every page while the phone will not give a fix.
 * Used by: fleet/templates/fleet/parts/gps_gate.html (the markup); loaded right after ezzy-gps.js by fleet/pwa_base.html and templates/fleet_dashboard_base.html, approved drivers only.
 * Notes:   Never takes a fix of its own — EzzyGPS stays the one GPS consumer and this only listens to its events. Battery: no timer; a re-check costs one fix per tap or return to the app.
 */
(function() {
    var gate = document.getElementById('fleet_gpsgate_overlay');
    if (!gate || !window.EzzyGPS) return;

    var reasonEl = document.getElementById('fleet_gpsgate_text_reason');
    var statusEl = document.getElementById('fleet_gpsgate_text_status');
    var retryBtn = document.getElementById('fleet_gpsgate_btn_retry');

    /* What the driver is told, by cause. The steps underneath cover every
     * cause at once on purpose: phones misreport which switch is off — an
     * Android phone with Location off can answer "permission denied". */
    var REASONS = {
        ask: 'EzzyDelivery needs your location while you work. Tap the button and choose Allow.',
        denied: 'Location is blocked for EzzyDelivery on this phone.',
        off: 'Your phone\'s location (GPS) is turned off.',
        unsupported: 'This browser cannot share your location. Open EzzyDelivery in Chrome.'
    };

    /* One "position unavailable" is not proof the GPS is off — a driver in a
     * basement car park or a lift gets one too, and locking the screen on them
     * mid-delivery would be worse than the gap. Unavailable only locks when
     * nothing has come back for this long. A refusal locks at once. */
    var UNAVAILABLE_GRACE_MS = 90000;

    var lastFixAt = 0;
    var permission = null;   // 'granted' | 'denied' | 'prompt', or null where the browser will not say
    var checking = false;    // a re-check the driver asked for is in flight
    var inerted = [];

    var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    document.getElementById('fleet_gpsgate_list_ios').hidden = !isIOS;
    document.getElementById('fleet_gpsgate_list_android').hidden = isIOS;

    /* Everything else on the page stops taking taps and focus while the lock
     * is up. Only what this switched off is switched back on. */
    function setInert(on) {
        if (on) {
            Array.prototype.forEach.call(document.body.children, function(el) {
                if (el !== gate && !el.inert) { el.inert = true; inerted.push(el); }
            });
        } else {
            inerted.forEach(function(el) { el.inert = false; });
            inerted = [];
        }
    }

    function lock(reason) {
        reasonEl.textContent = REASONS[reason] || REASONS.off;
        if (checking) {
            checking = false;
            statusEl.textContent = 'Location is still off. Follow the steps above, then try again.';
        }
        if (!gate.hidden) return;
        gate.hidden = false;
        setInert(true);
        document.documentElement.classList.add('fleet-gpsgate-locked');
        console.log('[EzzyGPS] Location lock on —', reason);
    }

    function unlock() {
        checking = false;
        statusEl.textContent = '';
        if (gate.hidden) return;
        gate.hidden = true;
        setInert(false);
        document.documentElement.classList.remove('fleet-gpsgate-locked');
        console.log('[EzzyGPS] Location lock off');
    }

    function onGpsError(err) {
        if (!err) return;
        if (err.code === 1) {
            // A refusal while the site permission still reads "granted" is the
            // phone's own Location switch (or Chrome's app permission) saying no.
            lock(permission === 'granted' ? 'off' : (permission === 'prompt' ? 'ask' : 'denied'));
        } else if (err.code === 2) {
            if (Date.now() - lastFixAt > UNAVAILABLE_GRACE_MS) lock('off');
        } else if (checking) {
            // A timeout is weak signal, not a switch that is off.
            checking = false;
            statusEl.textContent = 'Still looking for your position. Move near a window or outside, then try again.';
        }
    }

    document.addEventListener('ezzy:gps', function() {
        lastFixAt = Date.now();
        unlock();
    });

    document.addEventListener('ezzy:gps-error', function(e) {
        onGpsError(e.detail);
    });

    retryBtn.addEventListener('click', function() {
        checking = true;
        statusEl.textContent = 'Checking your location…';
        window.EzzyGPS.recheck();
    });

    /* Back from the phone's settings. A running EzzyGPS already takes a fix on
     * its way back to the foreground; one stopped by a refusal needs a restart. */
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible' && !gate.hidden && !window.EzzyGPS.isRunning()) {
            window.EzzyGPS.recheck();
        }
    });

    if (navigator.permissions && navigator.permissions.query) {
        navigator.permissions.query({ name: 'geolocation' }).then(function(status) {
            permission = status.state;
            if (permission === 'denied') lock('denied');
            status.onchange = function() {
                permission = status.state;
                if (permission === 'denied') {
                    lock('denied');
                } else if (!gate.hidden) {
                    // Allowed from the browser's settings while the lock was up.
                    window.EzzyGPS.recheck();
                }
            };
        }).catch(function() { /* not answerable here (older Safari) — the fix errors still drive the lock */ });
    }

    if (!('geolocation' in navigator)) {
        lock('unsupported');
        return;
    }

    /* EzzyGPS starts while it loads, so its first answer can land while this
     * file is still downloading. Catch up on anything already said. */
    var early = window.EzzyGPS.getLastError();
    var pos = window.EzzyGPS.getPosition();
    if (pos) lastFixAt = Date.now();
    if (early && (!pos || pos.fixedAt < early.at)) onGpsError(early);
})();
