import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, PASSWORD, shots, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, characterTab } from "./support";

/** What the custodian does with people's accounts and characters. */

closeContextsAfterEach();

/** Chooses `item` from the ⋯ on `name`'s row of Custodian → People. */
async function personAction(row: Locator, name: string, item: string) {
  await row.getByRole("button", { name: `Actions for ${name}` }).click();
  await row.page().getByRole("menu", { name: `Actions for ${name}` }).getByRole("menuitem", { name: item }).click();
}

/** A badge on a row of People: in its Status column on a wide screen, under the name on a phone. */
function badge(row: Locator, text: string) {
  return row.getByText(text, { exact: true }).filter({ visible: true });
}

test("a player fills in their profile, and the custodian resets their password", async ({ browser }) => {
  const custodian = await person(browser, "people-custodian");
  makeCustodian(custodian.email);
  const player = await person(browser, "people-player");

  // The player fills in their profile from their name in the header.
  const p = player.page;
  await p.getByRole("link", { name: "people-player" }).click();
  await expect(p.getByRole("heading", { name: "Your account" })).toBeVisible();
  await p.getByLabel("Bio").fill("Playing since the Masquerade was young.");
  await p.getByLabel("Discord username").fill("@Carbuncle_Fan");
  await p.getByRole("button", { name: "Add a link" }).click();
  await p.getByLabel("Label").fill("Bluesky");
  await p.getByLabel("Address").fill("https://bsky.app/profile/carbuncle.example");
  await p.getByRole("button", { name: "Save profile" }).click();
  await expect(p.getByText("Saved.")).toBeVisible();

  // The custodian finds them in Custodian → People and makes a reset link without
  // leaving the list. Email is off in this suite, so the link is there to copy.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(player.email);
  const row = c.locator("main tr").filter({ hasText: player.email });
  await expect(row).toContainText(`@${player.handle}`);
  // Everything they can do with the account waits behind the ⋯ on its row.
  await row.getByRole("button", { name: "Actions for people-player" }).click();
  await c.screenshot(shots("people-menu"));
  await c.getByRole("menuitem", { name: "Reset password…" }).click();
  const reset = c.getByRole("dialog", { name: "Reset people-player's password" });
  await expect(reset.getByText("Send it to them yourself.")).toBeVisible();
  await reset.getByRole("button", { name: "Make a reset link" }).click();
  const cancelled = await reset.getByLabel("Reset link", { exact: true }).inputValue();
  expect(cancelled).toContain("/reset-password/");
  await expect(reset.getByText(/^people-player has a reset link, unused, until /)).toBeVisible();
  await expect(badge(row, "Reset link out")).toBeVisible();
  const resets = c.locator("section", { has: c.getByRole("heading", { name: "Password resets" }) });
  await expect(resets.getByRole("button", { name: "Cancel people-player's reset link" }).first()).toBeVisible();
  await expect(resets.getByText("people-custodian made a password reset link for people-player.").first()).toBeVisible();
  await c.screenshot(shots("people-reset"));

  // They think better of it and cancel it.
  await reset.getByRole("button", { name: "Cancel link" }).click();
  await expect(reset.getByText("Make a link that lets people-player set a new password", { exact: false })).toBeVisible();
  await expect(row.getByText("Reset link out")).toHaveCount(0);
  await reset.getByRole("button", { name: "Close" }).click();
  await expect(reset).toBeHidden();
  // Closing gives focus back to the ⋯ it was opened from.
  await expect(row.getByRole("button", { name: "Actions for people-player" })).toBeFocused();

  // They open the profile.
  await row.getByRole("link", { name: "people-player", exact: true }).click();
  await expect(c.getByRole("heading", { name: "people-player" })).toBeVisible();
  await expect(c.getByText(new RegExp(`^@${player.handle} · Member since .+\\(new this month\\)$`))).toBeVisible();
  await expect(c.getByText("Playing since the Masquerade was young.")).toBeVisible();
  await expect(c.getByText("@carbuncle_fan")).toBeVisible();
  await expect(c.getByRole("link", { name: "bsky.app/profile/carbuncle.example" })).toBeVisible();
  await c.screenshot(shots("profile"));

  // …and makes a new link there, which the player uses from a fresh browser. The
  // cancelled one no longer works.
  await c.getByRole("button", { name: "Make a reset link" }).click();
  const url = await c.getByLabel("Reset link", { exact: true }).inputValue();
  expect(url).toContain("/reset-password/");
  const fresh = await (await browser.newContext()).newPage();
  await fresh.goto(new URL(cancelled).pathname);
  await expect(fresh.getByText("This reset link has expired or been used.")).toBeVisible();
  await fresh.goto(new URL(url).pathname);
  await expect(fresh.getByText(`For people-player (${player.email})`)).toBeVisible();
  await fresh.getByLabel("New password").fill("a brand new password");
  await fresh.getByRole("button", { name: "Set password and sign in" }).click();
  await expect(fresh.getByRole("heading", { name: "Your characters" })).toBeVisible();

  // The old session has ended, and the link is spent.
  await p.goto("/characters");
  await expect(p.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await p.goto(new URL(url).pathname);
  await expect(p.getByText("This reset link has expired or been used.")).toBeVisible();
  await p.screenshot(shots("reset-spent"));

  // "Forgot your password?" needs email; without it, the page says to ask the custodian.
  await p.getByRole("link", { name: "Back to sign in" }).click();
  await p.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(p.getByText("Horatio can't send email here, so ask the custodian to make you a reset link.")).toBeVisible();
  await p.screenshot(shots("forgot"));

  // The custodian sees who reset their password, and when.
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await expect(c.getByText("people-player set a new password with a reset link.").first()).toBeVisible();
  await expect(c.getByText("people-custodian cancelled people-player's reset link.").first()).toBeVisible();
  await c.screenshot(shots("password-resets"));
});

test("the custodian changes a player's email, and the player confirms it from the new address", async ({ browser }) => {
  const custodian = await person(browser, "chmail-custodian");
  makeCustodian(custodian.email);
  const player = await person(browser, "chmail-player");
  const newEmail = `chmail-new-${run}@example.com`;

  // Email is off in this suite, so the player can't change their own: their link
  // could only go to the new address by email.
  const p = player.page;
  await p.getByRole("link", { name: "chmail-player" }).click();
  await p.locator("main").getByRole("link", { name: "Settings", exact: true }).click();
  await expect(p.getByText(`You sign in with ${player.email}`)).toBeVisible();
  await expect(p.getByText("Horatio can't send email here, so ask the custodian to change your email.")).toBeVisible();

  // The custodian changes it from the People list, with a reason. An address
  // another account uses is refused.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(player.email);
  const row = c.locator("main tr").filter({ hasText: player.email });
  await personAction(row, "chmail-player", "Change email…");
  const change = c.getByRole("dialog", { name: "Change chmail-player's email" });
  await change.getByLabel("New email").fill(custodian.email);
  await change.getByLabel("Reason").fill("Lost access to the old address");
  await change.getByRole("button", { name: "Change email", exact: true }).click();
  await expect(change.getByText(`uses ${custodian.email} already. If both accounts are the same person's, merge them instead.`, { exact: false })).toBeVisible();
  await change.getByLabel("New email").fill(newEmail);
  await change.getByRole("button", { name: "Change email", exact: true }).click();

  // Nothing changes until the link is opened: the custodian sends it on.
  await expect(change.getByText(`Waiting for chmail-player to confirm ${newEmail}`, { exact: false })).toBeVisible();
  await expect(badge(row, "New email waiting")).toBeVisible();
  const changes = c.locator("section", { has: c.getByRole("heading", { name: "Email changes" }) });
  await expect(changes.getByText(`${player.email} → ${newEmail}`, { exact: false })).toBeVisible();
  const url = await change.getByLabel("Link to confirm the new email").inputValue();
  expect(url).toContain("/confirm-email/");
  await expect(changes.getByText(`chmail-custodian started changing chmail-player's email from ${player.email} to ${newEmail} (Lost access to the old address).`)).toBeVisible();
  await c.screenshot(shots("email-change"));

  // The player opens it, signed out, confirms, and signs in with the new address.
  const fresh = await (await browser.newContext()).newPage();
  await fresh.goto(new URL(url).pathname);
  await expect(fresh.getByText(`Change the email of chmail-player's Horatio account (@${player.handle}) to ${newEmail}?`)).toBeVisible();
  await fresh.getByRole("button", { name: "Confirm new email" }).click();
  await expect(fresh.getByText(`Done: your email is now ${newEmail}.`, { exact: false })).toBeVisible();
  await fresh.screenshot(shots("email-confirmed"));
  await fresh.getByRole("link", { name: "Sign in" }).click();
  await fresh.getByLabel("Email or handle").fill(player.email);
  await fresh.getByLabel("Password").fill(PASSWORD);
  await fresh.getByRole("button", { name: "Sign in" }).click();
  await expect(fresh.getByText("Wrong email, handle or password.")).toBeVisible();
  await fresh.getByLabel("Email or handle").fill(newEmail);
  await fresh.getByRole("button", { name: "Sign in" }).click();
  await expect(fresh.getByRole("heading", { name: "Your characters" })).toBeVisible();

  // The link is spent, and the custodian sees the change confirmed.
  await fresh.goto(new URL(url).pathname);
  await expect(fresh.getByText("This link has expired, been used or been replaced by a newer one.")).toBeVisible();
  await c.reload();
  await expect(changes.getByText(`chmail-player confirmed their new email, ${newEmail}, changed by chmail-custodian from ${player.email} (Lost access to the old address).`)).toBeVisible();
  await expect(changes.getByText(`${player.email} → ${newEmail}`, { exact: false })).toHaveCount(0);
});

test("the custodian filters People by the troupe a player's active character is home in", async ({ browser }) => {
  const custodian = await person(browser, "tpf-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tpf-lead");
  const alpha = await person(browser, "tpf-alpha");
  const beta = await person(browser, "tpf-beta");
  const visitor = await person(browser, "tpf-visitor");
  const northName = `Court of Frost ${run}`;
  const southName = `Court of Ashfall ${run}`;

  const send = async (p: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const north = await send(custodian.page, "POST", "/api/troupes", { name: northName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, north.id);
  const south = await send(custodian.page, "POST", "/api/troupes", { name: southName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, south.id);

  // Alpha's character is accepted by the first troupe, beta's by the second. The
  // visitor only visits the first.
  const home = async (player: { page: Page }, name: string, troupeId: string) => {
    const id = await builtVampire(player.page, name, "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
    const approval = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${approval.id}/approve`, {});
    return id;
  };
  await home(alpha, "Frostbitten", north.id);
  await home(beta, "Emberling", south.id);
  const wanderer = await builtVampire(visitor.page, "Wanderer", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
  await send(visitor.page, "POST", `/api/characters/${wanderer}/troupes`, { troupe_id: north.id });

  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  const list = c.locator("main tr");
  const filter = c.getByLabel("Active character in");
  await expect(filter.locator("option").first()).toHaveText("Any troupe");

  await filter.selectOption({ label: northName });
  await expect(list.filter({ hasText: alpha.email })).toBeVisible();
  await expect(list.filter({ hasText: beta.email })).toHaveCount(0);
  await expect(list.filter({ hasText: visitor.email })).toHaveCount(0);
  await c.screenshot(shots("people-by-troupe"));

  // The search narrows it further: both apply.
  await c.getByLabel("Search people").fill(beta.email);
  await expect(c.getByText("No one matches.")).toBeVisible();
  await filter.selectOption({ label: southName });
  await expect(list.filter({ hasText: beta.email })).toBeVisible();
  await expect(list.filter({ hasText: alpha.email })).toHaveCount(0);

  await filter.selectOption({ label: "Any troupe" });
  await c.getByLabel("Search people").fill(visitor.email);
  await expect(list.filter({ hasText: visitor.email })).toBeVisible();
});

test("the custodian views Horatio as a player, read-only, and the player sees that they did", async ({ browser }) => {
  const custodian = await person(browser, "viewas-custodian");
  makeCustodian(custodian.email);
  const player = await person(browser, "viewas-player");
  const p = player.page;
  const made = await p.request.post("/api/characters", { headers: { "X-Horatio": "1" }, data: { splat: "vampire", name: "Marisol" } });
  expect(made.status(), await made.text()).toBe(201);

  // The custodian starts from People, saying why.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(player.email);
  const row = c.locator("main tr").filter({ hasText: player.email });
  await personAction(row, "viewas-player", "View as…");
  const dialog = c.getByRole("dialog", { name: `View as @${player.handle}` });
  await dialog.getByLabel("Reason").fill("Can't find her character");
  await dialog.getByRole("button", { name: "Start viewing" }).click();

  // Horatio as the player sees it, with the banner.
  const banner = c.getByRole("status").filter({ hasText: `Viewing as @${player.handle}, read-only.` });
  await expect(banner).toBeVisible();
  await expect(c.getByRole("heading", { name: "Your characters" })).toBeVisible();
  await expect(c.locator("main").getByText("Marisol")).toBeVisible();
  await expect(c.getByRole("link", { name: "Custodian", exact: true })).toHaveCount(0);
  await c.screenshot(shots("view-as"));

  // Nothing can be changed: the API refuses, whatever the page sends.
  await c.getByRole("link", { name: "viewas-player" }).click();
  await c.getByLabel("Bio").fill("Not mine to write.");
  await c.getByRole("button", { name: "Save profile" }).click();
  await expect(c.getByText(`You are viewing Horatio as @${player.handle}, read-only. Stop viewing to make changes.`)).toBeVisible();
  const refused = await c.request.post("/api/characters", { headers: { "X-Horatio": "1" }, data: { splat: "vampire", name: "Intruder" } });
  expect(refused.status()).toBe(403);
  await expect(banner).toBeVisible();

  // Stopping makes them the custodian again.
  await banner.getByRole("button", { name: "Stop" }).click();
  await expect(c.getByRole("link", { name: "Custodian", exact: true })).toBeVisible();
  await expect(c.getByText(`Viewing as @${player.handle}, read-only.`)).toHaveCount(0);

  // The player sees when, by whom and why in their account's settings; their bio is as it was.
  await p.reload();
  await p.getByRole("link", { name: "viewas-player" }).click();
  await expect(p.getByLabel("Bio")).toHaveValue("");
  await p.locator("main").getByRole("link", { name: "Settings", exact: true }).click();
  const visits = p.locator("section", { has: p.getByRole("heading", { name: "When the custodian viewed as you" }) });
  await expect(visits.getByText("Can't find her character")).toBeVisible();
  await expect(visits.getByText(/, by viewas-custodian$/)).toBeVisible();
  await p.screenshot(shots("viewed-as"));
});

test("the custodian searches the audit log across troupes by person, days and character, and exports it", async ({ browser }) => {
  const custodian = await person(browser, "logsearch-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "logsearch-lead");
  const player = await person(browser, "logsearch-play");
  const inkwells = `Court of Inkwells ${run}`;
  const seals = `Court of Seals ${run}`;
  const character = `Wilhelmina ${run}`;

  const send = async (p: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  // The lead makes the player a narrator in each of two troupes: one change in each.
  for (const name of [inkwells, seals]) {
    const troupe = await send(custodian.page, "POST", "/api/troupes", { name, lead_handle: lead.handle });
    await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: player.handle, role: "narrator" });
  }
  // And the player's character has two changes of its own.
  const made = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: character });
  await send(player.page, "PUT", `/api/characters/${made.id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await send(player.page, "PUT", `/api/characters/${made.id}/traits`, { category: "sect", name: "Camarilla", rating: null });

  // Only the custodian can search it.
  expect((await lead.page.request.get("/api/audit")).status()).toBe(403);
  expect((await lead.page.request.get("/api/audit/export")).status()).toBe(403);

  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "Audit", exact: true }).click();
  const found = c.getByRole("list", { name: "Audit log" }).getByRole("listitem");

  // Everything the lead did today, in both troupes.
  const today = await c.evaluate(() => new Date().toLocaleDateString("en-CA"));
  await c.getByLabel("Who did it").fill(lead.handle);
  await c.getByRole("option").filter({ hasText: lead.handle }).click();
  await c.getByLabel("From", { exact: true }).fill(today);
  await c.getByLabel("To", { exact: true }).fill(today);
  await c.getByRole("button", { name: "Search", exact: true }).click();
  await expect(found).toHaveCount(2);
  await expect(found.filter({ hasText: seals })).toContainText("logsearch-lead made logsearch-play narrator.");
  await expect(found.filter({ hasText: inkwells })).toContainText("logsearch-lead made logsearch-play narrator.");
  await expect(c).toHaveURL(new RegExp(`person=${lead.handle}`));
  await c.screenshot(shots("audit-by-person"));

  const exported = async () => {
    const download = c.waitForEvent("download");
    await c.getByRole("link", { name: "Export as CSV" }).click();
    const chunks: Buffer[] = [];
    for await (const chunk of await (await download).createReadStream()) chunks.push(chunk as Buffer);
    return Buffer.concat(chunks).toString("utf8");
  };
  const byLead = await exported();
  expect(byLead.split("\n").filter((line) => line.trim())).toHaveLength(3);
  expect(byLead).toContain(inkwells);
  expect(byLead).toContain(seals);

  // The same days, nothing yesterday.
  await c.getByLabel("To", { exact: true }).fill(await c.evaluate(() => new Date(Date.now() - 86_400_000).toLocaleDateString("en-CA")));
  await c.getByLabel("From", { exact: true }).fill("");
  await c.getByRole("button", { name: "Search", exact: true }).click();
  await expect(c.getByText("Nothing in the log matches.")).toBeVisible();

  // Every change to one character, whoever made it.
  await c.getByRole("button", { name: "Clear" }).click();
  // The form is filled in afresh from the cleared address before anything is typed.
  await expect(c.getByLabel("Who did it")).toHaveValue("");
  await c.getByLabel("Character", { exact: true }).fill(character);
  await c.getByRole("option").filter({ hasText: character }).click();
  await c.getByRole("button", { name: "Search", exact: true }).click();
  await expect(found).toHaveCount(2);
  await expect(found.first()).toContainText(`logsearch-play chose Camarilla as ${character}'s sect.`);
  await expect(found.nth(1)).toContainText(`logsearch-play chose Brujah as ${character}'s clan.`);
  const byCharacter = await exported();
  expect(byCharacter).toContain(`chose Camarilla as ${character}'s sect.`);
  expect(byCharacter).toContain(`chose Brujah as ${character}'s clan.`);

  // Each change leads to its character.
  await found.first().getByRole("link", { name: /Camarilla/ }).click();
  await expect(c).toHaveURL(new RegExp(`/characters/${made.id}`));
});

test("the custodian suspends a lead storyteller, who can't sign in until it is lifted", async ({ browser }) => {
  const custodian = await person(browser, "susp-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "susp-lead");
  const troupeName = `Court of Exile ${run}`;
  const c = custodian.page;
  await c.reload();
  const made = await c.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);

  // The custodian suspends them from People, with a reason only they see.
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(lead.email);
  const row = c.locator("main tr").filter({ hasText: lead.email });
  await personAction(row, "susp-lead", "Suspend…");
  const suspend = c.getByRole("dialog", { name: "Suspend susp-lead" });
  await suspend.getByLabel("Reason").fill("Threatened another player at the last game");
  await suspend.getByRole("button", { name: "Suspend susp-lead" }).click();
  await expect(suspend).toBeHidden();
  await expect(c.getByText("susp-lead is suspended.", { exact: true })).toBeVisible();
  await expect(badge(row, "Suspended")).toBeVisible();

  // They are listed as suspended, with the troupe that wants a new lead, and it is logged.
  // Other tests may suspend people at the same time, so look only at this one.
  const suspended = c.getByRole("list", { name: "Suspended people" }).getByRole("listitem").filter({ hasText: `@${lead.handle}` });
  await expect(suspended.getByText("“Threatened another player at the last game”")).toBeVisible();
  await expect(suspended.getByRole("link", { name: troupeName })).toBeVisible();
  await expect(c.getByText("susp-custodian suspended susp-lead (Threatened another player at the last game).").first()).toBeVisible();
  await c.screenshot(shots("suspended"));

  // The troupe list marks the troupe.
  await c.getByRole("link", { name: "Troupes", exact: true }).click();
  await expect(c.locator("main li").filter({ hasText: troupeName }).getByText("Lead suspended")).toBeVisible();

  // The lead is signed out at once, and told why they can't sign in, but not the reason.
  const l = lead.page;
  await l.goto("/characters");
  await expect(l.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await l.getByLabel("Email or handle").fill(lead.email);
  await l.getByLabel("Password").fill(PASSWORD);
  await l.getByRole("button", { name: "Sign in" }).click();
  await expect(l.getByText("Your account is suspended. To ask about it, contact the custodian.")).toBeVisible();
  await l.screenshot(shots("suspended-sign-in"));

  // The custodian lifts it, and they can sign in again.
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(lead.email);
  await personAction(row, "susp-lead", "Lift suspension…");
  const lift = c.getByRole("dialog", { name: "Lift susp-lead's suspension" });
  await lift.getByLabel("Why lift it").fill("Apologised and agreed to the code of conduct");
  await lift.getByRole("button", { name: "Lift suspension", exact: true }).click();
  await expect(lift).toBeHidden();
  await expect(row.getByText("Suspended", { exact: true })).toHaveCount(0);
  await expect(suspended).toHaveCount(0);
  await l.getByRole("button", { name: "Sign in" }).click();
  await expect(l.getByRole("heading", { name: "Your characters" })).toBeVisible();
});

test("the custodian moves a character to another player, not while its game is under way, and back again", async ({ browser }) => {
  const custodian = await person(browser, "mvc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "mvc-lead");
  const before = await person(browser, "mvc-before");
  const after = await person(browser, "mvc-after");
  const troupeName = `Court of Second Hands ${run}`;
  const send = async (p: Page, method: "GET" | "POST", url: string, data?: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  // The character was built on the wrong account, and is at home in the troupe.
  const id = await builtVampire(before.page, "Ottilie Marsh", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
  const approval = await send(before.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${approval.id}/approve`, {});
  // Its player is at a game with it: a tap on the Play View.
  await send(before.page, "GET", `/api/characters/${id}/play`);
  await send(before.page, "POST", `/api/characters/${id}/play/taps`, {
    taps: [{ id: crypto.randomUUID(), happened_at: new Date().toISOString(), kind: "change", tracker: "blood", amount: -1 }],
  });

  // The custodian finds the player on People, opens their characters and moves it.
  const c = custodian.page;
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(before.email);
  const row = c.locator("main tr").filter({ hasText: before.email });
  await personAction(row, "mvc-before", "Characters");
  const characters = c.getByRole("dialog", { name: "mvc-before's characters" });
  await expect(characters.getByRole("link", { name: /Ottilie Marsh/ })).toContainText(troupeName);
  await characters.getByRole("button", { name: "Move Ottilie Marsh to another player" }).click();
  const dialog = c.getByRole("dialog", { name: "Move Ottilie Marsh to another player" });
  await expect(dialog.getByText(`Ottilie Marsh is played by mvc-before @${before.handle}.`)).toBeVisible();
  await dialog.getByLabel("New player").fill(after.handle);
  await dialog.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${after.handle}` }).click();
  await dialog.getByLabel("Reason").fill("Signed up twice; this is their real account");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByText(`Its home troupe is ${troupeName}.`, { exact: false })).toBeVisible();
  await expect(dialog.getByText("Its sheet, XP, history, titles and status go with it.")).toBeVisible();
  await expect(dialog.getByText(`@${before.handle} can no longer open it; @${after.handle} can, at once.`)).toBeVisible();
  // Its game is under way, so the move waits until the game ends.
  await expect(dialog.getByText("Ottilie Marsh is in a game on the Play View. End it first with Reset for next game, so the game isn't split between two people.")).toBeVisible();
  const confirm = dialog.getByRole("button", { name: `Move Ottilie Marsh to @${after.handle}` });
  await expect(confirm).toBeDisabled();
  await c.screenshot(shots("move-character-refused"));

  // The lead ends the troupe's games, and the move goes ahead.
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/play/reset`);
  await dialog.getByRole("button", { name: "Back" }).click();
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(confirm).toBeEnabled();
  await c.screenshot(shots("move-character-confirm"));
  await confirm.click();
  await expect(dialog).toBeHidden();
  // The list of their characters stays open behind it, now without it.
  await expect(characters.getByText("No characters.")).toBeVisible();

  // The new player has it in their vault, with its history and the move in its log.
  const a = after.page;
  await a.reload();
  await a.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(a.getByText(`The custodian moved Ottilie Marsh to you from @${before.handle}: Signed up twice; this is their real account`)).toBeVisible();
  await a.keyboard.press("Escape");
  await a.locator("main").getByRole("link", { name: /Ottilie Marsh/ }).click();
  await characterTab(a, "Log");
  await expect(
    a.getByText(`The custodian, mvc-custodian, moved Ottilie Marsh (mvc-after) from @${before.handle} to @${after.handle}: Signed up twice; this is their real account`),
  ).toBeVisible();
  await expect(a.getByText(/^mvc-lead accepted Ottilie Marsh/)).toBeVisible();
  await a.screenshot(shots("move-character-log"));

  // The old player can no longer open it, and they and the lead are told.
  const b = before.page;
  await b.goto(`/characters/${id}`);
  await expect(b.getByText("No such character.")).toBeVisible();
  await b.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(b.getByText(`The custodian moved Ottilie Marsh to @${after.handle}: Signed up twice; this is their real account`)).toBeVisible();
  await lead.page.reload();
  await lead.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(lead.page.getByText(`The custodian moved Ottilie Marsh from @${before.handle} to @${after.handle}`, { exact: false })).toBeVisible();

  // Undoing it is another move, back, from the character's own page.
  await c.goto(`/characters/${id}`);
  await c.getByRole("button", { name: "More for Ottilie Marsh" }).click();
  await c.getByRole("menuitem", { name: "Move to another player…" }).click();
  const back = c.getByRole("dialog", { name: "Move Ottilie Marsh to another player" });
  await expect(back.getByText(`Ottilie Marsh is played by mvc-after @${after.handle}.`)).toBeVisible();
  await back.getByLabel("New player").fill(before.handle);
  await back.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${before.handle}` }).click();
  await back.getByLabel("Reason").fill("Moved by mistake");
  await back.getByRole("button", { name: "Continue" }).click();
  await back.getByRole("button", { name: `Move Ottilie Marsh to @${before.handle}` }).click();
  await expect(back).toBeHidden();
  await b.goto(`/characters/${id}`);
  await expect(b.getByRole("heading", { name: "Ottilie Marsh", level: 1 })).toBeVisible();
});

test("the custodian merges two accounts of one person: the characters and staff role move, and the other account is closed", async ({ browser }) => {
  const custodian = await person(browser, "mga-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "mga-lead");
  const real = await person(browser, "mga-real");
  const twice = await person(browser, "mga-twice");
  const troupeName = `Court of Two Faces ${run}`;
  const send = async (p: Page, method: "POST" | "PUT", url: string, data?: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  // The person signed up twice: the second account has a character at home in the
  // troupe, and is one of its narrators.
  const id = await builtVampire(twice.page, "Hester Vane", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
  const approval = await send(twice.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${approval.id}/approve`, {});
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: twice.handle, role: "narrator" });
  // It has pronouns and lines and veils, which the first has not, and the custodian
  // has started changing its email.
  await send(twice.page, "PUT", "/api/profile", { display_name: "mga-twice", pronouns: "they/them" });
  await send(twice.page, "PUT", "/api/profile/lines-veils", { lines: ["Spiders"], veils: [], shared: false });
  const twiceId = (await (await twice.page.request.get("/api/auth/me")).json()).id;
  const newEmail = `new-${twice.email}`;
  await send(custodian.page, "POST", `/api/players/${twiceId}/email-change`, { email: newEmail, reason: "Lost the old address" });

  // The custodian finds the second account on People and merges it into the first.
  const c = custodian.page;
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(twice.email);
  const row = c.locator("main tr").filter({ hasText: twice.email });
  await personAction(row, "mga-twice", "Merge…");
  const dialog = c.getByRole("dialog", { name: "Merge mga-twice with another account" });
  await dialog.getByLabel("The same person's other account").fill(real.handle);
  await dialog.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${real.handle}` }).click();
  await dialog.getByRole("radio", { name: `@${real.handle}` }).check();
  await dialog.getByLabel("Reason").fill("Signed up with Google and with email");
  await dialog.getByRole("button", { name: "Continue" }).click();
  await expect(dialog.getByText(`Merge mga-twice @${twice.handle} into mga-real @${real.handle}? This can't be undone.`)).toBeVisible();
  await expect(dialog.getByRole("listitem").filter({ hasText: "Hester Vane" })).toContainText(troupeName);
  await expect(dialog.getByText(`${troupeName}: its narrator role`)).toBeVisible();
  await expect(dialog.getByText(`@${twice.handle} will find @${real.handle}, for good`)).toBeVisible();
  await expect(dialog.getByText(`Its pronouns, lines and veils (not shared), as @${real.handle} has none`)).toBeVisible();
  await expect(dialog.getByText(`Its change of email waiting, to ${newEmail}, is cancelled.`)).toBeVisible();
  await c.screenshot(shots("merge-accounts-confirm"));
  await dialog.getByRole("button", { name: `Merge into @${real.handle}` }).click();
  await expect(dialog).toBeHidden();
  // The closed account is no longer listed; searching its handle finds the other.
  await c.getByLabel("Search people").fill(twice.handle);
  await expect(c.locator("main tr").filter({ hasText: real.email })).toBeVisible();
  // (Its email is still in the log of recent account events below.)
  await expect(c.getByRole("button", { name: "Actions for mga-twice" })).toHaveCount(0);

  // The closed account is signed out, and can't sign in again.
  const t = twice.page;
  await t.goto("/characters");
  await expect(t.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await t.getByLabel("Email or handle").fill(twice.email);
  await t.getByLabel("Password").fill(PASSWORD);
  await t.getByRole("button", { name: "Sign in" }).click();
  await expect(t.getByText("Wrong email, handle or password.")).toBeVisible();

  // The staying account has the character, and is told.
  const r = real.page;
  await r.reload();
  // Its bell has the closed account's messages too.
  await r.getByRole("button", { name: /^Notifications, \d+ waiting$/ }).click();
  await expect(r.getByText(`The custodian merged your account @${twice.handle} into this one, @${real.handle}: Signed up with Google and with email`)).toBeVisible();
  await r.keyboard.press("Escape");
  await r.locator("main").getByRole("link", { name: /Hester Vane/ }).click();
  await characterTab(r, "Log");
  // Its history keeps who did it, saying whom they were merged into.
  await expect(r.getByText(`mga-twice (merged into @${real.handle})`, { exact: false }).first()).toBeVisible();
  await r.screenshot(shots("merge-accounts-log"));

  // The lead is told, and the staying account is now on the troupe's staff.
  await lead.page.reload();
  await lead.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(
    lead.page.getByText(`The custodian merged @${twice.handle} into @${real.handle}, the same person, moving Hester Vane, its narrator role: Signed up with Google and with email`),
  ).toBeVisible();
});

/** Takes the fitted creation picks off an NPC, as an NPC built before #527 had none. */
function asBuiltBeforeFitting(npcId: string) {
  const script = [
    "import uuid",
    "from horatio import npc_picks",
    "from horatio.db import get_sessionmaker",
    "from horatio.models import Character",
    "with get_sessionmaker()() as db, db.begin():",
    `    npc_picks.unfit(db, db.get_one(Character, uuid.UUID("${npcId}")))`,
  ].join("\n");
  execFileSync("uv", ["run", "python", "-c", script], { cwd: "../backend", stdio: "ignore" });
}

test("the custodian chooses the loading animation, which shows as Horatio next opens, before it has loaded", async ({ browser }) => {
  const custodian = await person(browser, "loadanim-cust");
  makeCustodian(custodian.email);
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "Settings", exact: true }).click();

  // Each of the four, moving as it would, with the blood drip until another is chosen.
  const choices = c.getByRole("radiogroup", { name: "Loading animation" });
  await expect(choices.getByRole("radio")).toHaveText([/^Blood drip/, /^Rising blood/, /^Candle/, /^Heartbeat/]);
  await expect(choices.locator(".loader-block")).toHaveCount(4);
  // The other projects' run of this test may have chosen another already: only this run's choice is checked.
  const motif = test.info().project.name === "phone" ? "Heartbeat" : "Candle";
  const key = motif === "Candle" ? "candle" : "heartbeat";

  // Full screen, as Horatio opens.
  await c.getByRole("button", { name: `Preview ${motif.toLowerCase()} full screen` }).click();
  const preview = c.getByRole("dialog", { name: `${motif}, full screen` });
  await expect(preview.locator(`.splash[data-motif="${key}"] .loader-full.loader-${key}`)).toBeVisible();
  await c.screenshot(shots(`loading-${key}-full`));
  await preview.getByRole("button", { name: "Close" }).click();
  await expect(preview).toBeHidden();

  await choices.getByRole("radio", { name: motif }).click();
  await expect(c.getByText(`Horatio now shows the ${motif.toLowerCase()} while it loads.`)).toBeVisible();
  await expect(choices.getByRole("radio", { name: motif })).toHaveAttribute("aria-checked", "true");
  await c.screenshot(shots("loading-animation"));

  // Opening Horatio again, the screen before the app arrives shows it: kept on this device.
  await c.route("**/assets/**", (route) => route.abort());
  await c.goto("/characters");
  const splash = c.locator("#root > .splash");
  await expect(splash).toHaveAttribute("data-motif", key);
  await expect(splash.locator(`.loader-${key}`)).toBeVisible();
  await expect(splash.locator(".loader-drip")).toBeHidden();
  await expect(c.getByRole("status", { name: "Loading" })).toBeVisible();
  await c.unroute("**/assets/**");

  // Anyone may ask which it is, signed in or not.
  const signedOut = await (await browser.newContext()).newPage();
  const appearance = await signedOut.request.get("/api/appearance");
  expect(appearance.status()).toBe(200);
  expect(Object.keys((await appearance.json()).loading_animation)).toContain("default");

  // Back to the blood drip, as the other tests expect.
  const reset = await c.request.put("/api/appearance/loading-animation", { headers: { "X-Horatio": "1" }, data: { loading_animation: { default: "drip" } } });
  expect(reset.status(), await reset.text()).toBe(200);
});

test("the custodian previews fitting a troupe's NPC creation picks, then fits them", async ({ browser }) => {
  const custodian = await person(browser, "fitpicks-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "fitpicks-lead");
  const troupeName = `Court of Fitted Picks ${run}`;
  const lucien = `Lucien Fitted ${run}`;
  const stan = `Stan Stock ${run}`;
  const c = custodian.page;
  await c.reload();
  const send = async (p: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const troupe = await send(c, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  // An NPC built quickly before its picks were fitted (#527), and a Stock NPC.
  const npc = await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: lucien, wizard: false });
  for (const [category, name, rating] of [
    ["attributes", "Physical", 5],
    ["skills", "Brawl", 5],
    ["disciplines", "Celerity", 2],
  ]) {
    await send(lead.page, "PUT", `/api/characters/${npc.id}/npc/ratings`, { category, name, rating });
  }
  asBuiltBeforeFitting(npc.id);
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: stan, npc_kind: "mortal", npc_form: "stock" });

  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "Tools", exact: true }).click();
  const tool = c.locator("section").filter({ has: c.getByRole("heading", { name: "Fit NPC creation picks" }) });
  await tool.getByLabel("Troupe").selectOption({ label: troupeName });
  await tool.getByRole("button", { name: "Preview" }).click();

  // The preview: Lucien's every dot is priced as bought until his picks are fitted.
  const preview = tool.getByRole("region", { name: "Preview" });
  await expect(preview.getByText(`Of ${troupeName}'s 1 NPC built without the wizard, 1 would change. Nothing has changed yet.`)).toBeVisible();
  const toFit = preview.getByRole("table", { name: "NPCs to fit" });
  await expect(toFit.getByRole("row", { name: lucien })).toContainText("42 → 17");
  await expect(toFit.getByRole("row", { name: /^Total/ })).toContainText("42 → 17");
  await expect(preview.getByRole("listitem").filter({ hasText: stan })).toContainText("A Stock NPC: it has no sheet to fit picks to.");

  await tool.getByRole("button", { name: "Fit 1 NPC" }).click();
  await expect(tool.getByRole("status")).toHaveText(`Fitted. Of ${troupeName}'s 1 NPC built without the wizard, 1 changed.`);
  const log = await (await c.request.get(`/api/troupes/${troupe.id}/log`)).json();
  expect(log.map((e: { message: string }) => e.message)).toContain(
    "fitpicks-cust fitted the creation picks of the troupe's NPCs built without the wizard: 1 of 1 changed.",
  );

  // Fitting again would change nothing.
  await tool.getByRole("button", { name: "Preview" }).click();
  await expect(preview.getByText(`Of ${troupeName}'s 1 NPC built without the wizard, 0 would change. Nothing has changed yet.`)).toBeVisible();
  const again = preview.getByRole("row", { name: lucien });
  await expect(again).toContainText("17 → 17");
  await expect(again).toContainText("Fitted already");
  await expect(tool.getByRole("button", { name: "Fit 0 NPCs" })).toBeDisabled();
});

test("the custodian fetches the Dark Pack resources and the VTES symbols onto the server, then removes them", async ({ browser }) => {
  const custodian = await person(browser, "fetchkit-cust");
  makeCustodian(custodian.email);
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "Tools", exact: true }).click();
  const card = (title: string) => c.locator("section").filter({ has: c.getByRole("heading", { name: title, exact: true }) });
  const darkPack = card("Dark Pack resources");
  const vtes = card("VTES symbols");

  // The e2e server has no Dark Pack folder, so there is nowhere to fetch to.
  await expect(darkPack.getByText("This server has no Dark Pack folder")).toBeVisible();
  await expect(vtes.getByText("This server has no Dark Pack folder")).toBeVisible();
  await expect(darkPack.getByRole("button", { name: "Fetch and import" })).toHaveCount(0);

  // The rest with the server's answers faked in the browser: tests never reach Paradox or KRCG.
  const dropbox = "https://www.dropbox.com/scl/fo/kit?dl=1";
  const job = (stage: string, done: number, total: number) => ({ stage, done, total, started_at: new Date().toISOString(), by: "fetchkit-cust" });
  const common = { configured: true, writable: true, agreement: "https://www.paradoxinteractive.com/dark-pack-agreement", job: null, error: null, error_at: null };
  const empty = { ...common, default_address: dropbox, imported: false, imported_at: null, how: null, address: null, sources: [], logo: false, clans: [], missing: [] };
  const imported = {
    ...empty,
    imported: true,
    imported_at: new Date().toISOString(),
    how: "fetched",
    address: dropbox,
    sources: ["World of Darkness Community Assets.zip", "WoD-Logos-and-Symbols.zip"],
    logo: true,
    clans: ["Brujah", "Giovanni"],
    missing: ["Lamia"],
  };
  const downloading = { ...empty, job: job("Downloading", 120 * 1024 * 1024, 432 * 1024 * 1024) };
  let darkPackNow: object = empty;
  // After the fetch starts, it's asked after twice while it downloads; then it's done.
  let downloadingFor = 0;
  const fetched: unknown[] = [];
  await c.route("**/api/tools/dark-pack", async (route) => {
    if (route.request().method() === "DELETE") darkPackNow = empty;
    if (downloadingFor > 0 && --downloadingFor === 0) darkPackNow = imported;
    await route.fulfill({ json: downloadingFor > 0 ? downloading : darkPackNow });
  });
  await c.route("**/api/tools/dark-pack/fetch", async (route) => {
    fetched.push(route.request().postDataJSON());
    downloadingFor = 3;
    await route.fulfill({ status: 202, json: downloading });
  });
  const vtesEmpty = {
    ...common,
    default_address: "https://static.krcg.org/",
    fetched: false,
    fetched_at: null,
    address: null,
    counts: [],
    fonts: [],
    clans: [],
    disciplines: [],
    large_png: [],
  };
  let vtesNow: object = vtesEmpty;
  await c.route("**/api/tools/vtes-symbols", (route) => route.fulfill({ json: vtesNow }));
  await c.route("**/api/tools/vtes-symbols/fetch", async (route) => {
    vtesNow = { ...vtesEmpty, error: "https://static.krcg.org/svg/clan/ answered 503 Service Unavailable.", error_at: new Date().toISOString() };
    await route.fulfill({ status: 202, json: vtesNow });
  });
  await c.reload();

  // The Dark Pack: the usual address, and nothing until the licence is accepted.
  await expect(darkPack.getByText("Not on this server yet.")).toBeVisible();
  await expect(darkPack.getByLabel("Address")).toHaveValue(dropbox);
  const fetch = darkPack.getByRole("button", { name: "Fetch and import" });
  await expect(fetch).toBeDisabled();
  await darkPack.getByLabel("I accept Paradox's Dark Pack Agreement for this server").first().check();
  await fetch.click();
  await expect(darkPack.getByRole("status")).toContainText("Downloading: 120 MB of 432 MB… Started");
  expect(fetched).toEqual([{ address: dropbox, accept_licence: true }]);
  const status = darkPack.getByRole("region", { name: "On the server" });
  await expect(status).toContainText(`Fetched`, { timeout: 10_000 });
  await expect(status).toContainText(`from ${dropbox}, from World of Darkness Community Assets.zip and WoD-Logos-and-Symbols.zip.`);
  await expect(status).toContainText("The Dark Pack logo is here.");
  await expect(status).toContainText("Clan symbols (2): Brujah, Giovanni.");
  await expect(status).toContainText("Not in the kit: Lamia.");

  // Removing it asks first.
  await darkPack.getByRole("button", { name: "Remove" }).click();
  const confirm = c.getByRole("dialog", { name: "Remove the Dark Pack resources?" });
  await confirm.getByRole("button", { name: "Keep them" }).click();
  await expect(status).toBeVisible();
  await darkPack.getByRole("button", { name: "Remove" }).click();
  await confirm.getByRole("button", { name: "Remove them" }).click();
  await expect(darkPack.getByText("Not on this server yet.")).toBeVisible();

  // The VTES symbols: a fetch that fails says why, and that nothing was lost.
  await expect(vtes.getByLabel("Address")).toHaveValue("https://static.krcg.org/");
  await vtes.getByLabel("I accept Paradox's Dark Pack Agreement for this server").check();
  await vtes.getByRole("button", { name: "Fetch", exact: true }).click();
  await expect(vtes.getByRole("alert")).toContainText("failed: https://static.krcg.org/svg/clan/ answered 503 Service Unavailable.");
  await expect(vtes.getByRole("alert")).toContainText("What was here before it is still here.");
});

test("the custodian imports a troupe's characters from Yorick, matching a line and overwriting an NPC of the same name", async ({ browser }) => {
  const custodian = await person(browser, "yorick-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "yorick-lead");
  const troupeName = `Court of Yorick ${run}`;
  const c = custodian.page;
  // A card of the tab, by its title.
  const card = (title: string) => c.locator("section").filter({ has: c.getByRole("heading", { name: title, exact: true }) });
  await c.reload();
  const created = await c.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(created.status(), await created.text()).toBeLessThan(300);
  const troupeId: string = (await created.json()).id;
  const agnes = `Agnes Wren ${run}`;
  const thaddeus = `Thaddeus Ashby ${run}`;
  const mystery = `Mystery Woman ${run}`;
  // The made-up page from the backend's tests, its names and Yorick ids made this run's own.
  const page = readFileSync("../backend/tests/fixtures/yorick_print.html", "utf8")
    .replaceAll("aGnEsWr3n1", `aGnEsWr3n1${run}`)
    .replaceAll("Th4ddAshby", `Th4ddAshby${run}`)
    .replaceAll("Agnes Wren", agnes)
    .replaceAll("Thaddeus Ashby", thaddeus)
    .replaceAll("Mystery Woman", mystery)
    // Mystery Woman's Auspicious gives her Rugged (#577): her merits are the only empty ones.
    .replace("Merits</h4> <h4", "Merits</h4> Auspicious (1, Rugged)<br> <h4")
    // Thaddeus's notes name Potence in-clan, through Additional Common Discipline: the
    // first empty notes are his.
    .replace("Talisman (2)<br>", "Talisman (2)<br> Additional Common Discipline (4)<br>")
    .replace('<div class="ui-block-a"></div></div>', '<div class="ui-block-a">In clan: Celerity, Obfuscate, Protean, Potence</div></div>');
  // The lead has made Agnes already, by hand.
  const npc = await lead.page.request.post(`/api/troupes/${troupeId}/npcs`, { headers: { "X-Horatio": "1" }, data: { name: agnes, wizard: false } });
  expect(npc.status(), await npc.text()).toBe(201);

  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "Import from Yorick" }).click();
  await c.getByLabel("Troupe").selectOption({ label: troupeName });
  await c.getByLabel("Print Characters page").setInputFiles({ name: "Print Troupe Characters.html", mimeType: "text/html", buffer: Buffer.from(page) });

  // The dry run runs in the background, and saves nothing.
  const dry = card("Dry run");
  await expect(dry.getByText(/^3 characters read from the page: 2 to be made/)).toBeVisible({ timeout: 30_000 });
  await expect(c.getByRole("button", { name: `Import into ${troupeName}` })).toBeDisabled();
  await expect(c.getByText("1 printed character share a name with a character here: choose what to do with each first.")).toBeVisible();

  // Agnes is here already: overwrite the NPC the lead made.
  const shared = card("Already here under the same name");
  await shared.getByLabel(agnes).selectOption({ label: `Overwrite ${agnes}` });
  await expect(shared.getByText("Needs a choice")).toBeHidden();

  // Police is Law Enforcement; the other unmatched line staff fix by hand.
  const unmatched = card("Printed lines that matched nothing");
  await unmatched.getByRole("button", { name: "Match Influences: The Underworld: Police x1 to…" }).click();
  const dialog = c.getByRole("dialog", { name: "Match to…" });
  await dialog.getByLabel("Horatio's Influence area").fill("Law Enforcement");
  await dialog.getByRole("button", { name: "Match" }).click();
  await expect(dialog).toBeHidden();
  await unmatched.getByRole("listitem").filter({ hasText: "Backgrounds: Influences x1" }).getByRole("button", { name: "Staff will fix by hand" }).click();
  await expect(card("The troupe's names").getByText("“Police” → Law Enforcement")).toBeVisible();
  await expect(dry.getByText("Names or choices have changed since")).toBeVisible();

  await dry.getByRole("button", { name: "Run the dry run again" }).click();
  await expect(dry.getByText(/^3 characters read from the page: 2 to be made, 0 to be updated, 1 to be overwritten/)).toBeVisible({ timeout: 30_000 });
  await expect(unmatched.getByText("Influences: The Underworld: Police x1")).toBeHidden();

  // No backups here: say to go ahead without one, and import.
  await c.getByLabel("Backups aren't set up on this server: import without one").check();
  await c.getByRole("button", { name: `Import into ${troupeName}` }).click();
  await c.getByRole("dialog", { name: `Import into ${troupeName}?` }).getByRole("button", { name: "Import" }).click();
  const done = card("Imported");
  await expect(done.getByText(/^3 characters read from the page: 2 made, 0 updated, 1 overwritten/)).toBeVisible({ timeout: 30_000 });
  await expect(c.getByText("No page uploaded: the last one was imported, and deleted.")).toBeVisible();

  // The lead finds them among the troupe's NPCs, Agnes once.
  await lead.page.goto(`/troupes/${troupeId}/npcs`);
  await expect(lead.page.getByRole("link", { name: thaddeus })).toBeVisible();
  await expect(lead.page.getByRole("link", { name: agnes })).toHaveCount(1);

  // Potence is in-clan for Thaddeus beyond his bloodline's own three.
  await lead.page.getByRole("link", { name: thaddeus }).click();
  await expect(lead.page.getByRole("checkbox", { name: "Potence", exact: true })).toBeChecked();
  await expect(lead.page.getByRole("checkbox", { name: "Protean", exact: true })).toHaveCount(0);

  // Mystery Woman's Auspicious gives her Rugged, as a player's choice would.
  await lead.page.goto(`/troupes/${troupeId}/npcs`);
  await lead.page.getByRole("link", { name: mystery }).click();
  await lead.page.waitForURL(/\/characters\/[^/]+$/);
  await lead.page.goto(`${lead.page.url()}/sheet`);
  await expect(lead.page.locator('[data-free-choices="Auspicious"]')).toContainText("Rugged");
});
