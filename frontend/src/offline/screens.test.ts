import { describe, expect, it } from "vitest";
import { characterOf, screenName } from "./screens";

const ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

describe("screenName", () => {
  it("names a character's tabs, and its sheet", () => {
    expect(screenName(`/characters/${ID}/downtime`)).toBe("The Downtime tab");
    expect(screenName(`/characters/${ID}/xp`)).toBe("The Experience tab");
    expect(screenName(`/characters/${ID}`)).toBe("This character's sheet");
  });

  it("names staff screens and the rest", () => {
    expect(screenName(`/play/troupes/${ID}/scenes`)).toBe("The Scenes page");
    expect(screenName(`/play/troupes/${ID}/scenes/${ID}`)).toBe("This scene");
    expect(screenName(`/troupes/${ID}/check-in`)).toBe("The troupe's page");
    expect(screenName(`/troupes/${ID}/downtimes/${ID}/responses`)).toBe("The downtime cycle");
    expect(screenName(`/cycles/${ID}`)).toBe("The downtime cycle");
    expect(screenName("/check-in/ABCD")).toBe("Check-in");
    expect(screenName("/custodian/people")).toBe("The Custodian page");
    expect(screenName(`/play/characters/${ID}`)).toBe("This Play View");
    expect(screenName("/characters")).toBe("The Characters page");
    expect(screenName("/somewhere")).toBe("This screen");
  });
});

describe("characterOf", () => {
  it("finds the character a page or Play View is about", () => {
    expect(characterOf(`/characters/${ID}/downtime`)).toBe(ID);
    expect(characterOf(`/play/characters/${ID}`)).toBe(ID);
    expect(characterOf("/troupes")).toBeNull();
  });
});
