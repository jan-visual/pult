// Pult: service worker. Nic necachuje (aplikace je vždy čerstvá ze serveru), jen když server
// neběží, ukáže místo chyby prohlížeče stránku „Pult neběží“ a sám se znovu připojí.
const OFFLINE = "/static/offline.html";
self.addEventListener("install", (e) => { e.waitUntil(caches.open("pult-offline-1").then((c) => c.add(OFFLINE))); self.skipWaiting(); });
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  if (e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request).catch(() => caches.match(OFFLINE)));
});
