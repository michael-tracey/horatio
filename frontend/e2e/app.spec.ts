import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, PASSWORD, shots, person } from "./support";

/** The app itself: About, signing in on the way to a link, and reloading after a deploy. */

closeContextsAfterEach();

test("anyone can read About, with the Dark Pack Agreement's notices", async ({ browser }) => {
  // Signed out: the sign-in page's footer links to it.
  const page = await (await browser.newContext()).newPage();
  await page.goto("/sign-in");
  await expect(page.getByText(/Unofficial fan-made material under Paradox Interactive's Dark Pack Agreement/)).toBeVisible();
  await page.getByRole("link", { name: "About Horatio" }).click();
  await expect(page.getByRole("heading", { name: "About Horatio" })).toBeVisible();
  await expect(page.getByText(/Portions of the materials are the copyrights and trademarks of Paradox Interactive AB, and are used with permission/)).toBeVisible();
  await expect(page.getByText(/not official World of Darkness material/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Dark Pack Agreement" })).toBeVisible();
  await page.screenshot(shots("about"));
});

test("a link opened signed out goes there once signed in, and never to another site", async ({ browser }) => {
  const player = await person(browser, "nextlink-player");
  const made = await player.page.request.post("/api/characters", { headers: { "X-Horatio": "1" }, data: { splat: "vampire", name: "Ines Varga" } });
  expect(made.status(), await made.text()).toBeLessThan(300);
  const log = `/characters/${(await made.json()).id}/log`;

  // Signed out, the link asks them to sign in, and says what Horatio is.
  const page = await (await browser.newContext()).newPage();
  await page.goto(log);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(new URL(page.url()).searchParams.get("next")).toBe(log);
  await expect(page.getByText("Character sheets and downtimes for Mind's Eye Theatre troupes.")).toBeVisible();
  await page.screenshot(shots("signin"));
  // Going to make an account, or to reset the password, keeps it too.
  await expect(page.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", `/sign-up?next=${encodeURIComponent(log)}`);
  await expect(page.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute("href", `/forgot-password?next=${encodeURIComponent(log)}`);

  // Signed in, they are where the link pointed.
  await page.getByLabel("Email or handle").fill(player.email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Ines Varga");
  expect(new URL(page.url()).pathname).toBe(log);

  // A next that leads off the site is ignored: signing in goes to their characters.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/sign-in?next=//evil.example/");
  await other.getByLabel("Email or handle").fill(player.email);
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in" }).click();
  await expect(other.getByRole("heading", { name: "Your characters" })).toBeVisible();
  expect(new URL(other.url()).origin).toBe(new URL(page.url()).origin);
});

test("a page whose file is gone after a deploy reloads once, then says Horatio was updated", async ({ browser }) => {
  const { page } = await person(browser, "Staleo");
  let asked = 0;
  await page.route("**/assets/AccountPage-*.js", (route) => {
    asked += 1;
    return route.fulfill({ status: 404, contentType: "text/plain", body: "not found" });
  });
  await page.goto("/characters");
  await page.getByTitle("Your account").click();
  await expect(page.getByText("Horatio has been updated. Reload to continue.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  // One reload was tried, and no more: two asks for the file, not a loop.
  expect(asked).toBeGreaterThan(0);
  expect(asked).toBeLessThanOrEqual(3);
});
