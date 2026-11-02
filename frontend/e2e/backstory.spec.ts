import { expect, test, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, builtVampire, closeContextsAfterEach, makeCustodian, person, run, shots, characterTab } from "./support";

/** A character's backstory: written in the editor or built from the troupe's questions, and approved as part of accepting the character. */

closeContextsAfterEach();

const BRUJAH_NEONATE = {
  ...ATTRIBUTES_AND_FOCUSES,
  backgrounds: [["Fame", 3], ["Herd", 2], ["Generation", 1]] as [string, number][],
  disciplines: [["Celerity", 2], ["Potence", 1], ["Presence", 1]] as [string, number][],
};

async function send(page: Page, method: "POST" | "PUT", url: string, data: object) {
  const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

/** The backstory as the API has it, for its writer: the latest version and the draft. */
async function stored(page: Page, id: string): Promise<{ text: string; version: number; draft: { text: string; behind: boolean } | null }> {
  const response = await page.request.get(`/api/characters/${id}/backstory`);
  expect(response.status()).toBe(200);
  return response.json();
}

/** The formatted editor, as a screen reader finds it. */
const richEditor = (page: Page) => page.getByRole("textbox", { name: "Your backstory", exact: true });

test("a troupe asks its questions only: the lead loads the template and rewords one, and a neonate's player builds a backstory of a section each", async ({ browser }) => {
  const custodian = await person(browser, "quiz-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "quiz-lead");
  const player = await person(browser, "quiz-player");
  const troupeName = `Court of Questions ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  const p = player.page;
  const id = await builtVampire(p, "Wren", "Brujah", BRUJAH_NEONATE);
  await send(p, "POST", `/api/characters/${id}/home-troupe`, { troupe_id: troupe.id });

  // Free text only, as a troupe starts: the questions aren't offered.
  await p.goto(`/characters/${id}/backstory`);
  await expect(p.getByText(`${troupeName} needs it approved before accepting the character.`)).toBeVisible();
  await expect(p.getByRole("button", { name: "Write the backstory" })).toBeVisible();
  await expect(p.getByRole("button", { name: "Answer the troupe's questions" })).toHaveCount(0);

  // The lead chooses the questions only, and loads the template.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/rules/backstories`);
  await l.getByRole("button", { name: "Change backstory settings" }).click();
  await l.getByRole("radio", { name: /The questions only/ }).check();
  await l.getByRole("button", { name: "Save", exact: true }).click();
  await expect(l.getByText("The questions only:")).toBeVisible();
  await l.getByRole("button", { name: "Load the template" }).click();
  const shortForm = l.getByRole("list", { name: "Short Form questions" });
  await expect(shortForm.getByRole("listitem")).toHaveCount(24);
  await expect(shortForm.getByRole("listitem").filter({ hasText: "Tell us what it was like being a Neonate (Embraced to 50)" })).toContainText("Elder only");
  await l.screenshot(shots("backstory-questions"));

  // It rewords the sire question and gives it a short title.
  await shortForm.getByRole("button", { name: "Edit “Who was your Sire?”" }).click();
  await l.getByLabel("Question", { exact: true }).fill("Who was your Sire, and why did they choose you?");
  await l.getByLabel("Short title").fill("My sire");
  await l.getByRole("button", { name: "Save the question" }).click();
  await expect(shortForm.getByText("Who was your Sire, and why did they choose you?")).toBeVisible();
  await expect(shortForm.getByText("Heading: My sire")).toBeVisible();

  // Wren is a Neonate: the wizard shows the Short Form without the Ancilla and Elder questions.
  await p.reload();
  const wizard = p.locator("form").filter({ has: p.getByRole("button", { name: /Build the backstory from/ }) });
  await p.getByRole("button", { name: "Short Form", exact: true }).click();
  await expect(wizard.getByText("What has your life been like since your Embrace?")).toBeVisible();
  await expect(wizard.getByText("Who was your Sire, and why did they choose you?")).toBeVisible();
  await expect(wizard.getByText(/Ancilla/)).toHaveCount(0);
  await expect(wizard.getByText(/Eldering/)).toHaveCount(0);

  // Required questions first.
  await wizard.getByRole("button", { name: "Build the backstory from Short Form" }).click();
  await expect(p.getByText(/Answer every question that isn't optional first/)).toBeVisible();

  await wizard.getByPlaceholder("YYYY").fill("1971");
  const boxes = wizard.getByRole("textbox");
  const count = await boxes.count();
  for (let i = 0; i < count; i++) {
    const box = boxes.nth(i);
    if ((await box.getAttribute("placeholder")) === "YYYY") continue;
    await box.fill(`Answer ${i + 1}`);
  }
  await wizard.getByRole("radio", { name: "More Love than Loathe" }).check();
  await wizard.getByRole("radio", { name: "More Action than Intrigue" }).check();
  await wizard.getByRole("radio", { name: "Evenly Character driven Plot and Storyteller driven Plot" }).check();
  await p.screenshot(shots("backstory-wizard"));
  await wizard.getByRole("button", { name: "Build the backstory from Short Form" }).click();

  // One section each: 18 answered, with The Pitch heading those after it.
  const main = p.locator("main");
  const text = main.locator("section").filter({ has: p.getByRole("heading", { name: "Backstory", level: 2 }) });
  await expect(main.getByRole("heading", { name: "My sire", level: 4 })).toBeVisible();
  await expect(main.getByRole("heading", { name: "The Pitch", level: 3 })).toBeVisible();
  await expect(text.locator("h4")).toHaveCount(18);
  await expect(main.getByText("More Action than Intrigue")).toBeVisible();
  await p.screenshot(shots("backstory-built"));

  // The player then edits it freely in the formatted editor, where the marks around the built sections show as
  // dividers. Their own words after the sections stay when they answer again.
  await p.getByRole("button", { name: "Edit the backstory" }).click();
  const editor = richEditor(p);
  await expect(editor.getByText("From the troupe's questions")).toBeVisible();
  await expect(editor.getByText("End of the troupe's questions")).toBeVisible();
  await expect(editor.getByRole("heading", { name: "My sire" })).toBeVisible();
  await editor.click();
  await p.keyboard.press("Control+End");
  await p.getByRole("button", { name: "Subheading" }).click();
  await p.keyboard.type("A word of my own");
  await p.keyboard.press("Enter");
  await p.keyboard.type("Wren never forgave him.");
  await expect(p.getByText(/^Saved \d/)).toBeVisible();
  await p.getByRole("button", { name: "Submit the backstory", exact: true }).click();
  await expect(editor).toHaveCount(0);
  await expect(main.getByRole("heading", { name: "A word of my own" })).toBeVisible();
  // The marks came through the edit exactly, once each, with the player's words after them.
  const edited = (await stored(p, id)).text;
  expect(edited.match(/<!-- questions:[\w-]+ -->/g)).toHaveLength(1);
  expect(edited.match(/<!-- \/questions:[\w-]+ -->/g)).toHaveLength(1);
  expect(edited).toMatch(/<!-- \/questions:[\w-]+ -->\n\n## A word of my own\n\nWren never forgave him\.$/);
  await p.getByRole("button", { name: "Answer the troupe's questions" }).click();
  await p.getByRole("group", { name: "Question sets" }).getByRole("button", { name: /^Short Form/ }).click();
  await wizard.getByRole("textbox").first().fill("Answered again");
  await wizard.getByRole("button", { name: "Build the backstory from Short Form" }).click();
  await expect(main.getByText("Answered again")).toBeVisible();
  await expect(main.getByRole("heading", { name: "A word of my own" })).toBeVisible();
  // Built again between its marks, not added a second time at the end.
  await expect(text.locator("h4")).toHaveCount(19);
});

test("a player writes a backstory in the formatted editor: it saves as a draft, comes back after a reload, warns before leaving, and only Submit makes a version", async ({ browser }) => {
  const player = await person(browser, "draft-player");
  const p = player.page;
  const id = await builtVampire(p, "Mireille", "Brujah", BRUJAH_NEONATE);
  await p.goto(`/characters/${id}/backstory`);
  await p.getByRole("button", { name: "Write the backstory" }).click();

  // No Markdown needed: the toolbar formats it.
  const editor = richEditor(p);
  const toolbar = p.getByRole("toolbar", { name: "Formatting" });
  if ((p.viewportSize()?.width ?? 1280) < 640) {
    // Big enough for a thumb on a phone, and all of it on the screen.
    const bold = await toolbar.getByRole("button", { name: "Bold" }).boundingBox();
    expect(bold!.height).toBeGreaterThanOrEqual(40);
    const bar = await toolbar.boundingBox();
    expect(bar!.x + bar!.width).toBeLessThanOrEqual(p.viewportSize()!.width);
  }
  await editor.click();
  await toolbar.getByRole("button", { name: "Subheading" }).click();
  await p.keyboard.type("My sire");
  await p.keyboard.press("Enter");
  await p.keyboard.type("He was ");
  await toolbar.getByRole("button", { name: "Bold" }).click();
  await p.keyboard.type("cruel");
  await toolbar.getByRole("button", { name: "Bold" }).click();
  await p.keyboard.type(".");
  await p.keyboard.press("Enter");
  await toolbar.getByRole("button", { name: "Bulleted list" }).click();
  await p.keyboard.type("I fled");
  await p.keyboard.press("Enter");
  await p.keyboard.type("I hid");

  // It saves itself as a draft a moment after typing stops: kept as Markdown, and not yet a version.
  await expect(p.getByText(/^Saved \d/)).toBeVisible();
  await expect(p.getByText("Draft, not yet submitted")).toBeVisible();
  const markdown = "## My sire\n\nHe was **cruel**.\n\n- I fled\n- I hid";
  await expect.poll(async () => (await stored(p, id)).draft?.text).toBe(markdown);
  expect(await stored(p, id)).toMatchObject({ version: 0, text: "" });
  await p.screenshot(shots("backstory-editor"));

  // Reloading (or coming back on another device) opens the draft where it was left.
  await p.reload();
  await expect(editor.getByRole("heading", { name: "My sire" })).toBeVisible();
  await expect(editor.locator("strong", { hasText: "cruel" })).toBeVisible();
  await expect(p.getByText("Draft, not yet submitted")).toBeVisible();

  // Leaving with writing not yet saved asks first.
  await editor.getByText("I hid").click();
  await p.keyboard.press("End");
  await p.keyboard.type(" in the docks");
  const asked = new Promise<string>((resolve) =>
    p.once("dialog", (dialog) => {
      resolve(dialog.type());
      void dialog.dismiss();
    }),
  );
  await p.close({ runBeforeUnload: true });
  expect(await asked).toBe("beforeunload");
  await expect.poll(async () => (await stored(p, id)).draft?.text).toBe(`${markdown} in the docks`);
  await expect(p.getByText(/^Saved \d/)).toBeVisible();

  // The Markdown view shows the same writing, for those who prefer it.
  await p.getByRole("button", { name: "Markdown", exact: true }).click();
  await expect(p.getByLabel("Your backstory, in Markdown")).toHaveValue(`${markdown} in the docks`);
  await p.getByRole("button", { name: "Formatted", exact: true }).click();

  // Autosaves made no version: Submit makes exactly one, and the draft goes.
  await p.getByRole("button", { name: "Submit the backstory", exact: true }).click();
  await expect(p.getByText(/^Last changed /)).toBeVisible();
  await expect(p.getByRole("listitem").filter({ hasText: "I hid in the docks" })).toBeVisible();
  expect(await stored(p, id)).toMatchObject({ version: 1, text: `${markdown} in the docks`, draft: null });
});

test("the cursor stays where the player writes: an autosave coming back never moves it, on the same line or after Enter", async ({ browser }) => {
  const player = await person(browser, "steady-writer");
  const p = player.page;
  const id = await builtVampire(p, "Margit", "Brujah", BRUJAH_NEONATE);
  await send(p, "PUT", `/api/characters/${id}/backstory`, { text: "Born in 1890.", version: 0 });
  await p.goto(`/characters/${id}/backstory`);
  await p.getByRole("button", { name: "Edit the backstory" }).click();
  const editor = richEditor(p);
  await editor.click();
  await p.keyboard.press("Control+End");
  await p.keyboard.type(" In Dublin.");
  await expect.poll(async () => (await stored(p, id)).draft?.text).toBe("Born in 1890. In Dublin.");
  await expect(p.getByText(/^Saved \d/)).toBeVisible();

  // Writing on after the save carries on where it left off, on the same line and after Enter.
  await p.keyboard.type(" Then Cork.");
  await p.keyboard.press("Enter");
  await p.keyboard.type("She fled to Chicago.");
  await expect(p.getByText("Not saved yet")).toBeVisible();
  const written = "Born in 1890. In Dublin. Then Cork.\n\nShe fled to Chicago.";
  await expect.poll(async () => (await stored(p, id)).draft?.text).toBe(written);
  await expect(p.getByText(/^Saved \d/)).toBeVisible();
  await p.keyboard.type(" Then Paris.");
  await expect.poll(async () => (await stored(p, id)).draft?.text).toBe(`${written} Then Paris.`);
  await expect(editor.getByRole("paragraph")).toHaveText(["Born in 1890. In Dublin. Then Cork.", "She fled to Chicago. Then Paris."]);
});

test("a version submitted on another device while the player writes never loses their draft: they compare the two and keep their own", async ({ browser }) => {
  const player = await person(browser, "clash-player");
  const p = player.page;
  const id = await builtVampire(p, "Odile", "Brujah", BRUJAH_NEONATE);
  await send(p, "PUT", `/api/characters/${id}/backstory`, { text: "Born in 1890.", version: 0 });
  await p.goto(`/characters/${id}/backstory`);
  await p.getByRole("button", { name: "Edit the backstory" }).click();
  const editor = richEditor(p);
  await editor.click();
  await p.keyboard.press("Control+End");
  await p.keyboard.press("Enter");
  await p.keyboard.type("She fled to Chicago.");
  await expect.poll(async () => (await stored(p, id)).draft?.text).toBe("Born in 1890.\n\nShe fled to Chicago.");

  // Meanwhile, on another device, the player submits something else.
  await send(p, "PUT", `/api/characters/${id}/backstory`, { text: "Born in 1900, in Cork.", version: 1 });
  expect((await stored(p, id)).draft).toMatchObject({ text: "Born in 1890.\n\nShe fled to Chicago.", behind: true });

  // Writing on here finds the newer version: both are kept, and the player chooses.
  await p.keyboard.type(" Then Paris.");
  const newer = p.getByRole("region", { name: "A newer version" });
  await expect(newer).toBeVisible();
  await expect(p.getByRole("button", { name: "Submit the backstory", exact: true })).toBeDisabled();
  await newer.getByRole("button", { name: "Compare them" }).click();
  const compared = newer.getByLabel("Your draft against the newer version");
  await expect(compared).toContainText("Only in the newer version: Born in 1900, in Cork.");
  await expect(compared).toContainText("Only in your draft: She fled to Chicago. Then Paris.");
  await p.screenshot(shots("backstory-newer-version"));

  await newer.getByRole("button", { name: "Keep mine" }).click();
  await expect(newer).toHaveCount(0);
  await expect(editor).toContainText("She fled to Chicago. Then Paris.");
  await p.getByRole("button", { name: "Submit the backstory", exact: true }).click();
  await expect(p.getByText(/^Last changed /)).toBeVisible();
  expect(await stored(p, id)).toMatchObject({ version: 3, text: "Born in 1890.\n\nShe fled to Chicago. Then Paris.", draft: null });
});

test("staff read a joining character's backstory, send it back on one section, and approve it once revised before accepting the character", async ({ browser }) => {
  const custodian = await person(browser, "tale-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tale-lead");
  const assistant = await person(browser, "tale-assistant");
  const player = await person(browser, "tale-player");
  const troupeName = `Court of Tales ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: assistant.handle, role: "assistant_storyteller" });
  const p = player.page;
  const id = await builtVampire(p, "Isolde", "Brujah", BRUJAH_NEONATE);

  // Isolde's player writes her backstory in Markdown, sees it formatted, and submits it.
  await p.goto(`/characters/${id}`);
  await characterTab(p, "Backstory");
  await p.getByRole("button", { name: "Write the backstory" }).click();
  await p.getByRole("button", { name: "Markdown", exact: true }).click();
  await p.getByLabel("Your backstory, in Markdown").fill("## My sire\n\nHe was **cruel**.\n\n## Since\n\n- I fled\n- I hid");
  await p.getByRole("button", { name: "Formatted", exact: true }).click();
  await expect(richEditor(p).getByRole("heading", { name: "My sire" })).toBeVisible();
  await expect(richEditor(p).locator("strong", { hasText: "cruel" })).toBeVisible();
  await p.getByRole("button", { name: "Submit the backstory", exact: true }).click();
  await expect(p.getByText(/^Last changed /)).toBeVisible();
  await expect(p.getByRole("listitem").filter({ hasText: "I hid" })).toBeVisible();

  await characterTab(p, "Troupes");
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead can't accept Isolde until her backstory is approved: it reads it there, and sends it back on one section.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/approvals`);
  const card = l.locator("section").filter({ hasText: "Isolde" });
  await expect(card.getByText("Not yet approved")).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  await card.getByRole("button", { name: "Read the backstory" }).click();
  await expect(card.getByRole("heading", { name: "My sire" })).toBeVisible();
  await card.getByLabel("Feedback on").selectOption("My sire");
  await card.getByLabel("Feedback for the player").fill("More about the sire, please");
  await l.screenshot(shots("backstory-feedback"));
  await card.getByRole("button", { name: "Send back with feedback" }).click();
  await expect(card.getByText("Sent back to the player")).toBeVisible();

  // The player is told, sees the feedback on the Backstory tab, revises and resubmits.
  await p.reload();
  await p.getByRole("button", { name: /Notifications, \d+ waiting/ }).click();
  await p.getByRole("button", { name: /sent Isolde's backstory back \(on “My sire”\)/ }).click();
  await expect(p.getByText(`${troupeName}'s storytellers asked for changes: see their feedback below`)).toBeVisible();
  const thread = p.getByRole("list", { name: "Feedback and replies" });
  await expect(thread).toContainText("on “My sire”");
  await expect(thread).toContainText("More about the sire, please");
  await p.getByRole("button", { name: "Edit the backstory" }).click();
  await p.getByRole("button", { name: "Markdown", exact: true }).click();
  await p.getByLabel("Your backstory, in Markdown").fill("## My sire\n\nHe was **cruel**, and taught me to hunt the docks.\n\n## Since\n\n- I fled\n- I hid");
  await p.getByRole("button", { name: "Submit the backstory", exact: true }).click();
  await expect(p.getByLabel("Your backstory, in Markdown")).toHaveCount(0);
  await expect(p.getByText("taught me to hunt the docks")).toBeVisible();
  await p.getByLabel("Reply to the storytellers").fill("Added the docks.");
  await p.getByRole("button", { name: "Resubmit the backstory" }).click();
  await expect(p.getByText(`Revised and back with ${troupeName}'s storytellers. Nothing for you to do yet.`)).toBeVisible();
  await p.screenshot(shots("backstory-resubmitted"));

  // An assistant storyteller approves it; then the character can be accepted.
  const a = assistant.page;
  await a.goto(`/troupes/${troupe.id}/approvals`);
  const theirs = a.locator("section").filter({ hasText: "Isolde" });
  await expect(theirs.getByText("Revised and resubmitted")).toBeVisible();
  await theirs.getByRole("button", { name: "Read the backstory" }).click();
  await expect(theirs.getByText("taught me to hunt the docks")).toBeVisible();
  await expect(theirs.getByRole("list", { name: "Feedback and replies" })).toContainText("Added the docks.");
  await theirs.getByRole("button", { name: "Approve the backstory" }).click();
  await expect(theirs.getByText("Approved", { exact: true })).toBeVisible();
  await theirs.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(a.getByText("Nothing pending.")).toBeVisible();

  await p.reload();
  await expect(p.getByText(new RegExp(`Approved by ${troupeName} \\(tale-assistant`))).toBeVisible();
});
