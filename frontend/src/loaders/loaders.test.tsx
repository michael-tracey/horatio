import { onlineManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Loaded, Loading, LOADING_DELAY_MS } from "../components/ui";
import { loaders } from "./art";
import { withLoadingScreen } from "./indexHtml";
import { cachedMotif, chooseOnLoad, DEFAULT_MOTIF, MOTIF_KEY, motifFor, MOTIFS, rememberMotif } from "./motifs";

beforeEach(() => {
  vi.useFakeTimers();
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  onlineManager.setOnline(true);
});

/** On a page with the API never asked, so the motif is the one kept on the device. */
function show(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const wait = (ms: number) => act(() => vi.advanceTimersByTime(ms));

describe("Loading", () => {
  it("shows nothing for a moment, so a quick answer doesn't flash it", () => {
    show(<Loading />);
    wait(LOADING_DELAY_MS - 10);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("then shows the loading animation, as a status with its label", () => {
    const { container } = show(<Loading />);
    wait(LOADING_DELAY_MS);
    expect(screen.getByRole("status", { name: "Loading…" })).toBeTruthy();
    expect(container.querySelector(".loader-block.loader-drip svg")).toBeTruthy();
  });

  it("uses the motif last seen on this device until the custodian's is known", () => {
    rememberMotif("candle");
    const { container } = show(<Loading compact label="Searching…" />);
    wait(LOADING_DELAY_MS);
    expect(screen.getByRole("status", { name: "Searching…" }).textContent).toBe("Searching…");
    expect(container.querySelector(".loader-compact.loader-candle")).toBeTruthy();
  });

  it("says the screen needs a connection when offline, at once", () => {
    onlineManager.setOnline(false);
    show(<Loading />);
    expect(screen.getByText(/needs a connection/)).toBeTruthy();
  });
});

describe("Loaded", () => {
  it("shows the loader until the answer, never what it would say for none", () => {
    const none = (items: string[]) => (items.length ? items.join(", ") : "No characters match.");
    const { rerender } = show(<Loaded query={{ data: undefined as string[] | undefined, error: null }}>{none}</Loaded>);
    wait(LOADING_DELAY_MS);
    expect(screen.getByRole("status", { name: "Loading…" })).toBeTruthy();
    expect(screen.queryByText("No characters match.")).toBeNull();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <Loaded query={{ data: [] as string[], error: null }}>{none}</Loaded>
      </QueryClientProvider>,
    );
    expect(screen.getByText("No characters match.")).toBeTruthy();
  });

  it("shows the error, not the loader, when the question failed", () => {
    show(<Loaded query={{ data: undefined, error: new Error("Down for a moment.") }}>{() => "found"}</Loaded>);
    expect(screen.getByRole("alert").textContent).toBe("Down for a moment.");
  });
});

describe("the motifs", () => {
  it("are each drawn, with a name for the custodian", () => {
    expect(Object.keys(loaders).sort()).toEqual([...MOTIFS].sort());
    for (const m of MOTIFS) expect(loaders[m].label).not.toBe("");
  });

  it("each have their styles, and a still version where less motion is asked for", () => {
    const css = readFileSync(join(process.cwd(), "src/loaders/loaders.css"), "utf8");
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const m of MOTIFS) {
      expect(css).toMatch(new RegExp(`\\.loader-${m} [^{]*\\{[^}]*animation`));
      expect(reduced).toContain(`.loader-${m} `);
    }
  });

  it("go by splat, with the default for a splat without its own", () => {
    const bySplat = { default: "heartbeat", ghoul: "rising" } as const;
    expect(motifFor(bySplat)).toBe("heartbeat");
    expect(motifFor(bySplat, "ghoul")).toBe("rising");
    expect(motifFor(bySplat, "werewolf")).toBe("heartbeat");
    expect(motifFor(undefined)).toBe(DEFAULT_MOTIF);
  });

  it("fall back to the blood drip where nothing is kept, or the device keeps nothing", () => {
    expect(cachedMotif()).toBe("drip");
    localStorage.setItem(MOTIF_KEY, "quill");
    expect(cachedMotif()).toBe("drip");
    const refusing = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } } as unknown as Storage;
    expect(cachedMotif(refusing)).toBe("drip");
    expect(() => rememberMotif("candle", refusing)).not.toThrow();
  });
});

describe("index.html's loading screen", () => {
  const page = withLoadingScreen(
    '<head><!-- loaders.css --></head><body><div id="root"><!-- loading screen --></div></body>',
    ".splash { color: red; }",
  );

  it("has the styles, and every motif under the logo", () => {
    expect(page).toContain("<style>\n.splash { color: red; }</style>");
    for (const m of MOTIFS) expect(page).toContain(`loader-full loader-${m}`);
    expect(page).toContain('role="status"');
    expect(page).not.toContain('rel="preload"');
  });

  it("shows the motif last seen on this device", () => {
    const run = () => {
      document.body.innerHTML = renderToStaticMarkup(<div id="root" />);
      document.getElementById("root")!.innerHTML = '<div class="splash"></div>';
      new Function(chooseOnLoad())();
      return document.querySelector(".splash")!.getAttribute("data-motif");
    };
    expect(run()).toBe("drip");
    rememberMotif("heartbeat");
    expect(run()).toBe("heartbeat");
    localStorage.setItem(MOTIF_KEY, "<script>");
    expect(run()).toBe("drip");
  });
});
