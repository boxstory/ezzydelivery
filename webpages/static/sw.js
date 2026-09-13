// EzzyDriver Service Worker
const CACHE_NAME = 'ezzydriver-v8';
const STATIC_CACHE = 'ezzydriver-static-v8';
const DYNAMIC_CACHE = 'ezzydriver-dynamic-v8';

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

// Handle push notifications
self.addEventListener('push', event => {
  const options = {
    body: event.data ? event.data.text() : 'New notification',
    icon: '/static/webpages/img/ezzy-logo-512-512.png',
    badge: '/static/webpages/img/ezzy-logo-sqr-round.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    }
  };

  event.waitUntil(
    self.registration.showNotification('EzzyDriver', options)
  );
});

// Handle notification click
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow('/fleet/dashboard/')
  );
});
