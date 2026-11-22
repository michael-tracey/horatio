import { expect, test, type Page } from "@playwright/test";
import { closeContextsAfterEach, makeCustodian, person, run, shots } from "./support";

/** The game developer blog (#1155): staff write articles, and the custodian publishes them. */

closeContextsAfterEach();

async function send(page: Page, method: "POST" | "PUT", url: string, data: object) {
  const response = await page.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
  expect(response.status(), await response.text()).toBeLessThan(300);
  return response.json();
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

test("the custodian adds, renames, retires and merges a tag in Custodian › Blog › Tags, each showing its articles (#1161)", async ({ browser }) => {
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
  await row.getByRole("button", { name: `Actions for ${renamed}` }).click();
  await c.getByRole("menuitem", { name: "Merge into…" }).click();
  const merging = c.getByRole("dialog", { name: `Merge ${renamed}` });
  await merging.getByLabel("Merge it into").selectOption({ label: "Community" });
  await merging.getByRole("button", { name: "Merge into Community" }).click();
  await expect(tags.getByRole("row", { name: renamed })).toHaveCount(0);
  const merged = await (await c.request.get(`/api/blog/articles/${article.id}`)).json();
  expect(merged.tags.map((t: { name: string }) => t.name)).toEqual(["Community"]);
});
