import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, run, shots, person, makeCustodian, builtVampire, ATTRIBUTES_AND_FOCUSES } from "./support";

/** Quests, the troupe's locations, and shared backgrounds. */

closeContextsAfterEach();

test("quests: a player asks for one, staff build it Complex 2 and send it, it is shared and joined, Elite 6 is spent, and it is completed with its tale", async ({ browser }) => {
  // Four people, two characters, and the whole of a quest from request to tale.
  test.slow();
  const custodian = await person(browser, "quest-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "quest-lead");
  const player = await person(browser, "quest-player");
  const second = await person(browser, "quest-second");
  const headers = { "X-Horatio": "1" };
  const made = await custodian.page.request.post("/api/troupes", { headers, data: { name: `Court of Quests ${run}`, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId = (await made.json()).id;
  const home = async (p: Page, id: string) => {
    const asked = await p.request.post(`/api/characters/${id}/home-troupe`, { headers, data: { troupe_id: troupeId } });
    expect(asked.status(), await asked.text()).toBe(201);
    const approved = await lead.page.request.post(`/api/approvals/${(await asked.json()).id}/approve`, { headers, data: {} });
    expect(approved.status(), await approved.text()).toBe(200);
  };
  const disciplines: [string, number][] = [["Celerity", 2], ["Potence", 1], ["Presence", 1]];
  // Agnes has Medicine 3; Bram has Elite 5 with High Society, enough for an Elite 6 action.
  const agnes = await builtVampire(player.page, "Agnes", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]], disciplines }, [
    ["skills", "Medicine", 3],
  ]);
  const bram = await builtVampire(second.page, "Bram", "Brujah", { ...ATTRIBUTES_AND_FOCUSES, backgrounds: [["Influences: The Elite", 3], ["Herd", 2], ["Generation", 1]], disciplines }, [
    ["backgrounds", "Influences: The Elite", 5],
    ["influence_elite_specializations", "High Society", 1],
  ]);
  await home(player.page, agnes);
  await home(second.page, bram);

  // Quests are off: Agnes's player sees no Quests tab. The lead turns them on, one request a cycle.
  const p = player.page;
  await p.goto(`/characters/${agnes}`);
  await expect(p.locator("main").getByRole("link", { name: "Results", exact: true })).toBeVisible();
  await expect(p.locator("main").getByRole("link", { name: "Quests", exact: true })).toHaveCount(0);
  const l = lead.page;
  await l.goto(`/troupes/${troupeId}/rules/quests`);
  await l.getByRole("button", { name: "Change quest settings" }).click();
  await l.getByLabel("Run quests in this troupe").check();
  await l.getByLabel("Requests per character per cycle").fill("1");
  await l.getByRole("button", { name: "Save" }).click();
  await expect(l.getByText("On: 1 request per character each downtime cycle.")).toBeVisible();

  // The player asks for a quest; a second is refused with the reason.
  await p.reload();
  await p.locator("main").getByRole("link", { name: "Quests", exact: true }).click();
  await p.getByLabel("What do you want to achieve?").fill("Find Miles' journal");
  await p.getByLabel("Why (optional)").fill("It names his sire");
  await p.getByRole("button", { name: "Ask for this quest" }).click();
  const request = p.getByRole("listitem", { name: "Quest request" });
  await expect(request.getByText("Waiting")).toBeVisible();
  await expect(p.getByText("Agnes has made 1 of 1 quest request until the next downtime cycle.")).toBeVisible();
  await expect(p.getByRole("button", { name: "Ask for this quest" })).toHaveCount(0);

  // The lead's bell has it as a task; the queue shows it as new, and the lead takes it on.
  await l.reload();
  await l.getByRole("button", { name: "Notifications, 1 waiting" }).click();
  await l.getByRole("button", { name: /Agnes asks for a quest: Find Miles' journal/ }).click();
  const card = l.getByRole("listitem", { name: "Request from Agnes" });
  await expect(card.getByText("New")).toBeVisible();
  await expect(l.getByRole("link", { name: /Quests/ }).getByLabel("1 waiting")).toBeVisible();
  await card.getByLabel("Assign Agnes's request to").selectOption({ label: "quest-lead" });
  await expect(card.getByText("Assigned to quest-lead")).toBeVisible();
  await p.reload();
  await expect(request.getByText("Being worked on")).toBeVisible();

  // Built from the request as Complex 2, with the book's numbers as a guide.
  await card.getByRole("button", { name: "Build a quest" }).click();
  await l.getByLabel("Quest name").fill("The Lost Journal");
  await l.getByLabel("Category").selectOption("complex");
  await l.getByLabel("Difficulty").selectOption("2");
  await expect(l.getByText("The book gives this 4 requirements and 2 scenarios.", { exact: false })).toBeVisible();
  await l.getByRole("button", { name: "Build the quest" }).click();
  await expect(l.getByRole("heading", { name: "The Lost Journal" })).toBeVisible();
  await expect(l.getByText("Complex 2 · Leader: Agnes", { exact: false })).toBeVisible();

  // Four requirements: "Medicine 3 or Science (Biology)", "Expend Elite 6 (High Society)", an aspect and words.
  const builder = l.getByRole("form", { name: "New requirement" });
  const alternative = (n: number) => builder.getByRole("group", { name: `Alternative ${n}` });
  await alternative(1).getByLabel("Name").fill("Medicine");
  await alternative(1).getByLabel("Rating").fill("3");
  await builder.getByRole("button", { name: "Add an alternative" }).click();
  await alternative(2).getByLabel("Name").fill("Science");
  await alternative(2).getByLabel("Specialisation").fill("Biology");
  await builder.getByRole("button", { name: "Add requirement" }).click();
  const requirement = (n: number) => l.getByRole("listitem", { name: `Requirement ${n}` });
  await expect(requirement(1).getByText("Medicine 3 or Science (Biology)", { exact: true })).toBeVisible();
  await alternative(1).getByLabel("Kind").selectOption({ label: "Expend influence" });
  await alternative(1).getByLabel("Level").fill("6");
  await alternative(1).getByLabel("Area").fill("High Society");
  await builder.getByRole("button", { name: "Add requirement" }).click();
  await expect(requirement(2).getByText("Expend Elite 6 (High Society)", { exact: true })).toBeVisible();
  await alternative(1).getByLabel("Kind").selectOption({ label: "A clan, bloodline or sect" });
  await alternative(1).getByLabel("Name").fill("Brujah");
  await builder.getByRole("button", { name: "Add requirement" }).click();
  await expect(requirement(3).getByText("Brujah (clan)", { exact: true })).toBeVisible();
  await alternative(1).getByLabel("Kind").selectOption({ label: "Something else, in words" });
  await alternative(1).getByLabel("Text").fill("Access to Miles' journal");
  await builder.getByRole("button", { name: "Add requirement" }).click();
  await expect(requirement(4).getByText("Access to Miles' journal", { exact: true })).toBeVisible();
  // Checked against the party's sheets: Agnes has Medicine 3, but no Elite.
  await expect(requirement(1).getByText("Medicine 3: Agnes meets it now")).toBeVisible();
  await expect(requirement(2).getByText("Expend Elite 6 (High Society): no one in the party meets it now")).toBeVisible();

  // Its two scenarios' text, written ahead; then the requirements are sent.
  await l.getByRole("button", { name: "Edit scenarios" }).click();
  await l.getByRole("group", { name: "Scenario 1" }).getByLabel("Success text").fill("You find the cellar beneath the chantry.");
  await l.getByRole("group", { name: "Scenario 2" }).getByLabel("Success text").fill("The journal is yours.");
  await l.getByRole("button", { name: "Save scenarios" }).click();
  await l.getByRole("button", { name: "Send requirements" }).click();
  await expect(l.getByText("Under way")).toBeVisible();
  await l.screenshot(shots("quest-staff"));

  // The player is told, sees the requirements, and shares the quest with Bram.
  await p.reload();
  await p.getByRole("button", { name: /^Notifications, \d+ waiting$/ }).click();
  await p.getByRole("button", { name: /The quest The Lost Journal for Agnes: its requirements are here/ }).click();
  await expect(p.getByRole("heading", { name: "The Lost Journal" })).toBeVisible();
  await expect(p.getByText("Expend Elite 6 (High Society)")).toBeVisible();
  await p.getByLabel("Share with").selectOption({ label: "Bram" });
  await p.getByRole("button", { name: "Share", exact: true }).click();

  // Bram's player sees it shared, and joins.
  const s = second.page;
  await s.goto(`/characters/${bram}`);
  await s.locator("main").getByRole("link", { name: "Quests", exact: true }).click();
  await s.getByRole("link", { name: "The Lost Journal" }).click();
  await expect(s.getByText("Shared with you", { exact: false })).toBeVisible();
  await s.getByRole("button", { name: "Join this quest" }).click();
  await expect(s.getByText("The party: Agnes, Bram")).toBeVisible();

  // The lead marks Expend Elite 6 met by Bram: it goes in the influence log.
  await l.reload();
  await expect(requirement(2).getByText("Expend Elite 6 (High Society): Bram meets it now")).toBeVisible();
  await requirement(2).getByLabel("Met by").selectOption({ label: "Bram" });
  await requirement(2).getByRole("button", { name: "Mark met" }).click();
  await expect(requirement(2).getByText("Met by Bram (logged as E1).", { exact: false })).toBeVisible();
  await l.goto(`/troupes/${troupeId}/influence`);
  await expect(l.getByRole("listitem", { name: "Entry E1" }).getByText("For the quest The Lost Journal")).toBeVisible();

  // Scenario 1's result, then scenario 2's: the quest is completed.
  await l.goBack();
  await l.getByRole("button", { name: "Send scenario 1's result" }).click();
  await expect(l.getByRole("listitem", { name: "Scenario 1" }).getByText("Scenario 1: passed")).toBeVisible();
  await l.getByRole("button", { name: "Send scenario 2's result" }).click();
  await expect(l.getByText("Completed", { exact: true })).toBeVisible();

  // The leader's player reads the results and tells the tale; the lead approves it.
  await p.reload();
  await expect(p.getByText("The journal is yours.")).toBeVisible();
  await expect(p.getByText(/Completed on .*, by Agnes, Bram\./)).toBeVisible();
  await p.getByLabel("The tale").fill("We went by night, and Bram called in a favour from the gala.");
  await p.getByRole("button", { name: "Save the tale" }).click();
  await expect(p.getByText("Waiting for approval")).toBeVisible();
  await l.reload();
  await expect(l.getByLabel("The tale")).toHaveValue("We went by night, and Bram called in a favour from the gala.");
  await l.getByRole("button", { name: "Approve the tale" }).click();
  await expect(l.getByText("Approved", { exact: true })).toBeVisible();
  await s.reload();
  await expect(s.getByText("We went by night, and Bram called in a favour from the gala.")).toBeVisible();
  await expect(s.getByText("Approved", { exact: true })).toBeVisible();
  await s.screenshot(shots("quest-player"));
});

test("quests in downtime: a Quest action joins a Downtime Only quest, one result answers both members, and it goes out with the delivery", async ({ browser }) => {
  test.slow();
  const custodian = await person(browser, "qdt-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "qdt-lead");
  const leader = await person(browser, "qdt-leader");
  const joiner = await person(browser, "qdt-joiner");
  const idler = await person(browser, "qdt-idler");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Downtime Questers ${run}`, lead_handle: lead.handle });
  const build = async (page: Page, name: string) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const agnes = await build(leader.page, "Agnes");
  const bram = await build(joiner.page, "Bram");
  const cara = await build(idler.page, "Cara");

  // Quests on; a Complex 2 quest for Agnes, Downtime Only, sent and shared with Bram.
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/quest-settings`, { enabled: true, requests_per_cycle: 1 });
  const quest = await send(lead.page, "POST", `/api/troupes/${troupe.id}/quests`, {
    name: "The Drowned Archive",
    category: "complex",
    difficulty: 2,
    downtime_only: true,
    leader_id: agnes,
    scenarios: [{ success_text: "You find the cellar beneath the chantry." }, { success_text: "The archive is yours." }],
  });
  await send(lead.page, "POST", `/api/quests/${quest.id}/requirements`, { options: [{ kind: "text", text: "A boat at night" }] });
  await send(lead.page, "POST", `/api/quests/${quest.id}/send`);
  await send(leader.page, "POST", `/api/characters/${agnes}/quests/${quest.id}/share`, { character_ids: [bram] });
  // Cara is in the party too, but will put in no Quest action.
  await send(lead.page, "POST", `/api/quests/${quest.id}/members`, { character_ids: [cara], joined: true });

  // A new cycle's form has the Quest action, spending a general action.
  const now = Date.now();
  const cycle = await send(lead.page, "POST", `/api/troupes/${troupe.id}/cycles`, {
    name: "Flood month",
    closes_at: new Date(now + 7 * 86400e3).toISOString(),
    grace_ends_at: new Date(now + 9 * 86400e3).toISOString(),
  });
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/open`);
  const l = lead.page;
  await l.goto(`/cycles/${cycle.id}/form`);
  const form = l.locator("section").filter({ has: l.getByRole("heading", { name: "Quest action" }) });
  await expect(form.getByLabel("Spends")).toHaveValue("general");

  // Bram's player picks the quest shared with him, says what he does, and submits: he joins it.
  const b = joiner.page;
  await b.goto(`/characters/${bram}/downtime`);
  const card = b.locator("section").filter({ has: b.getByRole("heading", { name: "Quest", exact: true }) });
  await card.getByRole("button", { name: /Add an action/ }).click();
  await expect(card.getByLabel("Which quest").locator("option", { hasText: "The Drowned Archive: Complex 2 · Downtime only · scenario 1 of 2 · choosing it joins the party" })).toHaveCount(1);
  await card.getByLabel("Which quest").selectOption(quest.id);
  await card.getByLabel("Quest", { exact: true }).fill("Bram rows out to the flooded chantry.");
  await b.getByRole("button", { name: "Submit downtime" }).click();
  await expect(b.getByText("submitted", { exact: true })).toBeVisible();
  await expect(b.getByText("1 / 3")).toBeVisible();
  await b.goto(`/characters/${bram}/quests/${quest.id}`);
  await expect(b.getByText("The party: Agnes, Bram")).toBeVisible();
  await expect(b.getByText("Complex 2 · Downtime only", { exact: false })).toBeVisible();

  // Agnes puts in hers too; the cycle closes.
  const agnesForm = await (await leader.page.request.get(`/api/characters/${agnes}/downtime`)).json();
  const question = agnesForm.questions.find((q: { kind: string }) => q.kind === "quest");
  await send(leader.page, "PUT", `/api/characters/${agnes}/downtime/answers`, {
    answers: [{ question_id: question.id, body: "Agnes bribes the ferryman.", structured: { quest_id: quest.id } }],
  });
  await send(leader.page, "POST", `/api/characters/${agnes}/downtime/submit`);
  await send(lead.page, "POST", `/api/cycles/${cycle.id}/close`, { add_to_ceiling: false });

  // The lead answers beside the quest: one success, and both responses show it.
  await l.goto(`/cycles/${cycle.id}/responses`);
  const forAgnes = l.getByRole("region", { name: "Quest: The Drowned Archive" }).first();
  await expect(forAgnes.getByText("Complex 2 · Downtime only · Scenario 1 of 2")).toBeVisible();
  await expect(forAgnes.getByText("Still to meet: A boat at night")).toBeVisible();
  await expect(forAgnes.getByText("Also put in a Quest action: Bram.")).toBeVisible();
  // Nothing's Simple: Cara, in the party with no Quest action, shows as not having spent one.
  await expect(forAgnes.getByText("Not spent the action this scenario needs: Cara.", { exact: false })).toBeVisible();
  await expect(forAgnes.getByLabel("What the party is told")).toHaveValue("You find the cellar beneath the chantry.");
  await forAgnes.getByRole("button", { name: "Record scenario 1's result" }).click();
  await expect(l.getByText("Scenario 1: passed, recorded here; it goes out with this cycle's delivery.")).toHaveCount(2);
  await expect(l.getByLabel("Response to Agnes")).toHaveValue(/You find the cellar beneath the chantry\./);
  await expect(l.getByLabel("Response to Bram")).toHaveValue(/You find the cellar beneath the chantry\./);
  await l.screenshot(shots("quest-downtime-responses"));

  // Nothing reaches the party before the delivery.
  await b.reload();
  await expect(b.getByText("Scenario 1: passed")).toHaveCount(0);

  // The delivery sends it, and the quest moves on to scenario 2, still for downtime only.
  await l.goto(`/cycles/${cycle.id}`);
  await l.getByRole("button", { name: "Deliver results" }).click();
  await expect(l.getByText("Delivered 2 downtimes.", { exact: false })).toBeVisible();
  await b.reload();
  await expect(b.getByText("Scenario 1: passed")).toBeVisible();
  await b.goto(`/characters/${bram}/results`);
  await expect(b.getByText("The Drowned Archive, scenario 1: passed.", { exact: false })).toBeVisible();
  await b.screenshot(shots("quest-downtime-results"));
  // Cara, who put in no action, hears the result as the quest's news at the same delivery.
  await idler.page.goto(`/characters/${cara}/quests/${quest.id}`);
  await expect(idler.page.getByText("Scenario 1: passed")).toBeVisible();
  await l.goto(`/troupes/${troupe.id}/quests/${quest.id}`);
  await expect(l.getByText("In Flood month: Quest actions from Agnes, Bram.")).toBeVisible();
  await expect(l.getByRole("listitem", { name: "Scenario 2" }).getByText("Downtime only: its result is recorded from a Quest action", { exact: false })).toBeVisible();
  await expect(l.getByRole("button", { name: "Send scenario 2's result" })).toHaveCount(0);
});

test("a coterie's shared Haven: staff set it up, a player logs a use, and the other sharer reads it in the log", async ({ browser }) => {
  const custodian = await person(browser, "share-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "share-lead");
  const first = await person(browser, "share-first");
  const second = await person(browser, "share-second");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Shared Roof ${run}`, lead_handle: lead.handle });

  // Agnes and Bram, both at home in the troupe.
  const build = async (page: Page, name: string) => {
    const { id } = await send(page, "POST", "/api/characters", { splat: "vampire", name });
    await send(page, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
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
      await send(page, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(page, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(page, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const agnes = await build(first.page, "Agnes");
  const bram = await build(second.page, "Bram");

  // The lead sets up the coterie's Haven: Agnes puts in 2 dots, Bram 1.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Shared backgrounds" }).click();
  await l.getByRole("button", { name: "Set up a shared background" }).click();
  const setUp = l.getByRole("form", { name: "Set up a shared background" });
  await setUp.getByLabel("Name").fill("The coterie's Haven");
  await expect(setUp.getByLabel("Background")).toHaveValue("Haven");
  await setUp.getByLabel("What it gives (optional)").fill("Security, Guards");
  await setUp.getByLabel("Character 1", { exact: true }).selectOption({ label: "Agnes" });
  await setUp.getByLabel("Dots 1", { exact: true }).fill("2");
  await setUp.getByRole("button", { name: "Add a character" }).click();
  await setUp.getByLabel("Character 2", { exact: true }).selectOption({ label: "Bram" });
  await setUp.getByRole("button", { name: "Set up" }).click();
  await expect(l.getByRole("heading", { name: "The coterie's Haven" })).toBeVisible();
  await expect(l.getByText("3 of 5 dots")).toBeVisible();
  await expect(l.getByLabel("Sharing it")).toHaveText("Sharing it: Agnes 2 dots, Bram 1 dot.");
  await expect(l.getByText(/A record only: nothing logged here changes a rating/)).toBeVisible();

  // Agnes's player finds it on her page, and logs drawing on it.
  const a = first.page;
  await a.goto(`/characters/${agnes}`);
  await a.locator("main").getByRole("link", { name: "Shared backgrounds" }).click();
  await expect(a.getByRole("heading", { name: "The coterie's Haven" })).toBeVisible();
  await expect(a.getByRole("button", { name: "Log dots" })).toHaveCount(0);
  await a.getByRole("button", { name: "Log a use" }).click();
  const use = a.getByRole("form", { name: "Log a use" });
  await expect(use.getByLabel("Who drew on it")).toHaveValue(agnes);
  await use.getByLabel("What for").fill("Hiding from the hunters for the day");
  await use.getByRole("button", { name: "Log use" }).click();
  const log = a.getByRole("list", { name: "The coterie's Haven log" });
  await expect(log.getByRole("listitem").first()).toContainText("Agnes drew on it");
  await expect(log.getByRole("listitem").first()).toContainText("Hiding from the hunters for the day");
  await a.screenshot(shots("shared-background"));

  // Bram's player reads it in the same log, but cannot take Agnes's use off it.
  const b = second.page;
  await b.goto(`/characters/${bram}/shared`);
  const his = b.getByRole("list", { name: "The coterie's Haven log" });
  await expect(his.getByRole("listitem").first()).toContainText("Hiding from the hunters for the day");
  await expect(his.getByRole("listitem").first()).toContainText("logged by share-first");
  await expect(his.getByRole("listitem").first().getByRole("button", { name: "Delete" })).toHaveCount(0);

  // The lead logs Bram taking his dot out; the total follows the log.
  await l.reload();
  await expect(l.getByRole("list", { name: "The coterie's Haven log" }).getByRole("listitem").first()).toContainText("Agnes drew on it");
  await l.getByRole("button", { name: "Log dots" }).click();
  const dots = l.getByRole("form", { name: "Log dots" });
  await dots.getByLabel("Dots", { exact: true }).selectOption("Taken out");
  await dots.getByLabel("Who").selectOption({ label: "Bram (1 dot)" });
  await dots.getByLabel("Note (optional)").fill("Left the coterie");
  await dots.getByRole("button", { name: "Log dots" }).click();
  await expect(l.getByText("2 of 5 dots")).toBeVisible();
  await expect(l.getByLabel("Sharing it")).toHaveText("Sharing it: Agnes 2 dots. Took their dots out: Bram.");
});

test("the troupe's locations: a storyteller adds the Grove Arcade, is refused an eleventh quality, adds a secret negative, and a narrator never sees them", async ({ browser }) => {
  const custodian = await person(browser, "loc-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "loc-lead");
  const owner = await person(browser, "loc-owner");
  const narrator = await person(browser, "loc-narrator");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Grove Court ${run}`, lead_handle: lead.handle });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: narrator.handle, role: "narrator" });

  // Agnes, at home in the troupe, will control it.
  const { id: agnes } = await send(owner.page, "POST", "/api/characters", { splat: "vampire", name: "Agnes Grove" });
  await send(owner.page, "PUT", `/api/characters/${agnes}/traits`, { category: "clan", name: "Brujah", rating: null });
  const picks: Record<string, [string, number][]> = {
    attributes: [["Physical", 3], ["Social", 7], ["Mental", 5]],
    focus_physicals: [["Dexterity", 1]],
    focus_mentals: [["Intelligence", 1]],
    focus_socials: [["Manipulation", 1]],
    skills: [["Leadership", 4], ["Subterfuge", 3], ["Academics", 3], ["Awareness", 2], ["Empathy", 2], ["Investigation", 2], ["Dodge", 1], ["Drive", 1], ["Medicine", 1], ["Melee", 1]],
    backgrounds: [["Resources", 3], ["Haven", 2], ["Generation", 1]],
    disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
  };
  for (const [category, list] of Object.entries(picks))
    await send(owner.page, "PUT", `/api/characters/${agnes}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
  await send(owner.page, "POST", `/api/characters/${agnes}/creation/complete`);
  const asked = await send(owner.page, "POST", `/api/characters/${agnes}/home-troupe`, { troupe_id: troupe.id });
  await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);

  // The lead adds the Grove Arcade: prestige 5, with ten qualities.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("navigation", { name: "Troupe sections" }).getByRole("link", { name: "Characters", exact: true }).click();
  await l.getByRole("link", { name: "Locations", exact: true }).click();
  await expect(l.getByText("No locations yet.")).toBeVisible();
  await l.getByRole("button", { name: "Add a location" }).click();
  const add = l.getByRole("form", { name: "Add a location" });
  await add.getByLabel("Name", { exact: true }).fill("Grove Arcade");
  await add.getByLabel("Type").selectOption("prestige");
  await add.getByLabel("Rating").selectOption("5");
  for (const quality of ["Size", "Guards", "Location", "Staff", "Profitable", "Profitable", "Historic", "Fancy", "Luxury", "Haunt"])
    await add.getByLabel("Add a quality").selectOption(quality);
  await expect(add.getByText("Qualities · 10 of 10")).toBeVisible();
  await add.getByLabel("Address", { exact: true }).fill("1 Page Ave, Asheville");
  await add.getByLabel("Feeding block").fill("The Rack");
  await add.getByLabel("Influence", { exact: true }).selectOption("elite");
  await add.getByLabel("Influence area").fill("Commercial Industry");
  await add.getByLabel("Control", { exact: true }).selectOption("controlled");
  await add.getByRole("combobox", { name: "Controller" }).fill("Agnes");
  await add.getByRole("listbox", { name: "Characters" }).getByRole("option", { name: /Agnes Grove/ }).click();
  await add.getByRole("button", { name: "Add location" }).click();
  await expect(l.getByRole("heading", { name: "Grove Arcade" })).toBeVisible();
  await expect(l.getByText("Prestige 5 · 10 of 10 qualities")).toBeVisible();
  await expect(l.getByText("Commercial Industry (Elite)")).toBeVisible();

  // An eleventh quality is refused, with the reason.
  await l.getByRole("button", { name: "Edit" }).click();
  const edit = l.getByRole("form", { name: "Change Grove Arcade" });
  await edit.getByLabel("Add a quality").selectOption("Isolated");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(edit.getByRole("alert")).toHaveText(/A prestige 5 location has at most 10 qualities .*p\. 121.*this one would have 11\./);

  // Hunters watch it, kept secret from Agnes's player.
  await edit.getByRole("button", { name: "Remove Isolated" }).click();
  await edit.getByRole("button", { name: "Add a negative quality" }).click();
  await edit.getByLabel("Negative quality").selectOption("Compromised");
  await edit.getByLabel("Secret from the controller").check();
  await edit.getByLabel("Who is behind Compromised").fill("hunters");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(l.getByText("Compromised ×1", { exact: true })).toBeVisible();
  await expect(l.getByText("Secret", { exact: true })).toBeVisible();
  await expect(l.getByText(/changed Grove Arcade: negatives \+Compromised ×1, secret \(hunters\)/)).toBeVisible();
  await l.screenshot(shots("location"));

  // Back on the list, it's found by its quality.
  await l.getByRole("link", { name: "← All locations" }).click();
  await l.getByLabel("Quality").selectOption("Haunt");
  await expect(l.getByRole("list", { name: "Locations" }).getByRole("link", { name: "Grove Arcade" })).toBeVisible();
  await l.getByLabel("Quality").selectOption("Workshop");
  await expect(l.getByText("No locations match.")).toBeVisible();
  const wide = await l.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide).toBeLessThanOrEqual(0);

  // The sheet shows staff how many Agnes controls, of how many she may.
  await l.goto(`/characters/${agnes}`);
  await expect(l.getByText(/Controls 1 of 5 locations/)).toBeVisible();

  // Neither the narrator nor Agnes's player sees the list.
  const n = narrator.page;
  await n.goto(`/troupes/${troupe.id}`);
  await expect(n.getByRole("link", { name: "Locations", exact: true })).toHaveCount(0);
  expect((await n.request.get(`/api/troupes/${troupe.id}/locations`)).status()).toBe(403);
  expect((await owner.page.request.get(`/api/troupes/${troupe.id}/locations`)).status()).toBe(403);
  await owner.page.goto(`/characters/${agnes}`);
  await expect(owner.page.getByRole("heading", { name: "Agnes Grove" })).toBeVisible();
  await expect(owner.page.getByText(/Controls 1 of 5 locations/)).toHaveCount(0);
});

test("location quests: a player acquires Ruby's Bar, adds Profitable, a rival makes it Insolvent, and a repair brings the Resources back", async ({ browser }) => {
  // Three requests and their quests, from the Quests tab to the sheet.
  test.slow();
  const custodian = await person(browser, "lq-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "lq-lead");
  const owner = await person(browser, "lq-owner");
  const rival = await person(browser, "lq-rival");
  const headers = { "X-Horatio": "1" };
  const send = async (page: Page, method: "POST" | "PUT", url: string, data: object = {}) => {
    const response = await page.request.fetch(url, { method, headers, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  await custodian.page.reload();
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Ruby Court ${run}`, lead_handle: lead.handle });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/quest-settings`, { enabled: true, requests_per_cycle: 5 });

  // Agnes has Elite 3, for the repair; Bram is her rival. Both are at home in the troupe.
  const vampire = async (p: Page, name: string, backgrounds: [string, number][]) => {
    const { id } = await send(p, "POST", "/api/characters", { splat: "vampire", name });
    await send(p, "PUT", `/api/characters/${id}/traits`, { category: "clan", name: "Brujah", rating: null });
    const picks: Record<string, [string, number][]> = {
      attributes: [["Physical", 3], ["Social", 7], ["Mental", 5]],
      focus_physicals: [["Dexterity", 1]],
      focus_mentals: [["Intelligence", 1]],
      focus_socials: [["Manipulation", 1]],
      skills: [["Leadership", 4], ["Subterfuge", 3], ["Academics", 3], ["Awareness", 2], ["Empathy", 2], ["Investigation", 2], ["Dodge", 1], ["Drive", 1], ["Medicine", 1], ["Melee", 1]],
      backgrounds,
      disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]],
    };
    for (const [category, list] of Object.entries(picks))
      await send(p, "PUT", `/api/characters/${id}/creation/categories/${category}`, { picks: list.map(([n, rating]) => ({ name: n, rating })) });
    await send(p, "POST", `/api/characters/${id}/creation/complete`);
    const asked = await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });
    await send(lead.page, "POST", `/api/approvals/${asked.id}/approve`);
    return id as string;
  };
  const agnes = await vampire(owner.page, "Agnes Ruby", [["Influences: The Elite", 3], ["Haven", 2], ["Generation", 1]]);
  const bram = await vampire(rival.page, "Bram Rival", [["Resources", 3], ["Haven", 2], ["Generation", 1]]);

  const o = owner.page;
  const l = lead.page;
  const ask = async (p: Page, characterId: string, kind: string, fill: () => Promise<void>) => {
    await p.goto(`/characters/${characterId}/quests`);
    await p.getByLabel("What kind of request").selectOption({ label: kind });
    await fill();
    await p.getByRole("button", { name: "Ask for this quest" }).click();
  };
  // Staff build the quest from a request, send it, and pass its one scenario.
  const buildAndComplete = async (from: string) => {
    await l.goto(`/troupes/${troupe.id}/quests`);
    await l.getByRole("listitem", { name: `Request from ${from}` }).getByRole("button", { name: "Build a location quest" }).click();
    const builder = l.getByRole("form", { name: "Build a location quest" });
    await expect(builder.getByLabel("Category")).toHaveValue("simple");
    await builder.getByRole("button", { name: "Build the quest" }).click();
    await l.getByRole("button", { name: "Send requirements" }).click();
    await expect(l.getByText("Under way")).toBeVisible();
    await l.getByRole("button", { name: "Send scenario 1's result" }).click();
    await expect(l.getByText("Completed", { exact: true })).toBeVisible();
  };

  // Acquire: Agnes's player asks for Ruby's Bar, 12 Main St.
  await ask(o, agnes, "Acquire a location", async () => {
    await o.getByLabel("Name of the place").fill("Ruby's Bar");
    await o.getByLabel("Address").fill("12 Main St");
  });
  await expect(o.getByText("Acquire Ruby's Bar, 12 Main St")).toBeVisible();

  // The lead makes it a new standard 2 with a Hangout, and builds a Simple 2 from it.
  await l.goto(`/troupes/${troupe.id}/quests`);
  const request = l.getByRole("listitem", { name: "Request from Agnes Ruby" });
  const match = request.getByRole("group", { name: "Match to a location" });
  await match.getByLabel("Or a new standard location, rated").selectOption("2");
  await match.getByLabel("With the quality").selectOption("Hangout");
  await match.getByRole("button", { name: "Make Ruby's Bar a new location" }).click();
  await expect(request.getByRole("link", { name: "Ruby's Bar" })).toBeVisible();
  await request.getByRole("button", { name: "Build a location quest" }).click();
  const builder = l.getByRole("form", { name: "Build a location quest" });
  await expect(builder.getByLabel("Difficulty")).toHaveValue("2");
  await expect(builder.getByText("From Ruby's Bar: Rating 2.")).toBeVisible();
  await expect(builder.getByText("On success, control passes to its leader.")).toBeVisible();
  await expect(builder.getByLabel(/Empathy 2 \(Hangout\)/)).toBeChecked();
  await builder.getByRole("button", { name: "Build the quest" }).click();
  await expect(l.getByRole("heading", { name: "Acquire Ruby's Bar" })).toBeVisible();
  await expect(l.getByText("Simple 2 · Leader: Agnes Ruby", { exact: false })).toBeVisible();
  await expect(l.getByText("changes: control passes to its leader.", { exact: false })).toBeVisible();
  await l.getByRole("button", { name: "Send requirements" }).click();
  await l.getByRole("button", { name: "Send scenario 1's result" }).click();
  await expect(l.getByText("Completed", { exact: true })).toBeVisible();

  // Agnes controls it now: her player sees its name on the sheet, and its Hangout's Contacts.
  await o.goto(`/characters/${agnes}`);
  const held = o.getByRole("list", { name: "Locations held" });
  await expect(held.getByText("Ruby's Bar", { exact: true })).toBeVisible();
  await expect(held.getByText("Contacts 1, from Ruby's Bar (Hangout)")).toBeVisible();

  // Add a quality: Profitable, by a Simple quest; the bar is rated 3, and gives Resources 1.
  await ask(o, agnes, "Add a quality to one of your locations", async () => {
    await o.getByLabel("Which of your locations").selectOption({ label: "Ruby's Bar" });
    await o.getByLabel("The quality you want").selectOption("Profitable");
  });
  await expect(o.getByText("Add Profitable to Ruby's Bar")).toBeVisible();
  await buildAndComplete("Agnes Ruby");
  await l.getByRole("link", { name: "Ruby's Bar" }).click();
  await expect(l.getByText(/^Standard 3/)).toBeVisible();
  await o.goto(`/characters/${agnes}`);
  await expect(held.getByText("Resources 1, from Ruby's Bar (Profitable)", { exact: true })).toBeVisible();

  // Undermine: Bram's player wants it Insolvent; the lead matches it to the record.
  const r = rival.page;
  await ask(r, bram, "Undermine a location", async () => {
    await r.getByLabel("Name of the place").fill("Ruby's Bar");
    await r.getByLabel("Address").fill("12 Main St");
    await r.getByLabel("What you want to do to it").selectOption({ label: "Make it Insolvent" });
  });
  await expect(r.getByText("Undermine Ruby's Bar, 12 Main St: Insolvent")).toBeVisible();
  await l.goto(`/troupes/${troupe.id}/quests`);
  const undermine = l.getByRole("listitem", { name: "Request from Bram Rival" });
  await undermine.getByLabel("The troupe's record of it").selectOption({ label: "Ruby's Bar" });
  await undermine.getByRole("button", { name: "Match", exact: true }).click();
  await expect(undermine.getByRole("link", { name: "Ruby's Bar" })).toBeVisible();
  await buildAndComplete("Bram Rival");

  // Agnes's Resources from it are switched off, without saying why.
  await o.goto(`/characters/${agnes}`);
  await expect(held.getByText("Resources 1, from Ruby's Bar (Profitable): not available this cycle", { exact: true })).toBeVisible();
  await expect(held.getByText(/Insolvent/)).toHaveCount(0);
  await o.screenshot(shots("location-effects"));

  // Repair: her player asks, and the lead removes Insolvent for an Elite 3 action of hers.
  await ask(o, agnes, "Repair one of your locations", async () => {
    await o.getByLabel("Which of your locations").selectOption({ label: "Ruby's Bar" });
  });
  await l.goto(`/troupes/${troupe.id}/quests`);
  const repair = l.getByRole("listitem", { name: "Request from Agnes Ruby" });
  await expect(repair.getByText("Repair Ruby's Bar")).toBeVisible();
  await expect(repair.getByText("It takes Elite 3, at Ruby's Bar's rating.")).toBeVisible();
  await repair.getByRole("button", { name: "Remove one level" }).click();
  await expect(l.getByText("No quest requests here.")).toBeVisible();
  await o.goto(`/characters/${agnes}`);
  await expect(held.getByText("Resources 1, from Ruby's Bar (Profitable)", { exact: true })).toBeVisible();
  const wide = await o.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide).toBeLessThanOrEqual(0);
});
