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

test("a Jyhad card on its clan's crypt card template, which the custodian uploads in Tools (#850)", async ({ browser }) => {
  const custodian = await person(browser, "jyhad-tmpl-cust");
  makeCustodian(custodian.email);
  const player = await person(browser, "jyhad-tmpl-play");
  const headers = { "X-Horatio": "1" };

  // The templates are the Dark Pack's and the e2e server has no Dark Pack folder, so
  // the server's answers are stood in for: the Tools card's, and the card's template,
  // drawn here like a 2020 one (the frame, its transparent oval, the pale text box).
  const c = custodian.page;
  const empty = {
    configured: true,
    writable: true,
    agreement: "https://www.paradoxinteractive.com/games/world-of-darkness/community/dark-pack-agreement",
    uploaded_at: null,
    templates: [],
    clans: [
      { name: "Tzimisce", symbol: null },
      { name: "Ventrue", symbol: null },
    ],
    missing: ["Tzimisce", "Ventrue"],
  };
  const uploaded = {
    ...empty,
    uploaded_at: new Date().toISOString(),
    templates: [{ key: "tzimisce", name: "Tzimisce", uploaded_from: "2020_Crypt_Tzimisce.png" }],
    clans: [
      { name: "Tzimisce", symbol: "Tzimisce" },
      { name: "Ventrue", symbol: null },
    ],
    missing: ["Ventrue"],
  };
  let now: object = empty;
  const sent: string[] = [];
  await c.route("**/api/tools/crypt-templates", async (route) => {
    if (route.request().method() === "POST") {
      sent.push(route.request().postDataBuffer()?.toString("latin1") ?? "");
      now = uploaded;
      await route.fulfill({ json: { tool: uploaded, added: ["Tzimisce"], skipped: [{ name: "2020_Crypt_Unicorn.png", why: "not a 2020_Crypt_<Clan>.png file of a clan Horatio knows" }] } });
    } else await route.fulfill({ json: now });
  });
  await c.goto("/custodian/tools");
  const tool = c.locator("section").filter({ has: c.getByRole("heading", { name: "Jyhad card templates", exact: true }) });
  await expect(tool.getByText("None on this server yet.")).toBeVisible();
  const choose = tool.getByRole("button", { name: "Upload templates" });
  await expect(choose).toBeDisabled();
  await tool.getByLabel("I accept Paradox's Dark Pack Agreement for this server").check();
  await tool.getByLabel("Templates to upload").setInputFiles([
    { name: "2020_Crypt_Tzimisce.png", mimeType: "image/png", buffer: Buffer.from("tzimisce") },
    { name: "2020_Crypt_Unicorn.png", mimeType: "image/png", buffer: Buffer.from("unicorn") },
  ]);
  await expect(tool.getByRole("status")).toContainText("Added: Tzimisce.");
  await expect(tool.getByRole("status")).toContainText("2020_Crypt_Unicorn.png: not a 2020_Crypt_<Clan>.png file of a clan Horatio knows");
  expect(sent[0]).toContain('filename="2020_Crypt_Tzimisce.png"');
  expect(sent[0]).toContain('name="accept_licence"');
  const status = tool.getByRole("region", { name: "On the server" });
  await expect(status).toContainText("1 template, last uploaded");
  await expect(status).toContainText("Horatio's clans and bloodlines with a template: 1 of 2. Horatio's frame for: Ventrue.");

  // A Tzimisce with a picture.
  const p = player.page;
  const id = await builtVampire(p, "Sorin", "Tzimisce", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Animalism", 2], ["Auspex", 1], ["Vicissitude", 1]],
  });
  const picture = await p.request.post(`/api/characters/${id}/picture`, {
    headers,
    multipart: { file: { name: "portrait.jpg", mimeType: "image/jpeg", buffer: readFileSync("e2e/portrait.jpg") } },
  });
  expect(picture.status(), await picture.text()).toBeLessThan(300);
  await p.goto("/characters");
  const png = await p.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 819;
    canvas.height = 1114;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#3c4632";
    ctx.fillRect(0, 0, 819, 1114);
    ctx.fillStyle = "#cdc8b9";
    ctx.fillRect(188, 858, 546, 146);
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath();
    ctx.ellipse(459.5, 497.5, 265.5, 344.5, 0, 0, Math.PI * 2);
    ctx.fill();
    return canvas.toDataURL("image/png").split(",")[1]!;
  });
  // KRCG's white-bordered symbols (#869), stood in for: a white square round black.
  const edged = await p.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, 64, 64);
    ctx.fillStyle = "#000000";
    ctx.fillRect(6, 6, 52, 52);
    return canvas.toDataURL("image/png").split(",")[1]!;
  });
  const template = `/api/characters/${id}/jyhad-card/template.webp?v=1`;
  await p.route("**/api/characters/*/jyhad-card/template.webp**", (route) => route.fulfill({ contentType: "image/png", body: Buffer.from(png, "base64") }));
  await p.route("**/api/vtes-symbols/webp_wb/**", (route) => route.fulfill({ contentType: "image/png", body: Buffer.from(edged, "base64") }));
  await p.route(`**/api/characters/${id}/jyhad-card`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const real = await route.fetch();
    const card = await real.json();
    const disciplines = card.disciplines.map((d: { abbreviation: string; superior: boolean }) => ({
      ...d,
      symbol: `/api/vtes-symbols/webp_wb/disc/${d.superior ? "sup" : "inf"}/${d.abbreviation}.webp`,
      bordered: true,
    }));
    await route.fulfill({ response: real, json: { ...card, template, disciplines } });
  });

  await p.goto(`/print/characters/${id}/jyhad`);
  const card = p.getByRole("article", { name: "Jyhad card of Sorin" });
  await expect(card).toHaveAttribute("data-template", template);
  await expect(card.locator(`img[src="${template}"]`)).toBeVisible();
  // The disciplines down the sidebar; the template's own lines say it isn't for play,
  // so only Horatio's and KRCG's go on the edge below it.
  // White-bordered, as a printed card has them (#869): shown as they are, untinted, and
  // stacked up the sidebar from its foot, beside the text box.
  const disciplines = card.getByRole("list", { name: "Disciplines" }).getByRole("listitem");
  await expect(disciplines).toHaveCount(3);
  await expect(card.locator('img[src^="/api/vtes-symbols/webp_wb/disc/inf/"]')).toHaveCount(3);
  await expect(disciplines.nth(0)).toHaveAttribute("aria-label", "Animalism");
  await expect(disciplines.nth(2)).toHaveAttribute("aria-label", "Vicissitude");
  const top = (await disciplines.nth(0).locator("div").boundingBox())!;
  const foot = (await disciplines.nth(2).locator("div").boundingBox())!;
  const article = (await card.boundingBox())!;
  expect(foot.y).toBeGreaterThan(top.y);
  // The lowest ends in the card's last fifth, by the text box, as on KRCG's sample card.
  expect(foot.y + foot.height).toBeGreaterThan(article.y + article.height * 0.8);
  await expect(card.getByText("Unofficial · made with Horatio · symbols by KRCG", { exact: true })).toBeAttached();
  await expect(card.getByText("Unofficial · not a real card · made with Horatio", { exact: true })).toHaveCount(0);
  await expect(card).toContainText("Capacity 4.");
  await p.getByLabel("Card text").fill("Once each turn, Sorin may reshape a minion.");
  await expect(card).toContainText("Once each turn, Sorin may reshape a minion.");
  await p.screenshot(shots("jyhad-card-template"));

  // Downloaded as an image on the template too.
  const download = p.waitForEvent("download");
  await p.getByRole("button", { name: "Download image" }).click();
  expect((await download).suggestedFilename()).toBe("Sorin Jyhad card.png");
});
