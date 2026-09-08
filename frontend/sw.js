const CACHE_NAME = 'quant-ai-v1.1.9';
const ASSETS_TO_CACHE = [
  './',
  './index.html',
  './styles.css',
  './manifest.json',
  './src/app.js',
  './src/state.js',
  './src/tabs/tab_manager.js',
  './src/tabs/cockpit_view.js',
  './src/tabs/radar_view.js',
  './src/tabs/flow_view.js',
  './src/styles/radar.css',
  './src/styles/flow.css',
  './src/components/lock_screen.js',
  './src/components/message_renderer.js',
  './src/components/quant_chart.js',
  './src/components/lightbox.js',
  './src/components/diagnostics_modal.js',
  './src/components/settings_modal.js',
  './icons/icon-192.svg',
  './icons/icon-512.svg'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(ASSETS_TO_CACHE);
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Never cache API streaming or dynamic NAS endpoints
  if (event.request.url.includes('/api/')) {
    return;
  }

  // Network-first for html/js so updates are instant
  event.respondWith(
    fetch(event.request).then((networkResponse) => {
      if (networkResponse && networkResponse.status === 200) {
        const responseClone = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
      }
      return networkResponse;
    }).catch(() => {
      return caches.match(event.request);
    })
  );
});
