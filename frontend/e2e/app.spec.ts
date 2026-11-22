import { expect, test } from "@playwright/test";
import { closeContextsAfterEach, PASSWORD, run, shots, person, makeCustodian, topBar, expectPartOpen } from "./support";

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
  // On a narrow phone it waits in the footer, to keep the header to one line (#907).
  const narrow = (page.viewportSize()?.width ?? 1280) < 416;
  await page.getByRole(narrow ? "contentinfo" : "banner").getByRole("link", { name: "Help", exact: true }).click();
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

  // A long page offers a way back to the top once it is scrolled past one screen (#922).
  await p.goto("/help/players");
  await expect(p.getByRole("heading", { name: "Players", level: 1 })).toBeVisible();
  const top = p.getByRole("button", { name: "Back to the top" });
  await expect(top).toHaveCount(0);
  await p.evaluate(() => window.scrollTo(0, window.innerHeight * 3));
  await expect(top).toBeVisible();
  await top.click();
  await expect.poll(() => p.evaluate(() => window.scrollY)).toBe(0);
  await expect(top).toHaveCount(0);
});

test("signed out, the header offers Sign in and Create account, and an address that leads nowhere says so with ways on (#907)", async ({ browser }) => {
  const page = await (await browser.newContext()).newPage();
  await page.goto("/about");
  const banner = page.getByRole("banner");
  // Both ways in come back to the page they were on.
  await expect(banner.getByRole("link", { name: "Sign in", exact: true })).toHaveAttribute("href", `/sign-in?next=${encodeURIComponent("/about")}`);
  await expect(banner.getByRole("link", { name: "Create account", exact: true })).toHaveAttribute("href", `/sign-up?next=${encodeURIComponent("/about")}`);
  // One line, on a phone too.
  expect((await banner.boundingBox())!.height).toBeLessThan(70);

  await page.goto("/nonsense");
  await expect(page.getByRole("heading", { name: "Nothing here", level: 1 })).toBeVisible();
  const waysOn = page.getByRole("navigation", { name: "Ways on" });
  await expect(waysOn.getByRole("link")).toHaveText(["Sign in", "Help"]);
  await page.screenshot(shots("not-found-signed-out"));
  await banner.getByRole("link", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Create an account" })).toBeVisible();

  // Signed in, the ways on are their characters and troupes.
  const { page: p } = await person(browser, "notfound-player");
  await p.goto("/nonsense");
  await expect(p.getByRole("heading", { name: "Nothing here", level: 1 })).toBeVisible();
  await expect(p.getByRole("navigation", { name: "Ways on" }).getByRole("link")).toHaveText(["Characters", "Troupes", "Help"]);
  await p.getByRole("navigation", { name: "Ways on" }).getByRole("link", { name: "Troupes" }).click();
  await expect(p).toHaveURL(/\/troupes$/);
});

test("signed out, / is the landing page, with an article and a public troupe; signing in goes on to Characters as before (#1164)", async ({ browser }) => {
  const lead = await person(browser, "landing-lead");
  makeCustodian(lead.email);
  const player = await person(browser, "landing-player");
  const l = lead.page;
  const send = async (method: "PATCH" | "POST" | "PUT", url: string, data: object = {}) => {
    const response = await l.request.fetch(url, { method, headers: { "X-Horatio": "1" }, data });
    expect(response.status(), await response.text()).toBeLessThan(300);
    return response.json();
  };
  // A troupe whose profile is public, and a featured article from it.
  const troupeName = `Saltmarsh Landing Court ${run}`;
  const { id: troupeId } = await send("POST", "/api/troupes", { name: troupeName, lead_handle: lead.handle });
  await send("PATCH", `/api/troupes/${troupeId}`, { description: "A Camarilla court on the salt flats, where the tide keeps every secret for a night." });
  await send("PUT", `/api/troupes/${troupeId}/profile/public`, { public: true });
  const title = `Welcoming a new player to your court ${run}`;
  const article = await send("POST", "/api/blog/articles", { title, summary: "Five things to do at their first game.", body: "Say hello.", troupe_id: troupeId });
  await send("POST", `/api/blog/articles/${article.id}/submit`);
  await send("POST", `/api/blog/articles/${article.id}/publish`);
  await send("PUT", `/api/blog/articles/${article.id}/featured`, { featured: true });

  const page = await (await browser.newContext()).newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Welcome to Horatio", level: 1 })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  await expect(page).toHaveTitle("Welcome · Horatio");
  await expect(page.getByRole("heading", { name: "What Horatio is" })).toBeVisible();
  // The article, among the blog's featured and newest.
  await expect(page.getByRole("list", { name: "Articles" }).getByRole("link", { name: title })).toBeVisible();
  await expect(page.getByRole("link", { name: "Read the blog" })).toHaveAttribute("href", "/blog");
  // The troupe, by name among every public troupe: a page at a time until it shows.
  const ours = page.getByRole("list", { name: "Troupes" }).getByRole("link", { name: new RegExp(troupeName) });
  const pages = page.getByRole("navigation", { name: "Pages of troupes" });
  for (let n = 0; n < 100 && !(await ours.isVisible()); n++) {
    const range = await pages.getByRole("paragraph").textContent();
    await pages.getByRole("button", { name: "Next" }).click();
    await expect(pages.getByRole("paragraph")).not.toHaveText(range ?? "");
  }
  await expect(ours).toContainText("A Camarilla court on the salt flats");
  await page.screenshot(shots("landing"));
  await ours.click();
  await expect(page).toHaveURL(new RegExp(`/t/${troupeId}$`));
  await expect(page.getByRole("heading", { name: troupeName, level: 1 })).toBeVisible();

  // Signing in from it goes on to their characters, and / takes them there from then on.
  await page.goto("/");
  await page.getByRole("main").getByRole("link", { name: "Sign in", exact: true }).click();
  await page.getByLabel("Email or handle").fill(player.email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/characters");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Your characters" })).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/characters");
});

