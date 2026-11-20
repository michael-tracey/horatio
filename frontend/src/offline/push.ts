import { api, unwrap } from "../api/client";

/**
 * Push notifications on this device (#1054): the browser's own subscription with its
 * push service, made through the service worker that keeps the app (vite.config.ts,
 * public/push-sw.js shows each push). Horatio keeps the subscription as one of the
 * person's devices (horatio.web_push); which kinds come is chosen on Account ›
 * Notifications.
 */

/** What this browser can do: push, push once Horatio is on the Home Screen (an iPhone
 * or iPad in Safari), or nothing. */
export type PushSupport = "yes" | "home-screen" | "no";

export function pushSupport(nav: Navigator = navigator, win: object = window): PushSupport {
  if ("serviceWorker" in nav && "PushManager" in win && "Notification" in win) return "yes";
  // iPadOS says it is a Mac, but a Mac has no touch.
  const apple = /iPhone|iPad|iPod/.test(nav.userAgent) || (/Macintosh/.test(nav.userAgent) && nav.maxTouchPoints > 1);
  return apple ? "home-screen" : "no";
}

/** Whether the person has told this browser not to let Horatio notify them. */
export function blocked(): boolean {
  return typeof Notification !== "undefined" && Notification.permission === "denied";
}

/** The service worker, once it is running; null if there is none (the dev server has none). */
async function worker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator) || !(await navigator.serviceWorker.getRegistration())) return null;
  return Promise.race([navigator.serviceWorker.ready, new Promise<null>((done) => setTimeout(() => done(null), 10_000))]);
}

/** This browser's subscription, if it has one. */
export async function subscriptionHere(): Promise<PushSubscription | null> {
  try {
    if (pushSupport() !== "yes") return null;
    const registration = await navigator.serviceWorker.getRegistration();
    return (await registration?.pushManager.getSubscription()) ?? null;
  } catch {
    return null;
  }
}

export function fromBase64Url(text: string): Uint8Array<ArrayBuffer> {
  const plain = atob(text.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(plain, (c) => c.charCodeAt(0));
}

export function toBase64Url(bytes: ArrayBuffer | null): string {
  if (!bytes) return "";
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replace(/=+$/, "");
}

/** Ask the browser for a subscription with the server's key (`push_key`), asking the
 * person's leave first; what the server keeps of it. */
export async function subscribeHere(key: string): Promise<{ endpoint: string; p256dh: string; auth: string }> {
  const allowed = await Notification.requestPermission();
  if (allowed !== "granted") throw new Error("This browser won't let Horatio notify you. Allow notifications for Horatio in its settings, then try again.");
  const registration = await worker();
  if (!registration) throw new Error("This browser hasn't finished setting Horatio up yet. Reload the page and try again.");
  let subscription = await registration.pushManager.getSubscription();
  // One made with another key (the server's changed) is no use: start again.
  if (subscription && toBase64Url(subscription.options.applicationServerKey) !== key) {
    await subscription.unsubscribe();
    subscription = null;
  }
  subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: fromBase64Url(key) });
  const { keys } = subscription.toJSON();
  if (!keys?.p256dh || !keys.auth) throw new Error("This browser didn't give Horatio what it needs to send to it.");
  return { endpoint: subscription.endpoint, p256dh: keys.p256dh, auth: keys.auth };
}

/** At sign-out: push stops on this device, for the person signing out. Never in the way of
 * signing out: whatever goes wrong, or takes too long, is left. */
export async function stopPushHere(): Promise<void> {
  const work = (async () => {
    const subscription = await subscriptionHere();
    if (!subscription) return;
    const { devices } = await unwrap(api.GET("/api/notification-settings"));
    const here = devices.find((d) => d.endpoint === subscription.endpoint);
    if (here) await unwrap(api.DELETE("/api/notification-settings/devices/{device_id}", { params: { path: { device_id: here.id } } }));
    await subscription.unsubscribe();
  })();
  await Promise.race([work.catch(() => undefined), new Promise((done) => setTimeout(done, 3000))]);
}
