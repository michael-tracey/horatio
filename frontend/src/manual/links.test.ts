// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { checkManual, findManualLinks, type AppLink } from "./check";
import { MANUAL } from "./content";
import { buildManual } from "./manual";

/**
 * The link test (#483): every link in docs/manual goes to a page and heading that
 * exist, every image is there, and every manualLink(...) in the app names a heading
 * in the manual. It reads whatever files are there, so parts can arrive later.
 */

const SRC = fileURLToPath(new URL("..", import.meta.url));

/** Every manualLink call in frontend/src, but for the manual's own code and the tests. */
function appLinks(): AppLink[] {
  return (readdirSync(SRC, { recursive: true }) as string[])
    .filter((file) => /\.tsx?$/.test(file) && !/\.test\.tsx?$/.test(file) && !file.startsWith("manual") && !file.endsWith(".d.ts"))
    .flatMap((file) => findManualLinks(join("frontend/src", file), readFileSync(join(SRC, file), "utf8")));
}

describe("the manual", () => {
  it("is bundled from docs/manual", () => {
    expect(MANUAL.pages.has("README")).toBe(true);
    expect(MANUAL.pages.get("README")!.title).toBeTruthy();
  });

  it("has no broken links, missing images, or app links to a heading that doesn't exist", () => {
    const links = appLinks();
    expect(links.length).toBeGreaterThan(0);
    expect(checkManual(MANUAL, links)).toEqual([]);
  });
});

describe("findManualLinks", () => {
  it("finds each call, its page and anchor, and the line it's on", () => {
    const source = 'const a = manualLink();\nconst b = manualLink("players", "downtimes");\n<Link to={manualLink(\'glossary\')} />\nmanualLink(page, "x")';
    expect(findManualLinks("x.tsx", source)).toEqual([
      { file: "x.tsx", line: 1, page: "README", anchor: null, call: "manualLink()" },
      { file: "x.tsx", line: 2, page: "players", anchor: "downtimes", call: 'manualLink("players", "downtimes")' },
      { file: "x.tsx", line: 3, page: "glossary", anchor: null, call: "manualLink('glossary')" },
      { file: "x.tsx", line: 4, page: "", anchor: null, call: 'manualLink(page, "x")' },
    ]);
  });
});

describe("checkManual", () => {
  const files = {
    "README.md": "# Manual\n\n- [Players](players.md)\n- [Gone](gone.md)\n- [Renamed](players.md#old-heading)",
    "players.md":
      "# Players\n\n## Downtimes\n\nSee [above](#downtimes), [below](#nowhere) and [the sheet](images/players/sheet.png).\n\n![](images/players/sheet.png)\n\n![The cart](images/players/cart.png)\n\n##### Too deep",
    "glossary.md": "## No title\n\nWords.",
  };
  const manual = buildManual(files, { "images/players/sheet.png": "/assets/sheet.png" });

  it("passes a manual whose links all work", () => {
    expect(checkManual(buildManual({ "README.md": "# M\n\n[P](players.md#a)", "players.md": "# P\n\n## A\n\n[back](README.md)" }))).toEqual([]);
  });

  it("names each broken link, missing image and misplaced heading, with its file and line", () => {
    expect(checkManual(manual)).toEqual([
      'glossary.md: should start with exactly one "# Title" heading (it has 0)',
      'players.md: the heading "Too deep" is deeper than ####',
      "players.md:5: the link [below](#nowhere) is broken: players.md has no heading with the anchor #nowhere",
      "players.md:5: the link [the sheet](images/players/sheet.png) isn't to a manual page; write it as page.md#heading",
      "players.md:7: the image images/players/sheet.png has no alt text; say what the screen shows",
      "players.md:9: the image images/players/cart.png is missing from docs/manual",
      "README.md:4: the link [Gone](gone.md) is broken: gone.md doesn't exist",
      "README.md:5: the link [Renamed](players.md#old-heading) is broken: players.md has no heading with the anchor #old-heading",
    ]);
  });

  it("names each app link to a page or heading that doesn't exist", () => {
    const links = findManualLinks(
      "frontend/src/pages/X.tsx",
      'manualLink("players", "downtimes");\nmanualLink("players", "feeding");\nmanualLink("gone");\nmanualLink(name)',
    );
    expect(checkManual(manual, links).filter((e) => e.startsWith("frontend"))).toEqual([
      'frontend/src/pages/X.tsx:2: manualLink("players", "feeding") is broken: players.md has no heading with the anchor #feeding',
      'frontend/src/pages/X.tsx:3: manualLink("gone") is broken: gone.md doesn\'t exist',
      "frontend/src/pages/X.tsx:4: manualLink(name) must name its page and heading as plain strings, so this test can check them",
    ]);
  });
});
