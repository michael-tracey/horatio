// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// A query read as `query.data ?? []` is empty until its answer comes, so a screen
// built on it can say "No characters match" while it is still asking (#568). Each
// one here was checked: it waits for the answer (isPending, <Loaded>, a `loading`
// prop), or what it feeds says nothing about there being none (a menu's options, a
// count). A new one fails this test until it has been checked the same way.
const CHECKED: Record<string, number> = {
  "components/PatronPicker.tsx": 1, // the picker's `loading`
  "pages/CharactersPage.tsx": 2, // shown once the troupes are in
  "pages/TroupesPage.tsx": 1, // isPending first
  "pages/character/AddTraitPanel.tsx": 1, // free choices: the loader, and no adding, until answered (#576)
  "pages/character/Leaving.tsx": 1, // a warning, shown when there are titles
  "pages/character/PowerChoices.tsx": 1, // nothing shown for none
  "pages/character/ResultsTab.tsx": 1, // marks results seen
  "pages/character/Retainers.tsx": 1, // a menu's options
  "pages/character/TroupesTab.tsx": 1, // isPending first
  "pages/custodian/AuditTab.tsx": 1, // isPending first
  "pages/news/PostsSection.tsx": 1, // isPending first
  "pages/nominations/NominationsAbout.tsx": 1, // nothing shown for none
  "pages/play/Others.tsx": 1, // "No one" only once answered
  "pages/rules/RulesPage.tsx": 1, // a menu's options
  "pages/troupe/BookTraitsSection.tsx": 1, // isLoading first
  "pages/troupe/CyclePage.tsx": 1, // facts, once the cycle is in
  "pages/troupe/EquipmentEditor.tsx": 1, // shown when there are some
  "pages/troupe/FeedingTerritories.tsx": 2, // isPending first
  "pages/troupe/HouseSplat.tsx": 1, // a picker, shown for two or more
  "pages/troupe/NewNpc.tsx": 1, // a menu's options
  "pages/troupe/PlayersTab.tsx": 1, // staff roles beside names
  "pages/troupe/ProfileEditor.tsx": 1, // a menu's options
  "pages/troupe/QuestPage.tsx": 1, // menus' options
  "pages/troupe/QuestsTab.tsx": 1, // a menu's options
  "pages/troupe/ResponsesTab.tsx": 1, // menus' options
  "pages/troupe/RosterTab.tsx": 1, // only once the search has answered
  "pages/troupe/SettingsTab.tsx": 1, // isPending beside it
  "pages/troupe/ShareSettingsTab.tsx": 1, // shown when there are some
  "pages/troupe/TitlesTab.tsx": 1, // isPending first
};

const src = new URL(".", import.meta.url).pathname;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

describe("queries read as empty while they load", () => {
  it("are each checked for an empty state shown before the answer", () => {
    const found = Object.fromEntries(
      files(src)
        .map((path) => [relative(src, path), readFileSync(path, "utf8").match(/\.data \?\? \[\]/g)?.length ?? 0] as const)
        .filter(([, count]) => count > 0),
    );
    expect(found).toEqual(CHECKED);
  });
});
