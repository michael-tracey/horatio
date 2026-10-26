import { Component, Suspense, type ErrorInfo, type ReactNode } from "react";
import { useLocation } from "react-router";
import { Button, Loading } from "./components/ui";

// After a deploy, a tab opened before it asks for page files that no longer
// exist. Reloading fetches the new index.html, which names the new ones.

const FLAG = "horatio-reloaded-for-update";
const WINDOW_MS = 60_000;

/** Reload, once a minute at most. False when it did not (it just did, or the
 *  guard cannot be kept), so a file that is really missing cannot loop. */
export function reloadOnce(storage: Storage | undefined = globalThis.sessionStorage, now = Date.now(), reload = () => window.location.reload()): boolean {
  try {
    if (!storage) return false;
    const last = Number(storage.getItem(FLAG));
    if (last && now - last < WINDOW_MS) return false;
    storage.setItem(FLAG, String(now));
  } catch {
    return false;
  }
  reload();
  return true;
}

export function isLoadFailure(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|Failed to fetch dynamically|Unable to preload|error loading dynamically/i.test(text);
}

/** Vite says so when a page's file will not load. */
export function reloadOnPreloadError(): void {
  window.addEventListener("vite:preloadError", (event) => {
    if (reloadOnce()) event.preventDefault();
  });
}

export function UpdatedMessage({ failedToLoad = true }: { failedToLoad?: boolean }) {
  return (
    <div role="alert" className="py-8 text-center">
      <p className="mb-4">{failedToLoad ? "Horatio has been updated. Reload to continue." : "Something went wrong on this page."}</p>
      <Button onClick={() => window.location.reload()}>Reload</Button>
    </div>
  );
}

class Boundary extends Component<{ children: ReactNode; resetKey: string }, { error: unknown }> {
  state: { error: unknown } = { error: undefined };
  static getDerivedStateFromError(error: unknown) {
    return { error: error ?? new Error("failed") };
  }
  componentDidCatch(error: unknown, _info: ErrorInfo) {
    if (isLoadFailure(error)) reloadOnce();
  }
  componentDidUpdate(previous: { resetKey: string }) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: undefined });
  }
  render() {
    if (this.state.error === undefined) return this.props.children;
    return <UpdatedMessage failedToLoad={isLoadFailure(this.state.error)} />;
  }
}

/** Round the lazy pages: loading, and a message instead of a blank screen when a page fails. */
export function LazyPages({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return (
    <Boundary resetKey={pathname}>
      <Suspense fallback={<Loading />}>{children}</Suspense>
    </Boundary>
  );
}
