/**
 * How numbers read on charts (#706): whole and in full under 10,000 (0 / 1,000 /
 * 2,000); on an axis that reaches 10,000, short (10K / 20K), one style for the
 * whole axis. Halves keep their half (a trivial boon weighs 0.5).
 */
const full = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const short = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 });

export function formatValue(n: number): string {
  return Math.abs(n) >= 10_000 ? short.format(n) : full.format(n);
}

/** A formatter for one axis's ticks, in one style, from the largest value it shows. */
export function tickFormat(largest: number): (n: number) => string {
  return Math.abs(largest) >= 10_000 ? (n) => short.format(n) : (n) => full.format(n);
}
