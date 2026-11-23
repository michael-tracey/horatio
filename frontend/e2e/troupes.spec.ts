import { expect, test, type Locator, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, backstoryOptional, builtVampire, characterTab, chooseDots, choosePick, closeContextsAfterEach, makeCustodian, openNewTroupe, PASSWORD, person, run, shots, tapMid, topBar, troupeTab, expectTabOpen, expectTabCount, isPhone, shutSections, groupTabs, pagePart, tabSettings, closeTabSettings, settingsPart, expectPartOpen, addList, chooseIn, makeChanges, openSections } from "./support";

/** A troupe's setup: its rules, XP range, staff, profile and archiving, and asking for one. */

closeContextsAfterEach();

test("a troupe changes what new characters start with and their downtime actions", async ({ browser }) => {
  const custodian = await person(browser, "start-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "start-lead");
  const player = await person(browser, "start-player");
  const troupeName = `Court of Embers ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead gives new characters a bigger merit budget.
  const l = lead.page;
  await (await topBar(l)).getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await troupeTab(l, "House rules");
  await pagePart(l, "Starting points");
  await l.getByRole("button", { name: "Edit starting Merits" }).click();
  await l.getByLabel("Points for merits").fill("9");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("The rule set's: 7 points")).toBeVisible();
  await l.screenshot(shots("starting"));
  // …and four downtime actions a cycle instead of three.
  await pagePart(l, "Downtime actions");
  await l.getByRole("button", { name: "Edit actions for Everyone" }).click();
  await l.getByLabel("Downtime actions each cycle").fill("4");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("Replaced here")).toBeVisible();
  await expect(l.getByText("4 downtime actions")).toBeVisible();
  await l.screenshot(shots("actions"));

  // A character built for the troupe has that budget in the wizard.
  const p = player.page;
  await p.reload();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await chooseIn(p, "Clan", "Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  for (const heading of ["Attributes", "Focuses", "Skills", "Backgrounds", "Disciplines", "Merits & flaws"]) {
    // A vampire needs Generation before leaving Backgrounds.
    if (heading === "Disciplines") await choosePick(p, "Backgrounds", 1, "Generation");
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  }
  await expect(p.getByText("0 of 9 points")).toBeVisible();
});

test("Settings › Getting ready lists the steps, House rules opens on what plays differently from the book, and Checks come in folded groups that a search looks through (#377, #1048)", async ({ browser }) => {
  const custodian = await person(browser, "tally-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tally-lead");
  const troupeName = `House of Tallies ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // Settings opens on its Features; Getting ready has the steps: nothing is set up yet.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  await troupeTab(l, "Settings");
  await expectPartOpen(l, "Features", "Settings");
  await pagePart(l, "Getting ready", "Settings");
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings/getting-ready$`));
  const steps = l.getByRole("list", { name: "Getting your troupe ready" });
  await expect(steps.getByRole("listitem")).toHaveCount(8);
  await expect(l.getByText("0 of 8 done")).toBeVisible();
  await expect(l.locator("main").getByRole("switch")).toHaveCount(0);
  await l.screenshot(shots("getting-ready-settings"));
  // House rules open, for running staff, on where the troupe plays differently: nowhere yet.
  await troupeTab(l, "House rules");
  const houseRules = l.locator("section").filter({ has: l.getByRole("heading", { name: "Played differently from the book", exact: true }) });
  await expect(houseRules.getByText("Everything plays as the book has it.")).toBeVisible();
  await expect(houseRules.getByRole("list", { name: "Played differently" })).toHaveCount(0);

  // The old address of Setup lands on Getting ready.
  await l.goto(`/troupes/${troupeId}/customise`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings/getting-ready$`));

  // Checks open on the troupe's house rules, of which there are none yet.
  await steps.getByRole("link", { name: /^House rules\W+to do/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/house-rules/checks$`));
  await expect(l.getByText("No house rules yet.")).toBeVisible();
  // All of them come in groups, folded, each with its count.
  await l.getByRole("button", { name: /^All checks/ }).click();
  const clanMerits = l.locator("details").filter({ hasText: "Clan merits, only for their clan or bloodline" });
  await expect(clanMerits).toContainText(/\d{3} checks/);
  await expect(clanMerits).toHaveJSProperty("open", false);
  await expect(l.getByLabel(/^Setting for:/)).toHaveCount(0);
  const techniques = l.locator("details").filter({ has: l.getByRole("heading", { name: "Techniques", exact: true }) });
  await techniques.getByRole("heading", { name: "Techniques", exact: true }).click();
  await expect(techniques.getByLabel(/^Setting for: Animal Swarm needs/)).toBeVisible();

  // A search looks through them all, and opens the group it finds the check in.
  await l.getByLabel("Search checks").fill("Calm Heart");
  await expect(l.getByRole("group", { name: "Checks by kind" }).locator("details")).toHaveCount(1);
  await expect(l.locator("details").filter({ has: l.getByRole("heading", { name: "Merits", exact: true }) })).toContainText("1 of 29 checks");
  await l.getByLabel(/Setting for: Brujah cannot take Calm Heart/).selectOption({ label: "Off" });
  await expect(l.getByText("Saved: Calm Heart is now Off")).toBeVisible();
  await expect(l.getByRole("button", { name: "House rules (1)" })).toBeVisible();
  await l.screenshot(shots("customise-checks"));

  // Getting ready counts it.
  await settingsPart(l, troupeId, "getting-ready");
  await expect(steps.getByRole("link", { name: /^House rules\W+done/ })).toBeVisible();
  // The house rules now list Checks, linked into them.
  await troupeTab(l, "House rules");
  const differently = houseRules.getByRole("list", { name: "Played differently" });
  await expect(differently.getByRole("listitem")).toHaveCount(1);
  await expect(differently.getByRole("link", { name: /^Checks\s*1 of \d+ played differently$/ })).toHaveAttribute("href", `/troupes/${troupeId}/house-rules/checks`);
});

test("a new troupe's Overview shows its storytellers getting it ready, each step ticking itself as it is done, and the card hides and comes back from Settings › Getting ready (#1049, #1048)", async ({ browser }) => {
  const custodian = await person(browser, "ready-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ready-lead");
  const troupeName = `House of First Nights ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // A new troupe: the card is there with nothing done, the next step first, and every step folded away.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Getting your troupe ready" }) });
  await expect(card.getByText("0 of 8 done")).toBeVisible();
  await expect(card.getByRole("link", { name: "Profile", exact: true })).toBeVisible();
  const steps = card.getByRole("list", { name: "Getting your troupe ready" });
  await expect(steps).toHaveCount(0);
  await card.getByRole("button", { name: "Every step" }).click();
  await expect(steps.getByRole("listitem")).toHaveCount(8);
  await expect(steps.getByRole("link", { name: /\Wto do\./ })).toHaveCount(8);
  await l.screenshot(shots("getting-ready"));

  // Who may join: the step's link opens it; choosing a sect ticks it, back on the Overview.
  await steps.getByRole("link", { name: /^Who may join\W+to do/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings/joining$`));
  // The box follows the troupe as saved, so it ticks once the change is in.
  const camarilla = l.locator("section").filter({ has: l.getByRole("heading", { name: "Sects", exact: true }) }).getByRole("checkbox", { name: "Camarilla" });
  await camarilla.click();
  await expect(camarilla).toBeChecked();
  await expect(camarilla).toBeEnabled();
  await troupeTab(l, "Overview");
  await expect(card.getByText("1 of 8 done")).toBeVisible();

  // The first game, added on the profile on this same page, ticks without a reload.
  const profile = l.getByRole("region", { name: "Profile" });
  await profile.getByRole("button", { name: "Edit profile" }).click();
  await profile.getByRole("button", { name: "Edit when it plays" }).click();
  await l.getByLabel("Game starts").fill("2030-02-09T19:00");
  await l.getByRole("button", { name: "Add game" }).click();
  await expect(l.getByRole("list", { name: "Upcoming games to edit" }).getByRole("listitem")).toHaveCount(1);
  await expect(card.getByText("2 of 8 done")).toBeVisible();
  await card.getByRole("button", { name: "Every step" }).click();
  await expect(steps.getByRole("link", { name: /^First game\W+done/ })).toBeVisible();
  await expect(steps.getByRole("link", { name: /^Who may join\W+done/ })).toBeVisible();
  await expect(steps.getByRole("link", { name: /^Staff\W+to do/ })).toBeVisible();

  // Hidden, it is gone from the Overview, and Settings › Getting ready brings it back.
  await card.getByRole("button", { name: "Hide", exact: true }).click();
  await expect(l.getByText("Hidden. Bring it back from Settings › Getting ready.")).toBeVisible();
  await expect(card).toHaveCount(0);
  await troupeTab(l, "Settings");
  await pagePart(l, "Getting ready", "Settings");
  await expect(l.getByText("Hidden from the Overview.")).toBeVisible();
  await expect(l.getByRole("list", { name: "Getting your troupe ready" }).getByRole("link", { name: /^First game\W+done/ })).toBeVisible();
  await l.getByRole("button", { name: "Show on the Overview" }).click();
  await expect(l.getByRole("button", { name: "Hide from the Overview" })).toBeVisible();
  await troupeTab(l, "Overview");
  await expect(card.getByText("2 of 8 done")).toBeVisible();
});

test("a lead storyteller asks the staff to sign in with two steps, and a storyteller without it is sent to set it up first, reading why in the bell (#1057, #1111)", async ({ browser }) => {
  const { page: c, email: custodianEmail } = await person(browser, "twostep-cust");
  makeCustodian(custodianEmail);
  const { page: lead, handle: leadHandle } = await person(browser, "twostep-lead");
  const { page: st, handle: stHandle } = await person(browser, "twostep-st");
  const owls = `Owls ${run}`;
  const made = await c.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: owls, lead_handle: leadHandle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const staffed = await lead.request.put(`/api/troupes/${troupeId}/staff`, { headers: { "X-Horatio": "1" }, data: { handle: stHandle, role: "storyteller" } });
  expect(staffed.status(), await staffed.text()).toBe(200);

  // The lead needs a second step of their own first: a passkey on this device.
  const cdp = await lead.context().newCDPSession(lead);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
  });
  await lead.goto(`/troupes/${troupeId}/staff`);
  const card = lead.locator("section", { has: lead.getByRole("heading", { name: "Two-step sign-in", exact: true }) });
  await card.getByRole("switch", { name: "Staff must sign in with two steps" }).click();
  await expect(card.getByText(/Set up two-step sign-in yourself first/)).toBeVisible();
  await lead.goto("/account/sign-in");
  await lead.getByLabel("Your password").fill(PASSWORD);
  await lead.getByRole("button", { name: "Add a passkey" }).click();
  await lead.getByRole("button", { name: "I've kept them" }).click();
  await lead.goto(`/troupes/${troupeId}/staff`);
  await card.getByRole("switch", { name: "Staff must sign in with two steps" }).click();
  await expect(card.getByRole("switch", { name: "Staff must sign in with two steps" })).toBeChecked();
  await expect(card.getByText(/Not set up yet: twostep-st\. They're asked to set it up/)).toBeVisible();
  await lead.screenshot(shots("staff-two-step"));

  // The storyteller, signed in already, is sent to set it up before anything else.
  await st.goto(`/troupes/${troupeId}`);
  await expect(st).toHaveURL(/\/two-step\?next=/);
  await expect(st.getByRole("heading", { name: "Set up two-step sign-in" })).toBeVisible();
  await expect(st.getByText(`You need two-step sign-in as staff of Owls ${run}.`)).toBeVisible();
  await expect(st.getByRole("navigation", { name: "Main" })).toHaveCount(0);
  await st.screenshot(shots("two-step-setup-required"));

  // Their bell answers before then, and says why it was asked (#1096, #1111).
  await st.getByRole("button", { name: /^Notifications/ }).click();
  const bell = st.getByRole("dialog", { name: "Notifications" });
  const notice = bell.getByRole("button", { name: /asked the troupe's staff to sign in with two steps/ });
  await expect(notice).toHaveCount(1);
  await expect(notice).toContainText(owls);
  await expect(notice).toContainText("Set it up in Account › Sign-in and email");
  await expect(bell.getByRole("link", { name: "Notification settings" })).toHaveCount(0);
  // Tapping it reads it in place, marked read, rather than following its link back here (#1146).
  await expect(notice).toHaveAttribute("aria-expanded", "false");
  await notice.click();
  await expect(notice).toHaveAttribute("aria-expanded", "true");
  await expect(bell.getByRole("button", { name: "Mark all read" })).toHaveCount(0);
  await expect(st).toHaveURL(/\/two-step\?next=/);
  // Its button closes the bell, back to the setup form.
  await bell.getByRole("button", { name: "Set up two-step sign-in" }).click();
  await expect(bell).toBeHidden();
  await expect(st).toHaveURL(/\/two-step\?next=/);

  const stCdp = await st.context().newCDPSession(st);
  await stCdp.send("WebAuthn.enable");
  await stCdp.send("WebAuthn.addVirtualAuthenticator", {
    options: { protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true },
  });
  // On a slow connection, who they are answers after the recovery codes are up: going
  // on waits for it, rather than meeting the gate's old answer and landing back (#1168).
  await st.route("**/api/auth/me", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.continue();
  });
  // Asked for their password again, as on Account (#1110).
  await st.getByLabel("Your password").fill(PASSWORD);
  await st.getByRole("button", { name: "Add a passkey" }).click();
  await st.getByRole("button", { name: "I've kept them" }).click();
  // On to the troupe's page: its heading, as the address can pass through it on the way back.
  await expect(st.getByRole("heading", { name: owls })).toBeVisible();
  await expect(st).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  await st.unroute("**/api/auth/me");
  // Set up, the bell is as usual again, with its settings.
  await st.getByRole("button", { name: /^Notifications/ }).click();
  await expect(st.getByRole("dialog", { name: "Notifications" }).getByRole("link", { name: "Notification settings" })).toBeVisible();
});

test("a troupe's or character's tab that isn't there, or isn't open to them, says so with the way back (#907)", async ({ browser }) => {
  const custodian = await person(browser, "notopen-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "notopen-lead");
  const player = await person(browser, "notopen-player");
  const troupeName = `House of Closed Doors ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const notOpen = `This part of ${troupeName} isn't open to you, or doesn't exist.`;

  // Staff, at a tab that doesn't exist.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/nonsense`);
  await expect(l.getByText(notOpen)).toBeVisible();
  await l.getByRole("link", { name: `Back to ${troupeName}` }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  await expect(l.getByText(notOpen)).toHaveCount(0);

  // Someone not on its staff, at the staff's Settings.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}/settings`);
  await expect(p.getByText(notOpen)).toBeVisible();
  await p.screenshot(shots("troupe-tab-not-open"));

  // A character's page does the same.
  const character = await p.request.post("/api/characters", { headers: { "X-Horatio": "1" }, data: { splat: "vampire", name: "Hollis Doorward" } });
  expect(character.status(), await character.text()).toBe(201);
  const characterId: string = (await character.json()).id;
  await p.goto(`/characters/${characterId}/nonsense`);
  await expect(p.getByText("This part of Hollis Doorward isn't open to you, or doesn't exist.")).toBeVisible();
  // Back to it opens it, and a character in creation opens on its wizard (#915).
  await p.getByRole("link", { name: "Back to Hollis Doorward" }).click();
  await expect(p).toHaveURL(new RegExp(`/characters/${characterId}/create$`));
});

test("Settings open on a Features list: each optional feature on or off, and switching one on brings its tab, its settings behind its Settings button (#783, #784, #909)", async ({ browser }) => {
  const custodian = await person(browser, "switch-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "switch-lead");
  const troupeName = `House of Switches ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // Boons are off: there's no Boons tab under Court.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/titles`);
  // A group's tabs, under its name in the troupe's sections (on a phone, in the section picker).
  let court = await groupTabs(l, "Court");
  await expect(court.getByRole("link", { name: "Titles", exact: true })).toBeVisible();
  await expect(court.getByRole("link", { name: "Boons", exact: true })).toHaveCount(0);
  await shutSections(l);

  // Settings list every feature, on or off, before the groups of settings.
  await l.goto(`/troupes/${troupeId}/settings`);
  const list = l.getByRole("list", { name: "Features" });
  const boons = list.getByRole("listitem", { name: "Boons" });
  await expect(boons.getByText("Off", { exact: true })).toBeVisible();
  await expect(boons.getByRole("link", { name: "Open Boons" })).toHaveCount(0);
  await expect(list.getByRole("listitem", { name: "Feeding" }).getByRole("switch", { name: "Feeding" })).toHaveAttribute("aria-checked", "true");
  // Who's Who is always on: its switch is held on, so its row lines up with the rest (#908).
  await expect(list.getByRole("listitem", { name: "Who's Who" }).getByRole("switch", { name: "Who's Who" })).toBeDisabled();
  await expect(list.getByRole("listitem", { name: "Who's Who" }).getByRole("switch", { name: "Who's Who" })).toHaveAttribute("aria-checked", "true");

  // The lead switches Boons on from the list, the one place it is switched (#784): no card below has a switch of its own.
  await boons.getByRole("switch", { name: "Boons" }).click();
  await expect(boons.getByRole("switch", { name: "Boons" })).toHaveAttribute("aria-checked", "true");
  await expect(l.getByRole("checkbox", { name: /^Keep a boon ledger/ })).toHaveCount(0);
  await expect(l.getByRole("heading", { name: "Boons", exact: true })).toHaveCount(0);
  // Its Settings link lands on its tab, under Court, with its Settings dialog open (#909).
  await boons.getByRole("link", { name: "Settings for Boons" }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/boons#settings$`));
  let settings = await tabSettings(l, "Boons");
  await expect(settings.getByRole("radio", { name: /^Also what they're owed/ })).toBeVisible();
  // Closed, the ledger is there, and the address no longer opens them.
  await closeTabSettings(settings);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/boons$`));
  court = await groupTabs(l, "Court");
  await expect(court.getByRole("link", { name: "Boons", exact: true })).toBeVisible();
  await shutSections(l);
  await expect(l.getByRole("button", { name: "Register boons" })).toBeVisible();
  // Opened from the list, the tab has them behind its Settings button, nothing folded above the ledger.
  await l.goto(`/troupes/${troupeId}/settings`);
  await boons.getByRole("link", { name: "Open Boons" }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/boons$`));
  await expect(l.getByRole("radio", { name: /^Also what they're owed/ })).toHaveCount(0);
  await expect(l.locator("summary", { hasText: "Settings" })).toHaveCount(0);
  settings = await tabSettings(l, "Boons");
  await expect(settings.getByRole("radio", { name: /^Also what they're owed/ })).toBeVisible();
  await closeTabSettings(settings);

  // Each group of settings is a part of its own (#908): an old anchor from the one long page lands on its card, wherever it is now.
  await l.goto(`/troupes/${troupeId}/settings#feature-feeding`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings/blood#feature-feeding$`));
  await expectPartOpen(l, "Blood, diablerie and feeding", "Settings");
  await expect(l.locator("#feature-feeding").getByRole("heading", { name: "Feeding", exact: true })).toBeInViewport();
  await l.goto(`/troupes/${troupeId}/settings#feature-boons`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/boons#settings$`));
  await closeTabSettings(await tabSettings(l, "Boons"));
  // A part that isn't one goes back to the Features list.
  await l.goto(`/troupes/${troupeId}/settings/nonsense`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings$`));
  await expectPartOpen(l, "Features", "Settings");

  // Quests: switched on, a Quests tab under Between games; switched off again, it goes.
  await l.goto(`/troupes/${troupeId}/settings`);
  const quests = list.getByRole("listitem", { name: "Quests" });
  await quests.getByRole("switch", { name: "Quests" }).click();
  await expect(quests.getByText("On, 1 request a character each cycle")).toBeVisible();
  await quests.getByRole("link", { name: "Open Quests" }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/quests`));
  let downtimes = await groupTabs(l, "Between games");
  await expect(downtimes.getByRole("link", { name: "Quests", exact: true })).toBeVisible();
  await shutSections(l);
  await l.goto(`/troupes/${troupeId}/settings`);
  await quests.getByRole("switch", { name: "Quests" }).click();
  await expect(quests.getByRole("switch", { name: "Quests" })).toHaveAttribute("aria-checked", "false");
  await expect(quests.getByRole("link", { name: "Open Quests" })).toHaveCount(0);
  await l.goto(`/troupes/${troupeId}/downtimes`);
  downtimes = await groupTabs(l, "Between games");
  await expect(downtimes.getByRole("link", { name: "Downtimes", exact: true })).toBeVisible();
  await expect(downtimes.getByRole("link", { name: "Quests", exact: true })).toHaveCount(0);
});

test("a tab's own settings are behind one Settings button, not folded above its content, and an assistant storyteller reads them there (#909)", async ({ browser }) => {
  const custodian = await person(browser, "cogs-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "cogs-lead");
  const assistant = await person(browser, "cogs-assistant");
  await custodian.page.reload();
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Cogs ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  for (const [url, data] of [
    [`/api/troupes/${troupeId}/staff`, { handle: assistant.handle, role: "assistant_storyteller" }],
    [`/api/troupes/${troupeId}/boon-ledger`, { on: true }],
  ] as const) {
    const done = await lead.page.request.put(url, { headers, data });
    expect(done.status(), await done.text()).toBeLessThan(300);
  }

  // Approvals opens on what waits: no folded box above it, and the button at the right.
  const a = assistant.page;
  await a.goto(`/troupes/${troupeId}/approvals`);
  const button = a.locator("main").getByRole("button", { name: "Settings", exact: true });
  await expect(button).toBeVisible();
  await expect(a.locator("summary", { hasText: "Settings" })).toHaveCount(0);
  await expect(a.getByRole("region", { name: "Teachers" })).toHaveCount(0);
  const main = (await a.locator("main").boundingBox())!;
  const at = (await button.boundingBox())!;
  expect(main.x + main.width - (at.x + at.width)).toBeLessThan(40);

  // The assistant reads them, read-only, in a dialog named after the tab: the whole screen on a phone.
  const settings = await tabSettings(a, "Approvals");
  const teachers = settings.getByRole("region", { name: "Teachers" });
  await expect(teachers).toContainText("The troupe's storytellers change this.");
  await expect(teachers.getByRole("button", { name: "Add a rule" })).toHaveCount(0);
  if (isPhone(a)) expect((await settings.boundingBox())!.width).toBe(a.viewportSize()!.width);
  await closeTabSettings(settings);
  await expect(button).toBeFocused();

  // The Features list links them to a feature's settings too, which open on its tab, read-only.
  await a.goto(`/troupes/${troupeId}/settings`);
  await a.getByRole("list", { name: "Features" }).getByRole("link", { name: "Settings for Boons" }).click();
  await expect(a).toHaveURL(new RegExp(`/troupes/${troupeId}/boons#settings$`));
  const boons = await tabSettings(a, "Boons");
  await expect(boons.getByRole("region", { name: "Boons" })).toContainText("The troupe's storytellers change this.");
  await expect(boons.getByRole("radio")).toHaveCount(0);
});

test("the lead builds a check of the troupe's own from blocks, and it refuses a purchase (#432)", async ({ browser }) => {
  const custodian = await person(browser, "ownchk-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ownchk-lead");
  const player = await person(browser, "ownchk-player");
  const troupeName = `House of Own Checks ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // The lead keeps Iron Will for the Ventrue: a trait from the catalogue, and a clan block.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/checks`);
  await l.getByRole("button", { name: "Add a check" }).click();
  const form = l.getByRole("region", { name: "A new check" });
  await form.getByLabel("Kind of trait", { exact: true }).selectOption({ label: "Merits" });
  await form.getByLabel("Trait", { exact: true }).selectOption("Iron Will");
  await form.getByLabel("It", { exact: true }).selectOption({ label: "Is allowed only when…" });
  await form.getByLabel("Condition: add a block").selectOption({ label: "Clan or its bloodlines…" });
  await form.getByLabel("Condition 1: add a trait").selectOption("Ventrue");
  const preview = form.getByRole("region", { name: "Preview" });
  await expect(preview).toContainText("Iron Will: refused unless the clan is Ventrue or one of its bloodlines.");
  await expect(preview).toContainText("None of the troupe's characters breaks it now.");
  await form.getByLabel("Message the player sees").fill("Iron Will is for the Ventrue here.");
  await form.getByRole("button", { name: "Add the check" }).click();
  const own = l.getByRole("list", { name: "The troupe's own checks" });
  await expect(own.getByRole("listitem").filter({ hasText: "Iron Will is for the Ventrue here." })).toContainText("Our own");
  await l.screenshot(shots("customise-own-check"));

  // A Brujah being built for the troupe cannot take it on the Merits step.
  const p = player.page;
  const character = await p.request.post("/api/characters", { headers, data: { splat: "vampire", name: "Osric Vane", building_troupe_id: troupeId } });
  expect(character.status(), await character.text()).toBe(201);
  const characterId: string = (await character.json()).id;
  const clan = await p.request.put(`/api/characters/${characterId}/traits`, { headers, data: { category: "clan", name: "Brujah", rating: null } });
  expect(clan.status(), await clan.text()).toBe(200);
  const bought = await p.request.put(`/api/characters/${characterId}/creation/categories/merits`, { headers, data: { picks: [{ name: "Iron Will" }] } });
  expect(bought.status()).toBe(409);
  expect((await bought.json()).detail).toContain("Iron Will is for the Ventrue here.");

  // The players' House rules tab lists it as the troupe's own.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  await expect(p.getByText("Iron Will is for the Ventrue here.")).toBeVisible();
});

test("a teacher rule asks for a teacher, and a Lore specialisation is bought from one and approved (#440)", async ({ browser }) => {
  const custodian = await person(browser, "tutor-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tutor-lead");
  const mentor = await person(browser, "tutor-mentor");
  const pupil = await person(browser, "tutor-pupil");
  const troupeName = `House of Tutors ${run}`;
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(lead.page, troupeId);

  // The lead adds the first example: Lore specialisations after creation, with a downtime action.
  // Teachers moved from House rules to Approvals' Settings (#785, #909): the old address opens them there.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/teachers`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals#settings-teachers$`));
  await expect((await tabSettings(l, "Approvals")).getByText("No teacher rules.")).toBeVisible();
  await l.getByRole("button", { name: "Add a rule" }).click();
  const form = l.getByRole("region", { name: "A new teacher rule" });
  await form.getByLabel("Start from an example (optional)").selectOption({ label: "Lore specialisations after creation, with a downtime action" });
  const rule = "Lore Specialisations need a teacher who holds it at the rating learned and 1 downtime action, once creation is finished.";
  await expect(form.getByRole("region", { name: "Preview" })).toContainText(rule);
  await form.getByRole("button", { name: "Add the rule" }).click();
  await expect(l.getByRole("list", { name: "Teacher rules" })).toContainText(rule);
  await l.screenshot(shots("customise-teacher-rule"));

  // Brother Tobiah knows the Sabbat; Wren, his pupil, has a dot of Lore and no subject yet. Both join.
  const skills = ATTRIBUTES_AND_FOCUSES.skills.map(([name, rating]): [string, number] => [name === "Medicine" ? "Lore" : name, rating]);
  const build = { ...ATTRIBUTES_AND_FOCUSES, skills, backgrounds: [["Generation", 1], ["Herd", 2], ["Fame", 3]] as [string, number][], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][] };
  const tobiah = await builtVampire(mentor.page, "Brother Tobiah", "Brujah", build, [["lore_specializations", "Sabbat", 1]]);
  const wren = await builtVampire(pupil.page, "Wren Hallow", "Brujah", build);
  for (const [who, id] of [[mentor, tobiah], [pupil, wren]] as const) {
    const asked = await who.page.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
    expect(asked.status(), await asked.text()).toBe(201);
    const approved = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
    expect(approved.status(), await approved.text()).toBe(200);
  }

  // Wren adds the Sabbat to her Lore: the sheet asks who teaches it, offering Brother Tobiah.
  const p = pupil.page;
  await p.goto(`/characters/${wren}`);
  const lore = p.locator("section").filter({ has: p.getByRole("heading", { name: "Skills", exact: true }) }).locator("li[data-trait='Lore']");
  await makeChanges(p);
  await lore.getByRole("button", { name: "Add to Lore Specialisations" }).click();
  await lore.getByRole("button", { name: "Sabbat", exact: true }).click();
  await expect(lore.getByText("Needs a teacher who holds it at 1 or more.")).toBeVisible();
  const add = lore.getByRole("button", { name: "Add with this teacher" });
  await expect(add).toBeDisabled();
  await lore.getByLabel("Teacher for Sabbat").selectOption({ label: "Brother Tobiah" });
  await add.click();
  await expect(lore.getByText("Lore Specialisations 1 of 1")).toBeVisible();
  await p.screenshot(shots("teacher-lore-specialisation"));

  // It waits on the troupe, taught by Brother Tobiah; approving owes the downtime action.
  await l.goto(`/troupes/${troupeId}/approvals`);
  await expect(l.getByText(/Taught by Brother Tobiah\. Learning takes 1 downtime action, owed when approved\./)).toBeVisible();
  // Wren's is the only request waiting.
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Taught by Brother Tobiah.", { exact: false })).toHaveCount(0);

  // The players' House rules tab lists the rule.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  await expect(p.getByRole("list", { name: "Teacher rules" })).toContainText(rule);
});

test("a troupe's players read its house rules: a price the lead changes shows there beside the book's", async ({ browser }) => {
  const custodian = await person(browser, "lantern-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "lantern-lead");
  const player = await person(browser, "lantern-player");
  const troupeName = `House of Lanterns ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // The lead prices attributes at 4 XP a dot, with a note for players.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/costs`);
  await l.getByRole("button", { name: "Edit the price for All Attributes" }).click();
  await l.getByLabel("How it's priced").selectOption({ label: "The same for each dot" });
  await l.getByLabel("XP per dot").fill("4");
  await l.getByLabel("Note for players").fill("Training is slow here");
  await l.getByRole("region", { name: /^Price for / }).getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("Only house rules (1)")).toBeVisible();

  // A player's character visits the troupe; from its Troupes tab the player opens the house rules.
  const p = player.page;
  const id = await builtVampire(p, "Liesl", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const joined = await p.request.post(`/api/characters/${id}/troupes`, { headers: { "X-Horatio": "1" }, data: { troupe_id: troupeId } });
  expect(joined.status(), await joined.text()).toBeLessThan(300);
  await p.goto(`/characters/${id}`);
  await characterTab(p, "Troupes");
  await p.getByRole("link", { name: `${troupeName}'s house rules` }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/house-rules$`));
  const costs = p.locator("section").filter({ has: p.getByRole("heading", { name: "Costs", exact: true }) });
  const attributes = costs.getByRole("listitem").filter({ hasText: "All Attributes" });
  await expect(attributes.getByText("4 XP per dot")).toBeVisible();
  await expect(attributes.getByText("By the book: 3 XP per dot")).toBeVisible();
  await expect(attributes.getByText("House rule: Training is slow here")).toBeVisible();
  await expect(p.getByText(/The storytellers approve it before the troupe accepts the character/)).toBeVisible();
  await p.screenshot(shots("house-rules"));
});

test("House rules and Specialisations pick their parts from one list: down the side on a wide screen, behind one button on a phone (#906)", async ({ browser }) => {
  const custodian = await person(browser, "partpick-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "partpick-lead", { viewport: { width: 375, height: 800 }, isMobile: true, hasTouch: true });
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Picked Parts ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const base = `/troupes/${(await made.json()).id}`;
  const parts = ["As players read it", "Checks", "Costs", "Starting points", "Downtime actions", "Downtime keywords", "Languages", "House merits and flaws", "Written rules", "Book traits"];

  // On a phone: no row of parts, one button naming the open one.
  const l = lead.page;
  // Customise › Rules became the House rules tab (#782): its old address opens Checks there.
  await l.goto(`${base}/rules`);
  await expect(l).toHaveURL(new RegExp(`${base}/house-rules/checks$`));
  const picker = l.locator("main").getByRole("navigation", { name: "House rules", exact: true });
  const button = picker.getByRole("button");
  await expect(button).toHaveAccessibleName("Checks");
  await expect(picker.getByRole("link")).toHaveCount(0);
  expect((await button.boundingBox())!.height).toBeLessThan(50);
  expect(await l.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  // It opens every part, one a line; the parts that set up a feature moved to that feature's tab (#785).
  await button.click();
  const sheet = l.getByRole("dialog", { name: "House rules" });
  await expect(sheet.getByRole("link")).toHaveText(parts);
  await expect(sheet.getByRole("link", { name: "Checks", exact: true })).toHaveAttribute("aria-current", "page");
  await l.screenshot(shots("house-rules-parts-sheet"));
  await sheet.getByRole("link", { name: "Book traits", exact: true }).click();
  await expect(sheet).toBeHidden();
  await expect(l).toHaveURL(new RegExp(`${base}/house-rules/book-traits$`));
  await expect(button).toHaveAccessibleName("Book traits");
  await l.screenshot(shots("house-rules-parts-phone"));

  // Specialisations: the same picker, its kinds under Skills and Backgrounds.
  await l.goto(`${base}/specialisations`);
  await expect(l).toHaveURL(new RegExp(`${base}/specialisations/lore$`));
  const kinds = l.locator("main").getByRole("navigation", { name: "Specialisations", exact: true });
  await expect(kinds.getByRole("button")).toHaveAccessibleName(/^Skills\W+Lore$/);
  await kinds.getByRole("button").click();
  const kindSheet = l.getByRole("dialog", { name: "Specialisations" });
  await expect(kindSheet.getByRole("heading", { level: 3 })).toHaveText(["Skills", "Backgrounds"]);
  await kindSheet.getByRole("list", { name: "Backgrounds" }).getByRole("link", { name: "Haven", exact: true }).click();
  await expect(l).toHaveURL(new RegExp(`${base}/specialisations/haven$`));
  await expect(kinds.getByRole("button")).toHaveAccessibleName(/^Backgrounds\W+Haven$/);

  // On a desktop: the parts in one column down the left, the open part beside them.
  const desk = await (await browser.newContext({ storageState: await l.context().storageState(), viewport: { width: 1280, height: 900 }, isMobile: false, hasTouch: false })).newPage();
  await desk.goto(`${base}/house-rules/checks`);
  const list = desk.locator("main").getByRole("navigation", { name: "House rules", exact: true });
  await expect(list.getByRole("button")).toBeHidden();
  await expect(list.getByRole("link")).toHaveText(parts);
  const boxes = await Promise.all((await list.getByRole("link").all()).map(async (link) => (await link.boundingBox())!));
  for (const [i, box] of boxes.entries()) {
    expect(box.x).toBe(boxes[0]!.x);
    // One line each, under the one before.
    expect(box.height).toBeLessThan(40);
    if (i > 0) expect(box.y).toBeGreaterThan(boxes[i - 1]!.y + boxes[i - 1]!.height - 1);
  }
  const search = (await desk.getByLabel("Search checks").boundingBox())!;
  expect(search.x).toBeGreaterThan(boxes[0]!.x + boxes[0]!.width);
  expect(await desk.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await list.getByRole("link", { name: "Costs", exact: true }).click();
  await expect(desk).toHaveURL(new RegExp(`${base}/house-rules/costs$`));
  await expect(list.getByRole("link", { name: "Costs", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(desk.getByRole("button", { name: "Add a price" })).toBeVisible();
  await desk.screenshot(shots("house-rules-parts-desktop"));
  await desk.goto(`${base}/specialisations/lore`);
  const kindList = desk.locator("main").getByRole("navigation", { name: "Specialisations", exact: true });
  await expect(kindList.getByRole("heading", { level: 3 })).toHaveText(["Skills", "Backgrounds"]);
  await expect(kindList.getByRole("link", { name: "Lore", exact: true })).toHaveAttribute("aria-current", "page");
  const lore = (await kindList.getByRole("link", { name: "Lore", exact: true }).boundingBox())!;
  const haven = (await kindList.getByRole("link", { name: "Haven", exact: true }).boundingBox())!;
  expect(haven.x).toBe(lore.x);
  expect(haven.y).toBeGreaterThan(lore.y);
  await desk.screenshot(shots("specializations-parts-desktop"));
});

test("on a touch screen the page tabs, info buttons, ⋯ menus and feature links are at least 40 px, and a mouse keeps them small (#903)", async ({ browser }) => {
  const custodian = await person(browser, "tapsize-custodian");
  makeCustodian(custodian.email);
  const touch = { viewport: { width: 375, height: 800 }, isMobile: true, hasTouch: true };
  const lead = await person(browser, "tapsize-lead", touch);
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Wide Taps ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const base = `/troupes/${(await made.json()).id}`;
  const l = lead.page;
  const box = async (target: Locator) => {
    await expect(target).toBeVisible();
    return (await target.boundingBox())!;
  };
  const tappable = async (target: Locator) => {
    const { width, height } = await box(target);
    expect(width, await target.textContent()).toBeGreaterThanOrEqual(40);
    expect(height, await target.textContent()).toBeGreaterThanOrEqual(40);
  };

  // House rules' part picker (#906): its button, and each part in its sheet.
  await l.goto(`${base}/house-rules/checks`);
  await tappable(l.locator("main").getByRole("navigation", { name: "House rules", exact: true }).getByRole("button"));
  await l.locator("main").getByRole("navigation", { name: "House rules", exact: true }).getByRole("button").click();
  const parts = l.getByRole("dialog", { name: "House rules" }).getByRole("link");
  await expect(parts.first()).toBeVisible();
  for (const part of await parts.all()) await tappable(part);
  await l.keyboard.press("Escape");

  await l.goto(`${base}/roster`);
  await tappable(l.getByRole("button", { name: "More for the troupe's characters" }));

  // The info button grows, but its line keeps the 20 px it had.
  await l.goto(`${base}/equipment`);
  const info = l.getByRole("button", { name: "About equipment" });
  await tappable(info);
  expect((await box(info.locator(".."))).height).toBeLessThanOrEqual(20);

  // A feature's links, 16 px apart.
  await l.goto(`${base}/settings`);
  const open = await box(l.getByRole("link", { name: "Open Who's Who" }));
  const settings = await box(l.getByRole("link", { name: "Settings for Who's Who" }));
  expect(open.height).toBeGreaterThanOrEqual(40);
  expect(settings.height).toBeGreaterThanOrEqual(40);
  if (settings.y === open.y) expect(settings.x - (open.x + open.width)).toBeGreaterThanOrEqual(16);

  // With a mouse they stay as small as they were.
  const desk = await (await browser.newContext({ storageState: await l.context().storageState(), viewport: { width: 1280, height: 900 }, isMobile: false, hasTouch: false })).newPage();
  await desk.goto(`${base}/equipment`);
  const small = await box(desk.getByRole("button", { name: "About equipment" }));
  expect(small.width).toBe(20);
  await desk.goto(`${base}/house-rules/checks`);
  expect((await box(desk.getByRole("navigation", { name: "House rules" }).getByRole("link", { name: "Checks", exact: true }))).height).toBeLessThan(40);
});

test("at 700 px a troupe's tab row that scrolls shows a chevron at the edge with more, and pressing it brings the rest into view (#921)", async ({ browser }) => {
  const custodian = await person(browser, "chevron-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "chevron-lead", { viewport: { width: 700, height: 900 } });
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Chevron Row ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const main = l.locator("main");
  // The group row fits at 700 px, Setting up and all, so it has no chevron.
  const groups = main.getByRole("navigation", { name: "Troupe sections" });
  await expect(groups.getByRole("link", { name: "Setting up", exact: true })).toBeInViewport({ ratio: 1 });
  await expect(groups.getByTestId(/^row-chevron/)).toHaveCount(0);

  // The Troupe group's tabs run on past the right edge: a chevron there, and none at the left.
  const pills = main.getByRole("navigation", { name: "Troupe", exact: true });
  const first = pills.getByRole("link").first();
  const last = pills.getByRole("link").last();
  await expect(first).toBeInViewport({ ratio: 1 });
  await expect(last).not.toBeInViewport({ ratio: 1 });
  const end = pills.getByTestId("row-chevron-end");
  await expect(end).toBeVisible();
  await expect(pills.getByTestId("row-chevron-start")).toHaveCount(0);
  const row = (await pills.boundingBox())!;
  const chevron = (await end.boundingBox())!;
  expect(Math.round(chevron.x + chevron.width)).toBe(Math.round(row.x + row.width));
  expect(chevron.width).toBe(40);
  expect(chevron.height).toBe(40);
  await l.screenshot(shots("troupe-tabs-chevron"));

  // Pressing it scrolls the row, and only that: the last tab comes into view, and the chevron moves to the left.
  await end.click();
  await expect(last).toBeInViewport({ ratio: 1 });
  await expect(end).toHaveCount(0);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  const start = pills.getByTestId("row-chevron-start");
  await expect(start).toBeVisible();
  await start.click();
  await expect(first).toBeInViewport({ ratio: 1 });
  await expect(start).toHaveCount(0);

  // On a wide screen the row fits, with no chevron.
  await l.setViewportSize({ width: 1280, height: 900 });
  await expect(last).toBeInViewport({ ratio: 1 });
  await expect(pills.getByTestId(/^row-chevron/)).toHaveCount(0);
});

test("a troupe's tabs: a player's one group is the only row, the phone's list starts with the tabs opened last on any device, and every old address lands on its new one (#1048)", async ({ browser }) => {
  const custodian = await person(browser, "recent-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "recent-lead");
  const player = await person(browser, "recent-player");
  await custodian.page.reload();
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Recent Rooms ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const base = `/troupes/${troupeId}`;
  await backstoryOptional(custodian.page, troupeId);
  const id = await builtVampire(player.page, "Ottavia Recent", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await player.page.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const approved = await lead.page.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBeLessThan(300);

  // A player sees one group: no group row, its tabs the only one (on a phone, no group named).
  const p = player.page;
  await p.goto(base);
  const sections = p.locator("main").getByRole("navigation", { name: "Troupe sections" });
  if (isPhone(p)) await expect(sections.getByRole("button")).toHaveAccessibleName(/^Overview\b/);
  else {
    await expect(sections.getByRole("link", { name: "Troupe", exact: true })).toHaveCount(0);
    await expect(sections.getByRole("link", { name: "Overview", exact: true })).toHaveAttribute("aria-current", "page");
  }
  await troupeTab(p, "House rules");
  await expectTabOpen(p, "Troupe", "House rules");

  // The lead opens a few tabs; the list is saved on their account a moment after the last.
  // Their list comes only once three are open, as from a busy server: none opened before it is lost (#1208).
  const l = lead.page;
  let answer = () => {};
  const answered = new Promise<void>((done) => (answer = done));
  await l.route(`**/api${base}/recent-tabs`, async (route) => {
    if (route.request().method() === "GET") await answered;
    await route.continue();
  });
  await l.goto(base);
  for (const [group, tab] of [["Characters", "Approvals"], ["Characters", "Roster"], ["Between games", "Downtimes"]] as const) {
    await troupeTab(l, tab);
    // Open before the next is chosen: on a busy phone, a sheet opened sooner is shut as the tab comes in.
    await expectTabOpen(l, group, tab);
  }
  answer();
  // The save with Settings first, not one sent before it.
  const saved = l.waitForResponse((r) => r.url().endsWith(`/api${base}/recent-tabs`) && r.request().method() === "PUT" && r.request().postDataJSON()?.tabs?.[0] === "/settings");
  await troupeTab(l, "Settings");
  expect((await saved).status()).toBe(200);
  // A wide screen has no Recent row.
  if (!isPhone(l)) await expect(l.getByText("Recent", { exact: true })).toHaveCount(0);

  // On their phone, the list starts with the last three, newest first, without the one open.
  const phone = await (await browser.newContext({ storageState: await l.context().storageState(), viewport: { width: 375, height: 800 }, isMobile: true, hasTouch: true })).newPage();
  await phone.goto(base);
  const sheet = await openSections(phone);
  await expect(sheet.getByRole("list", { name: "Recent", exact: true }).getByRole("link")).toHaveText(["Settings", "Downtimes", "Roster"]);
  await phone.screenshot(shots("troupe-tabs-recent"));
  await shutSections(phone);
  await phone.close();

  // Every old address lands on its new one, with what followed it and its query.
  const moved: [string, string][] = [
    ["characters?show=npcs", "roster\\?show=npcs"],
    ["lines-veils", "lines-and-veils"],
    ["shared", "shared-backgrounds"],
    ["play", "at-game"],
    ["xp", "award-xp"],
    ["court", "court-over-time"],
    ["obligations", "web-of-obligation"],
    ["work", "my-work"],
    ["tables", "fill-tables"],
    ["influence/effects", "influence-log/effects"],
    ["specializations/lore", "specialisations/lore"],
    ["share", "export-and-import"],
    ["news-agencies", "news/agencies"],
    ["log", "log"],
  ];
  for (const [old, now] of moved) {
    await l.goto(`${base}/${old}`);
    await expect(l).toHaveURL(new RegExp(`${base}/${now}$`));
  }
  // The log has no tab of its own: the Overview is open on it.
  await expectTabOpen(l, "Troupe", "Overview");
});

test("a lead prices skills at 1× for Generation background 2, and a Generation ●● character pays that in the cart (#522)", async ({ browser }) => {
  const custodian = await person(browser, "genprice-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "genprice-lead");
  const player = await person(browser, "genprice-player");
  const troupeName = `House of the Second Dot ${run}`;
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(custodian.page, troupeId);

  // The lead adds a price only for Generation background 2, with no JSON: rising, at 1 XP.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/costs`);
  await l.getByRole("button", { name: "Add a price" }).click();
  await l.getByLabel("Category").selectOption({ label: "Skills" });
  await l.getByRole("button", { name: "Add a condition" }).click();
  await l.getByLabel("Condition 1", { exact: true }).selectOption({ label: "Generation background" });
  await l.getByLabel("Condition 1: how").selectOption({ label: "is" });
  await l.getByLabel("Condition 1: rating").selectOption("2");
  await l.getByLabel("How it's priced").selectOption({ label: "Rising: each dot costs its number × the amount" });
  await l.getByLabel("XP per dot").fill("1");
  await expect(l.getByRole("row", { name: "As written 2 6 12 20 30" })).toBeVisible();
  await expect(l.getByRole("row", { name: "With the change 1 3 6 10 15" })).toBeVisible();
  await l.screenshot(shots("costs-condition"));
  await l.getByRole("button", { name: "Add the price" }).click();
  await expect(l.getByText("All Skills, Generation background 2", { exact: true })).toBeVisible();
  await expect(l.getByText("Only house rules (1)")).toBeVisible();

  // A Generation ●● character the troupe accepts pays 1× for Brawl, not the book's 2×.
  const p = player.page;
  const id = await builtVampire(p, "Sabeline", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Generation", 2], ["Herd", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const accepted = await l.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
  expect(accepted.status(), await accepted.text()).toBeLessThan(300);
  await p.goto(`/characters/${id}`);
  await makeChanges(p);
  await tapMid(p, "Raise Brawl");
  const cart = p.getByRole("list", { name: "Changes in the cart" });
  await expect(cart.getByRole("listitem").filter({ hasText: "Brawl 4 → 5" })).toContainText("Brawl 4 → 5 · 5 XP");
  await p.screenshot(shots("cart-condition"));

  // The house rules say it in plain words.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  const costs = p.locator("section").filter({ has: p.getByRole("heading", { name: "Costs", exact: true }) });
  await expect(costs.getByRole("listitem").filter({ hasText: "All Skills, Generation background 2" })).toContainText("1 XP × the new rating");
});

test("a lead chooses the accelerated chart of languages, and the House rules tab shows it (#437)", async ({ browser }) => {
  const custodian = await person(browser, "lingo-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "lingo-lead");
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Tongues of Babel ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // Setting up › House rules › Languages: the book's one per dot until the lead picks a chart.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/languages`);
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Languages from Linguistics" }) });
  await expect(card.getByLabel(/^Book/)).toBeChecked();
  await card.getByLabel(/Accelerated chart/).click();
  const languages = card.getByRole("row", { name: /^Languages/ });
  await expect(languages.getByRole("cell").nth(6)).toHaveText("32");
  await expect(card.getByRole("row", { name: /With Natural Linguist/ }).getByRole("cell").nth(6)).toHaveText("64");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(l.getByText("Saved: how many languages Linguistics gives")).toBeVisible();
  await expect(card.getByRole("button", { name: "Save" })).toBeDisabled();
  await l.screenshot(shots("languages-setting"));

  // Its players read the chart beside the book's.
  await l.goto(`/troupes/${troupeId}/house-rules`);
  const other = l.locator("section").filter({ has: l.getByRole("heading", { name: "Other house rules" }) });
  const rule = other.getByRole("listitem").filter({ hasText: "Languages from Linguistics" });
  await expect(rule.getByText(/^1, 2, 4, 8, 16, 24 and 32 languages/)).toBeVisible();
  await expect(rule.getByText(/By the book: One per dot of Linguistics/)).toBeVisible();
  await expect(rule.getByRole("row", { name: /^Languages/ }).getByRole("cell").nth(4)).toHaveText("16");
});

test("a troupe's written rules: the lead adds and orders them, and a player reads them by section, in the rules browser and on its profile (#434)", async ({ browser }) => {
  const custodian = await person(browser, "quill-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "quill-lead");
  const player = await person(browser, "quill-player");
  const troupeName = `Court of Quills ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // The lead writes three rules under Setting up › House rules › Written rules, one about a merit.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/checks`);
  await pagePart(l, "Written rules");
  const add = async (title: string, section: string, body: string, trait?: [string, string]) => {
    await l.getByRole("button", { name: "Add a rule" }).click();
    const dialog = l.getByRole("dialog", { name: "Add a written rule" });
    await dialog.getByLabel("Title").fill(title);
    await dialog.getByLabel("Section").fill(section);
    await dialog.getByLabel("The rule, in Markdown").fill(body);
    if (trait) {
      await dialog.getByLabel("About a trait").selectOption({ label: trait[0] });
      await dialog.getByLabel("Which one").fill(trait[1]);
      await dialog.getByLabel("Book page").fill("312");
    }
    await dialog.getByRole("button", { name: "Add it" }).click();
    await expect(dialog).toBeHidden();
    await expect(l.getByRole("button", { name: `Edit ${title}` })).toBeVisible();
  };
  await add("The Harpy vote", "Status", "The Harpies vote **openly**, at court.", ["Merits", "Calm Heart"]);
  await add("Crafts difficulties", "Skills", "Crafts tests are against a set difficulty.");
  await add("Performance difficulties", "Skills", "As Crafts.");
  // Performance first in its section.
  await l.getByRole("button", { name: "Move Performance difficulties up" }).click();
  await expect(l.getByRole("button", { name: "Move Performance difficulties up" })).toBeDisabled();
  await l.getByLabel(/Show them on the troupe's profile/).click();
  await expect(l.getByLabel(/Show them on the troupe's profile/)).toBeChecked();

  // A player reads them on the House rules tab, by section, from a contents list.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}/house-rules`);
  const written = p.locator("section").filter({ has: p.getByRole("heading", { name: "Written rules", exact: true }) });
  const contents = written.getByRole("navigation", { name: "Contents" });
  await expect(contents.getByRole("link")).toHaveText(["Performance difficulties", "Crafts difficulties", "The Harpy vote"]);
  await contents.getByRole("link", { name: "The Harpy vote" }).click();
  await expect(p).toHaveURL(/#written-rule-/);
  const harpy = written.getByTestId("written-rule").filter({ hasText: "The Harpy vote" });
  await expect(harpy.locator("strong")).toHaveText("openly");
  await expect(harpy).toContainText("About Calm Heart, see p. 312.");
  await p.screenshot(shots("written-rules"));

  // The rules browser finds them as the troupe's house rules, and Calm Heart links to its rule.
  await p.goto(`/rules?troupe=${troupeId}`);
  const search = p.getByRole("searchbox", { name: "Search the rules" });
  await search.fill("openly");
  const entry = p.getByTestId("rules-entry").filter({ hasText: "The Harpy vote" });
  await expect(entry.getByText("House rule", { exact: true })).toBeVisible();
  await search.fill("calm heart");
  const calm = p.getByTestId("rules-entry").filter({ has: p.getByRole("heading", { name: "Calm Heart", exact: true }) });
  await calm.getByRole("link", { name: "The Harpy vote" }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/house-rules#written-rule-`));

  // The troupe's profile, on its Overview, shows them too.
  await p.goto(`/troupes/${troupeId}`);
  const onProfile = p.locator("section").filter({ has: p.getByRole("heading", { name: "House rules", exact: true }) });
  await expect(onProfile.getByTestId("written-rule")).toHaveCount(3);
});

test("staff write the setting: a theme from the book, a mood of their own, put in order by dragging, and a note (#770)", async ({ browser }) => {
  const custodian = await person(browser, "motif-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "motif-lead");
  const assistant = await person(browser, "motif-assistant");
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Court of Motifs ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const staffed = await lead.page.request.put(`/api/troupes/${troupeId}/staff`, {
    headers: { "X-Horatio": "1" },
    data: { handle: assistant.handle, role: "assistant_storyteller" },
  });
  expect(staffed.status(), await staffed.text()).toBe(200);

  // The lead starts a theme from the book's Betrayal, and changes its questions.
  const l = lead.page;
  await settingsPart(l, troupeId, "setting");
  const setting = l.getByRole("group", { name: "The setting" });
  const card = (title: string) => setting.locator("section").filter({ has: l.getByRole("heading", { name: title, exact: true }) });
  await card("Themes").getByRole("button", { name: "Add a theme" }).click();
  const theme = l.getByRole("dialog", { name: "Add a theme" });
  await theme.getByLabel("Start from").selectOption({ label: "Betrayal (p. 325)" });
  await expect(theme.getByLabel("Name")).toHaveValue("Betrayal");
  await expect(theme.getByLabel("Description, in Markdown")).toHaveValue(/betray/);
  await theme.getByLabel("Description, in Markdown").fill("Who will sell out the **Prince**?");
  await theme.getByRole("button", { name: "Add it" }).click();
  await expect(theme).toBeHidden();
  const betrayal = card("Themes").getByRole("button", { name: "Betrayal", exact: true });
  await betrayal.click();
  await expect(betrayal).toHaveAttribute("aria-expanded", "true");
  await expect(card("Themes").getByRole("region", { name: "Betrayal" }).locator("strong")).toHaveText("Prince");
  await expect(card("Themes").getByRole("region", { name: "Betrayal" })).toContainText("From the book's sample, MET: VTM p. 325");

  // A mood of the troupe's own, then the book's Brooding, which is offered once.
  const addMood = async (from: string | null, name: string, description: string) => {
    await card("Moods").getByRole("button", { name: "Add a mood" }).click();
    const dialog = l.getByRole("dialog", { name: "Add a mood" });
    if (from) await dialog.getByLabel("Start from").selectOption({ label: from });
    await dialog.getByLabel("Name").fill(name);
    await dialog.getByLabel("Description, in Markdown").fill(description);
    await dialog.getByRole("button", { name: "Add it" }).click();
    await expect(dialog).toBeHidden();
  };
  await addMood(null, "Rain-soaked", "Grey, cold and *close*.");
  await addMood("Brooding (p. 326)", "Brooding", "Something is coming.");
  const moods = card("Moods").getByRole("list", { name: "Moods" }).getByRole("button");
  await expect(moods).toHaveText(["Rain-soaked", "Brooding"]);

  // Brooding dragged onto Rain-soaked goes first; the buttons move it back.
  await card("Moods").getByRole("listitem").filter({ hasText: "Brooding" }).dragTo(card("Moods").getByRole("listitem").filter({ hasText: "Rain-soaked" }));
  await expect(moods).toHaveText(["Brooding", "Rain-soaked"]);
  await moods.filter({ hasText: "Brooding" }).click();
  await card("Moods").getByRole("button", { name: "Move Brooding later" }).click();
  await expect(moods).toHaveText(["Rain-soaked", "Brooding"]);
  await l.reload();
  await expect(moods).toHaveText(["Rain-soaked", "Brooding"]);

  // An assistant storyteller writes a storyteller note and the scope.
  const a = assistant.page;
  await settingsPart(a, troupeId, "setting");
  const theirs = a.getByRole("group", { name: "The setting" }).locator("section");
  const notes = theirs.filter({ has: a.getByRole("heading", { name: "Storyteller notes", exact: true }) });
  await notes.getByRole("button", { name: "Add a note" }).click();
  const note = a.getByRole("dialog", { name: "Add a note" });
  await note.getByLabel("The note, in Markdown").fill("Characters are no older than ten years past the Embrace.");
  await note.getByRole("button", { name: "Add it" }).click();
  await expect(notes.getByRole("list", { name: "Storyteller notes" })).toContainText("ten years past the Embrace");
  const scope = theirs.filter({ has: a.getByRole("heading", { name: "Scope", exact: true }) });
  await scope.getByLabel("Power").fill("Neonates and ancillae.");
  await expect(scope.getByText("Not saved yet")).toBeVisible();
  await scope.getByRole("button", { name: "Save", exact: true }).click();
  await expect(scope.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await l.reload();
  await expect(card("Scope").getByLabel("Power")).toHaveValue("Neonates and ancillae.");
  await a.screenshot(shots("setting-style"));
});

test("players read the whole setting on its tab, in print, on the profile when shown, and in brief as they build (#771)", async ({ browser }) => {
  const custodian = await person(browser, "setdoc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "setdoc-lead");
  const player = await person(browser, "setdoc-player");
  await custodian.page.reload();
  const send = async (page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: unknown) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const troupeName = `Court of Settings ${run}`;
  const troupeId: string = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  const l = lead.page;
  // The parts staff write (#770), and settings the troupe already has.
  await send(l, "PATCH", `/api/troupes/${troupeId}`, { allowed_sects: ["Camarilla"] });
  await send(l, "PUT", `/api/troupes/${troupeId}/setting`, { subtitle: "A City Under Siege", teaser: "The domain stands *weary*, but proud.", power: "", agency: "" });
  await send(l, "POST", `/api/troupes/${troupeId}/setting/entries`, { kind: "theme", name: "Chaos", description: "" });
  await send(l, "POST", `/api/troupes/${troupeId}/setting/entries`, { kind: "mood", name: "Brooding", description: "" });

  // The lead gives a clan rarity a reason, under Rules' starting points.
  await l.goto(`/troupes/${troupeId}/house-rules/starting`);
  const rarity = l.locator("section").filter({ has: l.getByRole("heading", { name: "Clan rarity", exact: true }) });
  await rarity.getByRole("button", { name: "Edit clan rarity" }).click();
  await rarity.getByLabel("Lasombra rarity").selectOption("uncommon");
  await rarity.getByLabel("Why the Lasombra are uncommon").fill("due to story");
  await rarity.getByRole("button", { name: "Save" }).click();
  await expect(rarity.getByText("uncommon (house rule: due to story)")).toBeVisible();

  // Every member reads the whole document on The setting tab.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}`);
  await troupeTab(p, "The setting");
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/setting$`));
  const doc = p.getByRole("article", { name: "Setting Style Document" });
  await expect(doc.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(doc.getByText("A City Under Siege")).toBeVisible();
  await expect(doc.getByRole("region", { name: "Setting", exact: true })).toContainText("Camarilla. Every character is built by the Camarilla setting");
  await expect(doc.getByRole("region", { name: "Clan rarity adjustments" })).toContainText("Lasombra, from rare, due to story");
  await expect(doc.getByRole("region", { name: "Cost modifications" })).toContainText("Settings default");
  await expect(doc.getByRole("region", { name: "Setting-specific mechanics" })).toContainText("Initial XP is 30 XP.");
  await expect(doc.getByRole("link", { name: "Edit in Settings" })).toHaveCount(0);

  // The lead switches on the New Character Incentive; the document gives its working.
  await settingsPart(l, troupeId, "xp");
  await l.getByRole("switch", { name: /Use the New Character Incentive/ }).click();
  await expect(l.getByRole("switch", { name: /Use the New Character Incentive/ })).toBeChecked();
  await expect(l.getByText("Saved.", { exact: true })).toBeVisible();
  await l.goto(`/troupes/${troupeId}/setting`);
  await expect(l.getByRole("region", { name: "Setting-specific mechanics" })).toContainText("+ the New Character Incentive");
  await expect(l.getByRole("link", { name: "Edit in Settings" })).toHaveAttribute("href", `/troupes/${troupeId}/settings/joining`);

  // Printed, black on white, for the Storyteller table.
  await p.goto(`/print/setting/${troupeId}`);
  await expect(p.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(p).toHaveTitle(`Print · The setting · ${troupeName} · Horatio`);

  // On the profile only once the lead shows it there; a public profile shows it to anyone.
  await send(l, "PUT", `/api/troupes/${troupeId}/profile/public`, { public: true });
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor.getByRole("article", { name: "Setting Style Document" })).toHaveCount(0);
  await settingsPart(l, troupeId, "setting");
  await l.getByRole("switch", { name: /Show it on the troupe's profile/ }).click();
  await expect(l.getByRole("switch", { name: /Show it on the troupe's profile/ })).toBeChecked();
  await visitor.reload();
  await expect(visitor.getByRole("article", { name: "Setting Style Document" }).getByText("Chaos")).toBeVisible();
  // And on the troupe's Overview, with the rest of its profile (#781).
  await l.goto(`/troupes/${troupeId}`);
  await expect(l.getByRole("region", { name: "Profile" }).getByRole("article", { name: "Setting Style Document" }).getByText("Chaos")).toBeVisible();

  // A character built to the troupe's rules shows the setting in brief as it is made.
  const made = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Vesper", building_troupe_id: troupeId });
  await p.goto(`/characters/${made.id}/create/concept`);
  const brief = p.getByRole("region", { name: "The setting you're building for" });
  await expect(brief).toContainText("Theme: Chaos");
  await expect(brief).toContainText("Mood: Brooding");
  await expect(brief).toContainText("weary");
  await brief.getByRole("link", { name: "Read the whole setting" }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/setting$`));
});

test("a burst of changes to the setting rings one bell for the troupe's players, saying what changed and leading to The setting tab (#881)", async ({ browser }) => {
  const custodian = await person(browser, "setbell-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "setbell-lead");
  const player = await person(browser, "setbell-player");
  await custodian.page.reload();
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: unknown) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const troupeName = `Court of Bells ${run}`;
  const troupeId: string = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, troupeId);
  const id = await builtVampire(player.page, "Ysolde", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] });
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The lead adds a theme under Settings, then rewrites the teaser: one notice, naming both.
  const l = lead.page;
  await settingsPart(l, troupeId, "setting");
  const setting = l.getByRole("group", { name: "The setting" });
  const themes = setting.locator("section").filter({ has: l.getByRole("heading", { name: "Themes", exact: true }) });
  await themes.getByRole("button", { name: "Add a theme" }).click();
  const dialog = l.getByRole("dialog", { name: "Add a theme" });
  await dialog.getByLabel("Name").fill("Masks");
  await dialog.getByRole("button", { name: "Add it" }).click();
  await expect(dialog).toBeHidden();
  await send(l, "PUT", `/api/troupes/${troupeId}/setting`, { subtitle: "", teaser: "The *river* rose.", power: "", agency: "" });
  // The lead made the changes, so their own bell stays quiet.
  await l.getByRole("button", { name: /^Notifications/ }).click();
  await expect(l.getByRole("dialog", { name: "Notifications" }).getByText(/The setting changed/)).toHaveCount(0);

  const p = player.page;
  await p.goto("/");
  await p.getByRole("button", { name: /^Notifications/ }).click();
  const bell = p.getByRole("dialog", { name: "Notifications" });
  const notice = bell.getByRole("button", { name: /The setting changed/ });
  await expect(notice).toHaveCount(1);
  await expect(notice).toContainText("The setting changed: the theme Masks added; the teaser rewritten.");
  await expect(notice).toContainText(troupeName);
  await notice.click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/setting$`));
  await expect(p.getByRole("article", { name: "Setting Style Document" }).getByText("Masks")).toBeVisible();
});

test("staff keep a story bible beside the setting: their notes with the chronicle, NPCs and locations, printed apart, and players never see it (#879)", async ({ browser }) => {
  const custodian = await person(browser, "bible-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bible-lead");
  const assistant = await person(browser, "bible-assistant");
  const player = await person(browser, "bible-player");
  await custodian.page.reload();
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: unknown) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const troupeName = `Court of Secrets ${run}`;
  const troupeId: string = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupeId}/staff`, { handle: assistant.handle, role: "assistant_storyteller" });
  // What Horatio already holds: an NPC and a location.
  await send(l, "POST", `/api/troupes/${troupeId}/npcs`, { name: "Elder Ravel" });
  await send(l, "POST", `/api/troupes/${troupeId}/locations`, { name: "The Rookery", rating: 3, control: "named", controller_name: "The Sheriff" });

  // An assistant storyteller finds it from The setting tab, and writes two notes.
  const a = assistant.page;
  await a.goto(`/troupes/${troupeId}/setting`);
  await a.getByRole("link", { name: "story bible", exact: true }).click();
  await expect(a).toHaveURL(new RegExp(`/troupes/${troupeId}/setting/story-bible$`));
  // A part of The setting for running staff (#1048), where its old address lands too.
  await expect(a.locator("main").getByRole("navigation", { name: "The setting", exact: true }).getByRole("link", { name: "Story bible" })).toHaveAttribute("aria-current", "page");
  await a.goto(`/troupes/${troupeId}/story-bible`);
  await expect(a).toHaveURL(new RegExp(`/troupes/${troupeId}/setting/story-bible$`));
  const notes = a.locator("section").filter({ has: a.getByRole("heading", { name: "Staff notes", exact: true }) });
  const addNote = async (title: string, body: string) => {
    await notes.getByRole("button", { name: "Add a note" }).click();
    const dialog = a.getByRole("dialog", { name: "Add a note" });
    await dialog.getByLabel("Title").fill(title);
    await dialog.getByLabel("The note, in Markdown").fill(body);
    await dialog.getByRole("button", { name: "Add it" }).click();
    await expect(dialog).toBeHidden();
  };
  await addNote("The Prince's secret", "She drinks from **Baali** stock.");
  await addNote("Who burned the chantry", "The Sheriff, on orders.");
  const titles = notes.getByRole("list", { name: "Staff notes" }).getByRole("heading");
  await expect(titles).toHaveText(["The Prince's secret", "Who burned the chantry"]);
  await expect(notes.locator("strong")).toHaveText("Baali");
  await notes.getByRole("button", { name: "Move The Prince's secret down" }).click();
  await expect(titles).toHaveText(["Who burned the chantry", "The Prince's secret"]);

  // The rest is gathered from the troupe's own records.
  await expect(a.getByRole("region", { name: "Important NPCs" })).toContainText("Elder Ravel");
  await expect(a.getByRole("region", { name: "Recurring locales" })).toContainText("The Rookery · Standard 3 · held by The Sheriff");
  const chronology = a.getByRole("region", { name: "Chronology" });
  await chronology.getByText(/Without an in-game date/).click();
  await expect(chronology).toContainText("Elder Ravel");

  // Printed on its own, for staff.
  await l.goto(`/print/story-bible/${troupeId}`);
  await expect(l).toHaveTitle(`Print · Story bible · ${troupeName} · Horatio`);
  await expect(l.getByRole("region", { name: "Staff notes" })).toContainText("Who burned the chantry");
  await expect(l.getByRole("region", { name: "Recurring locales" })).toContainText("The Rookery");

  // A player has no tab for it, can't open it, and never reads it in the setting.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}/setting`);
  await expect(p.getByRole("article", { name: "Setting Style Document" })).toBeVisible();
  await expect(p.getByRole("link", { name: /story bible/i })).toHaveCount(0);
  await expect(p.getByText("Baali")).toHaveCount(0);
  expect((await p.request.get(`/api/troupes/${troupeId}/story-bible`)).status()).toBe(403);
  await p.goto(`/print/story-bible/${troupeId}`);
  await expect(p.getByText("You cannot do that in this troupe.")).toBeVisible();
  await expect(p.getByText("Baali")).toHaveCount(0);
});

test("a player looks up the rules: a power by name and by its summary, then as played in a troupe, a house price shown and a banned merit hidden (#422)", async ({ browser }) => {
  const custodian = await person(browser, "rulebook-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rulebook-lead");
  const player = await person(browser, "rulebook-player");
  const troupeName = `Hall of Statutes ${run}`;
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  // The troupe sells Absent Sway for 2 points rather than 3, and bans Calm Heart.
  for (const data of [
    { category: "merits", trait: "Absent Sway", scheme: "fixed", rate: 2 },
    { category: "merits", trait: "Calm Heart", scheme: "not_allowed", text: "No one keeps calm here" },
  ]) {
    const priced = await lead.page.request.post(`/api/troupes/${troupeId}/costs`, { headers: { "X-Horatio": "1" }, data });
    expect(priced.status(), await priced.text()).toBe(201);
  }

  // From the main nav, the book's rules: a power found by its name, and by a word of its summary.
  const p = player.page;
  await (await topBar(p)).getByRole("link", { name: "Rulebook", exact: true }).click();
  const search = p.getByRole("searchbox", { name: "Search the rules" });
  const entry = (name: string) => p.getByTestId("rules-entry").filter({ has: p.getByRole("heading", { name, exact: true }) });
  await search.fill("majesty");
  await expect(entry("Majesty")).toContainText("Presence 5");
  await search.fill("act against you");
  await expect(entry("Majesty")).toBeVisible();
  // A Dark Thaumaturgy ritual, from the V20 LARP SRD, links its page there (#414).
  await search.fill("vile swarm");
  const swarm = entry("Dark Thaumaturgy: Vile Swarm");
  await expect(swarm).toContainText("Level 4");
  await expect(swarm.getByRole("link", { name: "V20 LARP SRD" })).toHaveAttribute("href", "https://www.oneworldofdarkness.com/srd-v20/rituals/vile-swarm");

  // The merits a clan needs, and Calm Heart as the book has it.
  await search.fill("");
  await p.getByRole("button", { name: /^Merits/ }).click();
  await p.getByLabel("Clan").selectOption("Toreador");
  await expect(entry("Absent Sway")).toContainText("3 points");
  await p.getByLabel("Clan").selectOption("");
  await search.fill("calm heart");
  await expect(entry("Calm Heart")).toBeVisible();

  // As played in the troupe: Calm Heart is gone, unless asked for, marked as not allowed.
  await p.getByLabel("As played in").selectOption({ label: troupeName });
  await expect(p.getByText(`Nothing matches “calm heart”.`)).toBeVisible();
  await p.getByLabel(`Show the 1 not allowed in ${troupeName}`).check();
  await expect(entry("Calm Heart")).toContainText(`Not allowed in ${troupeName}`);
  await expect(entry("Calm Heart")).toContainText("House rule: No one keeps calm here");

  // Absent Sway at the troupe's price, beside the book's.
  await search.fill("absent sway");
  const sway = entry("Absent Sway");
  await expect(sway).toContainText("2 points");
  await expect(sway.getByText("House rule", { exact: true })).toBeVisible();
  await expect(sway).toContainText("By the book: 3 points");
  await p.screenshot(shots("rules-browser"));

  // The troupe's House rules page leads back here, the troupe chosen.
  await p.getByRole("link", { name: "What it changes" }).click();
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}/house-rules$`));
  await p.getByRole("link", { name: "Browse every rule as played here" }).click();
  await expect(p.getByLabel("As played in")).toHaveValue(troupeId);
});

test("a lead bans a merit on the Book traits page: it is greyed out with the reason in a player's picker, and listed on House rules (#431)", async ({ browser }) => {
  const custodian = await person(browser, "ban-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "ban-lead");
  const player = await person(browser, "ban-player");
  const troupeName = `Court of Refusals ${run}`;
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(lead.page, troupeId);

  // The lead finds Lucky in the catalogue and bans it, with a reason.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/book-traits`);
  await l.getByRole("searchbox", { name: "Search book traits" }).fill("lucky");
  await l.getByRole("list", { name: "Book traits found" }).getByRole("button", { name: /^Lucky/ }).click();
  await l.getByLabel("Banned in this troupe").check();
  await l.getByLabel("Reason (optional)").fill("Too swingy at our table.");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  const changed = l.locator("section").filter({ has: l.getByRole("heading", { name: "Changed in this troupe", exact: true }) });
  await expect(changed.getByRole("listitem").filter({ hasText: "Lucky" })).toContainText("Banned: Too swingy at our table.");
  await l.screenshot(shots("book-traits-ban"));

  // A player's character joins the troupe.
  const p = player.page;
  const id = await builtVampire(p, "Rosamund", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const [request] = await (await l.request.get(`/api/troupes/${troupeId}/approvals`)).json();
  const approved = await l.request.post(`/api/approvals/${request.id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBeLessThan(300);

  // In the merit picker, Lucky is greyed out with the troupe's reason.
  await p.goto(`/characters/${id}`);
  const part = p.locator("section").filter({ has: p.getByRole("heading", { name: "Merits and Flaws", exact: true }) });
  await makeChanges(p);
  await part.getByRole("button", { name: "Add" }).click();
  await p.getByLabel("Show").selectOption("all");
  await p.getByRole("combobox", { name: "Search Merits", exact: true }).fill("Lucky");
  const lucky = p.getByRole("option", { name: /^Lucky/ });
  await expect(lucky).toBeDisabled();
  await expect(lucky).toHaveAccessibleDescription("Lucky is banned in this troupe. Too swingy at our table.");

  // The troupe's House rules list it as banned.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  const banned = p.locator("section").filter({ has: p.getByRole("heading", { name: "Banned", exact: true }) });
  await expect(banned.getByRole("listitem").filter({ hasText: "Lucky" })).toContainText("Too swingy at our table.");
});

test("staff call the clan Banu Haqim or Assamite, and the sheet and the rules follow at once, either name found by a search (#430)", async ({ browser }) => {
  const custodian = await person(browser, "haqim-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "haqim-lead");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Alamut ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const l = lead.page;
  const send = async (url: string, data: object, method: "POST" | "PUT" = "POST") => {
    const response = await l.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // Rashid, the troupe's Vizier, with his caste's flaw: kept under the books' name.
  const { id } = await send(`/api/troupes/${troupeId}/npcs`, { name: "Rashid the Vizier", wizard: false });
  for (const [category, name, rating] of [
    ["clan", "Assamite: Vizier", null],
    ["flaws", "Assamite: Diluted Blood", 2],
  ] as const)
    await send(`/api/characters/${id}/npc/ratings`, { category, name, rating, detail: "" }, "PUT");
  const search = l.getByRole("searchbox", { name: "Search the rules" });
  const entry = (name: string) => l.getByTestId("rules-entry").filter({ has: l.getByRole("heading", { name, exact: true }) });

  // A new troupe calls the clan Banu Haqim, on the sheet and in its rules, where the books' name finds it.
  await l.goto(`/characters/${id}/sheet`);
  await expect(l.getByText("Banu Haqim: Diluted Blood", { exact: true })).toBeVisible();
  await expect(l.getByText("Banu Haqim: Vizier", { exact: true }).first()).toBeVisible();
  await expect(l.getByText("Assamite: Diluted Blood")).toHaveCount(0);
  await l.goto(`/rules?troupe=${troupeId}`);
  await search.fill("assamite vizier");
  await expect(entry("Banu Haqim: Vizier")).toBeVisible();

  // The lead calls it Assamite instead, in Settings.
  await settingsPart(l, troupeId, "names");
  const names = l.locator("section").filter({ has: l.getByRole("heading", { name: "Banu Haqim or Assamite" }) });
  await expect(names.getByRole("radio", { name: /^Banu Haqim/ })).toBeChecked();
  await names.getByRole("radio", { name: /^Assamite/ }).click();
  await expect(l.getByText("The clan is called the Assamites here now.")).toBeVisible();
  await expect(names.getByRole("radio", { name: /^Assamite/ })).toBeChecked();
  await l.screenshot(shots("clan-names-setting"));

  // The sheet and the rules follow straight away, and the other name still finds it.
  await l.goto(`/characters/${id}/sheet`);
  await expect(l.getByText("Assamite: Diluted Blood", { exact: true })).toBeVisible();
  await expect(l.getByText("Assamite: Vizier", { exact: true }).first()).toBeVisible();
  await expect(l.getByText("Banu Haqim: Diluted Blood")).toHaveCount(0);
  await l.goto(`/rules?troupe=${troupeId}`);
  await search.fill("banu haqim vizier");
  await expect(entry("Assamite: Vizier")).toBeVisible();
});

test("staff choose the core book's Tremere weakness and Volume 2's Brujah, and the troupe's rules follow; with no troupe the rules give both (#1127, #1197)", async ({ browser }) => {
  const custodian = await person(browser, "weakness-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "weakness-lead");
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Chantry of Vienna ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const l = lead.page;
  const search = l.getByRole("searchbox", { name: "Search the rules" });
  const tremere = l.getByTestId("rules-entry").filter({ has: l.getByRole("heading", { name: "Tremere", exact: true }) });

  // As the book has it, with no troupe, the weakness varies by troupe: both, each with its page.
  await l.goto("/rules");
  await search.fill("tremere");
  await expect(tremere).toContainText("Weakness: varies by troupe.");
  await expect(tremere.getByRole("listitem")).toHaveText([/^Volume 2: Their blood bonds other vampires only to the first stage.* Vol\. 2, p\. 22$/, /^Core book: Easily bound.* p\. 64$/]);

  // A troupe plays Volume 2's until its staff choose.
  await l.goto(`/rules?troupe=${troupeId}`);
  await search.fill("tremere");
  await expect(tremere).toContainText("Weakness: Their blood bonds other vampires only to the first stage; ghouls are bound as usual. Vol. 2, p. 22");

  // The lead chooses the core book's, in Settings.
  await settingsPart(l, troupeId, "blood");
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Clan weaknesses" }) });
  const tremereChoice = card.getByRole("radiogroup", { name: "The Tremere weakness" });
  await expect(tremereChoice.getByRole("radio", { name: /^Volume 2's \(the default\)/ })).toBeChecked();
  await tremereChoice.getByRole("radio", { name: /^Core book's/ }).click();
  await expect(l.getByText("The Tremere here play by the core book's weakness now.")).toBeVisible();
  await expect(tremereChoice.getByRole("radio", { name: /^Core book's/ })).toBeChecked();
  // The Brujah play the core book's by default (#1197); the lead takes Volume 2's reading.
  const brujahChoice = card.getByRole("radiogroup", { name: "The Brujah weakness" });
  await expect(brujahChoice.getByRole("radio", { name: /^Core book's \(the default\)/ })).toBeChecked();
  await brujahChoice.getByRole("radio", { name: /^Volume 2's/ }).click();
  await expect(l.getByText("The Brujah here play by Volume 2's weakness now.")).toBeVisible();
  await expect(tremereChoice.getByRole("radio", { name: /^Core book's/ })).toBeChecked();

  // The troupe's rules follow at once.
  await l.goto(`/rules?troupe=${troupeId}`);
  await search.fill("tremere");
  await expect(tremere).toContainText("Weakness: Easily bound: their first drink of another vampire's blood counts as two, so a second binds them fully. p. 64");
  await expect(tremere).not.toContainText("varies by troupe");
  await search.fill("brujah");
  const brujah = l.getByTestId("rules-entry").filter({ has: l.getByRole("heading", { name: "Brujah", exact: true }) });
  await expect(brujah).toContainText("Weakness: Quick to rage: counted as having 2 more Beast traits for frenzy, so they test sooner as well as harder. Vol. 2, p. 121");
});

test("a lead makes Soul Shard a general flaw on the Book traits page, and a player finds it among the general flaws (#436)", async ({ browser }) => {
  const custodian = await person(browser, "recat-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "recat-lead");
  const player = await person(browser, "recat-player");
  const troupeName = `Hall of Shards ${run}`;
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(lead.page, troupeId);

  // The lead opens Soul Shard, a Sabbat flaw by the book, and makes it General here.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/book-traits`);
  await l.getByLabel("Category", { exact: true }).selectOption({ label: "Flaws" });
  await l.getByRole("searchbox", { name: "Search book traits" }).fill("soul shard");
  await l.getByRole("list", { name: "Book traits found" }).getByRole("button", { name: /^Soul Shard/ }).click();
  await l.getByLabel("Category in this troupe").selectOption("General");
  await expect(l.getByRole("region", { name: "Category" })).toContainText("Characters who hold it keep it.");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  const changed = l.locator("section").filter({ has: l.getByRole("heading", { name: "Changed in this troupe", exact: true }) });
  await expect(changed.getByRole("listitem").filter({ hasText: "Soul Shard" })).toContainText("Category: General (Sabbat in the book)");

  // A player's character makes the troupe home.
  const p = player.page;
  const id = await builtVampire(p, "Shardwell", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const [request] = await (await l.request.get(`/api/troupes/${troupeId}/approvals`)).json();
  const approved = await l.request.post(`/api/approvals/${request.id}/approve`, { headers, data: {} });
  expect(approved.status(), await approved.text()).toBeLessThan(300);

  // Among the general flaws, Soul Shard, marked as changed here.
  await p.goto(`/characters/${id}`);
  const part = p.locator("section").filter({ has: p.getByRole("heading", { name: "Merits and Flaws", exact: true }) });
  await makeChanges(p);
  await part.getByRole("button", { name: "Add" }).click();
  await p.getByRole("navigation", { name: "Categories" }).getByRole("button", { name: /^Flaws/ }).click();
  await p.getByLabel("Show").selectOption("kind:General");
  await p.getByRole("combobox", { name: "Search Flaws", exact: true }).fill("Soul Shard");
  await expect(p.getByRole("option", { name: /^Soul Shard/ })).toBeVisible();
  await p.getByLabel("Show").selectOption("kind:Sabbat");
  await expect((await addList(p, "Flaws")).getByRole("option", { name: /^Soul Shard/ })).toHaveCount(0);

  // The troupe's House rules list the change.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  const categories = p.locator("section").filter({ has: p.getByRole("heading", { name: "Changed categories", exact: true }) });
  await expect(categories.getByRole("listitem").filter({ hasText: "Soul Shard" })).toContainText("General here; Sabbat in the book.");
});

test("a lead opens a book trait from far down the list: its panel opens under it with the focus, and the focus goes back to the row as it closes (#648)", async ({ browser }) => {
  const custodian = await person(browser, "farrow-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "farrow-lead");
  await custodian.page.reload();
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: `Hall of Far Rows ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // Every merit, forty of them shown: the lead opens the last.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/house-rules/book-traits`);
  await l.getByLabel("Category", { exact: true }).selectOption({ label: "Merits" });
  await expect(l.getByText(/^Showing 40 of \d+\./)).toBeVisible();
  const found = l.getByRole("list", { name: "Book traits found" });
  const last = found.getByRole("listitem").last();
  const name = (await last.getByRole("button").locator("span").first().textContent())!;
  const row = found.getByRole("button", { name: `${name} Merits` });
  await row.click();

  // Its panel opens under it, on screen, with the focus in it.
  const item = found.getByRole("listitem").filter({ has: l.getByRole("button", { name: `${name} Merits` }) });
  const panel = item.getByRole("region", { name, exact: true });
  await expect(panel).toBeInViewport();
  await expect(row).toHaveAttribute("aria-expanded", "true");
  await expect(panel.getByLabel("Banned in this troupe")).toBeFocused();
  await expect(l.getByRole("region", { name, exact: true })).toHaveCount(1);

  // A change saved keeps the panel where it is, though the trait now comes first among those found.
  await panel.getByLabel("House wording").fill("Here it needs a storyteller's nod first.");
  await panel.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText(`Saved: ${name} in this troupe`)).toBeVisible();
  await expect(row).toContainText("House wording");
  await expect(found.getByRole("listitem").last()).toContainText(name);
  await expect(panel).toBeInViewport();

  // Closed, the focus is back on its row.
  await panel.getByRole("button", { name: "Close", exact: true }).click();
  await expect(panel).toHaveCount(0);
  await expect(row).toBeFocused();
  await expect(row).toHaveAttribute("aria-expanded", "false");
});

test("a lead exports one troupe's settings and imports them into another, leaving out a section and renaming the troupe in its house wording (#521)", async ({ browser }) => {
  const custodian = await person(browser, "sharing-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "sharing-lead");
  const ashen = `Ashen Court ${run}`;
  const briar = `Briar Court ${run}`;
  const headers = { "X-Horatio": "1" };
  await custodian.page.reload();
  const ids: string[] = [];
  for (const name of [ashen, briar]) {
    const made = await custodian.page.request.post("/api/troupes", { headers, data: { name, lead_handle: lead.handle } });
    expect(made.status(), await made.text()).toBe(201);
    ids.push((await made.json()).id);
  }
  const [ashenId, briarId] = ids as [string, string];

  // Ashen Court has its own wording for Iron Will, starting with its name, and gives more XP a session.
  const l = lead.page;
  const wording = (troupe: string) => `${troupe}: only the Prince's favourites have it.`;
  const worded = await l.request.put(`/api/troupes/${ashenId}/book-traits`, {
    headers,
    data: { category: "merits", name: "Iron Will", wording: wording(ashen), wording_mode: "added" },
  });
  expect(worded.status(), await worded.text()).toBe(200);
  const xp = await l.request.patch(`/api/troupes/${ashenId}`, { headers, data: { session_xp: 12 } });
  expect(xp.status(), await xp.text()).toBe(200);

  // The lead exports Ashen Court's settings: every section that differs, ticked.
  await l.goto(`/troupes/${ashenId}/export-and-import`);
  const exporting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Export", exact: true }) });
  await expect(exporting.getByRole("checkbox", { name: /^Book traits/ })).toBeChecked();
  await expect(exporting.getByRole("checkbox", { name: /^XP/ })).toBeChecked();
  const [download] = await Promise.all([l.waitForEvent("download"), exporting.getByRole("button", { name: "Export", exact: true }).click()]);
  expect(download.suggestedFilename()).toMatch(/^ashen-court-\d+-settings-\d{4}-\d{2}-\d{2}\.json$/);
  const file = await download.path();

  // …and imports the file into Briar Court, leaving out the XP.
  await l.goto(`/troupes/${briarId}/export-and-import`);
  await l.getByLabel("Settings file").setInputFiles(file);
  await expect(l.getByText(`From ${ashen}`)).toBeVisible();
  const choosing = l.getByRole("group", { name: "What to import" });
  const books = choosing.getByRole("region", { name: "Book traits" });
  await books.getByRole("button", { name: /Show items/ }).click();
  await expect(books.getByRole("listitem").filter({ hasText: "Iron Will" })).toContainText("New");
  await choosing.getByRole("checkbox", { name: "XP", exact: true }).uncheck();
  await expect(l.getByText("Adds 1, changes 0.")).toBeVisible();

  // The wording names Ashen Court: find & replace makes it Briar Court's.
  const replacing = l.getByRole("region", { name: "Find and replace" });
  await replacing.getByRole("button", { name: `Replace “${ashen}” with “${briar}”` }).click();
  await expect(replacing.getByLabel("Find")).toHaveValue(ashen);
  await expect(replacing.getByText("1 match in 1 item")).toBeVisible();
  await replacing.getByRole("button", { name: "Replace all" }).click();
  await expect(replacing.getByText("0 matches in 0 items")).toBeVisible();
  await books.getByRole("button", { name: /^Edit/ }).click();
  await expect(books.getByLabel("House wording")).toHaveValue(wording(briar));
  await books.getByRole("button", { name: "Cancel" }).click();
  await expect(choosing.getByRole("checkbox", { name: "XP", exact: true })).not.toBeChecked();
  await l.screenshot(shots("share-settings"));
  await l.getByRole("button", { name: "Import", exact: true }).click();
  await expect(l.getByText("Imported: 1 added, 0 changed (Book traits).")).toBeVisible();

  // Briar Court's players read the wording, with its own name; its session XP is as it was.
  await l.goto(`/troupes/${briarId}/house-rules`);
  const changed = l.locator("section").filter({ has: l.getByRole("heading", { name: "Changed wording", exact: true }) });
  await expect(changed.getByRole("listitem").filter({ hasText: "Iron Will" })).toContainText(wording(briar));
  const briarNow = await (await l.request.get(`/api/troupes/${briarId}`)).json();
  expect(briarNow.session_xp).toBe(8);
});

test("a troupe's XP floor and ceiling: new characters start at the floor, and staff settle a joiner's XP", async ({ browser }) => {
  // A whole character creation, then a home troupe request.
  test.slow();
  const custodian = await person(browser, "floor-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "floor-lead");
  const player = await person(browser, "floor-player");
  const troupeName = `Court of Bones ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);

  // The chronicle began before Horatio: the lead sets the floor and ceiling by hand, in Settings.
  const l = lead.page;
  await (await topBar(l)).getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await troupeTab(l, "Settings");
  await pagePart(l, "XP", "Settings");
  const range = l.getByRole("region", { name: "XP floor and ceiling" });
  await range.getByLabel("Floor", { exact: true }).fill("100");
  await range.getByLabel("Ceiling", { exact: true }).fill("120");
  await range.getByLabel("Why", { exact: true }).fill("Chronicle began in 2019");
  await range.getByRole("button", { name: "Save", exact: true }).click();
  await expect(range.getByText("30 starting + 70 set by hand")).toBeVisible();
  await expect(range.getByText("30 starting + 90 set by hand")).toBeVisible();
  await l.screenshot(shots("xp-range"));

  // Players see where the troupe stands on its page.
  const p = player.page;
  await p.reload();
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("100 XP", { exact: true })).toBeVisible();

  // A character built for the troupe starts at its floor.
  await (await topBar(p)).getByRole("link", { name: "Characters" }).click();
  await p.getByLabel("Name").fill("Mara");
  await p.getByLabel("Which troupe will you play in?").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Create" }).click();
  await chooseIn(p, "Clan", "Brujah");
  await expect(p.getByLabel("Clan")).toHaveValue("Brujah");
  await chooseIn(p, "Sect", "Camarilla");
  const next = async (heading: string) => {
    await p.getByRole("button", { name: "Save and continue" }).click();
    await expect(p.getByRole("heading", { name: heading, exact: true })).toBeVisible({ timeout: 15_000 });
  };
  const tap = (...dots: string[]) => chooseDots(p, ...dots);
  await next("Attributes");
  await tap("Physical 7", "Social 5", "Mental 3");
  await next("Focuses");
  await tap("Strength 1", "Wits 1", "Charisma 1");
  await next("Skills");
  await tap("Brawl 4", "Dodge 3", "Athletics 3", "Awareness 2", "Empathy 2", "Firearms 2");
  await tap("Investigation 1", "Leadership 1", "Medicine 1", "Melee 1");
  await next("Backgrounds");
  await tap("Fame 3", "Herd 2", "Generation 1");
  await next("Disciplines");
  await tap("Celerity 2", "Potence 1", "Presence 1");
  await next("Merits & flaws");
  await next("Review");
  await p.getByRole("button", { name: "Finish creation" }).click();
  await p.getByRole("button", { name: "Yes, finish creation" }).click();
  await expect(p.getByRole("heading", { name: "Experience" })).toBeVisible();
  await characterTab(p, "Experience");
  await expect(p.getByText(`Starting experience: ${troupeName}'s XP floor`)).toBeVisible();

  // Mara was played elsewhere first: her player adds that XP themselves.
  await p.getByLabel("XP", { exact: true }).fill("30");
  await p.getByLabel("Why", { exact: true }).fill("Played at another troupe");
  await p.getByRole("button", { name: "Add", exact: true }).click();
  await expect(p.getByText("self-entered", { exact: true })).toBeVisible();

  // Asking to make the troupe her home, she sees she is above its ceiling.
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await expect(p.getByText("That is 10 XP above the ceiling.", { exact: false })).toBeVisible();
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead sees the self-entered XP apart, and what is above the ceiling, and removes it.
  await troupeTab(l, "Approvals");
  await expect(l.getByLabel("Self-entered XP: 30")).toBeVisible();
  await l.getByLabel("Above the ceiling by 10 XP").selectOption({ label: "Remove the 10 XP above the ceiling" });
  await expect(l.getByText("After joining it will have been given 120 XP.", { exact: false })).toBeVisible();
  await l.screenshot(shots("xp-approval"));
  await l.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(l.getByText("Nothing pending.")).toBeVisible();

  // Taking it away is its own entry in Mara's XP history.
  await characterTab(p, "Experience");
  await expect(p.getByText(`XP above ${troupeName}'s ceiling of 120`)).toBeVisible();
  await expect(p.getByText("above a ceiling", { exact: true })).toBeVisible();
});

test("storytellers filter the troupe's characters and print what they find", async ({ browser }) => {
  const custodian = await person(browser, "filter-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "filter-lead");
  const troupeName = `Court of Mirrors ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // Three NPCs, made straight through the API (the builder has its own test).
  const p = lead.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await p.getByRole("link", { name: troupeName }).click();
  const troupeId = new URL(p.url()).pathname.split("/")[2]!;
  const headers = { "X-Horatio": "1" };
  for (const [name, clan, occult] of [
    ["Prince", "Ventrue", 4],
    ["Mara", "Tremere", 1],
    ["Nell", "Giovanni", 0],
  ] as const) {
    const made = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(made.status(), await made.text()).toBe(201);
    const id = (await made.json()).id;
    const rate = (category: string, trait: string, rating: number | null) =>
      p.request.put(`/api/characters/${id}/npc/ratings`, { headers, data: { category, name: trait, rating, detail: "" } });
    expect((await rate("clan", clan, null)).status()).toBe(200);
    if (occult) expect((await rate("skills", "Occult", occult)).status()).toBe(200);
  }

  // The list opens on player characters; Everyone shows the NPCs too, and stays in the URL.
  await troupeTab(p, "Roster");
  await expect(p.getByText("No player characters have joined this troupe yet.")).toBeVisible();
  await p.locator("main").getByRole("radio", { name: "Everyone" }).click();
  await expect(p.getByText("3 of 3 characters")).toBeVisible();
  // Retired characters are hidden by default, and the Filter button says so rather than counting it.
  await expect(p.getByRole("button", { name: "Remove “Is active”" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Filter: active" })).toBeVisible();

  // Occult below 3, and (Tremere, or the Giovanni family).
  await p.getByRole("button", { name: "Filter" }).click();
  await p.getByRole("button", { name: "+ Condition", exact: true }).click();
  const occult = p.getByRole("group", { name: "Condition" }).nth(1);
  await occult.getByLabel("Category").selectOption({ label: "Skills" });
  await occult.getByLabel("Trait").selectOption("Occult");
  await occult.getByLabel("How").selectOption({ label: "below" });
  await occult.getByLabel("Number").fill("3");
  await expect(p.getByText("2 of 3 characters")).toBeVisible();
  await p.getByRole("button", { name: "+ Group" }).click();
  await p.getByLabel("Group match").selectOption({ label: "any of these (or)" });
  const tremere = p.getByRole("group", { name: "Condition" }).nth(2);
  await tremere.getByLabel("Value").selectOption("Tremere");
  await p.getByRole("button", { name: "Add a condition to this group" }).click();
  const giovanni = p.getByRole("group", { name: "Condition" }).nth(3);
  await giovanni.getByLabel("What").selectOption({ label: "Clan, sect, focus…" });
  await giovanni.getByLabel("How").selectOption({ label: "is in the family of" });
  await giovanni.getByLabel("Value").selectOption("Giovanni");
  await expect(p.getByText("2 of 3 characters")).toBeVisible();
  await expect(p.getByText("(Clan is Tremere, or Clan is in the Giovanni family)")).toBeVisible();
  await expect(p.getByRole("button", { name: "Filter (3)" })).toBeVisible();
  const list = p.getByRole("table", { name: "Characters" });
  await expect(list.getByRole("link", { name: "Prince" })).toHaveCount(0);
  // The number the filter compares: in an Occult column on a wide screen, under the name on a phone.
  const occultOf = (name: string) => list.locator("tbody tr").filter({ hasText: name }).getByText(/^(Occult )?\d$/).filter({ visible: true });
  await expect(occultOf("Mara")).toHaveText(/1$/);
  await expect(occultOf("Nell")).toHaveText(/0$/);
  await p.screenshot(shots("filter"));

  // The filter is in the URL, so it survives a reload.
  await p.reload();
  await expect(p.getByText("2 of 3 characters")).toBeVisible();

  // Print all prints what the filter shows.
  await p.getByRole("button", { name: "Print…" }).click();
  const printTab = p.context().waitForEvent("page");
  await p.getByRole("button", { name: "Print all 2" }).click();
  const printed = await printTab;
  await expect(printed.getByText("2 sheets", { exact: true })).toBeVisible();
  await printed.close();
});

test("the troupe's characters show a loader while the list and its filter load, never that there are none", async ({ browser }) => {
  const custodian = await person(browser, "loader-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "loader-lead");
  const c = custodian.page;
  await c.reload();
  const headers = { "X-Horatio": "1" };
  const made = await c.request.post("/api/troupes", { headers, data: { name: `Hall of Waiting ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const p = lead.page;
  for (const name of ["Ottilie", "Wenzel"]) {
    const npc = await p.request.post(`/api/troupes/${troupeId}/npcs`, { headers, data: { name, wizard: false } });
    expect(npc.status(), await npc.text()).toBe(201);
  }

  // The list and the search behind its filter ("is active", from the start), each held back until let go.
  const hold = (url: string, method: string) => {
    let release = () => {};
    const released = new Promise<void>((resolve) => (release = resolve));
    void p.route(url, async (route) => {
      if (route.request().method() !== method) return route.fallback();
      await released;
      await route.fallback();
    });
    return release;
  };
  const releaseList = hold(`**/api/troupes/${troupeId}/characters`, "GET");
  const releaseSearch = hold(`**/api/troupes/${troupeId}/characters/search`, "POST");
  await p.goto(`/troupes/${troupeId}/roster?show=everyone`);
  const main = p.locator("main");
  const none = main.getByText(/^No (characters|NPCs|player characters)/);

  // Until the list comes, the loader.
  await expect(main.getByRole("status", { name: "Loading…" }).first()).toBeVisible();
  await expect(none).toHaveCount(0);

  // The list comes, but not the search: the characters show under the search's loader.
  releaseList();
  await expect(main.getByRole("status", { name: "Searching…" })).toBeVisible();
  const list = main.getByRole("table", { name: "Characters" });
  await expect(list).toHaveAttribute("aria-busy", "true");
  await expect(list.getByRole("link", { name: "Ottilie" })).toBeVisible();
  await expect(none).toHaveCount(0);
  await expect(main.getByText("2 of 2 characters")).toBeVisible();

  // The search answers: the same two, no longer waiting.
  releaseSearch();
  await expect(main.getByRole("status", { name: "Searching…" })).toHaveCount(0);
  await expect(list).not.toHaveAttribute("aria-busy");
  await expect(list.getByRole("link", { name: "Wenzel" })).toBeVisible();
  await expect(none).toHaveCount(0);
});

test("on a phone the troupe's characters and a character's experience fold into blocks, nothing sideways with 20 long names; from sm up they are tables (#914)", async ({ browser }) => {
  const custodian = await person(browser, "fold914-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "fold914-lead");
  const c = custodian.page;
  await c.reload();
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, url: string, data: object) => {
    const response = await page.request.post(url, { headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const troupe = await send(c, "/api/troupes", { name: `Hall of Long Names ${run}`, lead_handle: lead.handle });
  const l = lead.page;
  // Twenty NPCs with long names, one a single word longer than a phone is wide.
  const names = Array.from({ length: 20 }, (_, i) =>
    i === 0 ? "Wolfeschlegelsteinhausenbergerdorffvoralternwarengewissenhaft" : `Bartholomew Featherstonehaugh-Cholmondeley of Wolverhampton ${i + 1}`,
  );
  for (const name of names) await send(l, `/api/troupes/${troupe.id}/npcs`, { name, wizard: false });
  const phone = test.info().project.name === "phone";
  // The narrowest phone the review measured.
  if (phone) await l.setViewportSize({ width: 375, height: 800 });
  // Against the viewport, not innerWidth: a phone widens its layout to fit what is too wide.
  const sideways = async () => (await l.evaluate(() => document.documentElement.scrollWidth)) - l.viewportSize()!.width;

  for (const show of ["everyone", "npcs"]) {
    await l.goto(`/troupes/${troupe.id}/roster?show=${show}`);
    const list = l.getByRole("table", { name: show === "npcs" ? "NPCs" : "Characters" });
    await expect(list.locator("tbody tr")).toHaveCount(20);
    await expect(list.getByRole("link", { name: names[0] })).toBeVisible();
    expect(await sideways()).toBe(0);
    // From sm up a table, its headings showing; on a phone what the columns show folds under the name, each with what it is.
    if (phone) await expect(list.locator("tbody tr").first().getByText(show === "npcs" ? "Form:" : "Age:", { exact: true })).toBeVisible();
    else await expect(list.getByRole("columnheader", { name: show === "npcs" ? "Kind" : "Clan" })).toBeVisible();
    await l.screenshot(shots(`roster-long-names-${show}`));
  }

  // Twenty entries with long reasons on the Experience tab of the lead's own character.
  const own = await send(l, "/api/characters", { name: names[1], splat: "vampire" });
  for (let i = 0; i < 20; i++) {
    await send(l, `/api/characters/${own.id}/xp/self-entered`, { amount: 1, reason: `Game ${i + 1}: held the Elysium against the Sabbat incursion until the sunrise, and wrote the whole report afterwards` });
  }
  await l.goto(`/characters/${own.id}/xp`);
  const history = l.getByRole("table", { name: "Experience history" });
  // Those and the XP it started with.
  await expect(history.locator("tbody tr")).toHaveCount(21);
  await expect(history.getByRole("cell", { name: /^Game 20: / })).toBeVisible();
  expect(await sideways()).toBe(0);
  // Its date, XP and balance: under what it was on a phone, in columns from sm up.
  if (phone) await expect(history.locator("tbody tr").first().getByText("Balance:", { exact: true })).toBeVisible();
  else await expect(history.getByRole("columnheader", { name: "Balance" })).toBeVisible();
  await expect(history.locator("tbody tr").first().getByText("+1", { exact: true }).filter({ visible: true })).toBeVisible();
  await l.screenshot(shots("xp-long-reasons"));
});

test("staff award XP, give equipment and print from a character's ⋯ on the Characters list, and see only what they may do (#539)", async ({ browser }) => {
  const custodian = await person(browser, "rowmenu-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rowmenu-lead");
  const assistant = await person(browser, "rowmenu-assist");
  const narrator = await person(browser, "rowmenu-narr");
  const player = await person(browser, "rowmenu-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupeName = `Vigil House ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: assistant.handle, role: "assistant_storyteller" });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: narrator.handle, role: "narrator" });

  // Odalys is the player's, at home in the troupe; Casimir is its NPC, built quickly, so it can be given to a player.
  const odalys = await builtVampire(player.page, "Odalys", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await send(player.page, "POST", `/api/characters/${odalys}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/npcs`, { name: "Casimir", wizard: false });

  // The lead's ⋯ on Odalys: what staff do most, then the printouts.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/roster`);
  const actions = async (page: Page, name: string) => {
    await page.getByRole("button", { name: `Actions for ${name}` }).click();
    return page.getByRole("menu", { name: `Actions for ${name}` });
  };
  let menu = await actions(l, "Odalys");
  await expect(menu.getByRole("menuitem")).toHaveText(["Award XP…", "Give equipment…", "Status…", "Titles…", "Print sheet", "Badge…"]);
  await l.screenshot(shots("roster-staff-menu"));
  await menu.getByRole("menuitem", { name: "Award XP…" }).click();
  const award = l.getByRole("dialog", { name: "Award XP to Odalys" });
  await award.getByLabel("XP for Odalys").fill("3");
  await award.getByLabel("Reason for Odalys's XP").fill("Held the line at Elysium");
  await award.getByRole("button", { name: "Award", exact: true }).click();
  await expect(award).toBeHidden();
  const xp: { amount: number; reason: string }[] = await (await l.request.get(`/api/characters/${odalys}/xp`)).json();
  expect(xp.filter((e) => e.reason === "Held the line at Elysium").map((e) => e.amount)).toEqual([3]);

  // Give equipment… opens the Equipment tab's form, given to Odalys.
  menu = await actions(l, "Odalys");
  await menu.getByRole("menuitem", { name: "Give equipment…" }).click();
  const form = l.getByRole("dialog", { name: "Give Odalys equipment" }).getByRole("form", { name: "Give equipment" });
  await form.getByLabel("Start from").selectOption({ label: "Silver Dagger" });
  await form.getByRole("button", { name: "Give to Odalys" }).click();
  await expect(l.getByText("Gave Odalys Silver Dagger.")).toBeVisible();
  await expect(l.getByRole("dialog")).toHaveCount(0);

  // Print sheet opens her sheet in a new tab, with the dagger on it.
  menu = await actions(l, "Odalys");
  const printTab = l.context().waitForEvent("page");
  await menu.getByRole("menuitem", { name: "Print sheet" }).click();
  const printed = await printTab;
  await expect(printed.getByRole("list", { name: "Equipment" })).toContainText("Silver Dagger");
  await printed.close();

  // Status… is the Status & Titles tab's card: she has no sect, so holds none.
  menu = await actions(l, "Odalys");
  await menu.getByRole("menuitem", { name: "Status…" }).click();
  const status = l.getByRole("dialog", { name: "Odalys's status" });
  await expect(status.getByText("Odalys has no sect, so holds no status.")).toBeVisible();
  await status.getByRole("button", { name: "Close" }).click();

  // Badge… shows what her badge says, takes a note for it, and prints it.
  menu = await actions(l, "Odalys");
  await menu.getByRole("menuitem", { name: "Badge…" }).click();
  const badge = l.getByRole("dialog", { name: "Odalys's badge" });
  await expect(badge.getByLabel("Also shown on the badge")).toBeVisible();
  await badge.getByRole("button", { name: "Close" }).click();

  // Casimir shows among the NPCs, with the same ⋯ (#556): Play, no XP, its Who's Who
  // listing, and only a storyteller can give it to a player or make a claim link.
  await l.locator("main").getByRole("radio", { name: "NPCs" }).click();
  await expect(l.getByRole("link", { name: "Odalys" })).toHaveCount(0);
  menu = await actions(l, "Casimir");
  await expect(menu.getByRole("menuitem")).toHaveText([
    "Play",
    "Give equipment…",
    "Status…",
    "Titles…",
    "List on the Who’s Who",
    "Give to a player…",
    "Claim link…",
    "Print sheet",
    "Badge…",
  ]);
  await menu.getByRole("menuitem", { name: "Give to a player…" }).click();
  await expect(l.getByRole("dialog", { name: "Give Casimir to a player" }).getByLabel("Player")).toBeVisible();
  await l.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  const a = assistant.page;
  await a.goto(`/troupes/${troupe.id}/roster?show=npcs`);
  menu = await actions(a, "Casimir");
  await expect(menu.getByRole("menuitem")).toHaveText(["Play", "Give equipment…", "Status…", "Titles…", "List on the Who’s Who", "Print sheet", "Badge…"]);

  // A narrator never sees character sheets, so has no Characters list at all: their
  // Characters group holds only the troupe's lines and veils, and opens on them (#779).
  const n = narrator.page;
  await n.goto(`/troupes/${troupe.id}`);
  if (isPhone(n)) {
    // On a phone, the section picker lists the group with that one tab.
    const characters = await groupTabs(n, "Characters");
    await expect(characters.getByRole("link")).toHaveText(["Lines and veils"]);
    await characters.getByRole("link", { name: "Lines and veils" }).click();
  } else {
    const sections = n.getByRole("navigation", { name: "Troupe sections" });
    await expect(sections.getByRole("link", { name: "Between games", exact: true })).toBeVisible();
    await sections.getByRole("link", { name: "Characters", exact: true }).click();
    await expect(n.getByRole("navigation", { name: "Characters", exact: true })).toHaveCount(0);
  }
  await expect(n).toHaveURL(new RegExp(`/troupes/${troupe.id}/lines-and-veils$`));
  await n.goto(`/troupes/${troupe.id}/roster`);
  await expect(n.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(n.getByRole("button", { name: "Actions for Odalys" })).toHaveCount(0);
});

test("the troupe list says what each troupe is, whether it takes new players and where you play, and keeps the ask form shut", async ({ browser }) => {
  const custodian = await person(browser, "chooser-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "chooser-lead");
  const player = await person(browser, "chooser-player");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const troupeName = `Court of the Corn Exchange ${run}`;
  const troupeId = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, troupeId);
  await send(lead.page, "PATCH", `/api/troupes/${troupeId}`, {
    description: "A **Camarilla** court that meets under the old dome.\n\nGames run monthly; see the profile for more.",
  });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/profile`, { new_players: "welcoming", venue: { region: "Leeds" } });
  const id = await builtVampire(player.page, "Clémence Aubry", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});

  // The player's own troupe comes first, with the start of its description as plain text.
  const p = player.page;
  await p.goto("/troupes");
  const list = p.locator("main ul").first();
  await expect(list.getByRole("listitem").first()).toContainText(troupeName);
  const row = list.getByRole("listitem").filter({ hasText: troupeName });
  await expect(row.getByText("A Camarilla court that meets under the old dome.", { exact: true })).toBeVisible();
  await expect(row.getByText("Leeds", { exact: true })).toBeVisible();
  await expect(row.getByText("Welcoming new players", { exact: true })).toBeVisible();
  await expect(row.getByText("You play here", { exact: true })).toBeVisible();
  await expect(row.getByText("Clémence Aubry", { exact: true })).toBeVisible();

  // Asking for a troupe of your own is one line until opened.
  const open = p.getByRole("button", { name: "Ask for a new troupe" });
  await expect(open).toHaveAttribute("aria-expanded", "false");
  await expect(p.getByLabel("Troupe name")).toHaveCount(0);
  await p.screenshot(shots("troupes-list"));

  // Its staff see that they run it.
  await lead.page.goto("/troupes");
  const theirs = lead.page.locator("main ul").first().getByRole("listitem").filter({ hasText: troupeName });
  await expect(theirs.getByText("You run this", { exact: true })).toBeVisible();
  await expect(theirs.getByText("You play here", { exact: true })).toHaveCount(0);
});

test("someone asks for a troupe of their own, and the custodian approves it", async ({ browser }) => {
  const custodian = await person(browser, "requests-custodian");
  makeCustodian(custodian.email);
  const asker = await person(browser, "requests-asker");
  const troupeName = `Court of Cinders ${run}`;

  const a = asker.page;
  await (await topBar(a)).getByRole("link", { name: "Troupes" }).click();
  await a.getByRole("button", { name: "Ask for a new troupe" }).click();
  await a.getByLabel("Troupe name").fill(troupeName);
  await a.getByLabel("Note to the custodian").fill("Eight players ready.");
  await a.getByRole("button", { name: "Send request" }).click();
  const mine = a.getByRole("listitem").filter({ hasText: troupeName });
  await expect(mine.getByText("Waiting", { exact: true })).toBeVisible();

  // It waits on the custodian's bell and under Custodian → Troupe management → Requests.
  const c = custodian.page;
  await c.reload();
  await (await topBar(c)).getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: /^Troupe management/ }).click();
  const requests = c.getByRole("region", { name: "Requests" });
  const request = requests.getByRole("listitem").filter({ hasText: troupeName });
  await expect(request.getByText("Eight players ready.")).toBeVisible();
  await expect(request.getByText(`(@${asker.handle}), `)).toBeVisible();
  await c.screenshot(shots("troupe-request"));
  await request.getByRole("button", { name: "Approve and make the troupe" }).click();
  await expect(requests.getByRole("link", { name: troupeName })).toBeVisible();

  // What is running, on the Site tab, and that the database is on its latest migration.
  await c.getByRole("link", { name: "Site", exact: true }).click();
  await expect(c.getByText("Up to date", { exact: true })).toBeVisible();
  await c.screenshot(shots("custodian-site"));

  // The asker now leads it.
  await a.reload();
  await expect(mine.getByText("Approved", { exact: true })).toBeVisible();
  await a.locator("main").getByRole("link", { name: troupeName }).first().click();
  await expect(a.getByText("Lead storyteller").first()).toBeVisible();

  // Appointing a new lead says, before it is done, that the asker would leave the staff.
  await c.goto(a.url());
  await troupeTab(c, "Staff");
  await expect(c.getByText("requests-asker will leave the staff, with no role in the troupe.", { exact: false })).toBeVisible();
});

test("archiving a troupe lets its characters go and ends its cycle, and the custodian reopens it", async ({ browser }) => {
  const custodian = await person(browser, "closing-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "closing-lead");
  const player = await person(browser, "closing-player");
  const visitor = await person(browser, "closing-visit");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const troupeName = `Court of Last Lamps ${run}`;
  const troupeId = (await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, troupeId);
  const otherId = (await send(custodian.page, "POST", "/api/troupes", { name: `Court of Far Lamps ${run}`, lead_handle: lead.handle })).id;
  await backstoryOptional(custodian.page, otherId);
  // A Brujah built through the API and accepted home in `home`.
  const build = async (page: Page, name: string, home: string): Promise<string> => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, chosen] of Object.entries(picks))
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: chosen.map(([name, rating]) => ({ name, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`, {});
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: home });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`, {});
    return id;
  };

  // Mireille is at home here, mid-game and in an open cycle; Tobias, at home in
  // another troupe, visits.
  const mireille = await build(player.page, "Mireille", troupeId);
  const tobias = await build(visitor.page, "Tobias", otherId);
  await send(visitor.page, "POST", `/api/characters/${tobias}/troupes`, { troupe_id: troupeId });
  const tap = { id: crypto.randomUUID(), happened_at: new Date().toISOString(), kind: "change", tracker: "blood", amount: -1 };
  await send(player.page, "POST", `/api/characters/${mireille}/play/taps`, { taps: [tap] });
  const day = 24 * 60 * 60 * 1000;
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupeId}/cycles`, {
    name: "Lamplight",
    closes_at: new Date(Date.now() + 7 * day).toISOString(),
    grace_ends_at: new Date(Date.now() + 14 * day).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`, {});

  // The lead archives it from the Overview, seeing first what that settles.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  await l.getByRole("button", { name: "Archive troupe…" }).click();
  const dialog = l.getByRole("dialog", { name: `Archive ${troupeName}` });
  await expect(dialog.getByText("leave these characters with no home troupe: Mireille (closing-player)")).toBeVisible();
  await expect(dialog.getByText("end these characters' visits: Tobias (closing-visit)")).toBeVisible();
  await expect(dialog.getByText("end the open downtime cycle, Lamplight, without answering or delivering it")).toBeVisible();
  await expect(dialog.getByText(/end the games under way .*: Mireille/)).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Archive troupe" })).toBeDisabled();
  await dialog.getByLabel("Reason").fill("The chronicle has ended");
  await l.screenshot(shots("archive-troupe"));
  await dialog.getByRole("button", { name: "Archive troupe" }).click();
  await expect(l).toHaveURL(/\/troupes$/);
  await expect(l.locator("main").getByRole("link", { name: troupeName })).toHaveCount(0);

  // Both players are told; Mireille has no home troupe now and Tobias still has his.
  const p = player.page;
  await p.reload();
  await p.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(p.getByText(`${troupeName} is archived (The chronicle has ended): Mireille has no home troupe now`, { exact: false })).toBeVisible();
  await p.keyboard.press("Escape");
  const memberships = await p.request.get(`/api/characters/${mireille}/troupes`, { headers });
  expect(await memberships.json()).toEqual([]);
  await visitor.page.reload();
  await visitor.page.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await expect(visitor.page.getByText(`${troupeName} is archived (The chronicle has ended): Tobias no longer visits it`)).toBeVisible();

  // The custodian finds it under Troupe management → Archived troupes, with who archived it, why, and
  // the characters it had; its log is still there to read.
  const c = custodian.page;
  await c.reload();
  await (await topBar(c)).getByRole("link", { name: "Custodian", exact: true }).click();
  await c.getByRole("link", { name: /^Troupe management/ }).click();
  const card = c.getByRole("region", { name: "Archived troupes" }).getByRole("listitem").filter({ has: c.getByRole("heading", { name: troupeName }) });
  await expect(card.getByText("The chronicle has ended")).toBeVisible();
  await expect(card.getByRole("link", { name: "closing-lead" })).toBeVisible();
  await expect(card.getByRole("link", { name: "Mireille" })).toBeVisible();
  await expect(card.getByRole("link", { name: "Tobias" })).toBeVisible();
  await c.screenshot(shots("archived-troupes"));
  await card.getByRole("link", { name: "Log", exact: true }).click();
  await expect(c.getByText("closing-lead archived the troupe (The chronicle has ended).")).toBeVisible();
  await expect(c.getByText("closing-lead ended the downtime cycle Lamplight unanswered, as the troupe was archived.")).toBeVisible();

  // Reopened, it is running again, but Mireille does not come back by herself.
  await c.goBack();
  await card.getByRole("button", { name: "Reopen…" }).click();
  const reopen = c.getByRole("dialog", { name: `Reopen ${troupeName}` });
  await reopen.getByLabel("Reason").fill("A new chronicle");
  await reopen.getByRole("button", { name: "Reopen troupe" }).click();
  await expect(c.getByRole("heading", { name: troupeName })).toHaveCount(0);
  await l.goto(`/troupes/${troupeId}`);
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  expect(await (await p.request.get(`/api/characters/${mireille}/troupes`, { headers })).json()).toEqual([]);
});

test("a lead adds staff by picking from a list of people, the troupe's own players first", async ({ browser }) => {
  const custodian = await person(browser, "staff-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "staff-lead");
  const player = await person(browser, "staff-player");
  const troupeName = `Court of Keys ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  // The custodian finds the lead in the list by typing part of their handle.
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle.slice(0, -2));
  await custodian.page.getByRole("listbox", { name: "People" }).getByRole("option", { name: `@${lead.handle}` }).click();
  await expect(custodian.page.getByLabel("Lead storyteller")).toHaveValue(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();

  // The player's character visits the troupe.
  const p = player.page;
  await p.getByLabel("Name").fill("Agnes Moreau");
  await p.getByRole("button", { name: "Create" }).click();
  await expect(p.getByRole("heading", { name: "Concept" })).toBeVisible();
  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe to join").selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Visit", exact: true }).click();
  await expect(p.getByRole("listitem").filter({ hasText: troupeName })).toBeVisible();
  // Home troupe comes first, then the visiting troupes, each with what it means behind its (i),
  // below the Next card above the tabs (#1051).
  await expect(p.locator('main section:not([aria-label="Next for this character"]) h2')).toHaveText(["Home troupe", "Visiting troupes"]);
  const card = (title: string) => p.locator("main section").filter({ has: p.getByRole("heading", { name: title }) });
  await expect(card("Home troupe").getByText("The one troupe that holds this character's sheet.")).toHaveCount(0);
  await card("Home troupe").getByRole("button", { name: "What a home troupe is" }).click();
  await expect(card("Home troupe").getByText("The one troupe that holds this character's sheet.")).toBeVisible();
  // Closed again first: on a phone it covers the next card's (i).
  await p.keyboard.press("Escape");
  await card("Visiting troupes").getByRole("button", { name: "What a visiting troupe is" }).click();
  await expect(card("Visiting troupes").getByText("A troupe this character plays in without its home there.")).toBeVisible();

  // The list opens as soon as the box is clicked: the troupe's player first.
  await (await topBar(lead.page)).getByRole("link", { name: "Troupes" }).click();
  await lead.page.getByRole("link", { name: troupeName }).click();
  await troupeTab(lead.page, "Staff");
  await lead.page.getByLabel("Person").click();
  const people = lead.page.getByRole("listbox", { name: "People" });
  await expect(people.getByRole("option").first()).toContainText(`@${player.handle}`);
  await expect(people.getByRole("option").first()).toContainText("Plays here");
  await expect(people).not.toContainText("@example.com");
  await lead.page.screenshot(shots("staff-picker"));
  await people.getByRole("option", { name: `@${player.handle}` }).click();
  await expect(lead.page.getByLabel("Person")).toHaveValue(player.handle);
  // Each role says in a line what it may do.
  const roles = lead.page.locator("section").filter({ has: lead.page.getByRole("heading", { name: "Roles", exact: true }) });
  await expect(roles.getByText("Never sees character sheets.")).toBeVisible();
  await expect(roles.getByText(/^Everything a storyteller does except manage staff/)).toBeVisible();
  await lead.page.getByRole("button", { name: "Add to staff" }).click();
  await expect(lead.page.getByText(`@${player.handle} · Narrator`)).toBeVisible();

  // Now on the staff, they are greyed out with their role.
  await lead.page.getByLabel("Person").click();
  const added = people.getByRole("option", { name: `@${player.handle}` });
  await expect(added).toHaveAttribute("aria-disabled", "true");
  await expect(added).toContainText("Narrator");
  // So is the lead.
  await lead.page.getByLabel("Person").fill(lead.handle);
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toHaveAttribute("aria-disabled", "true");
  await expect(people.getByRole("option", { name: `@${lead.handle}` })).toContainText("Lead storyteller");
  await lead.page.keyboard.press("Escape");

  // Their role is changed in the staff list.
  await lead.page.getByLabel("Role for staff-player").selectOption("assistant_storyteller");
  await expect(lead.page.getByText(`@${player.handle} · Assistant storyteller`)).toBeVisible();
});

test("a new player goes from a troupe's page to building a character for it, the troupe already chosen", async ({ browser }) => {
  const custodian = await person(browser, "playhere-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "playhere-lead");
  const player = await person(browser, "playhere-new");
  const troupeName = `Court of Open Doors ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;

  // A new player is welcomed with the steps to a first game; staff, with no characters either, land on their troupes.
  const p = player.page;
  await expect(p.getByRole("heading", { name: "Welcome to Horatio" })).toBeVisible();
  await lead.page.reload();
  await expect(lead.page.getByRole("heading", { name: "Your troupes" })).toBeVisible();
  await expect(lead.page.getByText("No characters of your own yet.", { exact: false })).toBeVisible();
  await expect(lead.page.getByRole("heading", { name: "Welcome to Horatio" })).toHaveCount(0);

  // The troupe's page says how to play there: one click to a character built for it.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "Play here" })).toBeVisible();
  await p.screenshot(shots("play-here"));
  await p.getByRole("link", { name: `Build a new character for ${troupeName}` }).click();
  await expect(p).toHaveURL(new RegExp(`/characters\\?troupe=${troupeId}`));
  await expect(p.getByLabel("Which troupe will you play in?")).toHaveValue(troupeId);
  await expect(p.getByText(`Your troupe: ${troupeName}`)).toBeVisible();
  await p.screenshot(shots("welcome"));

  // Its staff see no such card.
  await lead.page.goto(`/troupes/${troupeId}`);
  await expect(lead.page.getByRole("heading", { level: 1 })).toContainText(troupeName);
  await expect(lead.page.getByRole("heading", { name: "Play here" })).toHaveCount(0);
});

test("a player brings a character they have to a troupe from its page, and is told it waits for the storytellers", async ({ browser }) => {
  const custodian = await person(browser, "bringer-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bringer-lead");
  const player = await person(browser, "bringer-player");
  const troupeName = `Court of Second Chances ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(custodian.page, troupeId);
  const p = player.page;
  await builtVampire(p, "Ottoline", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });

  // "Ask to join" opens the character's Troupes tab with this troupe chosen.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "Play here" })).toBeVisible();
  await p.getByRole("listitem").filter({ hasText: "Ottoline" }).getByRole("link", { name: "Ask to join" }).click();
  await expect(p.getByRole("combobox", { name: "Troupe", exact: true })).toHaveValue(troupeId);
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(`Waiting for ${troupeName}'s storytellers to accept this character.`)).toBeVisible();

  // Back on the troupe's page, the card says so instead.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "Waiting for the storytellers" })).toBeVisible();
  await expect(p.getByRole("link", { name: `Build a new character for ${troupeName}` })).toHaveCount(0);
});

test("staff see the characters being built to their rules, read a sheet, and one leaves the list for Approvals once its player asks to join (#774)", async ({ browser }) => {
  const custodian = await person(browser, "beingbuilt-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "beingbuilt-lead");
  const player = await person(browser, "beingbuilt-play");
  const troupeName = `Court of Unfinished Business ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupeName, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  await backstoryOptional(custodian.page, troupeId);
  const p = player.page;
  // One finished and then brought to the troupe's rules, one only just begun.
  const marisol = await builtVampire(p, "Marisol", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Herd", 3], ["Fame", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  const brought = await p.request.put(`/api/characters/${marisol}/building-troupe`, { headers: { "X-Horatio": "1" }, data: { troupe_id: troupeId } });
  expect(brought.status(), await brought.text()).toBe(200);
  const begun = await p.request.post("/api/characters", { headers: { "X-Horatio": "1" }, data: { splat: "vampire", name: "Ysolde", building_troupe_id: troupeId } });
  expect(begun.status(), await begun.text()).toBe(201);

  const l = lead.page;
  // Nothing waits on staff yet, so the Characters group counts nothing; Approvals' Being built part counts them (#1048).
  await l.goto(`/troupes/${troupeId}`);
  await expect(l.getByRole("link", { name: /^Characters/ }).getByLabel(/waiting/)).toHaveCount(0);
  // On a phone, the section picker counts nothing waiting either.
  if (isPhone(l)) await expect(l.getByRole("navigation", { name: "Troupe sections" }).getByLabel(/waiting/)).toHaveCount(0);
  await l.goto(`/troupes/${troupeId}/approvals`);
  const building = l.locator("main").getByRole("navigation", { name: "Approvals", exact: true }).getByRole("link", { name: /^Being built/ });
  await expect(building.getByLabel("2 being built")).toBeVisible();
  await building.click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals/being-built$`));
  const ysolde = l.locator("section").filter({ has: l.getByRole("link", { name: "Ysolde", exact: true }) });
  await expect(ysolde.getByText("In creation")).toBeVisible();
  await expect(ysolde.getByText(/Still to place: .*Attributes/)).toBeVisible();
  const marisolCard = l.locator("section").filter({ has: l.getByRole("link", { name: "Marisol", exact: true }) });
  await expect(marisolCard.getByText("Finished, not yet submitted")).toBeVisible();
  await expect(marisolCard.getByText(`@${player.handle}`)).toBeVisible();
  await expect(l.getByText(player.email)).toHaveCount(0);

  // Its sheet opens to read, not to change.
  await marisolCard.getByRole("link", { name: "Read the sheet" }).click();
  await expect(l).toHaveURL(new RegExp(`/print/troupes/${troupeId}/builds/${marisol}`));
  await expect(l.getByText("Marisol").first()).toBeVisible();

  // Its player asks to join: it leaves the list for Approvals.
  await p.goto(`/characters/${marisol}/troupes`);
  await p.getByRole("combobox", { name: "Troupe", exact: true }).selectOption(troupeId);
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(`Waiting for ${troupeName}'s storytellers to accept this character.`)).toBeVisible();
  await l.goto(`/troupes/${troupeId}/approvals/being-built`);
  await expect(l.getByRole("link", { name: "Ysolde", exact: true })).toBeVisible();
  await expect(l.getByRole("link", { name: "Marisol", exact: true })).toHaveCount(0);
  await expect(building.getByLabel("1 being built")).toBeVisible();
  // Its old address lands on the part.
  await l.goto(`/troupes/${troupeId}/being-built`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals/being-built$`));
  await l.locator("main").getByRole("navigation", { name: "Approvals", exact: true }).getByRole("link", { name: "To decide" }).click();
  await expect(l.getByText("Asking to make this home")).toBeVisible();
});

test("the characters list and each Troupes tab say where a character stands: in creation, waiting, at home, or with no home yet, and whose rules it is built to (#368, #569)", async ({ browser }) => {
  // Five characters, a downtime cycle and a dozen pages.
  test.slow();
  const custodian = await person(browser, "whereami-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "whereami-lead");
  const player = await person(browser, "whereami-play");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const hearths = `Court of Hearths ${run}`;
  const farShores = `Court of Far Shores ${run}`;
  const home = await send(custodian.page, "POST", "/api/troupes", { name: hearths, lead_handle: lead.handle });
  const away = await send(custodian.page, "POST", "/api/troupes", { name: farShores, lead_handle: lead.handle });
  for (const t of [home, away]) await backstoryOptional(custodian.page, t.id);
  const p = player.page;
  // Characters made through the API: one left in creation, three finished.
  const make = async (name: string, finish: boolean) => {
    const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name, building_troupe_id: home.id });
    if (!finish) return id as string;
    await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
      focus_physicals: [["Strength", 1]],
      focus_mentals: [["Wits", 1]],
      focus_socials: [["Charisma", 1]],
      skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(p, "POST", `/api/characters/${id}/creation/complete`);
    return id as string;
  };
  const halfway = await make("Halfway Hester", false);
  const asker = await make("Asking Aldous", true);
  const settled = await make("Settled Seraphine", true);
  const loner = await make("Lone Lucan", true);
  // Built to the book's rules: no troupe chosen.
  const bookish = (await send(p, "POST", "/api/characters", { splat: "vampire", name: "Bookish Bede" })).id as string;
  await send(p, "POST", `/api/characters/${asker}/home-troupe`, { troupe_id: away.id });
  const asked = await send(p, "POST", `/api/characters/${settled}/home-troupe`, { troupe_id: home.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${home.id}/cycles`, {
    name: "Hearth month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);

  // The list says where each stands, and the downtime due.
  const row = (name: string) => p.getByRole("listitem").filter({ hasText: name });
  await p.goto("/characters");
  await expect(row("Halfway Hester")).toContainText("In creation");
  await expect(row("Asking Aldous")).toContainText(`Waiting for ${farShores}`);
  await expect(row("Settled Seraphine")).toContainText(`Home: ${hearths}`);
  await expect(row("Settled Seraphine").getByText(/^Downtime due \w{3} .+, \d{1,2}:\d{2} [ap]m$/)).toBeVisible();
  await expect(row("Lone Lucan")).toContainText("No home troupe yet");
  // With no home troupe yet, whose rules each is built to (#569).
  await expect(row("Lone Lucan")).toContainText(`Built to ${hearths}'s rules`);
  await expect(row("Halfway Hester")).toContainText(`Built to ${hearths}'s rules`);
  await expect(row("Asking Aldous")).toContainText(`Built to ${hearths}'s rules`);
  await expect(row("Bookish Bede")).toContainText("Built to the book's rules");
  await expect(row("Settled Seraphine")).not.toContainText("Built to");
  await expect(p.getByText("Active", { exact: true })).toHaveCount(0);
  await p.screenshot(shots("characters-standing"));

  // Submitted and answered, the results are new until the player opens them.
  const form = await send(p, "GET", `/api/characters/${settled}/downtime`);
  const question = form.questions.find((q: { prompt: string }) => q.prompt === "Downtime action");
  await send(p, "PUT", `/api/characters/${settled}/downtime/answers`, { answers: [{ question_id: question.id, slot: 1, body: "Tend the hearth." }] });
  await send(p, "POST", `/api/characters/${settled}/downtime/submit`);
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/close`, { add_to_ceiling: true });
  const [response] = await send(lead.page, "GET", `/api/cycles/${cycle.id}/responses`);
  await send(lead.page, "PUT", `/api/responses/${response.id}`, { body: "The fire holds." });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/deliver`, { partial: true });
  await p.reload();
  await expect(row("Settled Seraphine")).toContainText("New results");
  await expect(row("Settled Seraphine")).not.toContainText("Downtime due");
  await p.goto(`/characters/${settled}`);
  await characterTab(p, "Results");
  await expect(p.getByText("The fire holds.")).toBeVisible();
  await p.goto("/characters");
  await expect(row("Settled Seraphine")).toContainText(`Home: ${hearths}`);
  await expect(row("Settled Seraphine")).not.toContainText("New results");

  // Each Troupes tab opens with the home troupe, or says there is none yet and how to get one.
  const homeCard = p.locator("main section").filter({ has: p.getByRole("heading", { name: "Home troupe" }) });
  await p.goto(`/characters/${settled}/troupes`);
  await expect(homeCard).toContainText(`Home now: ${hearths}`);
  await expect(homeCard.getByRole("link", { name: `${hearths}'s house rules` })).toBeVisible();
  await p.screenshot(shots("troupes-home"));
  await expect(homeCard.getByRole("combobox")).toHaveCount(0);
  await homeCard.getByRole("button", { name: "Move or leave…" }).click();
  await expect(homeCard.getByRole("combobox", { name: "New home troupe" })).toBeVisible();
  await expect(homeCard.getByRole("button", { name: `Leave ${hearths} and have no home troupe` })).toBeVisible();

  await p.goto(`/characters/${asker}/troupes`);
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(homeCard).toContainText(`Waiting for ${farShores}'s storytellers to accept this character.`);
  await expect(homeCard).toContainText("Nothing for you to do until they decide.");

  await p.goto(`/characters/${loner}/troupes`);
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(homeCard).toContainText(`Built to ${hearths}'s house rules. Not accepted there yet.`);
  await expect(homeCard.getByRole("link", { name: `${hearths}'s house rules` })).toHaveAttribute("href", `/troupes/${home.id}/house-rules`);
  await expect(homeCard.getByRole("combobox", { name: "Troupe", exact: true })).toBeVisible();
  // The sheet's Troupes card says it too.
  await p.goto(`/characters/${loner}`);
  const troupesCard = p.locator("main section").filter({ has: p.getByRole("heading", { name: "Troupes", exact: true }) });
  await expect(troupesCard).toContainText("In your vault, in no troupe.");
  await expect(troupesCard).toContainText(`Built to ${hearths}'s house rules. Not accepted there yet.`);
  await p.goto(`/characters/${settled}`);
  await expect(troupesCard).toContainText(hearths);
  await expect(troupesCard).not.toContainText("Built to");

  await p.goto(`/characters/${bookish}/troupes`);
  await expect(homeCard).toContainText("Built to the book's rules (no troupe chosen yet).");

  await p.goto(`/characters/${halfway}/troupes`);
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(homeCard).toContainText(`then ask ${hearths} here`);
  await homeCard.getByRole("link", { name: "Create tab" }).click();
  await expect(p).toHaveURL(new RegExp(`/characters/${halfway}/create`));
});

test("a new character's Next card changes as it is built, asks to join and is accepted, and the Characters page lists the same (#1051, #1109)", async ({ browser }) => {
  const custodian = await person(browser, "nextstep-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "nextstep-lead");
  const player = await person(browser, "nextstep-play");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "GET" | "POST" | "PUT", url: string, data?: object) => {
    const response = await page.request.fetch(url, { method, headers, data: method === "GET" ? undefined : (data ?? {}) });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupeName = `Court of Next Steps ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Quillon Next", building_troupe_id: troupe.id });
  const card = p.getByRole("region", { name: "Next for this character" });
  const row = p.getByRole("listitem").filter({ hasText: "Quillon Next" });

  // Being built: finishing it is the player's.
  await p.goto(`/characters/${id}/sheet`);
  await expect(card.getByRole("list", { name: "For you" }).getByRole("link", { name: "Finish character creation" })).toHaveAttribute("href", `/characters/${id}/create`);
  await p.goto("/characters");
  await expect(row.getByRole("list", { name: "Next" }).getByRole("link", { name: "Finish character creation" })).toBeVisible();

  // Finished: asking its troupe to be its home is next, and the link asks it.
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number][]> = {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`);
  await p.goto(`/characters/${id}`);
  await expect(card.getByRole("link", { name: "Finish character creation" })).toHaveCount(0);
  await card.getByRole("link", { name: `Ask ${troupeName} to be its home` }).click();
  await expect(p.getByRole("combobox", { name: "Troupe", exact: true })).toHaveValue(troupe.id);
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();

  // Asked: now it waits on the troupe's staff, since today.
  const waiting = card.getByRole("list", { name: "Waiting on staff" });
  await expect(waiting.getByRole("listitem")).toHaveText(new RegExp(`^Asked ${troupeName} to be its home, since \\w{3} \\d{1,2} \\w{3}$`));
  await expect(card.getByRole("list", { name: "For you" })).toHaveCount(0);
  await p.screenshot(shots("next-for-character"));
  await p.goto("/characters");
  await expect(row.getByRole("list", { name: "Next" })).toContainText(`Waiting on staff: Asked ${troupeName} to be its home, since`);

  // Accepted, with nothing next: the card is gone, and so is its line.
  const [asked] = await send(lead.page, "GET", `/api/troupes/${troupe.id}/approvals`);
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await p.goto(`/characters/${id}`);
  await expect(p.getByRole("heading", { name: "Quillon Next" })).toBeVisible();
  await expect(card).toHaveCount(0);
  await p.goto("/characters");
  await expect(row).toContainText(`Home: ${troupeName}`);
  await expect(row.getByRole("list", { name: "Next" })).toHaveCount(0);

  // A game planned: coming up, it asks whether they're coming, answered on the card (#1109).
  const start = new Date(Date.now() + 3 * 24 * 3600 * 1000);
  await send(lead.page, "POST", `/api/troupes/${troupe.id}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 3600 * 1000).toISOString() });
  await p.reload();
  const line = row.getByRole("list", { name: "Next" });
  await expect(line.getByRole("link", { name: `${troupeName}'s next game` })).toHaveAttribute("href", `/troupes/${troupe.id}`);
  await expect(line.getByRole("link", { name: "say whether you're coming" })).toHaveAttribute("href", `/troupes/${troupe.id}`);
  await p.goto(`/characters/${id}`);
  const coming = card.getByRole("list", { name: "Coming up" });
  await expect(coming.getByRole("link", { name: `${troupeName}'s next game` })).toBeVisible();
  await coming.getByRole("group", { name: /^Are you coming on / }).getByRole("button", { name: "Maybe" }).click();
  await expect(coming).toContainText(", answered Maybe");
  await expect(coming.getByRole("group")).toHaveCount(0);
  // The troupe's Games card has the same answer.
  await p.goto(`/troupes/${troupe.id}`);
  await expect(p.getByRole("list", { name: "Games to come" }).getByRole("button", { name: "Maybe" })).toHaveAttribute("aria-pressed", "true");
  await p.goto("/characters");
  await expect(line).toContainText(", answered Maybe");
  await expect(line.getByRole("link", { name: "say whether you're coming" })).toHaveCount(0);
});

test("a player leaves the home troupe after a dialog naming the title that ends, and the card says there is none (#459)", async ({ browser }) => {
  const custodian = await person(browser, "partings-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "partings-lead");
  const player = await person(browser, "partings-play");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const partings = `Court of Partings ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: partings, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupe.id);

  // Parting Pell, a Camarilla Brujah built through the API, accepted home, and made Harpy.
  const p = player.page;
  const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name: "Parting Pell", building_troupe_id: troupe.id });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  await send(p, "PUT", `/api/characters/${id}/traits`, { category: "sect", name: "Camarilla", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Resources", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(p, "POST", `/api/characters/${id}/creation/complete`);
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/characters/${id}/titles`, { titles: ["Harpy"] });

  // Move or leave opens the move, with leaving beside it; the dialog names what ends.
  const homeCard = p.locator("main section").filter({ has: p.getByRole("heading", { name: "Home troupe" }) });
  await p.goto(`/characters/${id}/troupes`);
  await expect(homeCard).toContainText(`Home now: ${partings}`);
  await homeCard.getByRole("button", { name: "Move or leave…" }).click();
  await homeCard.getByRole("button", { name: `Leave ${partings} and have no home troupe` }).click();
  const dialog = p.getByRole("dialog", { name: `Leave ${partings}?` });
  await expect(dialog.getByRole("list", { name: "Titles that end" })).toHaveText("Harpy");
  await expect(dialog.getByText("It has no requests waiting there.")).toBeVisible();
  await expect(dialog.getByText("Its sheet, XP and history stay as they are, and so do its visits to other troupes.")).toBeVisible();
  await p.screenshot(shots("troupes-leave-home"));
  // Cancelling leaves it home.
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(homeCard).toContainText(`Home now: ${partings}`);

  await homeCard.getByRole("button", { name: `Leave ${partings} and have no home troupe` }).click();
  await dialog.getByRole("button", { name: `Leave ${partings}`, exact: true }).click();
  await expect(homeCard).toContainText("No home troupe yet");
  await expect(dialog).toBeHidden();
  await expect(homeCard.getByRole("combobox", { name: "Troupe", exact: true })).toBeVisible();
  await expect(homeCard.getByRole("button", { name: /^Leave / })).toHaveCount(0);

  // The title is gone, and the lead is told and reads it in the log.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/titles`);
  await expect(l.getByText("No one holds a title yet.")).toBeVisible();
  await l.goto(`/troupes/${troupe.id}/log`);
  await expect(l.getByText(`Parting Pell (partings-play) left ${partings} as its home troupe, and has no home troupe now.`)).toBeVisible();
});

test("a troupe's profile: storytellers fill it in, and people not signed in see it only when it is public", async ({ browser }) => {
  test.slow();
  // The troupe is made in New York, so it starts in New York's time zone (#1211), which
  // its games are entered in; the lead plans them there, and a visitor reads them in Tokyo.
  const custodian = await person(browser, "profile-custodian", { timezoneId: "America/New_York" });
  makeCustodian(custodian.email);
  const lead = await person(browser, "profile-lead", { timezoneId: "America/New_York" });
  const player = await person(browser, "profile-player");
  const visitor = await (await browser.newContext({ timezoneId: "Asia/Tokyo" })).newPage();
  const troupeName = `Lords of Leeds ${run}`;

  const c = custodian.page;
  await c.reload();
  await openNewTroupe(c);
  await c.getByLabel("Name").fill(troupeName);
  await c.getByLabel("Lead storyteller").fill(lead.handle);
  await c.getByRole("button", { name: "Create troupe" }).click();
  await expect(c.getByRole("link", { name: troupeName })).toBeVisible();

  // The lead fills in the profile on the troupe's Overview, part by part (#781), behind Edit profile (#912).
  const l = lead.page;
  await (await topBar(l)).getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  const troupeUrl = l.url();
  const troupeId = troupeUrl.split("/troupes/")[1]!.split("/")[0]!;
  await expectTabOpen(l, "Troupe", "Overview");
  const profile = l.getByRole("region", { name: "Profile" });
  // Saves the open card: done once its form has gone, not just its Save turned to Saving….
  const save = async () => {
    await profile.getByRole("button", { name: "Save", exact: true }).click();
    await expect(profile.getByRole("button", { name: /^(Save|Saving…)$/ })).toHaveCount(0);
  };
  // Folded away until asked for: the profile as players see it, with one Edit profile.
  await expect(profile.getByRole("button", { name: "Edit links" })).toHaveCount(0);
  await expect(l.getByRole("switch", { name: "Public" })).toHaveCount(0);
  await profile.getByRole("button", { name: "Edit profile" }).click();
  // A portrait, cropped square like a character's picture.
  await profile.getByRole("button", { name: "Add a portrait" }).click();
  await l.getByLabel("Choose a portrait").setInputFiles("e2e/portrait.jpg");
  await expect(l.getByRole("slider", { name: /Where the portrait is/ })).toBeVisible();
  await l.getByRole("dialog", { name: /'s portrait$/ }).getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByRole("dialog")).toBeHidden();
  await profile.getByRole("button", { name: "Edit links" }).click();
  await profile.getByLabel("Website").fill("https://lords.example.org");
  await profile.getByLabel("Discord invite").fill("https://discord.gg/lords");
  await save();
  await profile.getByRole("button", { name: "Edit when it plays" }).click();
  await profile.getByLabel("How often games run").fill("Second Saturday of the month, 7 pm to midnight");
  // A game: its end starts five hours on.
  await l.getByLabel("Game starts").fill("2030-01-12T19:00");
  await expect(l.getByLabel("Game ends")).toHaveValue("2030-01-13T00:00");
  // The browser draws each input in its own order; under it, the date the app's way.
  await expect(l.getByText("Sat 12 Jan 2030, 7:00 pm EST")).toBeVisible();
  await expect(l.getByText("Sun 13 Jan 2030, 12:00 am EST")).toBeVisible();
  await l.getByRole("button", { name: "Add game" }).click();
  await expect(l.getByRole("list", { name: "Upcoming games to edit" }).getByText("Sat 12 Jan 2030, 7 pm to Sun 13 Jan 2030, 12 am EST")).toBeVisible();
  await l.screenshot(shots("troupe-profile-edit"));
  await save();
  await profile.getByRole("button", { name: "Edit where it plays" }).click();
  await profile.getByLabel("City or region").fill("Leeds");
  await profile.getByLabel("Venue name").fill("The Crypt");
  await profile.getByLabel("Address", { exact: true }).fill("12 Mill Lane, Leeds");
  await profile.getByLabel("Accessibility").fill("Step-free access and a quiet room.");
  await save();
  await profile.getByRole("button", { name: "Edit the setting" }).click();
  await profile.getByLabel("Chronicle").fill("Leeds by Night");
  await profile.getByLabel("Era").fill("Modern nights");
  await save();
  await profile.getByRole("button", { name: "Edit new players" }).click();
  await profile.getByLabel("Taking new players?").selectOption({ label: "Welcoming new players" });
  await profile.getByLabel("Contact for new players").selectOption({ label: `profile-lead (@${lead.handle})` });
  await save();
  // Saving one card keeps what the others saved.
  await profile.getByRole("button", { name: "Edit age and content" }).click();
  await profile.getByLabel("Minimum age").fill("18");
  await profile.getByLabel("Content notes").fill("Violence and body horror.");
  await save();
  await profile.getByRole("button", { name: "Done" }).click();

  // It shows on the Overview, with the next game in the lead's own zone.
  await expect(profile.getByText("Sat 12 Jan 2030, 7 pm EST")).toBeVisible();
  await expect(profile.getByText("Welcoming new players").first()).toBeVisible();
  await expect(profile.getByText("12 Mill Lane, Leeds")).toBeVisible();
  await expect(profile.getByText("Leeds by Night")).toBeVisible();
  await expect(profile.getByText("18+").first()).toBeVisible();
  const website = l.getByRole("link", { name: "Website" });
  await expect(website).toHaveAttribute("href", "https://lords.example.org");
  await expect(website).toHaveAttribute("target", "_blank");
  await expect(l.getByRole("heading", { level: 1 }).locator('img[src*="/portraits/"]')).toBeVisible();
  await l.screenshot(shots("troupe-profile"));

  // Anyone signed in sees it, street address and all; and the portrait shows in the troupe list.
  const p = player.page;
  await (await topBar(p)).getByRole("link", { name: "Troupes" }).click();
  await expect(p.getByRole("link", { name: troupeName }).locator('img[src*="/portraits/"]')).toBeVisible();
  await p.getByRole("link", { name: troupeName }).click();
  await expect(p.getByText("12 Mill Lane, Leeds")).toBeVisible();
  await expect(p.getByRole("button", { name: /^Edit/ })).toHaveCount(0);
  await expect(p.getByRole("switch", { name: "Public" })).toHaveCount(0);
  // The old Profile address opens the Overview.
  await p.goto(`/troupes/${troupeId}/profile`);
  await expect(p).toHaveURL(new RegExp(`/troupes/${troupeId}$`));
  await expect(p.getByText("12 Mill Lane, Leeds")).toBeVisible();

  // Off, as it starts: someone not signed in is told nothing about it.
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await expect(visitor.getByText(troupeName)).toHaveCount(0);

  // Switched on: anyone can see it at its public address, but never the street address.
  await profile.getByRole("button", { name: "Edit profile" }).click();
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByText("Public: anyone can see this profile, even people not signed in")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor.getByText("The Crypt")).toBeVisible();
  await expect(visitor.getByText("to see the address.")).toBeVisible();
  await expect(visitor.getByText("12 Mill Lane")).toHaveCount(0);
  await expect(visitor.getByText(lead.email)).toHaveCount(0);
  await expect(visitor.getByText(`@${lead.handle}`).first()).toBeVisible();
  // The next game, in the visitor's own zone.
  await expect(visitor.getByText("Sun 13 Jan 2030, 9 am GMT+9")).toBeVisible();
  await expect(visitor.locator('img[src*="/portraits/"]').first()).toBeVisible();
  await visitor.screenshot(shots("troupe-profile-public"));
  // A link to it previews with the troupe's name and portrait.
  const shared = await (await visitor.request.get(`/t/${troupeId}`)).text();
  expect(shared).toContain(`<meta property="og:title" content="${troupeName}" />`);
  expect(shared).toMatch(/<meta property="og:image" content="[^"]*\/portraits\/[^"]*\/512\.webp" \/>/);

  // Switched off again, it is for people signed in only once more.
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByText("Signed-in only")).toBeVisible();
  await visitor.reload();
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
});

test("members say whether they are coming to a game, staff see who, and a calendar link can be reset", async ({ browser }) => {
  const custodian = await person(browser, "rsvp-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "rsvp-lead", { timezoneId: "Europe/London" });
  const player = await person(browser, "rsvp-player", { timezoneId: "Europe/London" });
  const troupeName = `Lanterns of Lincoln ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await send(lead.page, "POST", `/api/troupes/${troupeId}/games`, { starts_at: "2030-03-09T19:00:00Z", ends_at: "2030-03-10T00:00:00Z" });
  // Rosalind visits the troupe, which makes her player a member.
  const { id: rosalind } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Rosalind" });
  await send(player.page, "POST", `/api/characters/${rosalind}/troupes`, { troupe_id: troupeId });

  // The player says she's coming, on the troupe's About tab.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}`);
  const game = p.getByRole("list", { name: "Games to come" }).getByRole("listitem").filter({ hasText: "Sat 9 Mar 2030, 7 pm" });
  await expect(game.getByText("No answers yet")).toBeVisible();
  const choices = game.getByRole("group", { name: /^Are you coming on Sat 9 Mar 2030, 7 pm GMT/ });
  await choices.getByRole("button", { name: "Coming", exact: true }).click();
  await expect(p.getByText(/^Coming: Sat 9 Mar 2030, 7 pm GMT/)).toBeVisible();
  await expect(choices.getByRole("button", { name: "Coming", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(game.getByText("1 coming")).toBeVisible();
  // Players see how many, not who.
  await expect(game.getByText("See who answered")).toHaveCount(0);
  await p.screenshot(shots("troupe-games-rsvp"));

  // The lead sees who is coming, with the character she plays here.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const leadGame = l.getByRole("list", { name: "Games to come" }).getByRole("listitem").filter({ hasText: "Sat 9 Mar 2030, 7 pm" });
  await expect(leadGame.getByText("1 coming")).toBeVisible();
  await leadGame.getByText("See who answered").click();
  await expect(leadGame.getByRole("list", { name: "Coming" })).toContainText("rsvp-player");
  await expect(leadGame.getByRole("list", { name: "Coming" })).toContainText("Rosalind");
  await l.screenshot(shots("troupe-games-staff"));

  // She changes her mind: one answer per person.
  await choices.getByRole("button", { name: "Maybe" }).click();
  await expect(game.getByText("1 maybe")).toBeVisible();
  await expect(choices.getByRole("button", { name: "Coming", exact: true })).toHaveAttribute("aria-pressed", "false");

  // Her calendar link: the feed has the game with her answer (#1058), and
  // resetting it stops the old one.
  await p.getByRole("button", { name: "Subscribe to the calendar" }).click();
  const dialog = p.getByRole("dialog", { name: "Subscribe to the calendar" });
  const only = dialog.getByRole("region", { name: `${troupeName} only` });
  await only.getByRole("button", { name: "Get the link" }).click();
  const address = only.locator(".font-mono");
  await expect(address).toHaveText(/\/api\/calendar\/[\w-]+\.ics$/);
  await expect(only.getByRole("link", { name: "Open in your calendar app" })).toHaveAttribute("href", /^webcal:\/\//);
  await expect(dialog.getByText("Google Calendar")).toBeVisible();
  await p.screenshot(shots("troupe-calendar-subscribe"));
  const path = (url: string) => url.slice(url.indexOf("/api/"));
  const old = path((await address.textContent())!);
  const feed = await p.request.get(old);
  expect(feed.status()).toBe(200);
  expect(feed.headers()["content-type"]).toContain("text/calendar");
  const ics = await feed.text();
  expect(ics).toContain("BEGIN:VCALENDAR");
  expect(ics).toContain(`SUMMARY:Maybe · Game: ${troupeName}`);
  expect(ics).toContain("DESCRIPTION:You said maybe.");
  expect(ics).toContain("DTSTART:20300309T190000Z");
  expect(ics).not.toContain(player.email);
  await only.getByRole("button", { name: "Reset the link…" }).click();
  await only.getByRole("button", { name: "Reset the link", exact: true }).click();
  await expect(only.getByRole("status")).toHaveText("New link made. The old one no longer works.");
  await expect(address).not.toHaveText(new RegExp(old.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  expect((await p.request.get(old)).status()).toBe(404);
  expect((await p.request.get(path((await address.textContent())!))).status()).toBe(200);
});

test("players check in at the door and land in their Play View, and staff award the game's XP to those who came", async ({ browser }) => {
  const custodian = await person(browser, "door-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "door-lead");
  const player = await person(browser, "door-player");
  const troupeName = `Keepers of Kendal ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupeId);
  // A game under way: it started an hour ago.
  const start = new Date(Date.now() - 60 * 60_000);
  await send(lead.page, "POST", `/api/troupes/${troupeId}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 60 * 60_000).toISOString() });
  // Hester is at home in the troupe, with 7 XP already this month; Wilf only visits.
  const { id: hester } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Hester" });
  await send(player.page, "PUT", `/api/characters/${hester}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(player.page, "PUT", `/api/characters/${hester}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(player.page, "POST", `/api/characters/${hester}/creation/complete`);
  const asked = await send(player.page, "POST", `/api/characters/${hester}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
  await send(lead.page, "POST", `/api/characters/${hester}/xp`, { amount: 7, reason: "Game, earlier this month" });
  const { id: wilf } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name: "Wilf" });
  await send(player.page, "POST", `/api/characters/${wilf}/troupes`, { troupe_id: troupeId });

  // The lead opens check-in from the game on About: a code and a QR code for the door.
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}`);
  const leadGame = l.getByRole("list", { name: "Games to come" }).getByRole("listitem").first();
  await expect(leadGame.getByText("Nobody checked in yet")).toBeVisible();
  await leadGame.getByRole("link", { name: "Check-in and attendance" }).click();
  await expect(l.getByRole("heading", { name: "Game night" })).toBeVisible();
  await expect(l).toHaveTitle(/^Game night · /);
  // A breadcrumb leads back to the troupe and its At game tab (#777).
  const crumbs = l.getByRole("navigation", { name: "Breadcrumb" });
  await expect(crumbs.getByRole("link")).toHaveText([troupeName, "At game"]);
  await expect(crumbs.getByRole("link", { name: "At game" })).toHaveAttribute("href", `/troupes/${troupeId}/at-game`);
  await expect(l.getByText("Nobody has checked in yet.")).toBeVisible();
  await l.getByRole("button", { name: "Open check-in" }).click();
  await expect(l.getByText("Check-in is open.")).toBeVisible();
  await expect(l.getByRole("img", { name: /^QR code for check-in/ })).toBeVisible();
  const code = ((await l.getByLabel(/^Code /).textContent()) ?? "").replace(/\s/g, "");
  expect(code).toMatch(/^[A-Z2-9]{6}$/);
  await l.screenshot(shots("game-night-door"));
  await l.getByRole("button", { name: "Show at the door" }).click();
  await expect(l.getByRole("dialog", { name: "Check in" }).getByRole("img", { name: /^QR code for check-in/ })).toBeVisible();
  await l.screenshot(shots("game-night-door-shown"));
  await l.getByRole("dialog", { name: "Check in" }).getByRole("button", { name: "Close" }).last().click();

  // The QR code's link, followed signed out, signs the player in and comes back.
  const door = await (await browser.newContext()).newPage();
  await door.goto(`/check-in/${code}`);
  await expect(door.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(new URL(door.url()).searchParams.get("next")).toBe(`/check-in/${code}`);
  await door.getByLabel("Email or handle").fill(player.email);
  await door.getByLabel("Password").fill(PASSWORD);
  await door.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(door.getByRole("heading", { name: "Check in" })).toBeVisible();
  await expect(door.getByText(troupeName)).toBeVisible();
  await door.getByLabel("Hester").check();
  await door.screenshot(shots("check-in"));
  await door.getByRole("button", { name: "Check in Hester" }).click();
  // Her night starts on the Play View.
  await expect(door.getByRole("heading", { name: "Hester" })).toBeVisible();
  expect(new URL(door.url()).pathname).toBe(`/play/characters/${hester}`);

  // Wilf, from the game on About, without the code; no day's rest for him.
  const p = player.page;
  await p.goto(`/troupes/${troupeId}`);
  const game = p.getByRole("list", { name: "Games to come" }).getByRole("listitem").first();
  await expect(game.getByText("Checked in: Hester")).toBeVisible();
  await game.getByRole("button", { name: "Check in" }).click();
  const dialog = p.getByRole("dialog", { name: /^Check in: / });
  await expect(dialog).toContainText("Hester · checked in");
  await dialog.getByLabel("A full day's rest since the last game").uncheck();
  await dialog.getByRole("button", { name: "Check in Wilf" }).click();
  await expect(p.getByRole("heading", { name: "Wilf" })).toBeVisible();

  // The lead sees who came, checks Wilf out and back in by hand.
  await l.reload();
  const came = l.getByRole("table", { name: "Checked in" });
  await expect(l.getByRole("heading", { name: "Who came (2)" })).toBeVisible();
  const wilfRow = came.locator("tbody tr").filter({ hasText: "Wilf" });
  // In their columns on a wide screen, under the name on a phone.
  await expect(wilfRow.getByText("Visiting").filter({ visible: true })).toBeVisible();
  await expect(wilfRow.getByText("No day's rest").filter({ visible: true })).toBeVisible();
  await wilfRow.getByRole("button", { name: "Actions for Wilf" }).click();
  await l.screenshot(shots("game-night-menu"));
  await l.getByRole("menu", { name: "Actions for Wilf" }).getByRole("menuitem", { name: "Check out" }).click();
  await expect(l.getByText("Checked out: Wilf")).toBeVisible();
  await expect(came.locator("tbody tr")).toHaveCount(1);
  await l.getByLabel("Check someone in by hand").selectOption({ label: "Wilf (door-player)" });
  await l.getByRole("button", { name: "Check in", exact: true }).click();
  await expect(l.getByText("Checked in: Wilf")).toBeVisible();
  await expect(came.locator("tbody tr").filter({ hasText: "Wilf" }).getByText("By hand").filter({ visible: true })).toBeVisible();

  // The game's XP to those who came: the book's guidance, and a warning, not a refusal, past 10 in the month.
  await expect(l.getByText("The book suggests 3 to 5 XP a game, and no more than 8 to 10 a month (MET: VtM core, p. 108).")).toBeVisible();
  await expect(l.getByText("Wilf visiting: their home troupes award their XP.")).toBeVisible();
  await expect(l.getByRole("alert")).toHaveText("This takes Hester past 10 XP this month, more than the book suggests. You can still award it.");
  await l.getByRole("button", { name: "Less XP for the game" }).click();
  await l.getByRole("button", { name: "Award…" }).click();
  await l.screenshot(shots("game-night-award"));
  await l.getByRole("button", { name: "Yes, award 7 XP to 1 character" }).click();
  await expect(l.getByText("Awarded 7 XP to 1 character. Hester now has more than 10 this month.")).toBeVisible();
  await expect(l.getByText(/^7 XP awarded to everyone here who calls this troupe home/)).toBeVisible();
  await expect(l.getByText("Check-in closed when the game's XP was awarded.")).toBeVisible();

  // Hester's Experience tab has the award and the game she came to.
  await p.goto(`/characters/${hester}`);
  await characterTab(p, "Experience");
  await expect(p.getByRole("cell", { name: /^Game, / }).first()).toBeVisible();
  await expect(p.getByRole("heading", { name: "Games attended (1)" })).toBeVisible();
  await expect(p.getByRole("list", { name: "Games attended" })).toContainText(troupeName);
});

test("with Retainer upkeep on, checking in starts the night with the upkeep as its own line in the log (#442)", async ({ browser }) => {
  const custodian = await person(browser, "tithe-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tithe-lead");
  const player = await person(browser, "tithe-player");
  const troupeName = `Hall of Tithes ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupeId);
  const start = new Date(Date.now() - 60 * 60_000);
  const { id: gameId } = await send(lead.page, "POST", `/api/troupes/${troupeId}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 60 * 60_000).toISOString() });
  await send(lead.page, "PUT", `/api/troupes/${troupeId}/games/${gameId}/checkin`);
  // Perpetua has two Retainers, Bocephus and Rook, and calls the troupe home.
  const p = player.page;
  const perpetua = await builtVampire(p, "Perpetua", "Brujah", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  });
  for (const name of ["Bocephus", "Rook"]) await send(p, "PUT", `/api/characters/${perpetua}/traits`, { category: "backgrounds", name: "Retainers", detail: name, rating: 1 });
  const asked = await send(p, "POST", `/api/characters/${perpetua}/home-troupe`, { troupe_id: troupeId });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);

  // The lead switches upkeep on in the Roster's Settings: 1 Blood a game. The
  // Rules tab's old address for Retainers opens them there (#782, #785, #909).
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/retainers`);
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/roster#settings-retainers$`));
  const retainers = (await tabSettings(l, "Roster")).getByRole("region", { name: "Retainers", exact: true });
  await expect(retainers.getByLabel("Retainers cost upkeep")).not.toBeChecked();
  await retainers.getByLabel("Retainers cost upkeep").check();
  await expect(retainers.getByText("Not saved yet")).toBeVisible();
  await retainers.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("Saved.", { exact: true })).toBeVisible();
  await expect(retainers.getByRole("button", { name: "Save", exact: true })).toBeDisabled();

  // The House rules tab shows it; and so does each Retainer on the sheet.
  await p.goto(`/troupes/${troupeId}/house-rules`);
  await expect(p.getByText("Retainer upkeep")).toBeVisible();
  await p.goto(`/characters/${perpetua}`);
  await expect(p.getByRole("list", { name: "Retainers" }).getByText("· upkeep 1 Blood a game")).toHaveCount(2);

  // Checking in from the game starts her night, with the upkeep taken.
  await p.goto(`/troupes/${troupeId}`);
  await p.getByRole("list", { name: "Games to come" }).getByRole("listitem").first().getByRole("button", { name: "Check in" }).click();
  await p.getByRole("dialog", { name: /^Check in: / }).getByRole("button", { name: "Check in Perpetua" }).click();
  await expect(p.getByRole("heading", { name: "Perpetua" })).toBeVisible();
  await expect(p.getByText("Retainer upkeep: −2 Blood (Bocephus, Rook)")).toBeVisible();
  await expect(p.getByLabel("Blood: 8 of 10")).toBeVisible();
});

test("staff set a tapering game XP chart and award a game by it, with an absentee and an adjustment", async ({ browser }) => {
  const custodian = await person(browser, "chart-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "chart-lead");
  const player = await person(browser, "chart-player");
  const troupeName = `Tapers of the Teme ${run}`;
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await backstoryOptional(custodian.page, troupeId);
  const start = new Date(Date.now() - 60 * 60_000);
  await send(lead.page, "POST", `/api/troupes/${troupeId}/games`, { starts_at: start.toISOString(), ends_at: new Date(start.getTime() + 5 * 60 * 60_000).toISOString() });
  // Tamsin and Ulric are at home in the troupe; Tamsin has earned 250 XP, Ulric none.
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  const homed = async (name: string) => {
    const { id } = await send(player.page, "POST", "/api/characters", { splat: "vampire", name });
    await send(player.page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    for (const [category, list] of Object.entries(picks))
      await send(player.page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(player.page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(player.page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const tamsin = await homed("Tamsin");
  await homed("Ulric");
  await send(lead.page, "POST", `/api/characters/${tamsin}/xp`, { amount: 250, reason: "Games before Horatio" });

  // The lead starts from the Tapering chart, records absentee games, adds an adjustment, and switches the monthly cap off.
  const l = lead.page;
  await settingsPart(l, troupeId, "xp");
  const card = l.locator("section").filter({ has: l.getByRole("heading", { name: "Game XP chart", exact: true }) });
  await expect(card.getByText(/^Flat: everyone there gets the same XP/)).toBeVisible();
  await card.getByRole("button", { name: "Tapering" }).click();
  await expect(card.getByLabel("Band 2: earned XP up to")).toHaveValue("300");
  await card.getByLabel("Record absentee games").check();
  await card.getByRole("button", { name: "Add an adjustment" }).click();
  await card.getByLabel("Adjustment 1: name").fill("Helped");
  await card.getByLabel("Adjustment 1: times a month").fill("1");
  await card.getByLabel(/^Off/).check();
  await expect(card.getByText(/^Payments aren't tracked in Horatio/)).toBeVisible();
  await l.screenshot(shots("game-xp-chart-editor"));
  await card.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("Saved.", { exact: true })).toBeVisible();
  await expect(card.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await expect(card.getByLabel("Adjustment 1: name")).toHaveValue("Helped");

  // Players see it on the House rules tab.
  await player.page.goto(`/troupes/${troupeId}/house-rules`);
  const chart = player.page.getByRole("table", { name: "Game XP chart" });
  await expect(chart.getByRole("row")).toHaveCount(6);
  await expect(chart.getByRole("row", { name: "201–300 4 XP 3 XP" })).toBeVisible();
  await expect(chart.getByRole("row", { name: "501+ 1 XP 0 XP" })).toBeVisible();
  await expect(player.page.getByText("Adjustments: Helped +1, once a month.")).toBeVisible();

  // At the game: Tamsin is checked in by hand, Ulric marked absentee.
  await l.goto(`/troupes/${troupeId}`);
  await l.getByRole("list", { name: "Games to come" }).getByRole("listitem").first().getByRole("link", { name: "Check-in and attendance" }).click();
  await expect(l.getByRole("heading", { name: "Game night" })).toBeVisible();
  const choose = l.getByLabel("Check someone in by hand, or mark them absentee");
  await choose.selectOption({ label: "Tamsin (chart-player)" });
  await l.getByRole("button", { name: "Check in", exact: true }).click();
  await expect(l.getByText("Checked in: Tamsin")).toBeVisible();
  await choose.selectOption({ label: "Ulric (chart-player)" });
  await l.getByRole("button", { name: "Mark absentee" }).click();
  await expect(l.getByText("Marked absentee: Ulric")).toBeVisible();
  await expect(l.getByRole("heading", { name: "Who came (1)" })).toBeVisible();
  const absentees = l.getByRole("table", { name: "Absentee" });
  await expect(absentees).toContainText("Ulric");
  // Taking the absentee game back waits behind the ⋯ on his row.
  await absentees.getByRole("button", { name: "Actions for Ulric" }).click();
  await expect(l.getByRole("menu", { name: "Actions for Ulric" }).getByRole("menuitem")).toHaveText(["Take back the absentee game"]);
  await l.keyboard.press("Escape");

  // Each character's XP comes from the chart: Tamsin is in the 201–300 band, and helped; Ulric gets the absentee figure.
  const each = l.getByRole("list", { name: "Each character's XP" });
  const tamsinRow = each.getByRole("listitem").filter({ hasText: "Tamsin" });
  await expect(tamsinRow).toContainText("Attended, 201–300 band (250 earned): 4 XP");
  await expect(each.getByRole("listitem").filter({ hasText: "Ulric" })).toContainText("Absentee, 0–200 band (0 earned): 4 XP");
  await tamsinRow.getByLabel("Helped +1").check();
  await expect(l.getByLabel("Tamsin gets 5 XP")).toBeVisible();
  await l.getByRole("button", { name: "Award…" }).click();
  await l.screenshot(shots("game-night-chart-award"));
  await l.getByRole("button", { name: "Yes, award 9 XP to 2 characters" }).click();
  await expect(l.getByText("Awarded 9 XP in all to 2 characters.")).toBeVisible();
  const got = l.getByRole("list", { name: "What each character got" });
  await expect(got.getByRole("listitem").filter({ hasText: "Tamsin" })).toContainText("attended, 201–300 band, Helped +1");
  await expect(got.getByRole("listitem").filter({ hasText: "Ulric" })).toContainText("4 XP");

  // Tamsin's Experience tab has the award, its reason naming her band.
  await player.page.goto(`/characters/${tamsin}`);
  await characterTab(player.page, "Experience");
  await expect(player.page.getByRole("cell", { name: /: attended, 201–300 band, Helped \+1/ })).toBeVisible();
});

test("a troupe's public page asks a newcomer to make an account, which brings them on to build a character for it", async ({ browser }) => {
  const custodian = await person(browser, "joinlink-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "joinlink-lead");
  const troupeName = `Wardens of Whitby ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  const l = lead.page;
  await (await topBar(l)).getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  // Request to join goes through making an account, then into asking the troupe (#1192).
  const next = encodeURIComponent(`/troupes/${troupeId}/join`);

  // Signed-in only, the page still offers a way in.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await expect(visitor.getByRole("link", { name: "Request to join" })).toHaveAttribute("href", `/sign-up?next=${next}`);
  await expect(visitor.getByRole("main").getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", `/sign-in?next=${next}`);
  await visitor.screenshot(shots("anon-private-troupe"));

  // Public, the troupe's name leads, with the same two ways in.
  await troupeTab(l, "Overview");
  await l.getByRole("button", { name: "Edit profile" }).click();
  await l.getByRole("switch", { name: "Public" }).click();
  await expect(l.getByRole("switch", { name: "Public" })).toBeChecked();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  await expect(visitor.getByRole("main").getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", `/sign-in?next=${next}`);
  await visitor.screenshot(shots("anon-public-troupe"));

  // They make an account, and with no character to bring, go on to build one for the troupe.
  await visitor.getByRole("link", { name: "Request to join" }).click();
  await expect(visitor.getByRole("heading", { name: "Create an account" })).toBeVisible();
  await expect(visitor.getByText("Character sheets and downtimes for Mind's Eye Theatre troupes.")).toBeVisible();
  await visitor.screenshot(shots("signup"));
  await visitor.getByLabel("Your name").fill("joinlink-newcomer");
  await visitor.getByLabel("Handle").fill(`joinlink_${run.slice(-10)}`);
  await visitor.getByLabel("Email").fill(`joinlink-newcomer-${run}@example.com`);
  await visitor.getByLabel("Password").fill("a long enough password");
  await visitor.getByRole("button", { name: "Create account" }).click();
  await expect(visitor).toHaveURL(new RegExp(`/characters\\?troupe=${troupeId}$`));
  await expect(visitor.getByText(`Your troupe: ${troupeName}`)).toBeVisible();
});

test("signed out, the troupe directory finds a troupe by place, day (from its schedule or its next game) and new players, and Request to join goes through signing up", async ({ browser }) => {
  const custodian = await person(browser, "dirsearch-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "dirsearch-lead");
  const headers = { "X-Horatio": "1" };
  const place = `Fenwatch ${run}`;
  const found = `Fenwatch Court ${run}`;
  const closed = `Fenwatch Closed Court ${run}`;
  // Two public troupes in one place: one plays Fridays and welcomes new players; the
  // other's schedule says Saturdays and it doesn't, but its next game is on a Friday.
  const troupes: Record<string, string> = {};
  for (const [name, schedule, newPlayers] of [
    [found, "Every other Friday, 7 pm till late", "welcoming"],
    [closed, "Last Saturday of the month", "closed"],
  ] as const) {
    const made = await custodian.page.request.post("/api/troupes", { headers, data: { name, lead_handle: lead.handle } });
    expect(made.status(), await made.text()).toBe(201);
    const id = ((await made.json()) as { id: string }).id;
    troupes[name] = id;
    const profile = {
      schedule,
      new_players: newPlayers,
      min_age: 18,
      content_notes: "Horror and violence.",
      venue: { region: place, name: "The Mere Hall", address: "1 Secret Street", access: "" },
      public: true,
    };
    const saved = await lead.page.request.put(`/api/troupes/${id}/profile`, { headers, data: profile });
    expect(saved.status(), await saved.text()).toBe(200);
  }
  // Midday UTC on a Friday at least two days off: a Friday wherever the browser is.
  const friday = new Date();
  friday.setUTCDate(friday.getUTCDate() + 2 + ((5 - ((friday.getUTCDay() + 2) % 7) + 7) % 7));
  friday.setUTCHours(12, 0, 0, 0);
  const game = { starts_at: friday.toISOString(), ends_at: new Date(friday.getTime() + 4 * 3600_000).toISOString() };
  const added = await lead.page.request.post(`/api/troupes/${troupes[closed]}/games`, { headers, data: game });
  expect(added.status(), await added.text()).toBe(201);

  // From the landing page to the directory, and a search by place.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto("/");
  await visitor.getByRole("link", { name: "Search the troupe directory" }).click();
  await expect(visitor.getByRole("heading", { level: 1, name: "Find a troupe" })).toBeVisible();
  const search = visitor.getByRole("search", { name: "Search troupes" });
  await search.getByLabel("Place").fill(place);
  await search.getByRole("button", { name: "Search" }).click();
  const results = visitor.getByRole("list", { name: "Troupes found" });
  await expect(results.getByRole("link")).toHaveCount(2);
  // Never by the street address, which only people signed in see.
  await expect(visitor.getByText("1 Secret Street")).toHaveCount(0);

  // Fridays: both, the one by its schedule and the other by its next game, which its row shows.
  await search.getByLabel("Day").selectOption("friday");
  await expect(visitor).toHaveURL(/day=friday/);
  await expect(results.getByRole("link")).toHaveCount(2);
  await expect(results.getByRole("link", { name: new RegExp(closed) })).toContainText("Next game: Fri");
  // Welcoming new players too: only the one.
  await search.getByLabel("Only troupes welcoming new players").check();
  await expect(results.getByRole("link")).toHaveCount(1);
  const row = results.getByRole("link", { name: new RegExp(found) });
  await expect(row).toContainText("Every other Friday");
  await expect(row).toContainText("Welcoming new players");
  await expect(row).toContainText("18+");
  await expect(row).toContainText("Content notes: Horror and violence.");
  await expect(results.getByRole("link", { name: new RegExp(closed) })).toHaveCount(0);
  await expect(visitor).toHaveURL(/day=friday/);
  await visitor.screenshot(shots("troupe-directory"));

  // Its public profile, and Request to join, through making an account.
  await row.click();
  await expect(visitor).toHaveURL(new RegExp(`/t/${troupes[found]}$`));
  await expect(visitor.getByRole("heading", { level: 1, name: found })).toBeVisible();
  await visitor.getByRole("link", { name: "Request to join" }).click();
  await expect(visitor.getByRole("heading", { name: "Create an account" })).toBeVisible();
  await visitor.getByLabel("Your name").fill("dirsearch-newcomer");
  await visitor.getByLabel("Handle").fill(`dirsearch_${run.slice(-10)}`);
  await visitor.getByLabel("Email").fill(`dirsearch-newcomer-${run}@example.com`);
  await visitor.getByLabel("Password").fill(PASSWORD);
  await visitor.getByRole("button", { name: "Create account" }).click();

  // On to build a character for the troupe, chosen already.
  await expect(visitor).toHaveURL(new RegExp(`/characters\\?troupe=${troupes[found]}$`));
  await expect(visitor.getByText(`Your troupe: ${found}`)).toBeVisible();
  await expect(visitor.getByLabel("Which troupe will you play in?")).toHaveValue(troupes[found]!);
  await visitor.getByLabel("Name").fill(`Fenwatch Newcomer ${run}`);
  await visitor.getByRole("button", { name: "Create" }).click();
  await expect(visitor).toHaveURL(/\/characters\/[0-9a-f-]+\/create/);
});

test("storytellers set the troupe's time zone, games are entered in it, and the directory finds a 9:30 pm Friday game in New York under Friday whatever the lead's zone (#1211)", async ({ browser }) => {
  const custodian = await person(browser, "tzone-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tzone-lead");
  const assistant = await person(browser, "tzone-assistant");
  const headers = { "X-Horatio": "1" };
  const name = `Eastern Hours ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = ((await made.json()) as { id: string }).id;
  const l = lead.page;
  for (const [path, data] of [
    [`/api/troupes/${troupeId}/staff`, { handle: assistant.handle, role: "assistant_storyteller" }],
    [`/api/troupes/${troupeId}/profile/public`, { public: true }],
  ] as const) {
    const done = await l.request.put(path, { headers, data });
    expect(done.status(), await done.text()).toBe(200);
  }
  // The lead lives in Tokyo, where an evening game in New York is the next day.
  const zoned = await l.request.patch("/api/preferences", { headers, data: { time_zone: "Asia/Tokyo" } });
  expect(zoned.status(), await zoned.text()).toBe(200);

  // None of its own yet: the lead's.
  await settingsPart(l, troupeId, "time-zone");
  const card = l.getByRole("region", { name: "Time zone" });
  await expect(card).toContainText(/Now: Asia\/Tokyo \(.+\) \(the lead storyteller's\)/);
  await card.getByRole("combobox", { name: "Time zone" }).fill("America/New_York");
  await expect(l.getByText("Time zone: America/New York")).toBeVisible();
  await expect(card).toContainText(/Now: America\/New York \(E[SD]T\)/);
  await expect(card).not.toContainText("(the lead storyteller's)");
  await expect(card.getByRole("button", { name: "Use the lead storyteller's" })).toBeVisible();

  // The assistant storyteller reads it.
  await settingsPart(assistant.page, troupeId, "time-zone");
  const read = assistant.page.getByRole("region", { name: "Time zone" });
  await expect(read).toContainText("The troupe's storytellers change this.");
  await expect(read).toContainText("Now: America/New York");
  await expect(read.getByRole("combobox")).toHaveCount(0);

  // The schedule form says the times are the troupe's, and takes 9:30 pm on a Friday a few days off there.
  const friday = new Date();
  friday.setUTCDate(friday.getUTCDate() + 2 + ((5 - ((friday.getUTCDay() + 2) % 7) + 7) % 7));
  const day = friday.toISOString().slice(0, 10);
  await troupeTab(l, "Overview");
  const profile = l.getByRole("region", { name: "Profile" });
  await profile.getByRole("button", { name: "Edit profile" }).click();
  await profile.getByRole("button", { name: "Edit when it plays" }).click();
  await expect(l.getByText(/^Times are in America\/New York \(E[SD]T\), the troupe's time zone\./)).toBeVisible();
  await l.getByLabel("Game starts").fill(`${day}T21:30`);
  await expect(l.getByText(/^Fri \d+ \w+( \d{4})?, 9:30 pm E[SD]T$/)).toBeVisible();
  await l.getByRole("button", { name: "Add game" }).click();
  await expect(l.getByRole("list", { name: "Upcoming games to edit" }).getByText(/^Fri .*, 9:30 pm to Sat .*, 2:30 am E[SD]T$/)).toBeVisible();

  // Signed out, the directory finds it under Friday, not Saturday, and says when on the troupe's clock.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto(`/find-a-troupe?name=${encodeURIComponent(name)}&day=friday`);
  const results = visitor.getByRole("list", { name: "Troupes found" });
  await expect(results.getByRole("link", { name: new RegExp(name) })).toContainText(/Next game: Fri \d+ \w+( \d{4})?, 9:30 pm E[SD]T/);
  await visitor.goto(`/find-a-troupe?name=${encodeURIComponent(name)}&day=saturday`);
  await expect(visitor.getByText("No troupe matches that search. Try fewer filters.")).toBeVisible();
});

test("a troupe's Overview switches it public at once, shows its XP range, and Waiting on you leads to the work", async ({ browser }) => {
  const custodian = await person(browser, "tidy-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tidy-lead");
  const player = await person(browser, "tidy-player");
  const visitor = await (await browser.newContext()).newPage();
  const troupeName = `Court of Thresholds ${run}`;
  await custodian.page.reload();
  await openNewTroupe(custodian.page);
  await custodian.page.getByLabel("Name").fill(troupeName);
  await custodian.page.getByLabel("Lead storyteller").fill(lead.handle);
  await custodian.page.getByRole("button", { name: "Create troupe" }).click();
  await expect(custodian.page.getByRole("link", { name: troupeName })).toBeVisible();
  await backstoryOptional(custodian.page, troupeName);

  // The Overview, for the lead: nothing is waiting yet.
  const l = lead.page;
  await (await topBar(l)).getByRole("link", { name: "Troupes" }).click();
  await l.getByRole("link", { name: troupeName }).click();
  await expect(l.getByRole("heading", { name: troupeName })).toBeVisible();
  const troupeId = new URL(l.url()).pathname.split("/")[2]!;
  const waiting = l.locator("section").filter({ has: l.getByRole("heading", { name: "Waiting on you" }) });
  await expect(waiting.getByText("Nothing waiting.")).toBeVisible();

  // The Public switch, under Edit profile, saves as soon as it is changed.
  const editProfile = l.getByRole("region", { name: "Profile" }).getByRole("button", { name: "Edit profile" });
  await editProfile.click();
  const publicSwitch = l.getByRole("switch", { name: "Public" });
  await expect(publicSwitch).not.toBeChecked();
  await expect(l.getByText("Signed-in only")).toBeVisible();
  await visitor.goto(`/t/${troupeId}`);
  await expect(visitor.getByText(/only for people signed in, or there is no such troupe/)).toBeVisible();
  await publicSwitch.click();
  await expect(publicSwitch).toBeChecked();
  await expect(l.getByText("Public: anyone can see this profile, even people not signed in")).toBeVisible();
  await expect(l.getByText(`/t/${troupeId}`)).toBeVisible();
  await l.reload();
  await editProfile.click();
  await expect(l.getByRole("switch", { name: "Public" })).toBeChecked();
  await visitor.reload();
  await expect(visitor.getByRole("heading", { name: troupeName })).toBeVisible();
  // The lead's name and description are under Edit profile too (#912), and archiving under its own heading.
  await l.getByRole("button", { name: "Edit name and description" }).click();
  await l.getByLabel("Description").fill("A court that meets where the roads cross.");
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByRole("button", { name: "Edit name and description" })).toBeVisible();
  await l.getByRole("button", { name: "Done" }).click();
  await expect(l.getByRole("region", { name: "Profile" }).getByText("A court that meets where the roads cross.")).toBeVisible();
  await expect(l.getByRole("heading", { name: "Archive the troupe" })).toBeVisible();
  await l.screenshot(shots("troupe-profile-tab"));

  // The XP floor and ceiling are to read here, with Award XP beside them, and no settings.
  await expect(l.locator("main").getByRole("link", { name: "Award XP", exact: true })).toBeVisible();
  await expect(l.getByText("Player characters from any sect may join.")).toBeVisible();
  await expect(l.getByRole("checkbox")).toHaveCount(0);
  await expect(l.getByLabel("Floor", { exact: true })).toHaveCount(0);
  // The lead sets them by hand in Settings, each in its part (#908): who may join, and XP.
  await l.getByRole("link", { name: "Edit in Settings" }).first().click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings/joining$`));
  await expect(l.getByRole("group", { name: "Who may join", exact: true })).toBeVisible();
  await l.goBack();
  await l.getByRole("link", { name: "Edit in Settings" }).last().click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/settings/xp$`));
  await expect(l.getByRole("group", { name: "XP", exact: true })).toBeVisible();
  const range = l.getByRole("region", { name: "XP floor and ceiling" });
  await range.getByLabel("Floor", { exact: true }).fill("60");
  await range.getByLabel("Ceiling", { exact: true }).fill("75");
  await range.getByLabel("Why", { exact: true }).fill("Chronicle began in 2021");
  await range.getByRole("button", { name: "Save", exact: true }).click();
  await expect(range.getByText("30 starting + 30 set by hand")).toBeVisible();
  await expect(range.getByText("30 starting + 45 set by hand")).toBeVisible();
  // Starting points leads there for them, and the log on About has the change.
  await l.goto(`/troupes/${troupeId}/house-rules/starting`);
  await expect(l.getByRole("heading", { name: "XP floor and ceiling" })).toHaveCount(0);
  await expect(l.locator("main").getByRole("link", { name: "XP", exact: true }).last()).toHaveAttribute("href", `/troupes/${troupeId}/settings/xp`);
  await l.goto(`/troupes/${troupeId}`);
  await expect(waiting).toBeVisible();
  await expect(l.getByRole("heading", { name: "Latest in the log" })).toBeVisible();

  // A player asks for the troupe to be their character's home: an approval waits.
  const p = player.page;
  const send = async (method: "POST" | "PUT", url: string, data: object) => {
    const response = await p.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  const { id } = await send("POST", "/api/characters", { splat: "vampire", name: "Hollis" });
  await send("PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
  const build: Record<string, [string, number][]> = {
    attributes: [["Physical", 7], ["Social", 5], ["Mental", 3]],
    focus_physicals: [["Strength", 1]],
    focus_mentals: [["Wits", 1]],
    focus_socials: [["Charisma", 1]],
    skills: [["Brawl", 4], ["Dodge", 3], ["Athletics", 3], ["Awareness", 2], ["Empathy", 2], ["Firearms", 2], ["Investigation", 1], ["Leadership", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, picks] of Object.entries(build))
    await send("PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: picks.map(([name, rating]) => ({ name, rating })) });
  await send("POST", `/api/characters/${id}/creation/complete`, {});
  await send("POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });

  // Waiting on you says so, and its line goes straight to Approvals.
  await l.reload();
  const approvals = waiting.getByRole("link", { name: /Approvals waiting/ });
  await expect(approvals).toContainText("1");
  await l.screenshot(shots("troupe-about"));
  await approvals.click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals$`));
  await expect(l.getByText("Hollis").first()).toBeVisible();
  // Approvals comes first of the Characters tabs, with its count; the group itself opens on the roster.
  const characterTabs = await groupTabs(l, "Characters");
  await expect(characterTabs.getByRole("link").first()).toHaveText(/^Approvals/);
  await expect(characterTabs.getByRole("link", { name: /Approvals/ }).getByLabel("1 waiting")).toBeVisible();
  // The characters' records are among them too (#1048), and the troupe's locations are with its downtimes.
  await expect(characterTabs.getByRole("link")).toHaveText([/^Approvals/, "Roster", "Players", "Lines and veils", "Equipment", "Shared backgrounds"]);
  if (isPhone(l)) {
    const between = l.getByRole("dialog", { name: "Troupe sections" }).getByRole("list", { name: "Between games", exact: true });
    await expect(between.getByRole("link", { name: "Locations", exact: true })).toBeVisible();
    await shutSections(l);
  } else {
    const sections = l.getByRole("navigation", { name: "Troupe sections" });
    await sections.getByRole("link", { name: /^Characters/ }).click();
    await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/roster$`));
    await sections.getByRole("link", { name: "Between games", exact: true }).click();
    await expect(l.getByRole("navigation", { name: "Between games", exact: true }).getByRole("link", { name: "Locations", exact: true })).toBeVisible();
  }
  // On Hollis's sheet the lead is told whose it is and as whom they look, with the way back.
  await l.goto(`/characters/${id}`);
  const viewing = l.getByLabel("Viewing as staff");
  await expect(viewing).toContainText("Viewing as lead storyteller");
  await expect(viewing.getByRole("link", { name: "tidy-player" })).toBeVisible();
  await viewing.getByRole("link", { name: `← ${troupeName}` }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/approvals$`));

  // The player sees About without the box, and the XP range only to read.
  await p.goto(`/troupes/${troupeId}`);
  await expect(p.getByRole("heading", { name: "XP floor and ceiling" })).toBeVisible();
  await expect(p.getByText("60 XP", { exact: true })).toBeVisible();
  await expect(p.getByRole("heading", { name: "Waiting on you" })).toHaveCount(0);
  await expect(p.getByLabel("Floor", { exact: true })).toHaveCount(0);
});

test("Waiting on you shows the open cycle, a quest request and a backstory waiting, the tabs count them, and staff land on their troupes", async ({ browser }) => {
  const custodian = await person(browser, "bells-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "bells-lead");
  const player = await person(browser, "bells-player");
  const troupeName = `Court of Waiting Bells ${run}`;
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const { id: troupeId } = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  const l = lead.page;
  await send(l, "PUT", `/api/troupes/${troupeId}/backstory-settings`, { mode: "free", required: false });
  await send(l, "PUT", `/api/troupes/${troupeId}/quest-settings`, { enabled: true, requests_per_cycle: 1 });

  // The player's character joins, writes a backstory and asks for a quest; a cycle is open.
  const p = player.page;
  const id = await builtVampire(p, "Ilka Varga", "Toreador", {
    ...ATTRIBUTES_AND_FOCUSES,
    backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]],
    disciplines: [["Auspex", 2], ["Celerity", 1], ["Presence", 1]],
  });
  const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupeId });
  await send(l, "POST", `/api/approvals/${asked.id}/approve`);
  await send(p, "PUT", `/api/characters/${id}/backstory`, { text: "Embraced in a Budapest opera house, 1911.", version: 0 });
  const now = Date.now();
  const cycle = await send(l, "POST", `/api/troupes/${troupeId}/cycles`, {
    name: "November downtime",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(l, "POST", `/api/cycles/${cycle.id}/open`);
  await send(p, "POST", `/api/characters/${id}/quest-requests`, { objective: "Find the lost libretto", reason: "Her sire wrote it", companions: "" });

  // The lead, with no characters of their own, lands on their troupes, with what waits on them in each.
  await l.goto("/");
  await expect(l.getByRole("heading", { name: "Your troupes" })).toBeVisible();
  const home = l.getByRole("list", { name: `Waiting on you in ${troupeName}` });
  await expect(home.getByRole("link", { name: /^November downtime: 0 of 1 submitted · Due [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}( \d{4})?, \d{1,2}:\d{2} [ap]m \(in \d+ days\)$/ })).toBeVisible();
  await expect(l.getByRole("link", { name: troupeName }).getByLabel("2 waiting")).toBeVisible();
  await expect(l.getByText("No characters of your own yet.", { exact: false })).toBeVisible();
  await l.screenshot(shots("characters-home-staff"));

  // About's Waiting on you: the open cycle first, then the backstory and the quest request.
  await l.getByRole("link", { name: troupeName }).click();
  const waiting = l.getByRole("list", { name: "Waiting on you" });
  await expect(waiting.getByRole("link")).toHaveText([/^November downtime: 0 of 1 submitted · Due [A-Z][a-z]{2} \d{1,2} [A-Z][a-z]{2}( \d{4})?, \d{1,2}:\d{2} [ap]m \(in \d+ days\)$/, /^Backstories to read\s*1$/, /^Quest requests to answer\s*1$/]);
  await l.screenshot(shots("troupe-about-waiting"));
  // The tabs count the same: the backstory on the roster, the request on Quests.
  // On a phone, the section picker's sheet has each on its tab.
  const sections = l.getByRole("navigation", { name: "Troupe sections" });
  if (isPhone(l)) {
    await expectTabCount(l, "Quests", "1 waiting");
    await expectTabCount(l, "Roster", "1 waiting");
    await troupeTab(l, "Roster");
  } else {
    await expect(sections.getByRole("link", { name: /^Characters/ }).getByLabel("1 waiting")).toBeVisible();
    await expect(sections.getByRole("link", { name: /^Between games/ }).getByLabel("1 waiting")).toBeVisible();
    await sections.getByRole("link", { name: /^Characters/ }).click();
    const characterTabs = l.getByRole("navigation", { name: "Characters", exact: true });
    await expect(characterTabs.getByRole("link", { name: /^Roster/ }).getByLabel("1 waiting")).toBeVisible();
  }
  // The roster marks the backstory, and the mark opens it.
  await l.getByRole("link", { name: "Backstory to read" }).filter({ visible: true }).click();
  await expect(l).toHaveURL(new RegExp(`/characters/${id}/backstory`));
  await expect(l.getByText("Embraced in a Budapest opera house, 1911.")).toBeVisible();
  // The line itself goes straight to the backstory too, and the quest request's to Quests.
  await l.goto(`/troupes/${troupeId}`);
  await waiting.getByRole("link", { name: /^Quest requests to answer/ }).click();
  await expect(l).toHaveURL(new RegExp(`/troupes/${troupeId}/quests$`));
  await expect(l.getByText("Find the lost libretto")).toBeVisible();
  if (isPhone(l)) await expectTabCount(l, "Quests", "1 waiting");
  else await expect(sections.getByRole("link", { name: /^Between games/ }).getByLabel("1 waiting")).toBeVisible();
});
