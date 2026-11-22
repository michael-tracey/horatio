// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// A ratchet on hand-made controls in the pages (#924). Each raw `<button>`, `<input>` or
// `window.confirm` is a place where sizes, focus rings and colours can drift from the kit
// in `components/`. The numbers below are today's counts: a page may lose raw controls
// but not gain them. Whoever takes some out lowers the number in the same PR.
const dir = new URL("./pages/", import.meta.url);
const pages = (readdirSync(dir, { recursive: true }) as string[])
  .filter((file) => file.endsWith(".tsx") && !file.endsWith(".test.tsx"))
  .map((file) => readFileSync(new URL(file, dir), "utf8"));

const raw: { what: string; pattern: RegExp; max: number; use: string }[] = [
  // `\b` so that `<ButtonGroup` and the like don't count; JSX is case-sensitive anyway.
  // 162: the boon ledger's totals strip (#977), a number with a small label, not a Button's shape.
  { what: "<button", pattern: /<button\b/g, max: 162, use: "`Button` (components/ui.tsx) or `LinkButton` (components/LinkButton.tsx)" },
  // 162: the blog article's hidden picture input (#1156), opened by a Button, as a post's is.
  // 163: the slider sizing a blog article's hero picture (#1157), as the crop dialog's does.
  // 164: the file chooser for a picture in a blog article's words (#1163), which `Input` doesn't take.
  {
    what: "<input",
    pattern: /<input\b/g,
    max: 164,
    use: "`Input` (components/ui.tsx), or `Checkbox`, `Toggle`, `RadioList` or `Segmented` for a checkbox or radio",
  },
  { what: "<select", pattern: /<select\b/g, max: 7, use: "`Select` (components/ui.tsx)" },
  { what: "<textarea", pattern: /<textarea\b/g, max: 2, use: "`Textarea` (components/ui.tsx)" },
  {
    what: 'type="checkbox"',
    pattern: /type="checkbox"/g,
    max: 101,
    use: "`Checkbox` (components/Checkbox.tsx) or `Toggle` (components/Toggle.tsx)",
  },
  {
    what: 'type="radio"',
    pattern: /type="radio"/g,
    max: 37,
    use: "`RadioList` (components/RadioList.tsx) or `Segmented` (components/Segmented.tsx)",
  },
  { what: "window.confirm", pattern: /window\.confirm\b/g, max: 0, use: "`useConfirm` or `ConfirmDialog` (components/ConfirmDialog.tsx)" },
  { what: "window.alert", pattern: /window\.alert\b/g, max: 1, use: "`useConfirm` or `ConfirmDialog` (components/ConfirmDialog.tsx)" },
];

describe("the pages' hand-made controls", () => {
  it("finds the pages", () => {
    expect(pages.length).toBeGreaterThan(100);
  });

  it.each(raw)("has no more $what than before", ({ what, pattern, max, use }) => {
    const count = pages.reduce((n, text) => n + (text.match(pattern)?.length ?? 0), 0);
    expect(
      count,
      `src/pages has ${count} raw ${what}, more than the ${max} allowed. Use ${use} instead. ` +
        `If a page really needs a raw one, raise its number in kitUse.test.ts in the same PR, with a comment saying why.`,
    ).toBeLessThanOrEqual(max);
  });
});
