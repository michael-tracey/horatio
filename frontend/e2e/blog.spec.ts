import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, isNarrow, makeCustodian, person, run, shots } from "./support";

/** The game developer blog (#1155): staff write articles, the custodian publishes them, and anyone reads them. */

closeContextsAfterEach();

async function send(page: Page, method: "POST" | "PUT", url: string, data: object) {
  const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

/** The custodian writes an article, naming no troupe, and publishes it with `tags`. */
async function publishedArticle(c: Page, title: string, body: string, tags: string[], picture = false): Promise<{ id: string; slug: string }> {
  const article = await send(c, "POST", "/api/blog/articles", { title, summary: `A summary of ${title}.`, body, troupe_id: null });
  if (picture) {
    const upload = await c.request.post(`/api/blog/articles/${article.id}/picture`, {
      headers: { "X-Horatio": "1" },
      multipart: { file: { name: "portrait.jpg", mimeType: "image/jpeg", buffer: readFileSync("e2e/portrait.jpg") } },
    });
    expect(upload.status(), await upload.text()).toBeLessThan(300);
  }
  const all: { id: string; name: string }[] = await (await c.request.get("/api/blog/tags")).json();
  await send(c, "PUT", `/api/blog/articles/${article.id}/tags`, { tag_ids: all.filter((t) => tags.includes(t.name)).map((t) => t.id) });
  await send(c, "POST", `/api/blog/articles/${article.id}/submit`, {});
  return send(c, "POST", `/api/blog/articles/${article.id}/publish`, {});
}

test("a narrator sends an article to the custodian, who tags and publishes it from Custodian › Blog, and the narrator hears so (#1156)", async ({ browser }) => {
  const custodian = await person(browser, "blogdesk-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "blogdesk-lead");
  const narrator = await person(browser, "blogdesk-narr");
  const troupeName = `Court of Bloggers ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await send(lead.page, "PUT", `/api/troupes/${troupe.id}/staff`, { handle: narrator.handle, role: "narrator" });

  // The narrator writes it, naming their troupe, and submits it.
  const n = narrator.page;
  const title = `Narrating your first scene ${run}`;
  await n.goto("/blog/write/new");
  await n.getByLabel("Title").fill(title);
  await n.getByLabel("Summary").fill("Listen more than you talk.");
  await expect(n.getByLabel("Troupe")).toHaveValue(troupe.id);
  await n.getByRole("textbox", { name: "Article", exact: true }).click();
  await n.keyboard.type("Ask the players what their characters want, then wait.");
  await n.getByRole("button", { name: "Save draft" }).click();
  await expect(n).toHaveURL(/\/blog\/write\/[0-9a-f-]{36}$/);
  await expect(n.getByText("A draft: only you and the custodian can see it.")).toBeVisible();
  await expect(n.getByText(/^Its address: \/blog\/narrating-your-first-scene/)).toBeVisible();
  await n.getByRole("button", { name: "Submit to the custodian" }).click();
  await expect(n.getByText(/^Waiting for the custodian since /)).toBeVisible();

  // It waits on Custodian › Blog, whose tab counts what waits (the other project's too).
  const c = custodian.page;
  await c.goto("/custodian/blog");
  await expect(c.getByRole("link", { name: /^Blog/ })).toHaveText(/^Blog\d+$/);
  const waiting = c.getByRole("heading", { name: "Waiting", level: 2 }).locator("xpath=ancestor::section[1]");
  const item = waiting.getByRole("listitem", { name: title });
  await expect(item.getByText("blogdesk-narr")).toBeVisible();
  await expect(item.getByText(`of ${troupeName}`, { exact: false })).toBeVisible();
  await item.getByText("Read it").click();
  await expect(item.getByText("Ask the players what their characters want, then wait.")).toBeVisible();
  const tags = item.getByRole("list", { name: "Tags" });
  await tags.getByRole("button", { name: "Storytelling" }).click();
  await expect(tags.getByRole("button", { name: "Storytelling" })).toHaveAttribute("aria-pressed", "true");
  await c.screenshot(shots("blog-queue"));

  await item.getByRole("button", { name: "Publish", exact: true }).click();

  const published = c.getByRole("heading", { name: "Published", level: 2 }).locator("xpath=ancestor::section[1]");
  await expect(published.getByRole("listitem", { name: title })).toBeVisible();
  await expect(waiting.getByRole("listitem", { name: title })).toHaveCount(0);
  await expect(published.getByRole("listitem", { name: title }).getByRole("list", { name: "Tags" }).getByRole("button", { name: "Storytelling" })).toHaveAttribute("aria-pressed", "true");

  // The narrator hears of it on the bell, which leads back to the article.
  await n.goto("/characters");
  await n.getByRole("button", { name: /^Notifications/ }).click();
  await n.getByRole("dialog", { name: "Notifications" }).getByRole("button", { name: new RegExp(`Your article “${title}” is published on the blog`) }).click();
  await expect(n).toHaveURL(/\/blog\/write\/[0-9a-f-]{36}$/);
  await expect(n.getByText(/^Published on /)).toBeVisible();
});

/** A 240 × 60 picture, for the hero picture. */
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAPAAAAA8CAIAAADXHaAKAAAAwElEQVR4nO3SQQ3AIADAwDF5yMQNrjBBQtLcKeijY6/5QcX/OgBuMjQphibF0KQYmhRDk2JoUgxNiqFJMTQphibF0KQYmhRDk2JoUgxNiqFJMTQphibF0KQYmhRDk2JoUgxNiqFJMTQphibF0KQYmhRDk2JoUgxNiqFJMTQphibF0KQYmhRDk2JoUgxNiqFJMTQphibF0KQYmhRDk2JoUgxNiqFJMTQphibF0KQYmhRDk2JoUgxNiqFJMTQphiblAMqFAi20AaA8AAAAAElFTkSuQmCC",
  "base64",
);

test("a storyteller writes for the blog from their troupe, previews and submits it; the custodian returns it with a note, and they change it and submit it again (#1157)", async ({ browser }) => {
  const custodian = await person(browser, "blogret-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "blogret-lead");
  const troupeName = `Court of Returned Drafts ${run}`;
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  const l = lead.page;

  // Write for the blog is in the menu on a narrow screen, and on the account page on any.
  await l.goto("/account");
  await expect(l.getByRole("main").getByRole("link", { name: "Write for the blog" })).toHaveAttribute("href", "/blog/write");
  if (isNarrow(l)) {
    await l.getByRole("button", { name: "Menu" }).click();
    await expect(l.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Write for the blog" })).toBeVisible();
    await l.keyboard.press("Escape");
  }

  // From the troupe's Overview, a new article names the troupe; a private one is named, not linked.
  await l.goto(`/troupes/${troupe.id}`);
  await l.getByRole("link", { name: "Write for the blog" }).click();
  await expect(l).toHaveURL(new RegExp(`/blog/write/new\\?troupe=${troupe.id}$`));
  await expect(l.getByText("A new article, not yet saved.")).toBeVisible();
  await expect(l.getByLabel("Troupe")).toHaveValue(troupe.id);
  await expect(l.getByText(`${troupeName} isn't public, so the blog will show its name only.`, { exact: false })).toBeVisible();
  await expect(l.getByRole("link", { name: "the writing guide" })).toHaveAttribute("href", "/help/blog");

  const title = `Saying no to your players ${run}`;
  await l.getByLabel("Title").fill(title);
  await l.getByLabel("Summary").fill("A no can make the story better.");
  await l.getByRole("list", { name: "Tags" }).getByRole("button", { name: "Running a game" }).click();
  await l.getByRole("textbox", { name: "Article" }).click();
  await l.keyboard.type("Say yes, and. Then say no when it matters.");
  await l.getByRole("button", { name: "Save draft" }).click();
  await expect(l).toHaveURL(/\/blog\/write\/[0-9a-f-]{36}$/);
  await expect(l.getByText("A draft: only you and the custodian can see it.")).toBeVisible();

  // Its hero picture, placed in its 2:1 frame.
  await l.getByLabel("Choose a picture").setInputFiles({ name: "hero.png", mimeType: "image/png", buffer: PNG });
  const place = l.getByRole("dialog", { name: "Place the picture" });
  await expect(place.getByRole("slider", { name: /Where the frame is/ })).toBeVisible();
  await place.getByRole("button", { name: "Save the picture" }).click();
  await expect(place).toBeHidden();
  await expect(l.getByRole("img", { name: "The article's picture" })).toBeVisible();

  // The preview shows it as the blog will, under its banner, and fits a phone.
  await l.getByRole("radio", { name: "Preview" }).click();
  await expect(l.getByRole("note")).toHaveText(/^Preview: the article as the blog will show it\./);
  const shown = l.getByRole("article", { name: title });
  await expect(shown.getByRole("heading", { name: title })).toBeVisible();
  await expect(shown.getByText("Say yes, and. Then say no when it matters.")).toBeVisible();
  await expect(shown.getByText("Running a game")).toBeVisible();
  await expect(shown.getByText(troupeName, { exact: true })).toBeVisible();
  await expect(shown.getByRole("link", { name: troupeName })).toHaveCount(0);
  // With no author profile yet, the place for its card says how to set one up.
  await expect(shown.getByRole("link", { name: "Set up your author profile" })).toHaveAttribute("href", "/account/blog");
  expect(await l.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "nothing scrolls sideways").toBe(true);
  await l.screenshot(shots("blog-preview"));
  await l.getByRole("radio", { name: "Write" }).click();
  await l.getByRole("button", { name: "Submit to the custodian" }).click();
  await expect(l.getByText(/^Waiting for the custodian since /)).toBeVisible();
  await expect(l.getByRole("button", { name: "Withdraw" })).toBeVisible();

  // The custodian returns it with a note.
  const c = custodian.page;
  await c.goto("/custodian/blog");
  const waiting = c.getByRole("heading", { name: "Waiting", level: 2 }).locator("xpath=ancestor::section[1]");
  const item = waiting.getByRole("listitem", { name: title });
  await item.getByRole("button", { name: "Return with a note…" }).click();
  await item.getByLabel("Note to the author").fill("Give an example of a good no.");
  await item.getByRole("button", { name: "Return it" }).click();
  await expect(waiting.getByRole("listitem", { name: title })).toHaveCount(0);

  // The author sees the note in their list and on the article, changes it and submits it again.
  await l.goto("/blog/write");
  const line = l.getByRole("listitem", { name: title });
  await expect(line.getByText("Returned to you")).toBeVisible();
  await expect(line.getByText("Give an example of a good no.")).toBeVisible();
  await l.screenshot(shots("blog-mine"));
  await line.getByRole("link", { name: title }).click();
  const where = l.getByRole("region", { name: "Where it stands" });
  await expect(where.getByText("The custodian returned it to you, with a note.")).toBeVisible();
  await expect(where.getByText("Give an example of a good no.")).toBeVisible();
  await l.getByRole("textbox", { name: "Article" }).click();
  await l.keyboard.press("Control+End");
  await l.keyboard.press("Enter");
  await l.keyboard.type("No, the Prince won't see you tonight.");
  await l.getByRole("button", { name: "Submit to the custodian" }).click();
  await expect(where.getByText(/^Waiting for the custodian since /)).toBeVisible();

  await c.reload();
  await item.getByText("Read it").click();
  await expect(item.getByText("No, the Prince won't see you tonight.")).toBeVisible();
});

test("signed out, someone opens the blog, filters it by a tag, reads an article and its author's page, but never a draft (#1158)", async ({ browser }) => {
  const custodian = await person(browser, "blogread-cust");
  makeCustodian(custodian.email);
  const c = custodian.page;
  const combat = `Fair fights at the table ${run}`;
  const other = `Lore for new players ${run}`;
  const tagged = await publishedArticle(c, combat, "Call the **challenge** out loud, then wait for the answer.", ["Combat and challenges"], true);
  await publishedArticle(c, other, "Start with the city.", ["Setting and lore"]);
  const unready = `Not ready yet ${run}`;
  const draft = await send(c, "POST", "/api/blog/articles", { title: unready, summary: "", body: "Secret.", troupe_id: null });
  // Their author profile (#1159), for the card under each article and their page.
  await send(c, "PUT", "/api/blog/author", { display_name: "Odile Brandt", handle: custodian.handle, bio: "Runs games in *Lisbon*.", links: [] });

  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto("/blog");
  await expect(visitor).toHaveTitle("Blog · Horatio");
  await expect(visitor.getByRole("heading", { name: "Blog", level: 1 })).toBeVisible();
  const articles = visitor.getByRole("list", { name: "Articles" });
  await expect(articles.getByRole("listitem", { name: other })).toBeVisible();
  await expect(articles.getByRole("listitem", { name: combat })).toBeVisible();
  // The newer comes first.
  const order = await articles.getByRole("listitem").evaluateAll((items) => items.map((li) => li.getAttribute("aria-label")));
  expect(order.indexOf(other)).toBeLessThan(order.indexOf(combat));
  await visitor.screenshot(shots("blog-list"));

  // Filtered by a tag, the tag's own page lists only what has it.
  await visitor.getByRole("navigation", { name: "Tags" }).getByRole("link", { name: "Combat and challenges" }).click();
  await expect(visitor).toHaveURL(/\/blog\/tags\/combat-and-challenges$/);
  await expect(visitor.getByRole("heading", { name: "Combat and challenges", level: 1 })).toBeVisible();
  await expect(articles.getByRole("listitem", { name: combat })).toBeVisible();
  await expect(articles.getByRole("listitem", { name: other })).toHaveCount(0);

  // The article, with its picture, words, author and tags.
  await articles.getByRole("link", { name: combat }).click();
  await expect(visitor).toHaveURL(`/blog/${tagged.slug}`);
  await expect(visitor.getByRole("heading", { name: combat, level: 1 })).toBeVisible();
  await expect(visitor).toHaveTitle(`${combat} · Blog · Horatio`);
  await expect(visitor.getByText(`A summary of ${combat}.`)).toBeVisible();
  await expect(visitor.getByText("By Odile Brandt")).toBeVisible();
  await expect(visitor.locator("article strong", { hasText: "challenge" })).toBeVisible();
  const hero = visitor.locator("article img").first();
  await expect(hero).toBeVisible();
  expect(await hero.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(visitor.getByRole("list", { name: "Tags" }).getByRole("link", { name: "Combat and challenges" })).toHaveAttribute("href", "/blog/tags/combat-and-challenges");
  // Nothing to change for a visitor.
  await expect(visitor.getByRole("link", { name: "Change it" })).toHaveCount(0);
  const card = visitor.getByRole("region", { name: "About Odile Brandt" });
  await expect(card.getByText("Lisbon")).toBeVisible();
  await visitor.screenshot(shots("blog-article"));

  // The card leads to the author's page, with what they have published.
  await card.getByRole("link", { name: "Odile Brandt" }).click();
  await expect(visitor).toHaveURL(`/blog/authors/${custodian.handle}`);
  await expect(visitor.getByRole("heading", { name: "Odile Brandt", level: 1 })).toBeVisible();
  await expect(articles.getByRole("listitem", { name: combat })).toBeVisible();
  await expect(articles.getByRole("listitem", { name: other })).toBeVisible();
  await expect(articles.getByRole("listitem", { name: unready })).toHaveCount(0);

  // A draft isn't there, signed out or in.
  await visitor.goto(`/blog/${draft.slug}`);
  await expect(visitor.getByRole("heading", { name: "No such article", level: 1 })).toBeVisible();
  // Its author, signed in, has a way to change a published one from its page.
  await c.goto(`/blog/${tagged.slug}`);
  await expect(c.getByRole("link", { name: "Change it" })).toHaveAttribute("href", `/blog/write/${tagged.id}`);
});
