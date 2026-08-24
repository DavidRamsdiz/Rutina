const CACHE = 'rutina-cache-v1';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then(c => c.addAll(['./', './index.html'])).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// red primero (para coger versiones nuevas), cache de respaldo cuando no hay conexión
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request).then(resp => {
      if (resp && resp.ok) {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(event.request, clone));
      }
      return resp;
    }).catch(() => caches.match(event.request, {ignoreSearch:true}))
  );
});
