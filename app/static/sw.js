const CACHE_NAME = "salon-static-v12-mercadopago";
const STATIC_ASSETS = [
  "/static/css/style.css?v=2026-10-16-mobile-hero",
  "/static/js/theme.js?v=2026-10-16-dark",
  "/static/js/booking.js?v=2026-10-18-mercadopago-v1",
  "/static/js/payment.js?v=2026-10-18-mercadopago-v1",
  "/static/js/pwa.js?v=2026-10-16-wine-v2",
  "/static/icons/brand-wine.svg",
  "/static/icons/icon-wine-192.png",
  "/static/icons/icon-wine-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) {
    return;
  }
  if (url.pathname === "/static/downloads/agendamento-salao.apk") return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request).then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      });
    }),
  );
});
