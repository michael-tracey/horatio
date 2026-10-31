import { useSearchParams } from "react-router";

/**
 * Where to go after signing in or up: a `?next=` path on the sign-in, sign-up and
 * password pages, so a link followed while signed out still gets there (issue #364).
 */

const HOME = "https://horatio.invalid";

/**
 * `raw` when it is a path on this site, else null. Only a single leading `/` will
 * do: never `//host` or `/\host` (both reach another site), a scheme, a backslash,
 * or whitespace and control characters (a browser drops a tab or newline, so
 * `/\t/host` would become `//host`). The sign-in pages themselves are refused too,
 * so that nothing goes round in a circle.
 */
export function safeNext(raw: string | null | undefined): string | null {
  if (!raw || raw.length > 2000) return null;
  if (!raw.startsWith("/") || raw.startsWith("//")) return null;
  if (/[\\\s\p{Cc}]/u.test(raw)) return null;
  // Decoded once more, it must still be a plain path: no `/%2F/host` or `/%5Chost`.
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return null;
  }
  if (decoded.startsWith("//") || /[\\\p{Cc}]/u.test(decoded)) return null;
  // The last word: resolved against this site, it stays on it.
  let url: URL;
  try {
    url = new URL(raw, HOME);
  } catch {
    return null;
  }
  if (url.origin !== HOME) return null;
  if (/^\/(sign-in|sign-up)(\/|$)/.test(url.pathname)) return null;
  return raw;
}

/** `path` with `?next=` added, when there is somewhere safe to go on to. */
export function withNext(path: string, next: string | null | undefined): string {
  const safe = safeNext(next);
  return safe ? `${path}?next=${encodeURIComponent(safe)}` : path;
}

/** This page's checked `?next=`, or null. */
export function useNext(): string | null {
  const [params] = useSearchParams();
  return safeNext(params.get("next"));
}
