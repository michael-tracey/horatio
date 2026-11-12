/**
 * How numbers read on charts (#706): whole and in full under 10,000 (0 / 1,000 /
 * 2,000); on an axis that reaches 10,000, short (10K / 20K), one style for the
 * whole axis. Halves keep their half (a trivial boon weighs 0.5).
 */
const full = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

// Written out here, not with Intl's compact notation, whose letters differ
// between versions of the browser's locale data ("12.5K" in one, "12.5k" in another).
const STEPS = [
  { at: 1e9, unit: "B" },
  { at: 1e6, unit: "M" },
  { at: 1e3, unit: "K" },
] as const;

function short(n: number): string {
  const step = STEPS.find((s) => Math.abs(n) >= s.at);
  return step ? `${full.format(n / step.at)}${step.unit}` : full.format(n);
}

export function formatValue(n: number): string {
  return Math.abs(n) >= 10_000 ? short(n) : full.format(n);
}

/** A formatter for one axis's ticks, in one style, from the largest value it shows. */
export function tickFormat(largest: number): (n: number) => string {
  return Math.abs(largest) >= 10_000 ? short : (n) => full.format(n);
}
