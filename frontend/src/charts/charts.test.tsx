import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { scaleBand, scaleLinear } from "d3-scale";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { assignSlots, ChartFrame, clanKey, clanSlots, diverging, formatValue, Legend, sequential, series, tickFormat, ticksOf, useMarks } from ".";
import { CATEGORICAL_DARK, CATEGORICAL_PRINT, SEQUENTIAL } from "./palette";

afterEach(cleanup);

describe("categorical slots", () => {
  it("are given in order, one each, never cycling", () => {
    const slots = assignSlots(["Minor", "Major", "Trivial"]);
    expect([...slots]).toEqual([
      ["Minor", 1],
      ["Major", 2],
      ["Trivial", 3],
    ]);
  });

  it("fold everything past the cap into Other, keeping the last slot for it", () => {
    const keys = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];
    const slots = assignSlots(keys);
    expect(keys.map((k) => slots.get(k))).toEqual([1, 2, 3, 4, 5, 6, 7, "other", "other"]);
    // Eight fit exactly, with no Other.
    expect([...assignSlots(keys.slice(0, 8)).values()]).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
  });

  it("allow only three where any two marks can meet", () => {
    expect([...assignSlots(["a", "b", "c"], "allPairs").values()]).toEqual([1, 2, 3]);
    expect([...assignSlots(["a", "b", "c", "d"], "allPairs").values()]).toEqual([1, 2, "other", "other"]);
  });
});

describe("clan colours", () => {
  it("count a bloodline as its clan, and no clan as No clan", () => {
    expect(clanKey("Gangrel: Coyote")).toBe("Gangrel");
    expect(clanKey("Nosferatu")).toBe("Nosferatu");
    expect(clanKey("")).toBe("No clan");
    expect(clanKey(null)).toBe("No clan");
  });

  it("go to a troupe's clans by how many characters each has, then by name", () => {
    const slots = clanSlots([
      { clan: "Ventrue", count: 3 },
      { clan: "Brujah", count: 5 },
      { clan: "Gangrel: Coyote", count: 2 },
      { clan: "Gangrel", count: 1 },
      { clan: "Toreador", count: 3 },
    ]);
    expect([...slots]).toEqual([
      ["Brujah", 1],
      ["Gangrel", 2],
      ["Toreador", 3],
      ["Ventrue", 4],
    ]);
  });

  it("stay the same whatever one chart shows, given the troupe's counts", () => {
    const troupe = [
      { clan: "Tremere", count: 4 },
      { clan: "Malkavian", count: 2 },
    ];
    expect(clanSlots(troupe).get("Malkavian")).toBe(clanSlots([...troupe].reverse()).get("Malkavian"));
  });
});

