import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, PASSWORD, shots, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES, backstoryOptional, characterTab } from "./support";

/** What the custodian does with people's accounts and characters. */

closeContextsAfterEach();

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
  const row = c.locator("main li").filter({ hasText: player.email });
  await expect(row.getByText(`@${player.handle} · ${player.email}`, { exact: false })).toBeVisible();
  await row.getByRole("button", { name: "Reset password for people-player" }).click();
  await expect(row.getByText("Send it to them yourself.")).toBeVisible();
  await row.getByRole("button", { name: "Make a reset link" }).click();
  const cancelled = await row.getByLabel("Reset link", { exact: true }).inputValue();
  expect(cancelled).toContain("/reset-password/");
  await expect(row.getByText(/^people-player has a reset link, unused, until /)).toBeVisible();
  await expect(row.getByText("reset link out")).toBeVisible();
  const resets = c.locator("section", { has: c.getByRole("heading", { name: "Password resets" }) });
  await expect(resets.getByRole("button", { name: "Cancel people-player's reset link" }).first()).toBeVisible();
  await expect(resets.getByText("people-custodian made a password reset link for people-player.").first()).toBeVisible();
  await c.screenshot(shots("people-reset"));

  // They think better of it and cancel it.
  await row.getByRole("button", { name: "Cancel link" }).click();
  await expect(row.getByText("Make a link that lets people-player set a new password", { exact: false })).toBeVisible();
  await expect(row.getByText("reset link out")).toHaveCount(0);

  // They open the profile.
  await c.locator("main").getByRole("link", { name: new RegExp(player.email) }).click();
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
  await expect(p.getByText(`You sign in with ${player.email}`)).toBeVisible();
  await expect(p.getByText("Horatio can't send email here, so ask the custodian to change your email.")).toBeVisible();

  // The custodian changes it from the People list, with a reason. An address
  // another account uses is refused.
  const c = custodian.page;
  await c.reload();
  await c.getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: "People", exact: true }).click();
  await c.getByLabel("Search people").fill(player.email);
  const row = c
    .locator("main li")
    .filter({ hasText: player.email })
    .filter({ has: c.getByRole("button", { name: "Change email for chmail-player" }) });
  await row.getByRole("button", { name: "Change email for chmail-player" }).click();
  await row.getByLabel("New email").fill(custodian.email);
  await row.getByLabel("Reason").fill("Lost access to the old address");
  await row.getByRole("button", { name: "Change email", exact: true }).click();
  await expect(row.getByText(`uses ${custodian.email} already. If both accounts are the same person's, merge them instead.`, { exact: false })).toBeVisible();
  await row.getByLabel("New email").fill(newEmail);
  await row.getByRole("button", { name: "Change email", exact: true }).click();

  // Nothing changes until the link is opened: the custodian sends it on.
  await expect(row.getByText(`Waiting for chmail-player to confirm ${newEmail}`, { exact: false })).toBeVisible();
  await expect(row.getByText("new email waiting")).toBeVisible();
  const changes = c.locator("section", { has: c.getByRole("heading", { name: "Email changes" }) });
  await expect(changes.getByText(`${player.email} → ${newEmail}`, { exact: false })).toBeVisible();
  const url = await row.getByLabel("Link to confirm the new email").inputValue();
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
  const list = c.locator("main li");
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
  const row = c.locator("main li").filter({ hasText: player.email });
  await row.getByRole("button", { name: "View as viewas-player" }).click();
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
  const row = c.locator("main li").filter({ hasText: lead.email });
  await row.getByRole("button", { name: "Suspend susp-lead" }).click();
  await row.getByLabel("Reason").fill("Threatened another player at the last game");
  await row.getByRole("button", { name: "Suspend susp-lead" }).last().click();
  await expect(row.getByText("suspended", { exact: true })).toBeVisible();

  // They are listed as suspended, with the troupe that wants a new lead, and it is logged.
  // Other tests may suspend people at the same time, so look only at this one.
  const suspended = c.getByRole("list", { name: "Suspended people" }).getByRole("listitem").filter({ hasText: `@${lead.handle}` });
  await expect(suspended.getByText("“Threatened another player at the last game”")).toBeVisible();
  await expect(suspended.getByRole("link", { name: troupeName })).toBeVisible();
  await expect(c.getByText("susp-custodian suspended susp-lead (Threatened another player at the last game).").first()).toBeVisible();
  await c.screenshot(shots("suspended"));

  // The troupe list marks the troupe.
  await c.getByRole("link", { name: "Troupes", exact: true }).click();
  await expect(c.locator("main li").filter({ hasText: troupeName }).getByText("lead suspended")).toBeVisible();

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
  await row.getByRole("button", { name: "Lift the suspension of susp-lead" }).click();
  await row.getByLabel("Why lift it").fill("Apologised and agreed to the code of conduct");
  await row.getByRole("button", { name: "Lift suspension", exact: true }).click();
  await expect(row.getByText("suspended", { exact: true })).toHaveCount(0);
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
  const row = c.locator("main li").filter({ hasText: before.email }).first();
  await row.getByRole("button", { name: "Characters of mvc-before" }).click();
  await expect(row.getByRole("link", { name: /Ottilie Marsh/ })).toContainText(troupeName);
  await row.getByRole("button", { name: "Move Ottilie Marsh to another player" }).click();
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
  const row = c.locator("main li").filter({ hasText: twice.email }).first();
  await row.getByRole("button", { name: "Merge mga-twice with another account" }).click();
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
  await expect(c.locator("main li").filter({ hasText: real.email })).toBeVisible();
  // (Its email is still in the log of recent account events below.)
  await expect(c.getByRole("button", { name: "Merge mga-twice with another account" })).toHaveCount(0);

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
