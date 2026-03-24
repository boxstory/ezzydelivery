// EzzyDriver Service Worker
const CACHE_NAME = 'ezzydriver-v5';
const STATIC_CACHE = 'ezzydriver-static-v5';
const DYNAMIC_CACHE = 'ezzydriver-dynamic-v5';

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

  // Skip admin, API, and auth requests
  if (url.pathname.startsWith('/admin/') || url.pathname.startsWith('/api/') || url.pathname.startsWith('/accounts/')) {
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

  // For pages - network first, fallback to cache
  if (request.headers.get('accept').includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then(networkResponse => {
          // Only cache successful, non-redirected responses
          if (networkResponse.ok && !networkResponse.redirected) {
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
