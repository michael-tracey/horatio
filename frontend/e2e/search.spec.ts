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
    const button = l.getByRole("banner").getByRole("button", { name: "Search everything" });
    if (onPhone()) await button.click();
    else {
      await expect(button).toBeVisible();
      await l.keyboard.press("/");
    }
    const box = l.getByRole("searchbox", { name: "Search for" });
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

  // On the character's page its home troupe is the current one (#1147): its hits needn't name it.
  const boons = (await open()).getByRole("region", { name: "Boons" });
  await expect(boons.getByRole("link").first()).toContainText("Passage past the docks");
  await expect(boons.getByRole("link").first()).not.toContainText(`Court of Searching ${run}`);
  await boons.getByRole("link").first().click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupe.id}/boons\\?boon=${boon.id}`));
  const panel = onPhone() ? l.getByRole("dialog", { name: `${word} Marsh owes The Harbourmaster` }) : l.getByRole("complementary", { name: `${word} Marsh owes The Harbourmaster` });
  await expect(panel).toBeVisible();
});

test("Find a setting on Customise, and the top bar, open a setting where it is (#1047, #1133)", async ({ browser }) => {
  const custodian = await person(browser, "findset-custodian");
  makeCustodian(custodian.email);
  await custodian.page.reload();
  const viewport = onPhone() ? { width: 375, height: 800 } : { width: 1280, height: 720 };
  const lead = await person(browser, "findset-lead", { viewport });
  const narrator = await person(browser, "findset-narrator", { viewport });
  const assistant = await person(browser, "findset-assistant", { viewport });
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Court of Finding ${run}`, lead_handle: lead.handle });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: narrator.handle, role: "narrator" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: assistant.handle, role: "assistant_storyteller" });
  const l = lead.page;
  const base = `/troupes/${troupe.id}`;
  const width = l.viewportSize()!.width;

  // From Setup: part of a card's name, and the card is scrolled to and glows on its part of Troupe settings.
  await l.goto(`${base}/customise`);
  const find = l.getByRole("searchbox", { name: "Find a setting" });
  await find.fill("ceiling");
  const found = l.getByRole("list", { name: "Settings found" });
  const hit = found.getByRole("link", { name: /^XP floor and ceiling/ });
  await expect(hit).toBeVisible();
  // Nothing wider than the screen, and each a tap target.
  expect(await l.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  expect((await hit.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await hit.click();
  await expect(l).toHaveURL(new RegExp(`${base}/settings/xp#settings-xp-range$`));
  const card = l.getByRole("region", { name: "XP floor and ceiling" });
  await expect(card).toBeInViewport();
  await expect(card).toHaveAttribute("data-found", "");
  await expect(find).toHaveValue("");

  // From another Customise tab, a word of what it does: Enter opens the first, its tab's Settings open at its card.
  await l.goto(`${base}/specializations`);
  await find.fill("stickers");
  await expect(found.getByRole("link").first()).toContainText("Badges");
  await find.press("Enter");
  await expect(l).toHaveURL(new RegExp(`${base}/play#settings-badges$`));
  const dialog = l.getByRole("dialog", { name: "At game settings" });
  await expect(dialog.getByRole("region", { name: "Badges" })).toBeInViewport();
  await l.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // The top bar finds them too, on the troupe's pages.
  await l.goto(base);
  if (onPhone()) await l.getByRole("banner").getByRole("button", { name: "Search everything" }).click();
  else {
    await expect(l.getByRole("banner").getByRole("button", { name: "Search everything" })).toBeVisible();
    await l.keyboard.press("/");
  }
  await l.getByRole("searchbox", { name: "Search for" }).fill("throw pictures");
  const settings = l.getByRole("dialog", { name: "Search" }).getByRole("region", { name: "Settings" });
  await settings.getByRole("link", { name: /^Throw pictures/ }).click();
  await expect(l).toHaveURL(new RegExp(`${base}/play#settings-throw-pictures$`));
  await expect(l.getByRole("dialog", { name: "At game settings" }).getByRole("region", { name: "Throw pictures" })).toBeVisible();

  // An assistant storyteller finds a setting on Customise, but not from the top bar (#1133).
  const a = assistant.page;
  await a.goto(`${base}/customise`);
  await a.getByRole("searchbox", { name: "Find a setting" }).fill("ceiling");
  await expect(a.getByRole("list", { name: "Settings found" }).getByRole("link", { name: /^XP floor and ceiling/ })).toBeVisible();
  await a.goto(base);
  if (onPhone()) await a.getByRole("banner").getByRole("button", { name: "Search everything" }).click();
  else {
    await expect(a.getByRole("banner").getByRole("button", { name: "Search everything" })).toBeVisible();
    await a.keyboard.press("/");
  }
  await a.getByRole("searchbox", { name: "Search for" }).fill("throw pictures");
  const assistantSearch = a.getByRole("dialog", { name: "Search" });
  await expect(assistantSearch.getByRole("region", { name: "Help" })).toBeVisible();
  await expect(assistantSearch.getByRole("region", { name: "Settings" })).toHaveCount(0);

  // A narrator has no Customise, and finds no settings.
  const n = narrator.page;
  await n.goto(base);
  await expect(n.getByRole("searchbox", { name: "Find a setting" })).toHaveCount(0);
  if (onPhone()) await n.getByRole("banner").getByRole("button", { name: "Search everything" }).click();
  else {
    await expect(n.getByRole("banner").getByRole("button", { name: "Search everything" })).toBeVisible();
    await n.keyboard.press("/");
  }
  await n.getByRole("searchbox", { name: "Search for" }).fill("throw pictures");
  const search = n.getByRole("dialog", { name: "Search" });
  await expect(search.getByRole("region", { name: "Help" })).toBeVisible();
  await expect(search.getByRole("region", { name: "Settings" })).toHaveCount(0);
});
