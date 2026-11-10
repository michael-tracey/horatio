import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CharacterListOut } from "../api/types";
import { keeping, keptTroupes, recordKey, scenesKey, setKeeping, setKeptFor, tapsWaiting } from "./keep";
import { memoryShelf } from "./shelf";
import { dropRestored, forget, keptScenesSummary, refresh, removeKept, removeScenes, restore, save, saveScenes, scenesTouched, type Kept, type KeptScenes } from "./store";

/** The server, for refresh: each path answers with a little data, but those in `failing`, which answer 500. */
const failing = new Set<string>();
vi.mock(import("../api/client"), async (original) => ({
  ...(await original()),
  api: {
    GET: async (path: string, options?: { params?: { query?: { kind?: string } } }) => {
      const asked = options?.params?.query?.kind ? `${path}?kind=${options.params.query.kind}` : path;
      if (failing.has(asked)) return { error: { detail: "Down." }, response: new Response(null, { status: 500 }) };
      return { data: answers[path] ?? {}, response: new Response(null, { status: 200 }) };
    },
  } as never,
}));

const ME = "11111111-1111-4111-8111-111111111111";
const OTHER = "22222222-2222-4222-8222-222222222222";
const ROSA = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const BRAM = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";

/** What the server answers each path with, for refresh. */
const answers: Record<string, unknown> = {};

const rosa = { id: ROSA, name: "Rosa", player_id: ME, kind: "pc", status: "active", creation_complete: true, home_troupe_id: null, building_troupe_id: null } as unknown as CharacterListOut;

function signedIn(id = ME) {
  const client = new QueryClient();
  client.setQueryData(["me"], { id });
  client.setQueryData(["characters"], [rosa]);
  return client;
}

