import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { pageLabel, TraitInfo } from "./TraitInfo";

afterEach(cleanup);

describe("TraitInfo", () => {
  const celerity = () => <TraitInfo name="Celerity" description="Moving faster than the eye can follow." page="52" />;

  it("starts closed, with the description hidden", () => {
    render(celerity());
    const button = screen.getByRole("button", { name: "Celerity" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById(button.getAttribute("aria-controls")!)).toBeNull();
  });

  it("opens and closes on each press, with the description and page under it", () => {
    render(celerity());
    const button = screen.getByRole("button", { name: "Celerity" });
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const panel = document.getElementById(button.getAttribute("aria-controls")!)!;
    expect(panel.textContent).toContain("Moving faster than the eye can follow.");
    expect(panel.textContent).toContain("MET: VTM p. 52");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById(panel.id)).toBeNull();
  });

  it("lets several be open at once", () => {
    render(
      <>
        <TraitInfo name="Celerity" description="Fast." />
        <TraitInfo name="Potence" description="Strong." />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Celerity" }));
    fireEvent.click(screen.getByRole("button", { name: "Potence" }));
    expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-expanded"))).toEqual(["true", "true"]);
    expect(screen.getByText("Fast.")).toBeTruthy();
    expect(screen.getByText("Strong.")).toBeTruthy();
  });

  it("shows no chevron or button for a trait with no description", () => {
    render(<TraitInfo name="Willpower" after={<span>, 5</span>} description={null} page="52" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Willpower")).toBeTruthy();
    expect(screen.getByText(", 5")).toBeTruthy();
  });

  it("opens to more than a description, or to that alone", () => {
    render(<TraitInfo name="Celerity" more={<ol><li>Alacrity</li></ol>} />);
    fireEvent.click(screen.getByRole("button", { name: "Celerity" }));
    expect(screen.getByText("Alacrity")).toBeTruthy();
  });

  it("leaves the page out where there is none", () => {
    render(<TraitInfo name="Brawl" description="Fighting with your body." page={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Brawl" }));
    expect(screen.getByText("Fighting with your body.").parentElement!.children).toHaveLength(1);
  });

  it("links a page of the V20 LARP SRD, named for it", () => {
    const page = "https://www.oneworldofdarkness.com/srd-v20/rituals/vile-swarm";
    render(<TraitInfo name="Dark Thaumaturgy: Vile Swarm" description="Become a swarm." page={page} />);
    fireEvent.click(screen.getByRole("button", { name: "Dark Thaumaturgy: Vile Swarm" }));
    expect(screen.getByRole("link", { name: "V20 LARP SRD" }).getAttribute("href")).toBe(page);
  });

  it("keeps what follows the name on the same line", () => {
    render(<TraitInfo name="Contacts" after={<span>: Police</span>} description="People who help." />);
    expect(screen.getByText(": Police")).toBeTruthy();
  });
});

describe("pageLabel", () => {
  it("says which book a bare page is from", () => {
    expect(pageLabel("86")).toBe("MET: VTM p. 86");
    expect(pageLabel("54-55")).toBe("MET: VTM pp. 54-55");
    expect(pageLabel("31 & 24")).toBe("MET: VTM pp. 31 & 24");
  });

  it("keeps a reference that names its book, and drops a missing one", () => {
    expect(pageLabel("Vol. 2, p. 281")).toBe("Vol. 2, p. 281");
    expect(pageLabel("unknown")).toBeNull();
    expect(pageLabel("")).toBeNull();
    expect(pageLabel(null)).toBeNull();
  });

  it("names the SRD for a link to one of its pages", () => {
    expect(pageLabel("https://www.oneworldofdarkness.com/srd-v20/thaumaturgy/dark-thaumaturgy")).toBe("V20 LARP SRD");
  });
});
