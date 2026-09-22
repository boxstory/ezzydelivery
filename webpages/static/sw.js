// EzzyDriver Service Worker
const CACHE_NAME = 'ezzydriver-v9';
const STATIC_CACHE = 'ezzydriver-static-v9';
const DYNAMIC_CACHE = 'ezzydriver-dynamic-v9';

// Shared GPS queue implementation — the same module the page uses, so a ping
// queued in the tab and one replayed here go through identical code.
importScripts('/static/fleet/js/ezzy-gps-queue.js');

// Paths that must never be served from cache — see the fetch handler for why.
const AUTH_PATHS = ['/admin/', '/api/', '/accounts/', '/password/', '/join_us/', '/driver/start/'];

// Only the driver PWA's own screens are worth an offline copy. Everything else
// (marketing pages, forms, other apps' consoles) goes network-only.
const OFFLINE_HTML_PREFIXES = ['/fleet/', '/delivery/'];

// Static assets to cache
const STATIC_ASSETS = [
  '/static/fleet/css/fleet.css',
  '/static/fleet/css/fleet-mobile.css',
  '/static/brand-kit-pro.css',
  '/static/webpages/img/ezzy-logo-512-512.png',
  '/static/webpages/img/ezzy-logo-sqr-round.png'
];

// Install event - cache static assets
self.addEventListener('install', event => {
  console.log('[SW] Installing service worker...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('[SW] Pre-caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
      .catch(err => console.log('[SW] Pre-cache failed:', err))
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('[SW] Activating service worker...');
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
            .map(key => {
              console.log('[SW] Removing old cache:', key);
              return caches.delete(key);
            })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', event => {
  const request = event.request;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Never touch admin, API or auth pages.
  //
  // An HTML page replayed from Cache Storage arrives without its Set-Cookie
  // header and carries the csrfmiddlewaretoken of whoever filled the cache, so
  // posting that form fails with "CSRF cookie not set" — and because the cached
  // copy is served again on every retry, the driver can never get a fresh
  // cookie and is stuck on "Page Expired". Any page holding a CSRF form must
  // therefore come from the network or not at all.
  if (AUTH_PATHS.some(prefix => url.pathname.startsWith(prefix))) {
    return;
  }

  // For static assets - network first with cache fallback
  // This ensures ?v= cache-busting works correctly
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      fetch(request).then(networkResponse => {
        return caches.open(STATIC_CACHE).then(cache => {
          cache.put(request, networkResponse.clone());
          return networkResponse;
        });
      }).catch(() => {
        return caches.match(request).then(cachedResponse => {
          return cachedResponse || new Response('', { status: 408 });
        });
      })
    );
    return;
  }

  // For pages - network first, fallback to cache.
  // request.headers.get('accept') is null on some navigations; guard it.
  const accept = request.headers.get('accept') || '';
  if (accept.includes('text/html')) {
    const offlineCapable = OFFLINE_HTML_PREFIXES.some(p => url.pathname.startsWith(p));
    if (!offlineCapable) {
      return;  // network-only: no stale HTML, no stale CSRF token
    }
    event.respondWith(
      fetch(request)
        .then(networkResponse => {
          // Only cache successful, non-redirected responses the origin allows us
          // to store — a no-store page (auth, one-time forms) is never cached.
          const cc = networkResponse.headers.get('cache-control') || '';
          if (networkResponse.ok && !networkResponse.redirected && !cc.includes('no-store')) {
            const responseClone = networkResponse.clone();
            caches.open(DYNAMIC_CACHE).then(cache => {
              cache.put(request, responseClone);
            });
          }
          return networkResponse;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request).then(cachedResponse => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Return offline fallback page if available
            return caches.match('/fleet/dashboard/');
          });
        })
    );
    return;
  }
});

// Replay queued GPS pings once connectivity returns.
//
// This is the only path that works after the driver has closed the app: the
// browser wakes the worker when the device is back online and the queue drains
// without any page being open. Rejecting the promise tells the browser to
// retry the sync later with its own backoff, which costs no battery in between.
self.addEventListener('sync', event => {
  if (!self.EzzyGPSQueue || event.tag !== self.EzzyGPSQueue.SYNC_TAG) return;
  event.waitUntil(
    self.EzzyGPSQueue.flush().then(sent => {
      console.log('[SW] Replayed', sent, 'queued GPS ping(s)');
      return self.EzzyGPSQueue.count().then(left => {
        if (left > 0) throw new Error('GPS queue not empty — retry sync');
      });
    })
  );
});

// Handle push notifications.
//
// This is the only code of ours the browser will run once the PWA has lost the
// foreground — a driver inside Waze has a frozen page, and nothing on it can be
// called. It still cannot take a GPS fix: a service worker has no geolocation.
// All a push can do is put a notification in front of the driver so they come
// back to the app themselves, and Chrome requires that notification to be shown
// (userVisibleOnly), so there is no silent variant to reach for either.
self.addEventListener('push', event => {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (err) {
      payload = { body: event.data.text() };
    }
  }

  const title = payload.title || 'EzzyDriver';
  const options = {
    body: payload.body || 'Open the app',
    icon: '/static/webpages/img/ezzy-logo-512-512.png',
    badge: '/static/webpages/img/ezzy-logo-sqr-round.png',
    vibrate: [100, 50, 100],
    // Same tag replaces rather than stacks: three location requests should
    // leave one notification on the phone, not a pile to swipe away.
    tag: payload.tag || 'ezzy-driver',
    renotify: true,
    requireInteraction: !!payload.requireInteraction,
    data: {
      url: payload.url || '/fleet/dashboard/',
      sentAt: payload.sentAt || null,
      payload: payload.data || {}
    }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// Handle notification click — the tap that brings the PWA back to the
// foreground, which is what actually restarts GPS.
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/fleet/dashboard/';

  // Prefer an existing window: opening a second one leaves the driver with two
  // copies of the app, and on Android the new one may not come to the front at
  // all. focus() on a client we already hold always does.
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (const client of windowClients) {
        if (client.url.includes('/fleet/') && 'focus' in client) {
          if ('navigate' in client) {
            return client.navigate(target).then(c => (c || client).focus());
          }
          return client.focus();
        }
      }
      return clients.openWindow(target);
    })
  );
});
