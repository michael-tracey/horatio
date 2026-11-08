import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, backstoryOptional, builtVampire, closeContextsAfterEach, makeCustodian, person, run, shots } from "./support";

/** A character's Jyhad card (#537): a hidden, just-for-fun card in the style of a VTES crypt card. */

closeContextsAfterEach();

test("a player taps their clan seven times and finds a Jyhad card, and staff open it from the ⋯ on the Characters list (#537)", async ({ browser }) => {
  const custodian = await person(browser, "jyhad-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "jyhad-lead");
  const player = await person(browser, "jyhad-player");
  const headers = { "X-Horatio": "1" };
  const troupeName = `Crypt of Asheville ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(lead.page, troupeId);

  // A Toreador neonate with three disciplines, all inferior, and a picture.
  const p = player.page;
  const id = await builtVampire(p, "Celestine", "Toreador", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
  });
  const picture = await p.request.post(`/api/characters/${id}/picture`, {
    headers,
    multipart: { file: { name: "portrait.jpg", mimeType: "image/jpeg", buffer: readFileSync("e2e/portrait.jpg") } },
  });
  expect(picture.status(), await picture.text()).toBeLessThan(300);

  // Nothing says it's there. With no Dark Pack symbols on the server, the clan's name
  // in the header takes the taps: six do nothing, the seventh opens the card.
  await p.goto(`/characters/${id}`);
  const clan = p.locator("h1 + p").getByText("Toreador", { exact: true });
  for (let i = 0; i < 6; i++) await clan.click();
  await expect(p).toHaveURL(new RegExp(`/characters/${id}$`));
  await clan.click();
  const card = p.getByRole("article", { name: "Jyhad card of Celestine" });
  await expect(card).toBeVisible();
  // Three inferior disciplines are 3 points: a neonate's capacity 4. No VTES symbols here, so their letters.
  await expect(card).toContainText("Capacity 4.");
  await expect(card.getByRole("list", { name: "Disciplines" }).getByRole("listitem")).toHaveText(["aus", "cel", "pre"]);
  await expect(card.getByText("Unofficial · not a real card · made with Horatio", { exact: true })).toBeAttached();

  // The player writes its text; nothing is suggested.
  await expect(p.getByLabel("Card text")).toHaveValue("");
  await p.getByLabel("Card text").fill("Once each turn, Celestine may burn a blood to untap a Toreador.");
  await p.getByLabel("Flavour line").fill("Beauty is a knife.");
  await p.getByRole("button", { name: "Save text" }).click();
  await expect(p.getByRole("button", { name: "Save text" })).toBeDisabled();
  await p.screenshot(shots("jyhad-card"));

  // Downloaded as an image, for Discord.
  const download = p.waitForEvent("download");
  await p.getByRole("button", { name: "Download image" }).click();
  expect((await download).suggestedFilename()).toBe("Celestine Jyhad card.png");

  // Once the troupe has it, its staff find it in the character's ⋯.
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBe(201);
  const l = lead.page;
  const accepted = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBe(200);
  await l.goto(`/troupes/${troupeId}/characters`);
  await l.getByRole("button", { name: "Actions for Celestine" }).click();
  const opened = l.context().waitForEvent("page");
  await l.getByRole("menuitem", { name: "Show Jyhad card" }).click();
  const shown = await opened;
  const staffCard = shown.getByRole("article", { name: "Jyhad card of Celestine" });
  await expect(staffCard).toBeVisible();
  await expect(staffCard.getByText("Beauty is a knife.", { exact: true })).toBeAttached();
  // The text is the player's to write, not staff's.
  await expect(shown.getByLabel("Card text")).toHaveCount(0);
  await expect(shown.getByRole("link", { name: "← Back" })).toHaveAttribute("href", `/troupes/${troupeId}/characters`);
});
