/* Purpose: Durable IndexedDB queue for driver GPS pings — buffers when the network fails and replays in batches.
 * Used by: fleet/templates/fleet/pwa_base.html (EzzyGPS module) and webpages/static/sw.js (Background Sync flush).
 * Notes: Loaded in both window and ServiceWorker scope, so it must touch no DOM. The CSRF token travels with each
 *        queued row because a service worker cannot read cookies or the page's meta tag when it replays them.
 *        Editing this file means bumping the cache version in sw.js too, or installed workers keep the old copy.
 */
(function (scope) {
    'use strict';

    var DB_NAME = 'ezzy-gps';
    var DB_VERSION = 1;
    var STORE = 'pings';
    var ENDPOINT = '/api/driver/location/';
    var BATCH_SIZE = 100;    // must not exceed the server's _MAX_LOCATION_BATCH
    var MAX_QUEUE = 500;     // ~4 hours of 30s pings; older rows are dropped first
    var MAX_ATTEMPTS = 5;    // a row the server keeps rejecting is discarded

    function openDb() {
        return new Promise(function (resolve, reject) {
            var req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function () {
                var db = req.result;
                if (!db.objectStoreNames.contains(STORE)) {
                    db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
                }
            };
            req.onsuccess = function () { resolve(req.result); };
            req.onerror = function () { reject(req.error); };
        });
    }

    function withStore(mode, fn) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE, mode);
                var out = fn(tx.objectStore(STORE));
                tx.oncomplete = function () { db.close(); resolve(out && out.value); };
                tx.onerror = function () { db.close(); reject(tx.error); };
                tx.onabort = function () { db.close(); reject(tx.error); };
            });
        });
    }

    function readAll() {
        return withStore('readonly', function (store) {
            var box = {};
            store.getAll().onsuccess = function (e) { box.value = e.target.result || []; };
            return box;
        });
    }

    /* Append a ping. Oldest rows are evicted once the queue is full — a stale
     * position is worth less than the fresh one that would be turned away. */
    function enqueue(ping) {
        return withStore('readwrite', function (store) {
            store.add(Object.assign({}, ping, { queued: true, attempts: 0 }));
            store.count().onsuccess = function (e) {
                var overflow = e.target.result - MAX_QUEUE;
                if (overflow <= 0) return;
                store.openCursor().onsuccess = function (ev) {
                    var cursor = ev.target.result;
                    if (!cursor || overflow <= 0) return;
                    cursor.delete();
                    overflow -= 1;
                    cursor.continue();
                };
            };
            return {};
        });
    }

    function removeIds(ids) {
        if (!ids.length) return Promise.resolve();
        return withStore('readwrite', function (store) {
            ids.forEach(function (id) { store.delete(id); });
            return {};
        });
    }

    /* Count a failed delivery against each row, dropping the ones that have
     * exhausted their retries so a permanently rejected ping cannot wedge the
     * queue behind it. */
    function penalise(rows) {
        if (!rows.length) return Promise.resolve(0);
        return withStore('readwrite', function (store) {
            var box = { value: 0 };
            rows.forEach(function (row) {
                var attempts = (row.attempts || 0) + 1;
                if (attempts >= MAX_ATTEMPTS) {
                    store.delete(row.id);
                    box.value += 1;
                } else {
                    store.put(Object.assign({}, row, { attempts: attempts }));
                }
            });
            return box;
        });
    }

    function count() {
        return withStore('readonly', function (store) {
            var box = {};
            store.count().onsuccess = function (e) { box.value = e.target.result; };
            return box;
        });
    }

    function postBatch(rows, csrf) {
        return fetch(ENDPOINT, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf || '' },
            body: JSON.stringify({
                pings: rows.map(function (r) {
                    return {
                        latitude: r.latitude,
                        longitude: r.longitude,
                        accuracy: r.accuracy,
                        speed: r.speed,
                        heading: r.heading,
                        task_id: r.task_id,
                        fixed_at: r.fixed_at,
                        queued: true
                    };
                })
            })
        });
    }

    /* Drain the queue oldest-first.
     *
     * A network failure stops the drain and keeps everything — the driver is
     * still in the dead zone. A server rejection only penalises the batch, so a
     * rotated CSRF token or one malformed row resolves itself on a later pass
     * instead of blocking every ping behind it. Resolves with how many were
     * accepted. */
    function flush(csrf) {
        var sent = 0;
        function drain() {
            return readAll().then(function (rows) {
                if (!rows.length) return sent;
                var batch = rows.slice(0, BATCH_SIZE);
                var token = csrf || batch[batch.length - 1].csrf;
                return postBatch(batch, token).then(function (res) {
                    var ids = batch.map(function (r) { return r.id; });
                    if (res.ok) {
                        sent += batch.length;
                        return removeIds(ids).then(function () {
                            return rows.length > batch.length ? drain() : sent;
                        });
                    }
                    if (res.status >= 500 || res.status === 429) return sent;  // server sick — try later
                    return penalise(batch).then(function () { return sent; });
                });
            });
        }
        return drain().catch(function (err) {
            console.warn('[EzzyGPSQueue] Flush stopped:', err);
            return sent;
        });
    }

    scope.EzzyGPSQueue = {
        enqueue: enqueue,
        flush: flush,
        count: count,
        SYNC_TAG: 'ezzy-gps-flush'
    };
})(typeof self !== 'undefined' ? self : this);
