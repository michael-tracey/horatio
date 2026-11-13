import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import { GroupedTabs, PageTabs, PageTitle, Tabs } from "./components/ui";
import { openTab, tabOpens, textOf, titleOf, useTitle } from "./title";

afterEach(cleanup);

describe("titleOf", () => {
  it("puts the most specific part first and the site last (#775)", () => {
    expect(titleOf(["Approvals", "The Night Court"])).toBe("Approvals · The Night Court · Horatio");
    expect(titleOf([])).toBe("Horatio");
  });

  it("names a part once and skips empty ones", () => {
    expect(titleOf(["Sheet", "Sheet", " ", "Ada  Night"])).toBe("Sheet · Ada Night · Horatio");
  });
});

describe("textOf", () => {
  it("keeps a heading's words, not what its components draw", () => {
    function Pronouns() {
      return <span>they/them</span>;
    }
    expect(
      textOf(
        <>
          Ada Night
          <Pronouns />
        </>,
      ),
    ).toBe("Ada Night");
    expect(textOf(<span className="x">{["The ", "Night Court"]}</span>)).toBe("The Night Court");
  });
});

describe("openTab", () => {
  const tabs = [
    { to: "/troupes/1", label: "About", end: true },
    { to: "/troupes/1/approvals", label: "Approvals" },
    { to: "/troupes/1/rules", label: "Rules" },
  ];
  it("finds the tab a row marks open, as NavLink does", () => {
    expect(openTab(tabs, "/troupes/1")?.label).toBe("About");
    expect(openTab(tabs, "/troupes/1/approvals/")?.label).toBe("Approvals");
    expect(openTab(tabs, "/troupes/1/rules/teachers")?.label).toBe("Rules");
    expect(openTab(tabs, "/troupes/1/rulesets")).toBeUndefined();
  });

  it("finds a tab open under its also address, as a narrator's My work is inside a cycle (#789)", () => {
    const work = { to: "/troupes/1/work", label: "My work", also: "/troupes/1/downtimes" };
    expect(tabOpens(work, "/troupes/1/work")).toBe(true);
    expect(tabOpens(work, "/troupes/1/downtimes/7/work")).toBe(true);
    expect(tabOpens(work, "/troupes/1/downtimesheet")).toBe(false);
    expect(openTab([...tabs, work], "/troupes/1/downtimes/7/work")?.label).toBe("My work");
  });
});

describe("the browser tab's title", () => {
  it("comes from the page's heading and its open tabs, deepest first", () => {
    render(
      <MemoryRouter initialEntries={["/troupes/1/rules/teachers"]}>
        <PageTitle>
          <span>The Night Court</span>
        </PageTitle>
        <GroupedTabs
          label="Troupe sections"
          groups={[
            { label: "Troupe", tabs: [{ to: "/troupes/1", label: "About", end: true }] },
            {
              label: "Customise",
              tabs: [
                { to: "/troupes/1/settings", label: "Settings" },
                { to: "/troupes/1/rules", label: "Rules" },
              ],
            },
          ]}
        />
        <PageTabs
          label="House rules"
          tabs={[
            { to: "/troupes/1/rules", label: "Checks", end: true },
            { to: "/troupes/1/rules/teachers", label: "Teachers" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Teachers · Rules · The Night Court · Horatio");
  });

  it("goes back to the site's name when the page goes", () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={["/characters/2/sheet"]}>
        <PageTitle>Ada Night</PageTitle>
        <Tabs
          tabs={[
            { to: "/characters/2", label: "Build", end: true },
            { to: "/characters/2/sheet", label: "Sheet" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Sheet · Ada Night · Horatio");
    unmount();
    expect(document.title).toBe("Horatio");
  });

  it("puts a page's own name, with no place on the page, before its tabs", () => {
    function Play() {
      useTitle("Play · Ada Night");
      return <Tabs tabs={[{ to: "/play", label: "Tracker" }]} />;
    }
    render(
      <MemoryRouter initialEntries={["/play"]}>
        <Play />
      </MemoryRouter>,
    );
    expect(document.title).toBe("Tracker · Play · Ada Night · Horatio");
  });
});
