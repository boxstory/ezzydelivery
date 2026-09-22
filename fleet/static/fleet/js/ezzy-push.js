/* Purpose: Register the driver PWA for Web Push, and honour a push-triggered location request.
 * Used by: fleet/templates/fleet/pwa_base.html (reads window.EZZY_PUSH_CONFIG).
 * Notes: A push cannot take a GPS fix — the service worker has no geolocation. It only brings the
 *        driver back to the app; the fix is taken here, on the way in, via EzzyGPS.stamp().
 */
(function () {
    'use strict';

    var cfg = window.EZZY_PUSH_CONFIG || {};
    var PUBLIC_KEY = cfg.publicKey || '';
    var DISMISS_KEY = 'ezzy_push_prompt_dismissed';
    var SYNCED_KEY = 'ezzy_push_endpoint';

    function supported() {
        return ('serviceWorker' in navigator) && ('PushManager' in window) && ('Notification' in window);
    }

    function getCsrf() {
        var el = document.querySelector('meta[name="csrf-token"]');
        return el ? el.getAttribute('content') : '';
    }

    /* The browser wants the VAPID public key as raw bytes, but it travels as
     * base64url — and base64url is not what atob() reads, so the padding and
     * the two swapped characters have to be put back first. */
    function urlBase64ToUint8Array(base64String) {
        var padding = '='.repeat((4 - base64String.length % 4) % 4);
        var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        var raw = window.atob(base64);
        var out = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
        return out;
    }

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
            body: JSON.stringify(body)
        });
    }

    /* Send the subscription to the server, but only when it is new to this
     * device: the browser hands back the same object on every load, and posting
     * it each time would be a write per page view for nothing. */
    function syncSubscription(sub, force) {
        var json = sub.toJSON();
        var seen = null;
        try { seen = localStorage.getItem(SYNCED_KEY); } catch (e) { /* private mode */ }
        if (!force && seen === json.endpoint) return Promise.resolve(true);
        return post('/api/driver/push/subscribe/', { subscription: json })
            .then(function (r) {
                if (!r.ok) throw new Error('subscribe failed: ' + r.status);
                try { localStorage.setItem(SYNCED_KEY, json.endpoint); } catch (e) {}
                return true;
            })
            .catch(function (err) {
                console.warn('[EzzyPush] Could not register device:', err && err.message);
                // Clear the memo so the next load tries again rather than
                // believing a registration that never reached the server.
                try { localStorage.removeItem(SYNCED_KEY); } catch (e) {}
                return false;
            });
    }

    function subscribe(registration, force) {
        if (!PUBLIC_KEY) return Promise.resolve(false);
        return registration.pushManager.getSubscription().then(function (existing) {
            if (existing) return syncSubscription(existing, force);
            return registration.pushManager.subscribe({
                // Chrome refuses a subscription that may deliver silently, and
                // a push we cannot show is one the driver never acts on anyway.
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(PUBLIC_KEY)
            }).then(function (sub) {
                return syncSubscription(sub, true);
            });
        }).catch(function (err) {
            console.warn('[EzzyPush] Subscribe failed:', err && err.message);
            return false;
        });
    }

    function ready() {
        return navigator.serviceWorker.ready;
    }

    function enable() {
        return Notification.requestPermission().then(function (permission) {
            if (permission !== 'granted') {
                if (typeof showToast === 'function') {
                    showToast('Notifications are blocked. Enable them in your browser settings.', 'warning', 5000);
                }
                return false;
            }
            return ready().then(function (reg) { return subscribe(reg, true); }).then(function (ok) {
                if (ok && typeof showToast === 'function') showToast('Notifications on', 'success');
                return ok;
            });
        });
    }

    /* The prompt only ever appears for a driver who has neither granted nor
     * refused. Asking on load without a gesture is how browsers end up blocking
     * the origin permanently, so this is a button, not an automatic request. */
    function showPrompt() {
        var bar = document.getElementById('fleet_push_prompt');
        if (!bar) return;
        var dismissed = false;
        try { dismissed = localStorage.getItem(DISMISS_KEY) === '1'; } catch (e) {}
        if (dismissed) return;
        bar.classList.add('fpush__prompt--visible');

        var enableBtn = document.getElementById('fleet_push_enable');
        var laterBtn = document.getElementById('fleet_push_later');
        if (enableBtn) {
            enableBtn.addEventListener('click', function () {
                enable().then(function () { bar.classList.remove('fpush__prompt--visible'); });
            });
        }
        if (laterBtn) {
            laterBtn.addEventListener('click', function () {
                try { localStorage.setItem(DISMISS_KEY, '1'); } catch (e) {}
                bar.classList.remove('fpush__prompt--visible');
            });
        }
    }

    /* A load carrying ?locreq=1 is the driver answering a "where are you?"
     * notification. The duty cycle would get there on its own, but a dispatcher
     * who asked is waiting now — and after a spell in Waze the last stored fix
     * is wherever the driver was when they left. So take a fresh one at once,
     * and take the URL flag back out so a refresh does not re-fire it. */
    function handleLocationRequest() {
        var params = new URLSearchParams(window.location.search);
        if (params.get('locreq') !== '1') return;

        params.delete('locreq');
        var rest = params.toString();
        window.history.replaceState({}, '', window.location.pathname + (rest ? '?' + rest : ''));

        if (window.EzzyGPS && typeof window.EzzyGPS.stamp === 'function') {
            window.EzzyGPS.stamp().then(function (ok) {
                if (typeof showToast === 'function') {
                    showToast(ok ? 'Location sent to dispatch' : 'Could not get a GPS fix — check location permission',
                              ok ? 'success' : 'warning', 4000);
                }
            });
        }
    }

    function init() {
        handleLocationRequest();

        if (!supported() || !PUBLIC_KEY) return;
        if (Notification.permission === 'granted') {
            // Re-register quietly: a push service can rotate an endpoint, and a
            // driver whose row went stale would otherwise be unreachable with
            // nothing on screen to say so.
            ready().then(function (reg) { subscribe(reg, false); });
        } else if (Notification.permission === 'default') {
            showPrompt();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.EzzyPush = {
        enable: enable,
        isSupported: supported,
        permission: function () { return supported() ? Notification.permission : 'unsupported'; },
        disable: function () {
            return ready().then(function (reg) {
                return reg.pushManager.getSubscription().then(function (sub) {
                    if (!sub) return true;
                    var endpoint = sub.endpoint;
                    return sub.unsubscribe().then(function () {
                        try { localStorage.removeItem(SYNCED_KEY); } catch (e) {}
                        return post('/api/driver/push/unsubscribe/', { endpoint: endpoint });
                    }).then(function () { return true; });
                });
            });
        }
    };
})();
