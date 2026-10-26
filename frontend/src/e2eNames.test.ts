// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Every test in a Playwright worker shares one `run`, so two tests that sign up the
// same person, or make a troupe of the same name, clash only when they happen to run
// in the same worker: each passes on its own branch, and main breaks once both merge.
const spec = readFileSync(new URL("../e2e/journey.spec.ts", import.meta.url), "utf8");

const repeats = (names: string[]) => [...new Set(names.filter((n, i) => names.indexOf(n) !== i))];

describe("the e2e journey's names", () => {
  it("signs up each person in one test only", () => {
    // A handle is the first 14 characters of the name (`person` in the spec).
    const people = [...spec.matchAll(/person\(browser, "([^"]+)"/g)].map((m) => m[1]!.slice(0, 14));
    expect(repeats(people)).toEqual([]);
  });

  it("names each troupe in one test only", () => {
    // Any name made unique by `run` alone, however it is passed: `troupeName = `,
    // `const southName = `, `fill(`, or straight into a request body.
    const troupes = [...spec.matchAll(/`([A-Z][^`$]*)\$\{run\}`/g)].map((m) => m[1]!.trim());
    expect(repeats(troupes)).toEqual([]);
  });
});
