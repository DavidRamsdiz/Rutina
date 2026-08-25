const CACHE = 'rutina-cache-v2';

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

// Red primero, con la cache solo como respaldo sin conexion.
// cache:'no-store' evita que Chrome sirva su propia copia HTTP antigua del HTML,
// que es lo que hacia que la PWA instalada siguiera mostrando la version vieja.
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  if (new URL(req.url).origin !== self.location.origin) return; // fuentes y API de GitHub pasan directas
  event.respondWith(
    fetch(req, {cache: 'no-store'}).then(resp => {
      if (resp && resp.ok) {
        const clone = resp.clone();
        caches.open(CACHE).then(c => c.put(req, clone));
      }
      return resp;
    }).catch(() => caches.match(req, {ignoreSearch: true}))
  );
});

self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') self.skipWaiting();
});
