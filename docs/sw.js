// Service worker: l'app si apre anche offline; lo stato arriva dalla rete quando possibile.
const CACHE = "montegalletto-v1";
const SHELL = [
  "./", "index.html", "style.css", "app.js", "schedule.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/favicon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  // Rete prima, cache come riserva: così stato e codice sono sempre i più recenti quando c'è campo.
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          const key = url.pathname.endsWith("status.json") ? "status.json" : e.request;
          caches.open(CACHE).then((c) => c.put(key, copy));
        }
        return res;
      })
      .catch(() => caches.match(url.pathname.endsWith("status.json") ? "status.json" : e.request)),
  );
});
