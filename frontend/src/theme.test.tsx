import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Me } from "./api/types";
import { DEFAULT_PREFERENCES } from "./hooks";
import { withLoadingScreen } from "./loaders/indexHtml";
import { applyTheme, BAR_COLOUR, cachedTheme, rememberTheme, THEME_KEY, themeOnLoad } from "./theme";
import { useTheme } from "./useTheme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.head.innerHTML = '<meta name="theme-color" content="#141016" />';
});
afterEach(cleanup);

const theme = () => document.documentElement.getAttribute("data-theme");
const bar = () => document.querySelector('meta[name="theme-color"]')!.getAttribute("content");

describe("a theme", () => {
  it("shows on <html> and in the browser's bar, and Dark takes it away", () => {
    applyTheme("ultragoth");
    expect(theme()).toBe("ultragoth");
    expect(bar()).toBe(BAR_COLOUR.ultragoth);
    applyTheme("dark");
    expect(theme()).toBeNull();
    expect(bar()).toBe("#141016");
  });

  it("is kept on the device, Dark by keeping nothing", () => {
    expect(cachedTheme()).toBe("dark");
    rememberTheme("ultragoth");
    expect(cachedTheme()).toBe("ultragoth");
    rememberTheme("dark");
    expect(localStorage.getItem(THEME_KEY)).toBeNull();
    localStorage.setItem(THEME_KEY, "light");
    expect(cachedTheme()).toBe("dark");
    const refusing = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } } as unknown as Storage;
    expect(cachedTheme(refusing)).toBe("dark");
    expect(() => rememberTheme("ultragoth", refusing)).not.toThrow();
  });
});

describe("index.html", () => {
  it("sets the theme last shown on this device before anything shows", () => {
    const load = () => new Function(themeOnLoad())();
    load();
    expect(theme()).toBeNull();
    rememberTheme("ultragoth");
    load();
    expect(theme()).toBe("ultragoth");
    expect(bar()).toBe(BAR_COLOUR.ultragoth);
    document.documentElement.removeAttribute("data-theme");
    localStorage.setItem(THEME_KEY, '"><script>');
    load();
    expect(theme()).toBeNull();
  });

  it("runs that script in its head, after the bar's colour", () => {
    const page = withLoadingScreen('<head><meta name="theme-color" /><!-- theme --><!-- loaders.css --></head><body><div id="root"><!-- loading screen --></div></body>', "");
    const head = page.slice(0, page.indexOf("</head>"));
    expect(head).toContain(`<meta name="theme-color" /><script>${themeOnLoad()}</script>`);
  });
});

describe("the signed-in person's theme", () => {
  function Shows() {
    useTheme();
    return null;
  }
  const me = (theme: "dark" | "ultragoth") => ({ id: "u1", handle: "agnes", preferences: { ...DEFAULT_PREFERENCES, theme } }) as unknown as Me;

  it("shows, and is kept for next time; until it is known, the device's stays", async () => {
    rememberTheme("ultragoth");
    applyTheme("ultragoth");
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } });
    // The cache tells its screens on the next tick.
    const set = (key: string[], value: unknown) =>
      act(async () => {
        client.setQueryData(key, value);
        await new Promise((tick) => setTimeout(tick, 0));
      });
    render(
      <QueryClientProvider client={client}>
        <Shows />
      </QueryClientProvider>,
    );
    expect(theme()).toBe("ultragoth");
    await set(["me"], me("dark"));
    expect(theme()).toBeNull();
    expect(cachedTheme()).toBe("dark");
    await set(["me"], me("ultragoth"));
    expect(theme()).toBe("ultragoth");
    expect(cachedTheme()).toBe("ultragoth");
    // Signed out, the device keeps the last one shown.
    await set(["me"], null);
    expect(theme()).toBe("ultragoth");
  });
});

/** Ultra goth's colours, as index.css has them. */
function ultraGoth(): Record<string, string> {
  const css = readFileSync(join(__dirname, "index.css"), "utf8");
  const block = /html\[data-theme="ultragoth"\] \{([^}]*)\}/.exec(css)![1]!;
  const colours = Object.fromEntries([...block.matchAll(/--color-([a-z-]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1]!, m[2]!]));
  colours["blood-hover"] = /\.hover\\:bg-blood-bright:hover[^{]*\{\s*background-color:\s*(#[0-9a-f]{6})/.exec(css)![1]!;
  return colours;
}

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const hex = (c: number[]) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
const luminance = (h: string) => {
  const [r, g, b] = rgb(h).map((v) => v / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
};
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
};
/** A colour at `alpha` over another, as bg-gold/20 shows on dusk. */
const over = (top: string, alpha: number, under: string) => hex(rgb(top).map((v, i) => v * alpha + rgb(under)[i]! * (1 - alpha)));

describe("Ultra goth's colours", () => {
  const c = ultraGoth();
  const grounds = { night: c.night!, dusk: c.dusk!, ash: c.ash! };

  it("has every colour Dark has", () => {
    expect(Object.keys(c).sort()).toEqual(["ash", "blood", "blood-bright", "blood-hover", "dusk", "gold", "line", "mist", "night", "parchment"]);
  });

  it("keeps text at 4.5:1 on every background it sits on", () => {
    for (const text of ["parchment", "mist", "gold", "blood-bright"])
      for (const [name, ground] of Object.entries(grounds)) expect(contrast(c[text]!, ground), `${text} on ${name}`).toBeGreaterThanOrEqual(4.5);
    for (const ground of [c.night!, c.dusk!]) {
      // A chosen button, a note, a warning.
      expect(contrast(c.gold!, over(c.gold!, 0.2, ground))).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.parchment!, over(c.gold!, 0.1, ground))).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c["blood-bright"]!, over(c.blood!, 0.1, ground))).toBeGreaterThanOrEqual(4.5);
      expect(contrast(c.parchment!, over(c.blood!, 0.15, ground))).toBeGreaterThanOrEqual(4.5);
    }
    // A button on blood, and pointed at.
    expect(contrast(c.parchment!, c.blood!)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(c.parchment!, c["blood-hover"]!)).toBeGreaterThanOrEqual(4.5);
  });

  it("keeps lines and filled boxes at 3:1 on night and dusk", () => {
    for (const ground of [c.night!, c.dusk!]) {
      expect(contrast(c.line!, ground)).toBeGreaterThanOrEqual(3);
      expect(contrast(c.blood!, ground)).toBeGreaterThanOrEqual(3);
      expect(contrast(c.mist!, ground)).toBeGreaterThanOrEqual(3);
      expect(contrast(over(c.gold!, 0.7, ground), ground)).toBeGreaterThanOrEqual(3);
    }
  });

  it("paints the browser's bar in its night", () => {
    expect(BAR_COLOUR.ultragoth).toBe(c.night);
  });
});
