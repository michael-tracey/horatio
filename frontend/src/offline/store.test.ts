import { QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it } from "vitest";
import type { CharacterListOut } from "../api/types";
import { keeping, recordKey, setKeeping, setKeptFor, tapsWaiting } from "./keep";
import { memoryShelf } from "./shelf";
import { dropRestored, forget, removeKept, restore, save, type Kept } from "./store";

const ME = "11111111-1111-4111-8111-111111111111";
const OTHER = "22222222-2222-4222-8222-222222222222";
const ROSA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const BRAM = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

const rosa = { id: ROSA, name: "Rosa", player_id: ME, kind: "pc", status: "active", creation_complete: true, home_troupe_id: null, building_troupe_id: null } as unknown as CharacterListOut;

function signedIn(id = ME) {
  const client = new QueryClient();
  client.setQueryData(["me"], { id });
  client.setQueryData(["characters"], [rosa]);
  return client;
}

beforeEach(() => localStorage.clear());

describe("keeping a person's answers", () => {
  it("writes their own characters' answers and never a staff screen's or another character's", async () => {
    const shelf = memoryShelf();
    const client = signedIn();
    client.setQueryData(["play", ROSA], { blood: 7 });
    client.setQueryData(["play", BRAM], { blood: 3 });
    client.setQueryData(["scenes", "troupe", false], [{ id: "scene" }]);
    const kept = await save(client, ME, shelf);
    expect(kept?.characters).toEqual([{ id: ROSA, name: "Rosa" }]);
    const record = shelf.items.get(recordKey(ME)) as Kept;
    expect(record.queries.map((q) => q.queryKey)).toEqual(expect.arrayContaining([["me"], ["characters"], ["play", ROSA]]));
    expect(record.queries.map((q) => q.queryKey[0])).not.toContain("scenes");
    expect(record.queries.some((q) => q.queryKey[1] === BRAM)).toBe(false);
    expect(record.bytes).toBeGreaterThan(0);
  });

  it("writes nothing for someone who isn't the person signed in", async () => {
    const shelf = memoryShelf();
    expect(await save(signedIn(OTHER), ME, shelf)).toBeNull();
    expect(shelf.items.size).toBe(0);
  });

  it("keeps an answer no longer on screen until it is asked afresh", async () => {
    const shelf = memoryShelf();
    const client = signedIn();
    client.setQueryData(["sheet", ROSA], { traits: ["Brawl"] });
    await save(client, ME, shelf);
    client.removeQueries({ queryKey: ["sheet", ROSA] });
    client.setQueryData(["play", ROSA], { blood: 6 });
    await save(client, ME, shelf);
    const record = shelf.items.get(recordKey(ME)) as Kept;
    expect(record.queries.map((q) => q.queryKey)).toEqual(expect.arrayContaining([["sheet", ROSA], ["play", ROSA]]));
  });

  it("puts them back as the app opens, for the person last keeping them here", async () => {
    const shelf = memoryShelf();
    const before = signedIn();
    before.setQueryData(["play", ROSA], { blood: 7 });
    await save(before, ME, shelf);

    const opening = new QueryClient();
    expect(await restore(opening, shelf)).toBeNull(); // not loaded until their choice is on
    setKeeping(ME, "on");
    setKeptFor(ME);
    expect(await restore(opening, shelf)).toBe(ME);
    expect(opening.getQueryData(["play", ROSA])).toEqual({ blood: 7 });
    expect(opening.getQueryData(["me"])).toEqual({ id: ME });
  });

  it("takes restored answers off screen once someone else is signed in, or no one", async () => {
    const shelf = memoryShelf();
    const before = signedIn();
    before.setQueryData(["play", ROSA], { blood: 7 });
    await save(before, ME, shelf);
    setKeeping(ME, "on");
    setKeptFor(ME);
    const opening = new QueryClient();
    await restore(opening, shelf);
    dropRestored(opening, ME);
    expect(opening.getQueryData(["play", ROSA])).toBeDefined();
    dropRestored(opening, null);
    expect(opening.getQueryData(["play", ROSA])).toBeUndefined();
    // Still kept on the device, for when they sign in again.
    expect(shelf.items.has(recordKey(ME))).toBe(true);
  });
});

describe("removing and signing out", () => {
  it("Remove takes the person's answers off the device and turns keeping off", async () => {
    const shelf = memoryShelf();
    await save(signedIn(), ME, shelf);
    setKeeping(ME, "on");
    await removeKept(ME, shelf);
    expect(shelf.items.has(recordKey(ME))).toBe(false);
    expect(keeping(ME)).toBe("off");
  });

  it("signing out clears the person's answers, the taps waiting and the app's memory, and leaves another person's", async () => {
    const shelf = memoryShelf();
    await save(signedIn(), ME, shelf);
    await save(signedIn(OTHER), OTHER, shelf);
    localStorage.setItem(`horatio.play.${ROSA}`, JSON.stringify([{ id: "tap" }]));
    const client = signedIn();
    client.setQueryData(["play", ROSA], { blood: 7 });
    await forget(client, ME, shelf);
    expect(shelf.items.has(recordKey(ME))).toBe(false);
    expect(shelf.items.has(recordKey(OTHER))).toBe(true);
    expect(tapsWaiting()).toBe(0);
    expect(client.getQueryData(["play", ROSA])).toBeUndefined();
    expect(client.getQueryData(["me"])).toBeNull();
  });
});
