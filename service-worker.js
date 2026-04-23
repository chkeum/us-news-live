/* Market Live — Service Worker
 * Cache strategy:
 *   - App shell (HTML/CSS/JS): cache-first (fast load), background update
 *   - Data JSONs: network-first with 10s timeout → cache fallback
 *   - Icons/manifest: cache-first
 */
const VERSION = 'v1.0.0';
const SHELL_CACHE = `shell-${VERSION}`;
const DATA_CACHE = `data-${VERSION}`;

const SHELL_ASSETS = [
  './',
  'index.html',
  'assets/styles.css',
  'assets/app.js',
  'assets/icon.svg',
  'manifest.webmanifest',
];

const DATA_URLS = [
  /\/data\/.*\.json/,
];

// ----- Install -----
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(cache => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ----- Activate -----
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(names =>
      Promise.all(
        names.filter(n => n !== SHELL_CACHE && n !== DATA_CACHE)
             .map(n => caches.delete(n))
      )
    ).then(() => self.clients.claim())
  );
});

// ----- Fetch strategy -----
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  // Only handle same-origin
  if (url.origin !== self.location.origin) return;

  // Data JSONs — network-first with timeout, cache fallback
  if (DATA_URLS.some(p => p.test(url.pathname))) {
    event.respondWith(networkFirstWithCache(req, DATA_CACHE, 10_000));
    return;
  }

  // App shell — cache-first with background revalidate (stale-while-revalidate)
  event.respondWith(staleWhileRevalidate(req, SHELL_CACHE));
});

async function networkFirstWithCache(request, cacheName, timeoutMs) {
  const cache = await caches.open(cacheName);
  try {
    const timeoutPromise = new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), timeoutMs));
    const resp = await Promise.race([fetch(request), timeoutPromise]);
    if (resp && resp.ok) {
      cache.put(request, resp.clone()).catch(() => {});
      return resp;
    }
    throw new Error('bad response');
  } catch (_) {
    const cached = await cache.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: 'offline' }), {
      headers: { 'Content-Type': 'application/json' },
      status: 503,
    });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const fetchPromise = fetch(request).then(resp => {
    if (resp && resp.ok) cache.put(request, resp.clone()).catch(() => {});
    return resp;
  }).catch(() => null);
  return cached || fetchPromise || new Response('offline', { status: 503 });
}

// ----- Push notifications (foundation; requires backend push service for real use) -----
self.addEventListener('push', (event) => {
  if (!event.data) return;
  let data = {};
  try { data = event.data.json(); } catch { data = { title: 'Market Live', body: event.data.text() }; }
  const title = data.title || 'Market Live';
  const options = {
    body: data.body || '',
    icon: 'assets/icon-192.png',
    badge: 'assets/icon-192.png',
    tag: data.tag || 'market-live',
    data: { url: data.url || './' },
    vibrate: [100, 50, 100],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = event.notification.data?.url || './';
  event.waitUntil(
    self.clients.matchAll({ type: 'window' }).then(clients => {
      for (const client of clients) {
        if (client.url.includes(self.location.origin)) {
          client.focus();
          client.navigate(url);
          return;
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
