import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, makeCustodian, person, run } from "./support";

/**
 * Searching everything from the top bar (#1046): a character and a boon found and
 * opened, at a phone's 375 px (its button) and a desk's 1280 px (its shortcut), with
 * nothing on the screen wider than it.
 */
closeContextsAfterEach();

const onPhone = () => test.info().project.name === "phone";
const headers = { "X-Horatio": "1" };

async function send(page: Page, method: "POST" | "PUT", url: string, data: object = {}) {
  const response = await page.request.fetch(url, { method, headers, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

test("the top bar finds a character and a boon, each opening its page (#1046)", async ({ browser }) => {
  const custodian = await person(browser, "search-custodian");
  makeCustodian(custodian.email);
  await custodian.page.reload();
  const viewport = onPhone() ? { width: 375, height: 800 } : { width: 1280, height: 720 };
  const lead = await person(browser, "search-lead", { viewport });
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Court of Searching ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  // A word only this test's troupe has.
  const word = `Quillon${run}`;
  const npc = await send(l, "POST", `/api/troupes/${troupe.id}/npcs`, { name: `${word} Marsh`, wizard: false });
  await send(l, "PUT", `/api/troupes/${troupe.id}/boon-ledger`, { on: true });
  const [boon] = await send(l, "POST", `/api/troupes/${troupe.id}/boons`, {
    boons: [{ debtor: { character_id: npc.id }, creditor: { name: "The Harbourmaster" }, kind: "minor", made_on: "2026-10-03", reason: "Passage past the docks" }],
    note: "",
  });

  await l.goto(`/troupes/${troupe.id}`);
  const open = async () => {
    // A tap on its button on a phone; at a desk, the shortcut, once the bar is there.
    const button = l.getByRole("banner").getByRole("button", { name: "Search", exact: true });
    if (onPhone()) await button.click();
    else {
      await expect(button).toBeVisible();
      await l.keyboard.press("/");
    }
    const box = l.getByRole("searchbox", { name: "Search everything" });
    await expect(box).toBeFocused();
    await box.fill(word);
    return l.getByRole("dialog", { name: "Search" });
  };

  const search = await open();
  const characters = search.getByRole("region", { name: "Characters" });
  await expect(characters.getByRole("link", { name: `${word} Marsh` })).toBeVisible();
  await expect(search.getByRole("region", { name: "Boons" }).getByRole("link", { name: new RegExp(`${word} Marsh owes The Harbourmaster a minor boon`) })).toBeVisible();
  // The box fits the screen, a phone's whole screen, with nothing to scroll sideways.
  const width = l.viewportSize()!.width;
  if (onPhone()) expect((await search.boundingBox())!.width).toBe(width);
  expect(await l.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  // Each hit a tap target of its own.
  expect((await characters.getByRole("link").first().boundingBox())!.height).toBeGreaterThanOrEqual(44);

  await characters.getByRole("link", { name: `${word} Marsh` }).click();
  await expect(l).toHaveURL(new RegExp(`/characters/${npc.id}$`));
  await expect(search).toBeHidden();

  await (await open()).getByRole("region", { name: "Boons" }).getByRole("link").first().click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons\\?boon=${boon.id}`));
  const panel = onPhone() ? l.getByRole("dialog", { name: `${word} Marsh owes The Harbourmaster` }) : l.getByRole("complementary", { name: `${word} Marsh owes The Harbourmaster` });
  await expect(panel).toBeVisible();
});
