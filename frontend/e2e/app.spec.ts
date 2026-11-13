import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, PASSWORD, shots, person, makeCustodian, topBar } from "./support";

/** The app itself: About, the Help pages, signing in on the way to a link, and reloading after a deploy. */

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

test("Help opens the user manual from the top menu, signed out or in, with links to sections and search", async ({ browser }) => {
  // Signed out, from the sign-in page's menu.
  const page = await (await browser.newContext()).newPage();
  await page.goto("/sign-in");
  await page.getByRole("banner").getByRole("link", { name: "Help", exact: true }).click();
  await expect(page).toHaveURL(/\/help$/);
  await expect(page.getByRole("heading", { name: "Help", level: 1 })).toBeVisible();
  // The part for them is marked: signed out, the players'.
  await expect(page.getByRole("article").getByRole("link", { name: "Players for you" })).toBeVisible();

  // A link between pages to a section opens there.
  await page.getByRole("main").getByRole("link", { name: "Getting started", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Getting started", level: 1 })).toBeVisible();
  await page.getByRole("main").getByRole("article").getByRole("link", { name: "custodian", exact: true }).click();
  await expect(page).toHaveURL(/\/help\/glossary#custodian$/);
  await expect(page.getByRole("heading", { name: "Custodian", exact: true })).toBeInViewport();

  // A section that isn't there says so.
  await page.goto("/help/glossary#no-such-section");
  await expect(page.getByText(/There's no section “no-such-section” on this page/)).toBeVisible();
  await page.goto("/help/no-such-page");
  await expect(page.getByText("There's no help page called “no-such-page”.")).toBeVisible();

  // Signed in, from the top menu, and search across every part.
  const { page: p } = await person(browser, "helpmenu-player");
  await (await topBar(p)).getByRole("link", { name: "Help", exact: true }).click();
  await expect(p.getByRole("heading", { name: "Help", level: 1 })).toBeVisible();
  await p.getByRole("searchbox", { name: "Search the manual" }).fill("calendar link");
  const results = p.getByRole("region", { name: "Search results" });
  const hit = results.getByRole("link", { name: "Getting started › The calendar link" });
  await expect(hit).toBeVisible();
  await expect(results.locator("mark").first()).toBeVisible();
  await hit.click();
  await expect(p).toHaveURL(/\/help\/getting-started#the-calendar-link$/);
  await expect(p.getByRole("heading", { name: "The calendar link" })).toBeInViewport();
  // Its sections are listed: beside it on a computer, at the top on a phone.
  if ((p.viewportSize()?.width ?? 1280) < 1024) await p.locator("summary", { hasText: "On this page" }).click();
  const sectionList = p.getByRole("navigation", { name: "On this page" }).filter({ visible: true });
  await expect(sectionList.getByRole("link", { name: "The calendar link" })).toHaveAttribute("aria-current", "location");
  await p.screenshot({ path: `test-results/screens/${test.info().project.name}-help-sections.png` });
  // Its screenshot comes from the bundle.
  const image = p.getByRole("img", { name: /^Subscribe to the calendar/ });
  await image.scrollIntoViewIfNeeded();
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await p.screenshot(shots("help"));
  // Back goes to the results as they were.
  await p.goBack();
  await expect(p.getByRole("searchbox", { name: "Search the manual" })).toHaveValue("calendar link");
});

test("the top bar is one line, on a phone too: the bell and a menu that holds the links (#746)", async ({ browser }) => {
  // A custodian with a long name: the widest bar there is.
  const { page, email } = await person(browser, "phonebar-custodian-with-a-long-name");
  makeCustodian(email);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  const bell = page.getByRole("button", { name: /^Notifications/ });
  await expect(bell).toBeVisible();
  // One line: no taller than its padding and its tallest control.
  expect((await page.getByRole("banner").boundingBox())!.height).toBeLessThan(70);

  const menu = page.getByRole("button", { name: "Menu", exact: true });
  if ((page.viewportSize()?.width ?? 1280) < 1024) {
    // The links are behind the menu, which opens over the page and closes on going somewhere.
    await expect(page.getByRole("navigation", { name: "Main" })).toHaveCount(0);
    await menu.click();
    const nav = page.getByRole("navigation", { name: "Main" });
    for (const name of ["Characters", "Troupes", "Rulebook", "Help", "Custodian"]) await expect(nav.getByRole("link", { name, exact: true })).toBeVisible();
    await expect(nav.getByRole("link", { name: /^Your account: phonebar-custodian-with-a-long-name/ })).toContainText("(custodian)");
    await expect(nav.getByRole("button", { name: "Sign out" })).toBeVisible();
    await page.screenshot(shots("top-bar-menu"));
    await page.keyboard.press("Escape");
    await expect(nav).toHaveCount(0);
    await expect(menu).toBeFocused();
    await (await topBar(page)).getByRole("link", { name: "Troupes", exact: true }).click();
    await expect(page).toHaveURL(/\/troupes$/);
    await expect(nav).toHaveCount(0);
    await expect(menu).toHaveAttribute("aria-expanded", "false");
  } else {
    await expect(menu).toHaveCount(0);
    await expect(page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Custodian", exact: true })).toBeVisible();
  }

  // The bell still opens its list.
  await bell.click();
  await expect(page.getByRole("dialog", { name: "Notifications" })).toBeVisible();
  await page.screenshot(shots("top-bar"));
});

test("the chart kit draws its sample charts in Dark, Ultra goth and print, with tooltips and tables, d3 loading only then (#706)", async ({ browser }) => {
  const { page } = await person(browser, "kit-viewer");
  // d3 comes with the charts, never with the app's first load.
  const d3 = page.waitForRequest((r) => /\/assets\/d3-[^/]+\.js$/.test(r.url()));
  await page.goto("/charts");
  await expect(page.getByRole("heading", { name: "Chart kit", level: 1 })).toBeVisible();
  await d3;

  const columns = page.getByRole("figure", { name: "Open boons by type" });
  const minor = columns.getByRole("img", { name: "Minor: open 70" });
  await expect(minor).toBeVisible();
  // Keyboard focus shows the tooltip; Escape puts it away.
  await minor.focus();
  await expect(columns.getByText("70", { exact: true }).last()).toBeVisible();
  await page.keyboard.press("Escape");
  // The same data as a table, on request.
  await columns.getByRole("button", { name: "Show as table" }).click();
  await expect(columns.getByRole("row", { name: "Minor 70" })).toBeVisible();
  await columns.getByRole("button", { name: "Show as chart" }).click();
  await expect(minor).toBeVisible();

  // Clans past the seventh share Other.
  await expect(page.getByRole("figure", { name: "Clan colours" }).getByRole("img", { name: "Banu Haqim: characters 4" })).toBeVisible();
  // The chart fits the screen: nothing scrolls sideways, on a phone too.
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

  // Each theme sets the chart's colours: the series alike on both dark surfaces, the ink each theme's own.
  const colours = () =>
    columns.evaluate((figure) => {
      const style = getComputedStyle(figure);
      return { series: style.getPropertyValue("--chart-series-1").trim(), ink: style.getPropertyValue("--chart-ink").trim() };
    });
  expect(await colours()).toEqual({ series: "#3987e5", ink: "#ede4d3" });
  await page.screenshot(shots("chart-kit"));
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "ultragoth"));
  expect(await colours()).toEqual({ series: "#3987e5", ink: "#efe6dc" });
  await page.screenshot(shots("chart-kit-ultragoth"));
  // On paper, the hues stepped for white and black ink.
  await page.emulateMedia({ media: "print" });
  expect(await colours()).toEqual({ series: "#2a78d6", ink: "#0b0b0b" });
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

test("a session check that fails says so on the page with Try again, not the sign-in form", async ({ browser }) => {
  const { page } = await person(browser, "sessioncheck-player");
  // The server fails every check after a reload, until it is back.
  let failing = true;
  let failed = 0;
  await page.route("**/api/auth/me", (route) => {
    if (!failing) return route.fallback();
    failed += 1;
    return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: "The server is having a moment." }) });
  });
  await page.goto("/troupes");
  await expect(page.getByText("Couldn't check that you're signed in.")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveText("The server is having a moment.");
  await expect(page.getByRole("heading", { name: "Sign in" })).toHaveCount(0);
  expect(new URL(page.url()).pathname).toBe("/troupes");
  // Asked once, not again and again as the page opens on the failure.
  expect(failed).toBeLessThanOrEqual(2);

  failing = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Troupes", exact: true })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/troupes");
});

test("a page whose file is gone after a deploy reloads once, then says Horatio was updated", async ({ browser }) => {
  const { page } = await person(browser, "Staleo");
  let asked = 0;
  await page.route("**/assets/AccountPage-*.js", (route) => {
    asked += 1;
    return route.fulfill({ status: 404, contentType: "text/plain", body: "not found" });
  });
  await page.goto("/characters");
  await (await topBar(page)).getByTitle("Your account").click();
  await expect(page.getByText("Horatio has been updated. Reload to continue.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  // One reload was tried, and no more: two asks for the file, not a loop.
  expect(asked).toBeGreaterThan(0);
  expect(asked).toBeLessThanOrEqual(3);
});

test("the browser keeps the rules and asks again with their ETag: while they hold, no body comes (#643)", async ({ browser }) => {
  const { page } = await person(browser, "etag-reader");
  // What came over the wire for the rules browser's answer, each time it was asked for.
  const asked: { ifNoneMatch?: string; body: number }[] = [];
  page.on("requestfinished", async (request) => {
    if (new URL(request.url()).pathname !== "/api/rules/vampire/browse") return;
    const [headers, sizes] = await Promise.all([request.allHeaders(), request.sizes()]);
    asked.push({ ifNoneMatch: headers["if-none-match"], body: sizes.responseBodySize });
  });
  await page.goto("/rules");
  await expect(page.getByTestId("rules-entry").first()).toBeVisible();
  await expect.poll(() => asked.length).toBe(1);
  expect(asked[0].ifNoneMatch).toBeUndefined();
  expect(asked[0].body).toBeGreaterThan(100_000);
  // Opened again: the app asks again, the browser asks with the ETag it kept, and the
  // API's 304 brings no body; the browser gives the app the one it kept.
  await page.reload();
  await expect(page.getByTestId("rules-entry").first()).toBeVisible();
  await expect.poll(() => asked.length).toBe(2);
  expect(asked[1].ifNoneMatch).toMatch(/^W\/"/);
  expect(asked[1].body).toBe(0);
});
