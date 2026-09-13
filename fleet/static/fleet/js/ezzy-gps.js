/* Purpose: EzzyGPS — the driver's single GPS consumer: duty-cycled fixes, the offline queue,
 *          and the handoff record for every trip out to another app (Waze, Maps, WhatsApp, a call).
 * Used by: fleet/templates/fleet/pwa_base.html and templates/fleet_dashboard_base.html, both of
 *          which set window.EZZY_GPS_CONFIG before loading this and pull in ezzy-gps-queue.js first.
 * Notes:   There must be exactly one GPS consumer on a device — other code listens for the
 *          `ezzy:gps` event instead of starting a second watch. Editing this file means bumping
 *          its ?v= in both bases. onDuty comes from core.context_processors.driver_pending_tasks.
 */
(function() {
    /* Power profiles.
     *
     * The GPS radio, not the network, is what empties a driver's battery, so
     * high accuracy is spent only where it buys something: while a task is
     * actually in hand. Idle drivers are located from cell and wifi, which
     * costs almost nothing, and a driver who has stopped moving is polled
     * even less often. Fixes are taken on a duty cycle rather than through a
     * permanent watch, so the radio sleeps between them. */
    var PROFILES = {
        idle:   { high: false, sendMs: 180000, maxAge: 120000, timeout: 20000, label: 'Idle' },
        active: { high: true,  sendMs: 30000,  maxAge: 10000,  timeout: 15000, label: 'On task' },
        parked: { high: false, sendMs: 150000, maxAge: 120000, timeout: 20000, label: 'Parked' }
    };
    var STATIONARY_METRES = 40;      // movement below this doesn't count as travel
    var STATIONARY_AFTER_MS = 300000; // 5 min still on an active task → parked profile
    var MAX_ACCURACY = 100;          // above this a fix is flagged, never discarded

    // Whether the driver has a task in flight, decided server-side. This is
    // what keeps tracking sharp across the whole PWA rather than only on
    // the navigation screen, without the client having to guess.
    var onDuty = !!(window.EZZY_GPS_CONFIG || {}).onDuty;
    var mode = 'poll';        // poll = duty-cycled fixes; live = continuous watch (nav page)
    var profileName = 'idle';
    var watchId = null;
    var pollTimer = null;
    var running = false;
    var currentPos = null;
    var lastSentKey = null;   // fix+position already delivered; re-sending it stores a duplicate
    var lastMovedAt = 0;
    var anchorPos = null;     // position the stationary test measures against
    var activeTaskId = null;
    var gpsState = 'grey';    // grey|green|red|yellow
    var wakeLock = null;
    var wakeLockWanted = false;
    // Last positioning failure, kept for the Settings diagnostics panel. A
    // driver reporting "location denied" cannot read a console, so the raw
    // code/message is held here for the panel to show back to them.
    var lastError = null;

    function profile() { return PROFILES[profileName]; }

    function getCsrf() {
        return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    function metresBetween(a, b) {
        var R = 6371000, toRad = Math.PI / 180;
        var dLat = (b.lat - a.lat) * toRad;
        var dLng = (b.lng - a.lng) * toRad;
        var h = Math.sin(dLat / 2) * Math.sin(dLat / 2)
              + Math.cos(a.lat * toRad) * Math.cos(b.lat * toRad)
              * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return 2 * R * Math.asin(Math.sqrt(h));
    }

    function setGpsState(state, title) {
        if (state === gpsState) return;
        gpsState = state;
        var dot = document.getElementById('fleet_gps_status_dot');
        if (dot) {
            dot.className = 'fleet-gps-dot fleet-gps-dot--' + state;
            dot.title = 'GPS: ' + (title || state);
        }
        document.dispatchEvent(new CustomEvent('ezzy:gps-status', { detail: { state: state, title: title } }));
        console.log('[EzzyGPS] Status:', state, '-', title);
    }

    function buildPing() {
        if (!currentPos) return null;
        return {
            latitude: currentPos.lat,
            longitude: currentPos.lng,
            accuracy: currentPos.accuracy,
            speed: currentPos.speed,
            heading: currentPos.heading,
            fixed_at: new Date(currentPos.fixedAt).toISOString(),
            task_id: activeTaskId || null
        };
    }

    /* Deliver a ping, or park it in the offline queue.
     *
     * Anything that doesn't reach the server is kept rather than lost, and a
     * Background Sync is requested so the browser can replay it even after
     * the driver has closed the app. */
    function sendLocation(useKeepalive) {
        var ping = buildPing();
        if (!ping) return Promise.resolve(false);

        /* A fix already sent is never sent twice. getCurrentPosition hands
         * back a cached position while it is younger than maximumAge, and
         * this function is reached off-schedule too — the duty cycle
         * restarts itself on a profile change, and the error path
         * deliberately re-reports the last known fix. Each of those was
         * storing another row for a position the server already had.
         *
         * The scheduled poll is unaffected: every profile asks for a fix
         * fresher than its own send interval, so a normal cycle always
         * produces a new fixed_at — including a parked driver, whose trail
         * keeps its heartbeat. Costs no battery; saves a request. */
        var key = ping.fixed_at + '|' + ping.latitude + '|' + ping.longitude;
        if (key === lastSentKey) {
            console.log('[EzzyGPS] Same fix as last send — skipped');
            return Promise.resolve(false);
        }
        lastSentKey = key;

        return fetch('/api/driver/location/', {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: !!useKeepalive,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrf()
            },
            body: JSON.stringify(ping)
        }).then(function(r) {
            if (r.ok) {
                console.log('[EzzyGPS] Ping OK —', ping.latitude.toFixed(5), ping.longitude.toFixed(5),
                            Math.round(ping.accuracy || 0) + 'm', '[' + profileName + ']');
                return true;
            }
            console.warn('[EzzyGPS] Ping rejected:', r.status);
            if (r.status >= 500) queuePing(ping);
            return false;
        }).catch(function(err) {
            console.warn('[EzzyGPS] Ping failed, queued:', err && err.message);
            queuePing(ping);
            return false;
        });
    }

    function queuePing(ping) {
        if (!self.EzzyGPSQueue) return;
        EzzyGPSQueue.enqueue(Object.assign({}, ping, { csrf: getCsrf() })).then(requestSync).catch(function() {});
    }

    function requestSync() {
        if (!('serviceWorker' in navigator) || !self.EzzyGPSQueue) return;
        navigator.serviceWorker.ready.then(function(reg) {
            if (reg.sync) return reg.sync.register(EzzyGPSQueue.SYNC_TAG);
        }).catch(function() { /* Background Sync unsupported — flush on next foreground */ });
    }

    function flushQueue() {
        if (!self.EzzyGPSQueue || !navigator.onLine) return;
        EzzyGPSQueue.flush(getCsrf()).then(function(sent) {
            if (sent) console.log('[EzzyGPS] Replayed', sent, 'queued ping(s)');
        });
    }

    /* Drop to the parked profile once the driver has genuinely stopped, and
     * come straight back out on the first real movement.
     *
     * onDuty is what carries the active profile across the rest of the PWA:
     * a driver checking their COD screen mid-delivery is still mid-delivery,
     * and dropping them to the idle profile there is exactly how the trail
     * used to go coarse between task pages. */
    function reprofile() {
        if (!activeTaskId && !onDuty) {
            applyProfile('idle');
            return;
        }
        var stillFor = Date.now() - lastMovedAt;
        applyProfile(stillFor > STATIONARY_AFTER_MS ? 'parked' : 'active');
    }

    function applyProfile(name) {
        if (name === profileName) return;
        profileName = name;
        console.log('[EzzyGPS] Profile →', name);
        if (running) { stopSensors(); startSensors(); }
    }

    function onPosition(pos) {
        var c = pos.coords;
        var fix = {
            lat: c.latitude,
            lng: c.longitude,
            accuracy: c.accuracy,
            speed: c.speed,
            heading: c.heading,
            fixedAt: pos.timestamp || Date.now()
        };

        // A coarse fix is still worth reporting — a rough position beats a
        // hole in the trail — it is only marked as such.
        if (c.accuracy > MAX_ACCURACY) {
            setGpsState('yellow', 'Approximate (' + Math.round(c.accuracy) + 'm)');
        } else {
            setGpsState('green', 'Active (' + Math.round(c.accuracy) + 'm)');
        }

        var moved = !anchorPos || metresBetween(anchorPos, fix) > STATIONARY_METRES;
        if (moved) {
            anchorPos = fix;
            lastMovedAt = Date.now();
        }
        currentPos = fix;
        document.dispatchEvent(new CustomEvent('ezzy:gps', { detail: fix }));
        reprofile();
    }

    function onError(err) {
        console.warn('[EzzyGPS] Error:', err.code, err.message);
        lastError = { code: err.code, message: err.message || '', at: Date.now() };
        if (err.code === 1) { // PERMISSION_DENIED
            setGpsState('red', 'Permission denied');
            stop();
            if (typeof showToast === 'function') {
                showToast('Location permission denied. GPS tracking disabled.', 'warning', 5000);
            }
        } else if (err.code === 2) { // POSITION_UNAVAILABLE
            setGpsState('red', 'Position unavailable');
        } else if (err.code === 3) { // TIMEOUT
            setGpsState('yellow', 'GPS timeout — retrying');
        }
    }

    function geoOptions() {
        var p = profile();
        return { enableHighAccuracy: p.high, maximumAge: p.maxAge, timeout: p.timeout };
    }

    /* One duty cycle: wake the radio, take a fix, report it, sleep again. */
    function tick() {
        navigator.geolocation.getCurrentPosition(function(pos) {
            onPosition(pos);
            sendLocation();
        }, function(err) {
            onError(err);
            if (currentPos) sendLocation();  // report the last known rather than nothing
        }, geoOptions());
        pollTimer = setTimeout(tick, profile().sendMs);
    }

    function startSensors() {
        if (mode === 'live') {
            watchId = navigator.geolocation.watchPosition(onPosition, onError, geoOptions());
            pollTimer = setInterval(function() { sendLocation(); }, profile().sendMs);
        } else {
            tick();
        }
    }

    function stopSensors() {
        if (watchId !== null) { navigator.geolocation.clearWatch(watchId); watchId = null; }
        if (pollTimer) { clearTimeout(pollTimer); clearInterval(pollTimer); pollTimer = null; }
    }

    function stop() {
        if (!running) return;
        running = false;
        stopSensors();
        releaseWakeLock();
        setGpsState('grey', 'Stopped');
    }

    /* ---- Handoff to another app ----
     *
     * Tapping Waze, Google Maps, a customer's WhatsApp or a phone number
     * puts another app in front, and a backgrounded browser cannot take a
     * fix at all — the trail stops dead until the driver comes back. None
     * of that is recoverable here. What is recoverable is the *reason*: the
     * server is told the moment the driver leaves and the moment they
     * return, so staff see "In Waze since 14:32" rather than a marker that
     * looks like a dead phone.
     *
     * The pending handoff is kept in localStorage, not a variable, because
     * the driver may come back to a cold page: Android is free to discard
     * the PWA while Waze is in front, and the return then arrives as a
     * fresh load with no memory of having left.
     *
     * Battery: one request out, one fix and one request back, per trip to
     * the nav app. No watch, no wake lock, nothing left running. */
    var NAV_KEY = 'ezzy_nav_handoff';

    function navPending() {
        try { return JSON.parse(localStorage.getItem(NAV_KEY) || 'null'); }
        catch (e) { return null; }
    }

    function navRemember(row) {
        try {
            if (row) { localStorage.setItem(NAV_KEY, JSON.stringify(row)); }
            else { localStorage.removeItem(NAV_KEY); }
        } catch (e) { /* private mode — the server's ping-based close still covers it */ }
    }

    function navPost(body) {
        return fetch('/api/driver/nav-handoff/', {
            method: 'POST',
            credentials: 'same-origin',
            keepalive: true,   // the page is about to lose focus
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body: JSON.stringify(body)
        }).catch(function(err) {
            console.warn('[EzzyGPS] Nav handoff failed:', err && err.message);
            return null;
        });
    }

    function navOpen(provider, opts) {
        opts = opts || {};
        navRemember({ provider: provider, at: Date.now(), hid: false });
        console.log('[EzzyGPS] Nav handoff →', provider);
        return navPost({
            event: 'open',
            provider: provider,
            task_id: opts.taskId || null,
            pickup_task_id: opts.pickupTaskId || null,
            dest_lat: opts.lat || null,
            dest_lng: opts.lng || null
        });
    }

    /* The page has just lost the foreground.
     *
     * If a link was tapped, that handoff already explains the gap and only
     * needs to know the app really did go away. If nothing was tapped, this IS
     * the gap: the screen locked, the home button was pressed, something was
     * opened from the notification shade. Those are most of what actually puts
     * holes in the trail, and no button can ever see them — the trail used to
     * simply stop with no account of why.
     *
     * One small request, on a transition that already sends a keepalive ping.
     * A spell too short to have cost a fix is discarded server-side rather than
     * stored, so a glance at a notification leaves nothing behind. */
    function navBackground() {
        var pending = navPending();
        if (pending) {
            pending.hid = true;      // the link handoff really did leave
            navRemember(pending);
            return;
        }
        navRemember({ provider: 'background', at: Date.now(), hid: true, auto: true });
        navPost({ event: 'background' });
    }

    function navReturn() {
        var pending = navPending();
        if (!pending) return;
        navRemember(null);
        /* A fresh fix before the return is filed: it is the first honest
         * position since the driver left, and it is what the server closes
         * the gap with. The explicit return is the belt to that brace —
         * whichever lands first closes the handoff, and closing is
         * idempotent, so a failed fix still ends the gap. */
        EzzyGPS.stamp().then(function() {
            navPost({ event: 'return', left_foreground: !!pending.hid });
        });
    }

    /* Which app a link hands the driver to.
     *
     * The URL is the signal, not the button. These links are built in a
     * dozen templates — Navigate, Maps, Pin, the pickup and hub tiles, Call,
     * WhatsApp — and a list of selectors would be out of date the next time
     * one is added. Anything leaving this origin takes the foreground, so
     * anything leaving this origin is a handoff. */
    var NAV_MATCHERS = [
        ['phone',    /^tel:/i],
        ['whatsapp', /^whatsapp:|^https?:\/\/(wa\.me|[\w.-]*whatsapp\.com)\//i],
        ['waze',     /^waze:|^https?:\/\/([\w-]+\.)?waze\.com\//i],
        ['google',   /^comgooglemaps:|^https?:\/\/(maps\.app\.goo\.gl|maps\.google\.[\w.]+|([\w-]+\.)?google\.[\w.]+\/maps)/i],
        ['other',    /^(geo|maps|sms|mailto):/i]
    ];

    function navProviderFor(url) {
        if (!url) return null;
        for (var i = 0; i < NAV_MATCHERS.length; i++) {
            if (NAV_MATCHERS[i][1].test(url)) return NAV_MATCHERS[i][0];
        }
        // Any other absolute link still puts a browser tab or an app in
        // front of the driver; only our own pages keep the GPS running.
        if (/^https?:\/\//i.test(url)) {
            try {
                if (new URL(url, location.href).host !== location.host) return 'other';
            } catch (e) { /* unparseable — not worth a handoff */ }
        }
        return null;
    }

    /* Where the link was sending them, read out of the URL itself, so the
     * live map can draw the leg without every template having to say. */
    function navDestFrom(url) {
        if (!url) return null;
        var m = String(url).match(
            /[?&](?:destination|q|query|ll|daddr)=(-?\d+\.\d+)(?:,|%2C)(-?\d+\.\d+)/i);
        if (!m) m = String(url).match(/^geo:(-?\d+\.\d+),(-?\d+\.\d+)/i);
        return m ? { lat: m[1], lng: m[2] } : null;
    }

    function navOpenUrl(url, opts) {
        var provider = navProviderFor(url);
        if (!provider) return null;
        var dest = navDestFrom(url) || {};
        opts = opts || {};
        return navOpen(provider, {
            taskId: opts.taskId,
            pickupTaskId: opts.pickupTaskId,
            lat: opts.lat || dest.lat,
            lng: opts.lng || dest.lng
        });
    }

    /* Capture phase, because several of these links stop propagation to
     * keep their card from opening. data-nav-* is optional: it only adds
     * what the URL cannot say, which is the task the driver is on. */
    document.addEventListener('click', function(e) {
        var el = e.target && e.target.closest
            ? e.target.closest('a[href], [data-nav-app]') : null;
        if (!el) return;
        var href = el.getAttribute('href') || '';
        if (href === '#') return;  // link not wired to a destination
        var provider = el.getAttribute('data-nav-app') || navProviderFor(href);
        if (!provider) return;
        var dest = navDestFrom(href) || {};
        navOpen(provider, {
            taskId: el.getAttribute('data-nav-task'),
            pickupTaskId: el.getAttribute('data-nav-pickup'),
            lat: el.getAttribute('data-nav-lat') || dest.lat,
            lng: el.getAttribute('data-nav-lng') || dest.lng
        });
    }, true);

    // ---- Screen wake lock (opt-in, off by default) ----
    // Keeping the screen alive is the single biggest battery cost on the
    // device, so it is never taken automatically — only when a driver has
    // asked for it on the navigation screen.
    function acquireWakeLock() {
        if (!wakeLockWanted || wakeLock || !('wakeLock' in navigator)) return;
        if (document.visibilityState !== 'visible') return;
        navigator.wakeLock.request('screen').then(function(lock) {
            wakeLock = lock;
            lock.addEventListener('release', function() { wakeLock = null; });
        }).catch(function(err) { console.warn('[EzzyGPS] Wake lock refused:', err && err.message); });
    }

    function releaseWakeLock() {
        if (wakeLock) { wakeLock.release().catch(function() {}); wakeLock = null; }
    }

    window.EzzyGPS = {
        /* taskId names the specific job to stamp on each ping. Being on a
         * job at all — which is what unlocks the high-accuracy profile —
         * comes from the server via onDuty, so it holds on every page. */
        start: function(taskId) {
            if (taskId) {
                activeTaskId = taskId;
                lastMovedAt = Date.now();
            }
            if (running) { reprofile(); return; }
            if (!('geolocation' in navigator)) {
                setGpsState('grey', 'Not supported');
                if (typeof showToast === 'function') {
                    showToast('GPS not supported on this device.', 'warning');
                }
                return;
            }
            running = true;
            profileName = (activeTaskId || onDuty) ? 'active' : 'idle';
            if (profileName === 'active') lastMovedAt = Date.now();
            startSensors();
            flushQueue();
            console.log('[EzzyGPS] Started —', mode, 'mode,', profileName, 'profile');
        },
        stop: function() {
            activeTaskId = null;
            stop();
        },
        /* Continuous fixes for the turn-by-turn map. Costs more battery, so
         * only the navigation screen asks for it. */
        setLiveMode: function(on) {
            var next = on ? 'live' : 'poll';
            if (next === mode) return;
            mode = next;
            if (running) { stopSensors(); startSensors(); }
        },
        /* For the call sites that navigate from script rather than a link. */
        navHandoff: {
            open: navOpen,
            openUrl: navOpenUrl,   // for window.open call sites
            back: navReturn,
            pending: navPending
        },
        wakeLock: {
            enable: function() { wakeLockWanted = true; acquireWakeLock(); },
            disable: function() { wakeLockWanted = false; releaseWakeLock(); },
            isEnabled: function() { return wakeLockWanted; },
            isSupported: function() { return 'wakeLock' in navigator; }
        },
        /* Put a fix on the record BEFORE a status change is sent.
         *
         * The server stamps every status change with the driver's most
         * recent stored fix, so the quality of that evidence is decided
         * here, not there: with only the duty cycle running, the pin on
         * "Delivered" is whatever ping happened to land last — typically
         * seconds old, sometimes minutes, and on a phone that had been
         * asleep, days. Taking a fix at the tap makes the pin mean what
         * the timeline says it means.
         *
         * Always resolves, and never holds the action for more than
         * WAIT_MS: a driver standing at a door must not wait on GPS. A
         * failed or slow fix just leaves the previous behaviour in place.
         *
         * Battery: one extra fix per status change — a handful per job,
         * against a duty cycle already taking one every 30s while on task.
         * No wake lock, no watch, nothing left running afterwards. */
        stamp: function() {
            var WAIT_MS = 6000;
            if (!('geolocation' in navigator)) return Promise.resolve(false);
            return new Promise(function(resolve) {
                var settled = false;
                function finish(v) { if (!settled) { settled = true; resolve(v); } }
                setTimeout(function() { finish(false); }, WAIT_MS);
                navigator.geolocation.getCurrentPosition(function(pos) {
                    onPosition(pos);
                    sendLocation().then(finish).catch(function() { finish(false); });
                }, function(err) {
                    console.warn('[EzzyGPS] Stamp failed:', err && err.message);
                    // Nothing fresh — push the last known so the change is
                    // still witnessed by something rather than nothing.
                    sendLocation().then(finish).catch(function() { finish(false); });
                }, { enableHighAccuracy: true, maximumAge: 5000, timeout: WAIT_MS });
            });
        },
        getPosition: function() {
            return currentPos ? Object.assign({}, currentPos) : null;
        },
        getState: function() { return gpsState; },
        getProfile: function() { return profileName; },
        getLastError: function() { return lastError ? Object.assign({}, lastError) : null; },
        flushQueue: flushQueue
    };

    /* Backgrounded pages get their timers throttled and their GPS starved,
     * so tracking is torn down deliberately instead of being left to decay.
     * A final ping goes out first — that is what tells staff the difference
     * between "app closed here" and a dead marker with no explanation. */
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'hidden') {
            if (running) { sendLocation(true); stopSensors(); }
            releaseWakeLock();
            navBackground();
        } else {
            if (running) {
                startSensors();
                flushQueue();
                acquireWakeLock();
            }
            navReturn();
        }
    });

    window.addEventListener('pagehide', function() {
        if (running) sendLocation(true);
    });

    window.addEventListener('online', flushQueue);

    // Auto-start for every driver page. No task in hand means the cheap
    // idle profile — a fix roughly every 3 minutes, no GPS radio.
    EzzyGPS.start();

    // A driver coming back to a page that was discarded while Waze was in
    // front never fires visibilitychange — the trip ends on a fresh load.
    navReturn();
})();
