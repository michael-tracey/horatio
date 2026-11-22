import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, isNarrow, makeCustodian, person, run, shots } from "./support";

/** The game developer blog (#1155): staff write articles, the custodian publishes them, and anyone reads them. */

closeContextsAfterEach();

async function send(page: Page, method: "POST" | "PUT" | "PATCH", url: string, data: object) {
  const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
}

/** The custodian writes an article, naming `troupeId` or no troupe, and publishes it with `tags`. */
async function publishedArticle(c: Page, title: string, body: string, tags: string[], picture = false, troupeId: string | null = null): Promise<{ id: string; slug: string }> {
  const article = await send(c, "POST", "/api/blog/articles", { title, summary: `A summary of ${title}.`, body, troupe_id: troupeId });
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

test("a narrator sends an article to the custodian, who follows the bell to Custodian › Blog, tags and publishes it, and the narrator hears so (#1156, #1170)", async ({ browser }) => {
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

  // It is a task on the custodian's bell (#1170), which opens it on Custodian › Blog,
  // whose tab counts what waits (the other project's too).
  const c = custodian.page;
  await c.goto("/characters");
  await c.getByRole("button", { name: /^Notifications/ }).click();
  const task = c.getByRole("dialog", { name: "Notifications" }).getByRole("button", { name: new RegExp(`blogdesk-narr asks you to publish the blog article “${title}”`) });
  await task.click();
  await expect(c).toHaveURL(/\/custodian\/blog#article-[0-9a-f-]{36}$/);
  await expect(c.getByRole("link", { name: /^Blog/ })).toHaveText(/^Blog\d+$/);
  const waiting = c.getByRole("heading", { name: "Waiting", level: 2 }).locator("xpath=ancestor::section[1]");
  const item = waiting.getByRole("listitem", { name: title });
  await expect(item.getByText("blogdesk-narr")).toBeVisible();
  await expect(item.getByText(`of ${troupeName}`, { exact: false })).toBeVisible();
  await expect(item.getByText("Ask the players what their characters want, then wait.")).toBeVisible();
  const tags = item.getByRole("list", { name: "Tags" });
  await tags.getByRole("button", { name: "Storytelling" }).click();
  await expect(tags.getByRole("button", { name: "Storytelling" })).toHaveAttribute("aria-pressed", "true");
  await c.screenshot(shots("blog-queue"));

  await item.getByRole("button", { name: "Publish", exact: true }).click();

  const published = c.getByRole("heading", { name: "Published", level: 2 }).locator("xpath=ancestor::section[1]");
  await expect(published.getByRole("listitem", { name: title })).toBeVisible();
  await expect(waiting.getByRole("listitem", { name: title })).toHaveCount(0);
  await c.getByRole("button", { name: /^Notifications/ }).click();
  await expect(task).toHaveCount(0);
  await c.keyboard.press("Escape");
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

test("a storyteller puts a picture in an article's words, previews it, and once the custodian publishes it anyone can see the picture (#1163)", async ({ browser }) => {
  const custodian = await person(browser, "blogpic-cust");
  makeCustodian(custodian.email);
  const lead = await person(browser, "blogpic-lead");
  const troupe = await send(custodian.page, "POST", "/api/troupes", { name: `Court of Lit Halls ${run}`, lead_handle: lead.handle });
  const l = lead.page;

  const title = `Lighting a scene ${run}`;
  await l.goto(`/blog/write/new?troupe=${troupe.id}`);
  await l.getByLabel("Title").fill(title);
  const words = l.getByRole("textbox", { name: "Article" });
  await words.click();
  await l.keyboard.type("Candles do more than any speech.");
  // A new article is saved before a picture goes in its words.
  await l.getByRole("button", { name: "Insert a picture" }).click();
  await expect(l.getByText("Save it as a draft first, then add pictures to its words.")).toBeVisible();
  await l.getByRole("button", { name: "Close" }).click();
  await l.getByRole("button", { name: "Save draft" }).click();
  await expect(l).toHaveURL(/\/blog\/write\/[0-9a-f-]{36}$/);
  const address = (await l.getByText(/^Its address: /).textContent())!.replace("Its address: ", "");

  // Choose it, say what it shows (asked every time), and caption it.
  await words.click();
  await l.keyboard.press("Control+End");
  await l.getByRole("button", { name: "Insert a picture" }).click();
  const adding = l.getByRole("form", { name: "Add a picture to the words" });
  await adding.getByLabel("Picture to add").setInputFiles({ name: "hall.png", mimeType: "image/png", buffer: PNG });
  await adding.getByRole("button", { name: "Add the picture" }).click();
  await expect(adding.getByText(/^Say what the picture shows/)).toBeVisible();
  await adding.getByLabel("What it shows").fill("Candles along a long table");
  await adding.getByLabel("Caption (optional)").fill("The hall at midnight");
  await adding.getByRole("button", { name: "Add the picture" }).click();
  await expect(adding).toBeHidden();
  await expect(words.getByRole("img", { name: "Candles along a long table" })).toBeVisible();
  await l.getByRole("button", { name: "Save draft" }).click();
  await expect(l.getByRole("button", { name: "Save draft" })).toBeDisabled();

  // The preview shows it as the blog will, with its caption.
  await l.getByRole("radio", { name: "Preview" }).click();
  const shown = l.getByRole("article", { name: title });
  const picture = shown.getByRole("img", { name: "Candles along a long table" });
  await expect(picture).toBeVisible();
  await expect.poll(() => picture.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(shown.locator("figcaption")).toHaveText("The hall at midnight");
  expect(await l.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), "nothing scrolls sideways").toBe(true);
  const src = (await picture.getAttribute("src"))!;
  expect(src).toMatch(/^\/api\/blog\/body-pictures\/[0-9a-f-]{36}\/1200\.webp$/);
  await l.screenshot(shots("blog-picture-preview"));

  // Signed out, nobody sees it until it is published.
  const stranger = await browser.newContext();
  expect((await stranger.request.get(src)).status()).toBe(404);
  await l.getByRole("radio", { name: "Write" }).click();
  await l.getByRole("button", { name: "Submit to the custodian" }).click();
  await expect(l.getByText(/^Waiting for the custodian since /)).toBeVisible();

  const c = custodian.page;
  await c.goto("/custodian/blog");
  const waiting = c.getByRole("heading", { name: "Waiting", level: 2 }).locator("xpath=ancestor::section[1]");
  const item = waiting.getByRole("listitem", { name: title });
  await item.getByText("Read it").click();
  await expect(item.getByRole("img", { name: "Candles along a long table" })).toBeVisible();
  await item.getByRole("button", { name: "Publish", exact: true }).click();
  const published = c.getByRole("heading", { name: "Published", level: 2 }).locator("xpath=ancestor::section[1]");
  await expect(published.getByRole("listitem", { name: title })).toBeVisible();

  // Published, the picture is anyone's, and caches may keep it.
  const seen = await stranger.request.get(src);
  expect(seen.status()).toBe(200);
  expect(seen.headers()["content-type"]).toBe("image/webp");
  expect(seen.headers()["cache-control"]).toBe("public, max-age=3600");

  // A reader signed out sees it on the article's own page, with its caption.
  const reader = await stranger.newPage();
  await reader.goto(address);
  const read = reader.getByRole("article", { name: title });
  const there = read.getByRole("img", { name: "Candles along a long table" });
  // Loaded lazily, as it comes near.
  await there.scrollIntoViewIfNeeded();
  await expect(there).toBeVisible();
  await expect.poll(() => there.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(read.locator("figcaption")).toHaveText("The hall at midnight");
});

test("the custodian adds, renames, retires and merges a tag in Custodian › Blog › Tags, each showing its articles, and its old address leads to the other (#1161, #1184)", async ({ browser }) => {
  const custodian = await person(browser, "blogtags-cust");
  makeCustodian(custodian.email);
  const c = custodian.page;
  // Unique to the run and the project, within a tag name's 40 characters.
  const name = `Etiquette ${run} ${test.info().project.name.slice(0, 1)}`;

  await c.goto("/custodian/blog/tags");
  await expect(c.getByRole("link", { name: "Tags", exact: true })).toHaveAttribute("aria-current", "page");
  await c.getByRole("button", { name: "Add a tag" }).click();
  await c.getByRole("dialog", { name: "Add a tag" }).getByLabel("Name").fill(name);
  await c.getByRole("button", { name: "Add the tag" }).click();
  const tags = c.getByRole("table", { name: "Tags" });
  await expect(tags.getByRole("row", { name })).toContainText("No articles");

  // An article of the custodian's own carries it.
  const kept: { id: string; name: string }[] = await (await c.request.get("/api/blog/tags/kept")).json();
  const tag = kept.find((t) => t.name === name)!;
  const article = await send(c, "POST", "/api/blog/articles", { title: `Bowing at Elysium ${run}`, body: "Low, and not for long." });
  await send(c, "PUT", `/api/blog/articles/${article.id}/tags`, { tag_ids: [tag.id] });
  await c.reload();
  await expect(tags.getByRole("row", { name })).toContainText("1 article, none published");

  const renamed = `${name} rules`;
  await tags.getByRole("button", { name: `Actions for ${name}` }).click();
  await c.getByRole("menuitem", { name: "Rename…" }).click();
  const dialog = c.getByRole("dialog", { name: `Rename ${name}` });
  await expect(dialog.getByText(/follows the new name, as no published article has it yet/)).toBeVisible();
  await dialog.getByLabel("Name").fill(renamed);
  await dialog.getByRole("button", { name: "Rename" }).click();
  const row = tags.getByRole("row", { name: renamed });
  await expect(row).toBeVisible();

  await row.getByRole("button", { name: `Actions for ${renamed}` }).click();
  await c.getByRole("menuitem", { name: "Retire" }).click();
  await expect(row.getByText("Retired")).toBeVisible();
  await c.screenshot(shots("blog-tags"));

  // Merged into another, it goes, and the article has the other.
  const oldSlug = ((await (await c.request.get("/api/blog/tags/kept")).json()) as { name: string; slug: string }[]).find((t) => t.name === renamed)!.slug;
  await row.getByRole("button", { name: `Actions for ${renamed}` }).click();
  await c.getByRole("menuitem", { name: "Merge into…" }).click();
  const merging = c.getByRole("dialog", { name: `Merge ${renamed}` });
  await merging.getByLabel("Merge it into").selectOption({ label: "Community" });
  await merging.getByRole("button", { name: "Merge into Community" }).click();
  await expect(tags.getByRole("row", { name: renamed })).toHaveCount(0);
  const merged = await (await c.request.get(`/api/blog/articles/${article.id}`)).json();
  expect(merged.tags.map((t: { name: string }) => t.name)).toEqual(["Community"]);

  // Its old address leads to the tag it was merged into, and so does its feed (#1184).
  await c.goto(`/blog/tags/${oldSlug}`);
  await expect(c).toHaveURL(/\/blog\/tags\/community$/);
  await expect(c.getByRole("heading", { name: "Community", level: 1 })).toBeVisible();
  const feed = await c.request.get(`/blog/tags/${oldSlug}/feed.xml`, { maxRedirects: 0 });
  expect(feed.status()).toBe(301);
  expect(feed.headers()["location"]).toBe("/blog/tags/community/feed.xml");
});

test("signed out, someone opens the blog, filters it by a tag, reads an article, its author's page and its troupe's, but never a draft (#1158, #1160)", async ({ browser }) => {
  const custodian = await person(browser, "blogread-cust");
  makeCustodian(custodian.email);
  const c = custodian.page;
  // A public troupe the custodian runs, for the article's troupe card (#1160).
  const troupeName = `Lantern Court of the Blog ${run}`;
  const abbreviation = `LC${run.slice(-8)}`;
  const troupe = await send(c, "POST", "/api/troupes", { name: troupeName, lead_handle: custodian.handle });
  await send(c, "PATCH", `/api/troupes/${troupe.id}`, { description: "A Camarilla game by the harbour.", abbreviation });
  await send(c, "PUT", `/api/troupes/${troupe.id}/profile/public`, { public: true });
  const combat = `Fair fights at the table ${run}`;
  const other = `Lore for new players ${run}`;
  const tagged = await publishedArticle(c, combat, "Call the **challenge** out loud, then wait for the answer.", ["Combat and challenges"], true, troupe.id);
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
  // Its troupe is public, so it has a card beside the author's (#1160).
  const troupeCard = visitor.getByRole("region", { name: `About ${troupeName}` });
  await expect(troupeCard.getByText("A Camarilla game by the harbour.")).toBeVisible();
  await expect(troupeCard.getByTitle(troupeName)).toContainText(abbreviation);
  await visitor.screenshot(shots("blog-article"));
  // The card leads to the troupe's public profile, and back.
  await troupeCard.getByRole("link", { name: troupeName }).click();
  await expect(visitor).toHaveURL(`/t/${troupe.id}`);
  await expect(visitor.getByRole("heading", { name: troupeName, level: 1 })).toBeVisible();
  await visitor.goBack();
  await expect(visitor.getByRole("heading", { name: combat, level: 1 })).toBeVisible();

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

test("signed out, someone finds the blog from the sign-in page; its feeds, the sitemap and robots.txt hold only what is published, and an article's link has its own preview (#1162)", async ({ browser }) => {
  const custodian = await person(browser, "blogfeed-cust");
  makeCustodian(custodian.email);
  const c = custodian.page;
  const title = `Pacing a long night ${run}`;
  const article = await publishedArticle(c, title, "Break the night into **acts**.", ["Storytelling"], true);
  const unready = `Unfinished pacing ${run}`;
  const draft = await send(c, "POST", "/api/blog/articles", { title: unready, summary: "", body: "Secret.", troupe_id: null });

  // The sign-in page's footer leads to the blog, which links to its feed.
  const visitor = await (await browser.newContext()).newPage();
  await visitor.goto("/sign-in");
  await visitor.getByRole("contentinfo").getByRole("link", { name: "Blog" }).click();
  await expect(visitor.getByRole("heading", { name: "Blog", level: 1 })).toBeVisible();
  await expect(visitor.getByRole("link", { name: "Follow by feed" })).toHaveAttribute("href", "/blog/feed.xml");

  // The feed is the API's Atom, not a page of the app.
  const feed = await visitor.request.get("/blog/feed.xml");
  expect(feed.status()).toBe(200);
  expect(feed.headers()["content-type"]).toContain("application/atom+xml");
  const xml = await feed.text();
  expect(xml).toContain(`<title>${title}</title>`);
  expect(xml).toContain("&lt;strong&gt;acts&lt;/strong&gt;");
  expect(xml).toMatch(/&lt;img src="http[^"]+\/1200\.webp"/);
  expect(xml).not.toContain(unready);
  expect(await (await visitor.request.get("/blog/tags/storytelling/feed.xml")).text()).toContain(title);

  const sitemap = await visitor.request.get("/sitemap.xml");
  expect(sitemap.headers()["content-type"]).toContain("application/xml");
  const urls = await sitemap.text();
  expect(urls).toContain(`/blog/${article.slug}</loc>`);
  expect(urls).not.toContain(`/blog/${draft.slug}<`);
  const robots = await visitor.request.get("/robots.txt");
  expect(robots.headers()["content-type"]).toContain("text/plain");
  expect(await robots.text()).toMatch(/^Sitemap: http\S+\/sitemap\.xml$/m);

  // An article's page carries its own link preview for other sites; a draft's, the site's.
  const page = await (await visitor.request.get(`/blog/${article.slug}`)).text();
  expect(page).toContain(`<meta property="og:title" content="${title}" />`);
  expect(page).toContain('<meta property="og:type" content="article" />');
  expect(page).toMatch(/<meta property="og:image" content="http[^"]+\/1200\.webp" \/>/);
  const drafts = await (await visitor.request.get(`/blog/${draft.slug}`)).text();
  expect(drafts).toContain('<meta property="og:title" content="Horatio" />');
  expect(drafts).not.toContain(unready);
});
