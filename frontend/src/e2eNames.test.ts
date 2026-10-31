// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Every test in a Playwright worker shares one `run`, whatever its spec file, so two
// tests that sign up the same person, or make a troupe of the same name, clash only
// when they happen to run in the same worker: each passes on its own branch, and main
// breaks once both merge.
const dir = new URL("../e2e/", import.meta.url);
const specs = readdirSync(dir)
  .filter((file) => file.endsWith(".spec.ts"))
  .map((file) => ({ file, text: readFileSync(new URL(file, dir), "utf8") }));

/** The names found more than once, each with the files it is in. */
const repeats = (found: { name: string; file: string }[]) => {
  const files = new Map<string, string[]>();
  for (const { name, file } of found) files.set(name, [...(files.get(name) ?? []), file]);
  return [...files].filter(([, where]) => where.length > 1).map(([name, where]) => `${name} (${where.join(", ")})`);
};

// What each `person(browser, …)` is given, less any context options.
const people = specs.flatMap(({ file, text }) =>
  [...text.matchAll(/person\(browser, ([^()]*)\)/g)].map((m) => ({ file, args: m[1]!.replace(/\{[^}]*\}/g, "") })),
);

describe("the e2e specs' names", () => {
  it("finds every person signed up", () => {
    const calls = specs.reduce((n, { text }) => n + (text.match(/person\(browser,/g)?.length ?? 0), 0);
    expect(people.length).toBe(calls);
    // A name the spec works out can't be checked here.
    expect(people.filter(({ args }) => !args.includes('"')).map(({ file, args }) => `${file}: ${args}`)).toEqual([]);
  });

  it("signs up each person in one test only", () => {
    // A handle is the first 14 characters of the name (`person` in support.ts).
    const names = people.flatMap(({ file, args }) => [...args.matchAll(/"([^"]+)"/g)].map((m) => ({ name: m[1]!.slice(0, 14), file })));
    expect(repeats(names)).toEqual([]);
  });

  it("names each troupe in one test only", () => {
    // Any name made unique by `run` alone, however it is passed: `troupeName = `,
    // `const southName = `, `fill(`, or straight into a request body.
    const troupes = specs.flatMap(({ file, text }) => [...text.matchAll(/`([A-Z][^`$]*)\$\{run\}`/g)].map((m) => ({ name: m[1]!.trim(), file })));
    expect(repeats(troupes)).toEqual([]);
  });

  it("closes each test's browser contexts after it, in every spec", () => {
    // See `closeContextsAfterEach` in support.ts.
    expect(specs.filter(({ text }) => !/^closeContextsAfterEach\(\);$/m.test(text)).map(({ file }) => file)).toEqual([]);
  });
});