describe("colours", () => {
  it("name each slot by its custom property, and Other by its grey", () => {
    expect(series(3)).toBe("var(--chart-series-3)");
    expect(series("other")).toBe("var(--chart-other)");
  });

  it("are set in charts.css as palette.ts has them, for the screen and for print", () => {
    const css = readFileSync(join(__dirname, "charts.css"), "utf8");
    const [screenCss, printCss] = css.split("@media print");
    CATEGORICAL_DARK.forEach((hex, i) => expect(screenCss).toContain(`--chart-series-${i + 1}: ${hex};`));
    CATEGORICAL_PRINT.forEach((hex, i) => expect(printCss).toContain(`--chart-series-${i + 1}: ${hex};`));
  });

  it("stand out at least 3:1 from every surface a chart sits on in Dark and Ultra goth", () => {
    const luminance = (hex: string) => {
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    const contrast = (a: string, b: string) => {
      const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
      return (hi! + 0.05) / (lo! + 0.05);
    };
    // index.css: Dark's night and dusk, Ultra goth's night and dusk.
    for (const surface of ["#141016", "#1e1922", "#0a0909", "#131011"]) {
      for (const hex of CATEGORICAL_DARK) expect(contrast(hex, surface)).toBeGreaterThanOrEqual(3);
    }
  });

  it("step the sequential ramp in seven classes, clamped", () => {
    expect(sequential(0)).toBe(SEQUENTIAL[0]);
    expect(sequential(1)).toBe(SEQUENTIAL[6]);
    expect(sequential(-3)).toBe(SEQUENTIAL[0]);
    expect(sequential(0.5)).toBe(SEQUENTIAL[3]);
  });

  it("put grey at nothing, blue below and red above on the diverging scale", () => {
    expect(diverging(0)).toBe("rgb(56, 56, 53)");
    expect(diverging(-1)).toBe("rgb(57, 135, 229)");
    expect(diverging(1)).toBe("rgb(230, 103, 103)");
    expect(diverging(5)).toBe(diverging(1));
  });
});

describe("numbers", () => {
  it("read in full under 10,000, halves kept, and short above", () => {
    expect(formatValue(0.5)).toBe("0.5");
    expect(formatValue(1234)).toBe("1,234");
    expect(formatValue(12_500)).toBe("12.5K");
    expect(formatValue(2_500_000)).toBe("2.5M");
  });

  it("keep one style along an axis, from its largest tick", () => {
    expect(tickFormat(8000)(2000)).toBe("2,000");
    expect(tickFormat(20_000)(2000)).toBe("2K");
  });
});

describe("axes", () => {
  it("tick a band scale at each band's middle, by name", () => {
    const x = scaleBand(["Minor", "Major"], [0, 100]);
    expect(ticksOf(x)).toEqual([
      { at: 25, label: "Minor", key: "Minor" },
      { at: 75, label: "Major", key: "Major" },
    ]);
  });

  it("tick a continuous scale at round values", () => {
    const y = scaleLinear([0, 70], [100, 0]);
    expect(ticksOf(y, 4).map((t) => t.label)).toEqual(["0", "20", "40", "60"]);
  });
});

describe("Legend", () => {
  it("shows nothing for one series: the title names it", () => {
    const { container } = render(<Legend items={[{ key: "a", label: "Open", colour: series(1) }]} />);
    expect(container.innerHTML).toBe("");
  });

  it("toggles a series, keeping its entry", () => {
    let toggled = "";
    render(
      <Legend
        items={[
          { key: "r", label: "Registered", colour: series(1), mark: "line" },
          { key: "s", label: "Settled", colour: series(2), mark: "line" },
        ]}
        hidden={new Set(["s"])}
        onToggle={(k) => (toggled = k)}
      />,
    );
    expect(screen.getByRole("button", { name: "Registered" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Settled" }).getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Settled" }));
    expect(toggled).toBe("s");
  });
});

describe("ChartFrame", () => {
  // jsdom lays nothing out: give every element a width, so the plot draws.
  const width = Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth");
  beforeAll(() => Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 400 }));
  afterAll(() => width && Object.defineProperty(HTMLElement.prototype, "clientWidth", width));

  const table = { columns: [{ key: "type", label: "Type" }, { key: "open", label: "Open", numeric: true }], rows: [{ type: "Minor", open: 12 }] };

  function Bars() {
    const mark = useMarks();
    return <rect {...mark({ title: "Minor", rows: [{ label: "open", value: "12" }] }, { x: 50, y: 20 })} />;
  }

  it("draws the plot, with its table there for screen readers", () => {
    render(
      <ChartFrame title="Open boons" description="By type." height={120} table={table}>
        {() => <Bars />}
      </ChartFrame>,
    );
    const figure = screen.getByRole("figure", { name: "Open boons" });
    const plot = within(figure).getByRole("group", { name: "Open boons" });
    expect(document.getElementById(plot.getAttribute("aria-describedby")!)?.textContent).toBe("By type.");
    expect(within(figure).getByRole("img", { name: "Minor: open 12" })).toBeTruthy();
    // The twin table, hidden from sight, not from screen readers.
    expect(within(figure).getByRole("table", { name: "Open boons" }).parentElement?.classList.contains("sr-only")).toBe(true);
  });

  it("shows a mark's tooltip on keyboard focus, and drops it on Escape", () => {
    render(
      <ChartFrame title="Open boons" description="By type." height={120} table={table}>
        {() => <Bars />}
      </ChartFrame>,
    );
    const mark = screen.getByRole("img", { name: "Minor: open 12" });
    fireEvent.focus(mark);
    expect(screen.getByText("12", { selector: "strong" })).toBeTruthy();
    fireEvent.keyDown(mark, { key: "Escape" });
    expect(screen.queryByText("12", { selector: "strong" })).toBeNull();
  });

  it("keeps a tapped tooltip until the next tap", () => {
    render(
      <ChartFrame title="Open boons" description="By type." height={120} table={table}>
        {() => <Bars />}
      </ChartFrame>,
    );
    const mark = screen.getByRole("img", { name: "Minor: open 12" });
    fireEvent.click(mark);
    fireEvent.pointerLeave(mark);
    expect(screen.getByText("12", { selector: "strong" })).toBeTruthy();
    fireEvent.click(mark);
    expect(screen.queryByText("12", { selector: "strong" })).toBeNull();
  });

  it("swaps the plot for its table on request", () => {
    render(
      <ChartFrame title="Open boons" description="By type." height={120} table={table}>
        {() => <Bars />}
      </ChartFrame>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Show as table" }));
    expect(screen.queryByRole("group", { name: "Open boons" })).toBeNull();
    const shown = screen.getByRole("table", { name: "Open boons" });
    expect(shown.parentElement?.classList.contains("sr-only")).toBe(false);
    expect(within(shown).getByRole("cell", { name: "12" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show as chart" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("says when there is nothing to show, with no table button", () => {
    render(
      <ChartFrame title="Open boons" description="By type." height={120} table={table} state="empty" empty="No boons registered yet.">
        {() => <Bars />}
      </ChartFrame>,
    );
    expect(screen.getByText("No boons registered yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Show as table" })).toBeNull();
  });
});
