import { useRegisterSW } from "virtual:pwa-register/react";

/** How often an open app looks for a new version. */
const CHECK = 60 * 60_000;

/**
 * Registers the service worker that keeps the app on the device (vite.config.ts),
 * and once a new version is ready, offers it: "Update ready · Reload". It never
 * reloads by itself, so a tap is never cut off.
 */
export function UpdatePrompt() {
  const {
    needRefresh: [ready],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisteredSW(_url, registration) {
      if (registration) window.setInterval(() => void registration.update().catch(() => undefined), CHECK);
    },
  });
  if (!ready) return null;
  return (
    <div aria-live="polite" className="fixed bottom-3 left-3 z-50 flex items-center gap-2 rounded-full border border-gold/50 bg-dusk px-3 py-1.5 text-xs text-parchment shadow-lg">
      Update ready ·
      <button type="button" className="text-gold underline hover:text-parchment" onClick={() => void updateServiceWorker(true)}>
        Reload
      </button>
    </div>
  );
}
