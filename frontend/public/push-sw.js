/*
 * Push notifications (#1054), in the service worker that keeps the app on the device
 * (#502, vite.config.ts): the build's own worker imports this file, so there is one
 * worker, and the Play View's offline keeping is unchanged.
 *
 * A push carries what the bell shows (horatio.web_push): the troupe, the line, and the
 * link. Each is shown as it comes; a tap opens its link, in the app if it is open.
 */

self.addEventListener("push", (event) => {
  let shown = { title: "Horatio", body: "", link: "/" };
  try {
    shown = { ...shown, ...event.data.json() };
  } catch {
    // Nothing readable: the plain "Horatio" still says something came.
  }
  event.waitUntil(
    self.registration.showNotification(shown.title, {
      body: shown.body,
      icon: "/icon-192.png",
      badge: "/mark-64.png",
      data: { link: shown.link },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = new URL(event.notification.data?.link || "/", self.location.origin);
  event.waitUntil(
    (async () => {
      // A Discord channel or invite opens as it is; Horatio's own page opens in the app.
      if (link.origin !== self.location.origin) return void (await self.clients.openWindow(link.href));
      const open = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      const here = open.find((c) => new URL(c.url).origin === self.location.origin);
      if (here) {
        await here.focus();
        return void (await here.navigate(link.href).catch(() => self.clients.openWindow(link.href)));
      }
      await self.clients.openWindow(link.href);
    })(),
  );
});

// The push service replaced this device's subscription (Firefox does, now and then):
// tell Horatio the new one, as the page would, so pushes keep coming.
self.addEventListener("pushsubscriptionchange", (event) => {
  const old = event.oldSubscription;
  event.waitUntil(
    (async () => {
      const subscription =
        event.newSubscription ||
        (old && (await self.registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: old.options.applicationServerKey })));
      if (!subscription) return;
      const { endpoint, keys } = subscription.toJSON();
      await fetch("/api/notification-settings/devices", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-Horatio": "1" },
        body: JSON.stringify({ endpoint, p256dh: keys.p256dh, auth: keys.auth }),
      });
    })().catch(() => undefined),
  );
});
