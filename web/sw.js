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
      title: 'Evidence Vozidel',
      body: event.data ? event.data.text() : 'Nová notifikace',
    };
  }

  const notificationID = Number.isSafeInteger(payload.notification_id) && payload.notification_id > 0 ? payload.notification_id : null;
  const unified = notificationID !== null;
  const inboxPath = unified && payload.kind === 'admin_reply' ? '/web_admin/index.html' : '/web/customer.html';
  const title = unified ? 'Evidence Vozidel' : payload.title || 'Evidence Vozidel';
  const options = {
    body: unified ? 'Máte nové oznámení. Podrobnosti otevřete ve svém účtu.' : payload.body || 'Máte nové upozornění.',
    icon: sameOriginURL(payload.icon, '/web/assets/toozservis-logo-icon.png'),
    badge: sameOriginURL(payload.badge, '/web/assets/toozservis-logo-icon.png'),
    tag: unified ? 'evidence-notification-' + notificationID : payload.tag || 'sprava-vozidel-notification',
    data: {
      url: unified ? new URL(inboxPath+'#notifications/'+notificationID, self.location.origin).href : sameOriginURL(payload.url, '/web/index.html'),
      notification_id: notificationID,
      timestamp: payload.timestamp || Date.now(),
    },
    renotify: false,
    requireInteraction: false,
  };

  event.waitUntil(Promise.all([
    self.registration.showNotification(title, options),
    unified && Number.isSafeInteger(payload.badge_count) && payload.badge_count >= 0 && typeof self.navigator?.setAppBadge === 'function'
      ? Promise.resolve(payload.badge_count ? self.navigator.setAppBadge(payload.badge_count) : self.navigator.clearAppBadge?.()).catch(() => {})
      : Promise.resolve(),
    self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients => {
      for (const client of clients) {
        if (new URL(client.url).origin === self.location.origin && new URL(client.url).pathname === inboxPath) {
          client.postMessage({type:'EVIDENCE_NOTIFICATION_REFRESH'});
        }
      }
    }),
  ]));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = sameOriginURL(event.notification?.data?.url, '/web/index.html');

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url && new URL(client.url).origin === self.location.origin && (new URL(client.url).pathname.startsWith('/web/') || new URL(client.url).pathname === '/web_admin/index.html')) {
          if (Number.isSafeInteger(event.notification?.data?.notification_id)) {
            if (new URL(client.url).pathname !== new URL(targetUrl).pathname) continue;
            client.focus();
            client.postMessage({type:'EVIDENCE_NOTIFICATION_OPEN',notification_id:event.notification.data.notification_id});
            return;
          }
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
