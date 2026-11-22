import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, makeCustodian, person, run, shots } from "./support";

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

  // The narrator writes it on the plain writing page, naming their troupe, and sends it.
  const n = narrator.page;
  const title = `Narrating your first scene ${run}`;
  await n.goto("/blog/write");
  await n.getByLabel("Title").fill(title);
  await n.getByLabel("Summary").fill("Listen more than you talk.");
  await expect(n.getByLabel("Troupe")).toHaveValue(troupe.id);
  await n.getByRole("textbox", { name: "Article", exact: true }).click();
  await n.keyboard.type("Ask the players what their characters want, then wait.");
  await n.getByRole("button", { name: "Save draft" }).click();
  await expect(n).toHaveURL(/\/blog\/write\/[0-9a-f-]{36}$/);
  await expect(n.getByText(/^Draft\. Its address: \/blog\/narrating-your-first-scene/)).toBeVisible();
  await n.getByRole("button", { name: "Send to the custodian" }).click();
  await expect(n.getByText(/^Waiting for the custodian\./)).toBeVisible();

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
  await expect(n.getByText(/^Published\. Its address:/)).toBeVisible();
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