test("the top bar is one line, on a phone too: the bell and a menu that holds the links (#746)", async ({ browser }) => {
  // A custodian with a long name: the widest bar there is.
  const { page, email } = await person(browser, "phonebar-custodian-with-a-long-name");
  makeCustodian(email);
  // A troupe of their own, asked and approved, leaves a long notice in the bell.
  const headers = { "X-Horatio": "1" };
  const asked = await page.request.post("/api/troupe-requests", { headers, data: { name: `Top Bar Court of the Long Notice ${run}` } });
  expect(asked.status(), await asked.text()).toBeLessThan(300);
  const approved = await page.request.post(`/api/troupe-requests/${(await asked.json()).id}/approve`, { headers });
  expect(approved.status(), await approved.text()).toBeLessThan(300);
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

  // The bell still opens its list, and a long notice wraps inside it, on a computer too,
  // where the bar's links don't wrap (#1123).
  await bell.click();
  const panel = page.getByRole("dialog", { name: "Notifications" });
  await expect(panel).toBeVisible();
  const notice = panel.getByText(/^Your troupe Top Bar Court of the Long Notice .+ is ready, with you as its lead storyteller$/);
  await expect(notice).toBeVisible();
  expect((await notice.boundingBox())!.height, "the notice takes more than one line").toBeGreaterThan(30);
  expect(await panel.evaluate((el) => el.scrollWidth - el.clientWidth), "nothing in the panel scrolls sideways").toBeLessThanOrEqual(0);
  await page.screenshot(shots("top-bar"));
});