beforeEach(() => {
  localStorage.clear();
  failing.clear();
});

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

  it("has the screens ask afresh for what it puts back, however recently it was kept (#528)", async () => {
    const shelf = memoryShelf();
    const before = signedIn();
    before.setQueryData(["me"], { id: ME, preferences: { ratings: "pips" } });
    await save(before, ME, shelf);
    setKeeping(ME, "on");
    setKeptFor(ME);
    const opening = new QueryClient();
    await restore(opening, shelf);
    // Shown until the server answers, but never taken for its answer, though useMe waits a minute before asking again.
    expect(opening.getQueryData(["me"])).toEqual({ id: ME, preferences: { ratings: "pips" } });
    for (const key of [["me"], ["characters"]]) expect(opening.getQueryCache().find({ queryKey: key })!.isStaleByTime(60_000)).toBe(true);
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

describe("refreshing what's kept (#619)", () => {
  const TROUPE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
  const inTroupe = { ...rosa, home_troupe_id: TROUPE };
  afterEach(() => vi.useRealTimers());

  function online() {
    answers["/api/characters"] = [inTroupe];
    answers["/api/characters/{character_id}"] = { id: ROSA, splat: "vampire", home_troupe_id: TROUPE };
    answers["/api/troupes/{troupe_id}/posts"] = [];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    client.setQueryData(["me"], { id: ME });
    return client;
  }

  it("moves the time Updated when everything came", async () => {
    const shelf = memoryShelf();
    vi.setSystemTime(1000);
    const kept = await refresh(online(), ME, shelf);
    expect(kept).toMatchObject({ refreshedAt: 1000, partial: null });
  });

  it("keeps the time it last all came, and says how many didn't, when a sheet fails", async () => {
    const shelf = memoryShelf();
    const client = online();
    vi.setSystemTime(1000);
    await refresh(client, ME, shelf);
    client.setQueryData(["sheet", ROSA], { traits: ["Brawl"] });
    await save(client, ME, shelf);
    failing.add("/api/characters/{character_id}/sheet");
    vi.setSystemTime(2000);
    const kept = await refresh(client, ME, shelf);
    expect(kept).toMatchObject({ refreshedAt: 1000, partial: { failed: 1, triedAt: 2000 } });
    // What was kept for it before stays.
    const record = shelf.items.get(recordKey(ME)) as Kept;
    expect(record.queries.find((q) => q.queryKey[0] === "sheet")?.state.data).toEqual({ traits: ["Brawl"] });
  });

  it("is partial when a troupe's news fails too", async () => {
    const shelf = memoryShelf();
    failing.add("/api/troupes/{troupe_id}/posts?kind=news");
    vi.setSystemTime(2000);
    const kept = await refresh(online(), ME, shelf);
    expect(kept).toMatchObject({ refreshedAt: null, partial: { failed: 1, triedAt: 2000 } });
  });

  it("counts a character's catalogue and troupe as not refreshed when the character itself fails", async () => {
    failing.add("/api/characters/{character_id}");
    const kept = await refresh(online(), ME, memoryShelf());
    expect(kept?.partial?.failed).toBe(3);
  });

  it("clears the partial once a later refresh all comes", async () => {
    const shelf = memoryShelf();
    const client = online();
    failing.add("/api/characters/{character_id}/sheet");
    vi.setSystemTime(2000);
    await refresh(client, ME, shelf);
    // Written again as answers arrive, it still says so.
    expect(await save(client, ME, shelf)).toMatchObject({ partial: { failed: 1, triedAt: 2000 } });
    failing.clear();
    vi.setSystemTime(3000);
    const kept = await refresh(client, ME, shelf);
    expect(kept).toMatchObject({ refreshedAt: 3000, partial: null });
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

describe("a troupe's kept scenes", () => {
  const TROUPE = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
  const SCENE = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
  const NPC = "ffffffff-ffff-4fff-8fff-ffffffffffff";

  function running() {
    const client = signedIn();
    client.setQueryData(["troupe", TROUPE], { name: "Court of Ashes" });
    client.setQueryData(["scenes", TROUPE, false], [{ id: SCENE }]);
    client.setQueryData(["scene", SCENE], { id: SCENE, characters: [NPC, BRAM] });
    client.setQueryData(["play", NPC], { kind: "npc", blood: 5 });
    client.setQueryData(["play", BRAM], { kind: "pc", blood: 3 });
    client.setQueryData(["roster", TROUPE], [{ id: NPC }]);
    return client;
  }

  it("keeps the scenes, each card's Play View, PCs too, and nothing else of the troupe", async () => {
    const shelf = memoryShelf();
    const kept = await saveScenes(running(), ME, TROUPE, shelf, 1000);
    expect(kept).toMatchObject({ troupeName: "Court of Ashes", keptAt: 1000, sceneIds: [SCENE], cards: [NPC, BRAM], npcs: 1, pcs: 1 });
    const record = shelf.items.get(scenesKey(ME, TROUPE)) as KeptScenes;
    expect(record.queries.map((q) => q.queryKey[0]).sort()).toEqual(["play", "play", "scene", "scenes", "troupe"]);
    expect(keptTroupes(ME)).toEqual([TROUPE]);
    // Its cards' answers, when they change, are written again.
    expect(scenesTouched(["play", NPC])).toEqual([TROUPE]);
    expect(scenesTouched(["play", ROSA])).toEqual([]);
  });

  it("follows the line-up: a card taken off the scene goes from what's kept", async () => {
    const shelf = memoryShelf();
    const client = running();
    await saveScenes(client, ME, TROUPE, shelf);
    client.setQueryData(["scene", SCENE], { id: SCENE, characters: [NPC] });
    await saveScenes(client, ME, TROUPE, shelf);
    const record = shelf.items.get(scenesKey(ME, TROUPE)) as KeptScenes;
    expect(record.cards).toEqual([NPC]);
    expect(record.queries.some((q) => q.queryKey[1] === BRAM)).toBe(false);
  });

  it("goes back in the app as it opens, and goes with Remove, the device's setting, or signing out", async () => {
    const shelf = memoryShelf();
    await save(signedIn(), ME, shelf);
    await saveScenes(running(), ME, TROUPE, shelf);
    setKeeping(ME, "on");
    setKeptFor(ME);
    const opening = new QueryClient();
    await restore(opening, shelf);
    expect(opening.getQueryData(["play", NPC])).toEqual({ kind: "npc", blood: 5 });

    await removeScenes(ME, TROUPE, shelf);
    expect(shelf.items.has(scenesKey(ME, TROUPE))).toBe(false);
    expect(keptScenesSummary(TROUPE)).toBeNull();

    await saveScenes(running(), ME, TROUPE, shelf);
    await removeKept(ME, shelf);
    expect(shelf.items.has(scenesKey(ME, TROUPE))).toBe(false);
    expect(keptTroupes(ME)).toEqual([]);

    await saveScenes(running(), ME, TROUPE, shelf);
    await forget(signedIn(), ME, shelf);
    expect(shelf.items.has(scenesKey(ME, TROUPE))).toBe(false);
    expect(keptTroupes(ME)).toEqual([]);
  });
});
