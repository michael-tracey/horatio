import type { Preferences } from "./api/types";

/**
 * Horatio's themes (#635): Dark, the default, and Ultra goth, deep red on matte
 * black, chosen in Settings › Appearance and kept on the account. (Light is the
 * Easter egg in components/Sunrise.tsx, and never kept.) Ultra goth's colours are
 * index.css's, under html[data-theme="ultragoth"].
 */
export type Theme = Preferences["theme"];

export const THEMES: readonly Theme[] = ["dark", "ultragoth"];

/**
 * Where the theme last shown is kept on this device, for index.html, which sets
 * it before anything shows: no flash of Dark on a reload, or with no signal.
 */
export const THEME_KEY = "horatio.theme";

/** The browser's bar, in each theme's night. */
export const BAR_COLOUR: Record<Theme, string> = { dark: "#141016", ultragoth: "#0a0909" };

/**
 * What the Throws tab is drawn in, in each theme: its panel (dusk) and the word under
 * a throw (gold), as index.css has them; theme.test.tsx checks they match. For showing
 * a troupe's throw pictures in both themes at once (#670), whichever is on.
 */
export const THROW_PANEL: Record<Theme, { dusk: string; gold: string }> = {
  dark: { dusk: "#1e1922", gold: "#c9a24a" },
  ultragoth: { dusk: "#131011", gold: "#f95a63" },
};

export function isTheme(value: unknown): value is Theme {
  return typeof value === "string" && (THEMES as readonly string[]).includes(value);
}

/** The theme last shown on this device, or Dark. */
export function cachedTheme(storage: Storage | undefined = globalThis.localStorage): Theme {
  try {
    const kept = storage?.getItem(THEME_KEY);
    return isTheme(kept) ? kept : "dark";
  } catch {
    return "dark";
  }
}

export function rememberTheme(theme: Theme, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (theme === "dark") storage?.removeItem(THEME_KEY);
    else storage?.setItem(THEME_KEY, theme);
  } catch {
    // Only a convenience: the page shows Dark until the account says otherwise.
  }
}

/** Show a theme: <html>'s data-theme, and the colour of the browser's bar. */
export function applyTheme(theme: Theme, doc: Document = document): void {
  const root = doc.documentElement;
  if (theme === "dark") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  doc.querySelector('meta[name="theme-color"]')?.setAttribute("content", BAR_COLOUR[theme]);
}

/**
 * The script index.html runs in its head, before anything shows: the theme last
 * shown on this device, as applyTheme would set it.
 */
export function themeOnLoad(): string {
  const others = THEMES.filter((t) => t !== "dark");
  const bars = JSON.stringify(BAR_COLOUR);
  return `(function(){try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});if(${JSON.stringify(others)}.indexOf(t)<0)return;document.documentElement.setAttribute("data-theme",t);var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content",${bars}[t])}catch(e){}})();`;
}
