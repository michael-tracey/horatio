import { expect, test, type Page } from "@playwright/test";
import { ATTRIBUTES_AND_FOCUSES, builtVampire, closeContextsAfterEach, makeCustodian, person, run, shots } from "./support";

/** A character's backstory: written in Markdown or built from the troupe's questions, and approved as part of accepting the character. */

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

  // The player then edits it freely: their own words outside the sections stay when they answer again.
  await p.getByRole("button", { name: "Edit the backstory" }).click();
  const editor = p.getByLabel("Your backstory, in Markdown");
  await editor.fill(`${await editor.inputValue()}\n\n## A word of my own\n\nWren never forgave him.`);
  await p.getByRole("button", { name: "Save the backstory" }).click();
  await expect(main.getByRole("heading", { name: "A word of my own" })).toBeVisible();
  await p.getByRole("button", { name: "Answer the troupe's questions" }).click();
  await p.getByRole("group", { name: "Question sets" }).getByRole("button", { name: /^Short Form/ }).click();
  await wizard.getByRole("textbox").first().fill("Answered again");
  await wizard.getByRole("button", { name: "Build the backstory from Short Form" }).click();
  await expect(main.getByText("Answered again")).toBeVisible();
  await expect(main.getByRole("heading", { name: "A word of my own" })).toBeVisible();
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

  // Isolde's player writes her backstory in Markdown, previews it, and saves it.
  await p.goto(`/characters/${id}`);
  await p.locator("main").getByRole("link", { name: "Backstory", exact: true }).click();
  await p.getByRole("button", { name: "Write the backstory" }).click();
  await p.getByLabel("Your backstory, in Markdown").fill("## My sire\n\nHe was **cruel**.\n\n## Since\n\n- I fled\n- I hid");
  await p.getByRole("button", { name: "Preview" }).click();
  await expect(p.getByRole("heading", { name: "My sire" })).toBeVisible();
  await expect(p.locator("main strong", { hasText: "cruel" })).toBeVisible();
  await p.getByRole("button", { name: "Save the backstory" }).click();
  await expect(p.getByText(/^Last changed /)).toBeVisible();
  await expect(p.getByRole("listitem").filter({ hasText: "I hid" })).toBeVisible();

  await p.locator("main").getByRole("link", { name: "Troupes", exact: true }).click();
  await p.getByLabel("Troupe", { exact: true }).selectOption({ label: troupeName });
  await p.getByRole("button", { name: "Ask to join as home troupe" }).click();
  await expect(p.getByText(/Waiting for .* storytellers/)).toBeVisible();

  // The lead can't accept Isolde until her backstory is approved: it reads it there, and sends it back on one section.
  const l = lead.page;
  await l.goto(`/troupes/${troupe.id}/approvals`);
  const card = l.locator("section").filter({ hasText: "Isolde" });
  await expect(card.getByText("not yet approved")).toBeVisible();
  await expect(card.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
  await card.getByRole("button", { name: "Read the backstory" }).click();
  await expect(card.getByRole("heading", { name: "My sire" })).toBeVisible();
  await card.getByLabel("Feedback on").selectOption("My sire");
  await card.getByLabel("Feedback for the player").fill("More about the sire, please");
  await l.screenshot(shots("backstory-feedback"));
  await card.getByRole("button", { name: "Send back with feedback" }).click();
  await expect(card.getByText("sent back to the player")).toBeVisible();

  // The player is told, sees the feedback on the Backstory tab, revises and resubmits.
  await p.reload();
  await p.getByRole("button", { name: /Notifications, \d+ waiting/ }).click();
  await p.getByRole("button", { name: /sent Isolde's backstory back \(on “My sire”\)/ }).click();
  await expect(p.getByText(`${troupeName} sent it back with feedback.`)).toBeVisible();
  const thread = p.getByRole("list", { name: "Feedback and replies" });
  await expect(thread).toContainText("on “My sire”");
  await expect(thread).toContainText("More about the sire, please");
  await p.getByRole("button", { name: "Edit the backstory" }).click();
  await p.getByLabel("Your backstory, in Markdown").fill("## My sire\n\nHe was **cruel**, and taught me to hunt the docks.\n\n## Since\n\n- I fled\n- I hid");
  await p.getByRole("button", { name: "Save the backstory" }).click();
  await expect(p.getByText("taught me to hunt the docks")).toBeVisible();
  await p.getByLabel("Reply to the storytellers").fill("Added the docks.");
  await p.getByRole("button", { name: "Resubmit the backstory" }).click();
  await expect(p.getByText(`Revised and back with ${troupeName}'s storytellers.`)).toBeVisible();
  await p.screenshot(shots("backstory-resubmitted"));

  // An assistant storyteller approves it; then the character can be accepted.
  const a = assistant.page;
  await a.goto(`/troupes/${troupe.id}/approvals`);
  const theirs = a.locator("section").filter({ hasText: "Isolde" });
  await expect(theirs.getByText("revised and resubmitted")).toBeVisible();
  await theirs.getByRole("button", { name: "Read the backstory" }).click();
  await expect(theirs.getByText("taught me to hunt the docks")).toBeVisible();
  await expect(theirs.getByRole("list", { name: "Feedback and replies" })).toContainText("Added the docks.");
  await theirs.getByRole("button", { name: "Approve the backstory" }).click();
  await expect(theirs.getByText("approved", { exact: true })).toBeVisible();
  await theirs.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(a.getByText("Nothing pending.")).toBeVisible();

  await p.reload();
  await expect(p.getByText(new RegExp(`Approved by ${troupeName} \\(tale-assistant`))).toBeVisible();
});
