/* Parfüm Lab · çevrimdışı açılış için önbellek.
   Uygulama dosyaları önbellekten açılır; veriler her zaman Supabase'den gelir. */
const VERSION = 'pl-1.0.0';
const SHELL = ['./', './index.html', './config.js', './supabase.js', './manifest.webmanifest',
  './icons/icon-192.png', './icons/icon-512.png', './icons/apple-touch-icon.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
const SHELL_PATHS = new Set(SHELL.map((p) => new URL(p, self.location).pathname));

self.addEventListener('fetch', (e) => {
  const req = e.request; const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (req.mode !== 'navigate' && !SHELL_PATHS.has(url.pathname)) return; // yalnızca uygulama dosyaları
  const fresh = req.mode === 'navigate' || url.pathname.endsWith('/') || url.pathname.endsWith('.html') || url.pathname.endsWith('config.js');
  if (fresh) {
    // önce ağ: yeni sürüm hemen gelsin, çevrimdışıysa önbellek
    e.respondWith(fetch(req).then((res) => {
      const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res;
    }).catch(() => caches.match(req).then((r) => r || caches.match('./index.html'))));
    return;
  }
  e.respondWith(caches.match(req).then((r) => r || fetch(req).then((res) => {
    const copy = res.clone(); caches.open(VERSION).then((c) => c.put(req, copy)); return res;
  })));
});
