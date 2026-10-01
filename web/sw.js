// Notifications may only reopen this application's own routes and resources.
function sameOriginURL(value, fallback) {
  try {
    const url = new URL(String(value || fallback), self.location.origin);
    if (url.origin === self.location.origin && ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password) return url.href;
  } catch { /* malformed notification payload */ }
  return new URL(fallback, self.location.origin).href;
}

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    payload = {
      title: 'SprávaVozidel',
      body: event.data ? event.data.text() : 'Nová notifikace',
    };
  }

  const title = payload.title || 'SprávaVozidel';
  const options = {
    body: payload.body || 'Máte nové upozornění.',
    icon: sameOriginURL(payload.icon, '/web/assets/toozservis-logo-icon.png'),
    badge: sameOriginURL(payload.badge, '/web/assets/toozservis-logo-icon.png'),
    tag: payload.tag || 'sprava-vozidel-notification',
    data: {
      url: sameOriginURL(payload.url, '/web/index.html'),
      timestamp: payload.timestamp || Date.now(),
    },
    renotify: false,
    requireInteraction: false,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = sameOriginURL(event.notification?.data?.url, '/web/index.html');

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url && new URL(client.url).origin === self.location.origin && new URL(client.url).pathname.startsWith('/web/')) {
          client.focus();
          // Kanonický typ; stránka akceptuje i legacy TOOZHUB_NOTIFICATION_CLICK (starý SW) – viz index.html
          client.postMessage({ type: 'SPRAVA_VOZIDEL_NOTIFICATION_CLICK', url: targetUrl });
          return client.navigate(targetUrl);
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