test("a bell line naming a player wraps, its name opens their profile and the rest the task (#1131)", async ({ browser }) => {
  const { page } = await person(browser, "bellname-teacher");
  const pupil = await person(browser, "bellname-pupil-player");
  const me: { id: string } = await (await pupil.page.request.get("/api/auth/me")).json();
  // A teaching request in the bell, as the server words one: the e2e server has no teacher rules to make it.
  const summary = "Rook of the Long Road: Teaching Firearms 1 to Konrad von Ehrenberg (bellname-pupil-player)? It costs 1 Willpower.";
  await page.route("**/api/notifications", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    const item = { id: "teaching:e2e", kind: "teaching", task: true, troupe_id: null, troupe_name: null, summary, link: "/account", at: new Date().toISOString(), read: false, picture: null, player_id: me.id, player_name: "bellname-pupil-player" };
    await route.fulfill({ response, json: { items: [item, ...body.items], count: body.count + 1 } });
  });
  await page.reload();
  const bell = page.getByRole("button", { name: /^Notifications/ });
  await bell.click();
  const panel = page.getByRole("dialog", { name: "Notifications" });
  const task = panel.getByRole("button", { name: summary });
  await expect(task).toBeVisible();
  expect((await task.boundingBox())!.height, "the line takes more than one line").toBeGreaterThan(40);
  expect(await panel.evaluate((el) => el.scrollWidth - el.clientWidth), "nothing in the panel scrolls sideways").toBeLessThanOrEqual(0);

  // The player's name, over the row's button, opens their profile and closes the bell.
  await panel.getByRole("link", { name: "bellname-pupil-player" }).click();
  await expect(page).toHaveURL(new RegExp(`/players/${me.id}$`));
  await expect(page.getByRole("heading", { name: /^bellname-pupil-player/ })).toBeVisible();
  await expect(panel).toHaveCount(0);

  // The rest of the line opens the task.
  await bell.click();
  await panel.getByRole("button", { name: summary }).click();
  await expect(page).toHaveURL(/\/account$/);
});

test("the browser tab names the page: the tab open, then the troupe or character, then Horatio; signed out, nothing it couldn't show (#775)", async ({ browser }) => {
  const custodian = await person(browser, "tabtitle-custodian");
  makeCustodian(custodian.email);
  const lead = await person(browser, "tabtitle-lead");
  const troupe = `Tab Titles ${run}`;
  const made = await custodian.page.request.post("/api/troupes", { headers: { "X-Horatio": "1" }, data: { name: troupe, lead_handle: lead.handle } });
  expect(made.status(), await made.text()).toBe(201);
  const troupeId: string = (await made.json()).id;
  const p = lead.page;

  await p.goto(`/troupes/${troupeId}/players`);
  await expect(p).toHaveTitle(`Players · ${troupe} · Horatio`);
  // A tab's own tabs come first.
  await p.goto(`/troupes/${troupeId}/house-rules/costs`);
  await expectPartOpen(p, "Costs");
  expect(await p.title()).toMatch(new RegExp(`^Costs · .+ · ${troupe} · Horatio$`));

  const character = await p.request.post("/api/characters", { headers: { "X-Horatio": "1" }, data: { splat: "vampire", name: "Tabitha Tallis" } });
  expect(character.status(), await character.text()).toBe(201);
  const characterId: string = (await character.json()).id;
  await p.goto(`/characters/${characterId}/status`);
  await expect(p).toHaveTitle("Status & Titles · Tabitha Tallis · Horatio");
  await p.goto(`/print/characters/${characterId}`);
  await expect(p).toHaveTitle("Print · Tabitha Tallis · Horatio");
  await p.goto("/rules");
  await expect(p).toHaveTitle(/^\S+ · Horatio$/);

  // Signed out, the troupe's page asks for a sign-in, and its tab says only that.
  const stranger = await browser.newPage();
  await stranger.goto(`/troupes/${troupeId}/approvals`);
  await expect(stranger).toHaveTitle("Sign in · Horatio");
  await stranger.close();
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
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Ines Varga");
  expect(new URL(page.url()).pathname).toBe(log);

  // A next that leads off the site is ignored: signing in goes to their characters.
  const other = await (await browser.newContext()).newPage();
  await other.goto("/sign-in?next=//evil.example/");
  await other.getByLabel("Email or handle").fill(player.email);
  await other.getByLabel("Password").fill(PASSWORD);
  await other.getByRole("button", { name: "Sign in", exact: true }).click();
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
  await (await topBar(page)).getByRole("link", { name: /^Your account/ }).click();
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
