import { dehydrate, hydrate, type DehydratedState, type QueryClient } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import type { CharacterListOut, Me, PlayView, SceneOut } from "../api/types";
import { rulesTroupe } from "../pages/character/rules";
import {
  clearDevice,
  keepsQuery,
  keepsSceneQuery,
  keptCharacters,
  keptFor,
  keptTroupes,
  mineOf,
  recordKey,
  scenesKey,
  setKeeping,
  setKeptFor,
  setKeptTroupes,
  type Mine,
  type SceneSet,
} from "./keep";
import { indexedShelf, type Shelf } from "./shelf";

/**
 * A person's kept answers (#502): what the app had for their own characters, put
 * back in its cache as it opens, so the screens that use them work with no signal.
 * The rules for what is kept are keep.ts's.
 */

type Queries = DehydratedState["queries"];

export type Kept = {
  /** When it was last written. */
  savedAt: number;
  /** When every kept character was last asked for afresh (Update now, or opening the app). */
  refreshedAt: number | null;
  characters: { id: string; name: string }[];
  troupes: string[];
  queries: Queries;
  /** Roughly how much space it takes. */
  bytes: number;
};

/** What Account › This device shows: a person's kept answers, without the answers. */
export type KeptSummary = Omit<Kept, "queries">;

// --- Telling the screens ------------------------------------------------------

let summary: KeptSummary | null = null;
let version = 0;
const listeners = new Set<() => void>();

function told(next: KeptSummary | null | undefined) {
  if (next !== undefined) summary = next;
  version += 1;
  for (const listener of listeners) listener();
}

/** Something kept, or a choice about it, changed. */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Changes whenever `subscribe` tells: for screens that read the device's choices. */
export function keptVersion(): number {
  return version;
}

export function keptSummary(): KeptSummary | null {
  return summary;
}

/** The device's choices changed (a setting turned on or off): screens read them again. */
export function choicesChanged(): void {
  told(undefined);
}

function summarise({ queries: _, ...rest }: Kept): KeptSummary {
  return rest;
}

// --- Opening, keeping and clearing --------------------------------------------

/** Who the answers restored as the app opened belong to, until they are on screen for them. */
let restored: string | null = null;

/** As the app opens: put back the answers kept for whoever last kept theirs here. */
export async function restore(client: QueryClient, shelf: Shelf = indexedShelf, storage: Storage | undefined = globalThis.localStorage): Promise<string | null> {
  const who = keptFor(storage);
  if (!who) return null;
  const kept = await shelf.get<Kept>(recordKey(who));
  if (!kept) return null;
  // Kept answers stay in memory while the app is open, whether a screen shows them or not.
  const options = { defaultOptions: { queries: { gcTime: Infinity } } };
  hydrate(client, { queries: kept.queries, mutations: [] }, options);
  for (const troupeId of keptTroupes(who, storage)) {
    const scenes = await shelf.get<KeptScenes>(scenesKey(who, troupeId));
    if (!scenes) continue;
    hydrate(client, { queries: scenes.queries, mutations: [] }, options);
    sceneSummaries.set(troupeId, summariseScenes(scenes));
  }
  restored = who;
  told(summarise(kept));
  return who;
}

/** The person signed in is not whose answers were restored (their session ended): take them off screen. */
export function dropRestored(client: QueryClient, signedIn: string | null): void {
  if (!restored || restored === signedIn) return;
  restored = null;
  client.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
}

/** Read a person's kept answers, for Account › This device. */
export async function loadSummary(userId: string, shelf: Shelf = indexedShelf): Promise<KeptSummary | null> {
  const kept = await shelf.get<Kept>(recordKey(userId));
  const found = kept ? summarise(kept) : null;
  sceneSummaries.clear();
  for (const troupeId of keptTroupes(userId)) {
    const scenes = await shelf.get<KeptScenes>(scenesKey(userId, troupeId));
    if (scenes) sceneSummaries.set(troupeId, summariseScenes(scenes));
  }
  told(found);
  return found;
}

/** Write what the app has now for a person's own characters, keeping what it had before for those not on screen. */
export async function save(client: QueryClient, userId: string, shelf: Shelf = indexedShelf, refreshedAt?: number): Promise<KeptSummary | null> {
  // Only ever the signed-in person's own answers, under their own key.
  if (client.getQueryData<Me | null>(["me"])?.id !== userId) return null;
  const before = await shelf.get<Kept>(recordKey(userId));
  const list = client.getQueryData<CharacterListOut[]>(["characters"]);
  const mine: Mine = list ? mineOf(list, userId) : { characters: new Set(before?.characters.map((c) => c.id)), troupes: new Set(before?.troupes) };
  const now = dehydrate(client, { shouldDehydrateQuery: (q) => q.state.status === "success" && keepsQuery(q.queryKey, mine) }).queries;
  const queries = new Map<string, Queries[number]>();
  for (const q of before?.queries ?? []) if (keepsQuery(q.queryKey, mine)) queries.set(q.queryHash, q);
  for (const q of now) queries.set(q.queryHash, { ...q, promise: undefined });
  const kept: Omit<Kept, "bytes"> = {
    savedAt: Date.now(),
    refreshedAt: refreshedAt ?? before?.refreshedAt ?? null,
    characters: list ? keptCharacters(list, userId).map((c) => ({ id: c.id, name: c.name })) : (before?.characters ?? []),
    troupes: [...mine.troupes],
    queries: [...queries.values()],
  };
  const record: Kept = { ...kept, bytes: new Blob([JSON.stringify(kept)]).size };
  await shelf.put(recordKey(userId), record);
  const found = summarise(record);
  told(found);
  return found;
}

/** Ask afresh for everything kept for each of the person's characters, then keep it. Needs a connection. */
export async function refresh(client: QueryClient, userId: string, shelf: Shelf = indexedShelf): Promise<KeptSummary | null> {
  const fetch = <T>(queryKey: unknown[], queryFn: () => Promise<T>) => client.fetchQuery({ queryKey, queryFn, staleTime: 0 });
  const list = await fetch(["characters"], () => unwrap(api.GET("/api/characters")));
  await Promise.allSettled([fetch(["troupes"], () => unwrap(api.GET("/api/troupes"))), fetch(["splats"], () => unwrap(api.GET("/api/rules")))]);
  // One character at a time: the API is one process, and this is not what anyone is waiting on.
  for (const c of keptCharacters(list, userId)) {
    const path = { params: { path: { character_id: c.id } } };
    const [character] = await Promise.allSettled([
      fetch(["character", c.id], () => unwrap(api.GET("/api/characters/{character_id}", path))),
      fetch(["sheet", c.id], () => unwrap(api.GET("/api/characters/{character_id}/sheet", path))),
      fetch(["play", c.id], () => unwrap(api.GET("/api/characters/{character_id}/play", path))),
      fetch(["play-reference", c.id], () => unwrap(api.GET("/api/characters/{character_id}/play/reference", path))),
      fetch(["character-equipment", c.id], () => unwrap(api.GET("/api/characters/{character_id}/equipment", path))),
    ]);
    if (character.status !== "fulfilled") continue;
    const troupeId = rulesTroupe(character.value);
    const splat = character.value.splat;
    await Promise.allSettled([
      fetch(["catalogue", splat, troupeId], () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat }, query: { troupe_id: troupeId } } }))),
      ...(c.home_troupe_id ? [fetch(["troupe", c.home_troupe_id], () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: c.home_troupe_id! } } })))] : []),
    ]);
  }
  return save(client, userId, shelf, Date.now());
}

/** Account › This device's Remove: the person's kept answers go, and nothing more is kept here until they turn it on again. */
export async function removeKept(userId: string, shelf: Shelf = indexedShelf, storage: Storage | undefined = globalThis.localStorage): Promise<void> {
  setKeeping(userId, "off", storage);
  setKeptFor(null, storage);
  await shelf.remove(recordKey(userId));
  // Kept scenes need the device's setting: they go with it.
  await removeAllScenes(userId, shelf, storage);
  told(null);
}

/** Signing out: everything kept for the person on this device goes, unsent taps too, and the app forgets every answer it has. */
export async function forget(client: QueryClient, userId: string, shelf: Shelf = indexedShelf, storage: Storage | undefined = globalThis.localStorage): Promise<void> {
  clearDevice(storage);
  await shelf.remove(recordKey(userId));
  await removeAllScenes(userId, shelf, storage);
  restored = null;
  client.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
  client.setQueryData(["me"], null);
  told(null);
}

// --- A troupe's scenes, kept by its running staff (#503) ---------------------------

export type KeptScenes = {
  troupeId: string;
  troupeName: string;
  /** When the whole troupe's scenes were last asked for afresh (Keep, or Update). */
  keptAt: number;
  savedAt: number;
  sceneIds: string[];
  cards: string[];
  /** The cards' characters, as "3 scenes, 14 NPCs" counts them. */
  npcs: number;
  pcs: number;
  queries: Queries;
  bytes: number;
};

export type KeptScenesSummary = Omit<KeptScenes, "queries">;

const sceneSummaries = new Map<string, KeptScenesSummary>();

function summariseScenes({ queries: _, ...rest }: KeptScenes): KeptScenesSummary {
  return rest;
}

/** A troupe's kept scenes, as its Scenes page and Account › This device say them. */
export function keptScenesSummary(troupeId: string): KeptScenesSummary | null {
  return sceneSummaries.get(troupeId) ?? null;
}

export function keptScenesSummaries(): KeptScenesSummary[] {
  return [...sceneSummaries.values()];
}

/** The troupes whose kept scenes a query's answer belongs with: written again when it changes. */
export function scenesTouched(key: readonly unknown[]): string[] {
  return [...sceneSummaries.values()].filter((k) => keepsSceneQuery(key, setOf(k))).map((k) => k.troupeId);
}

function setOf(k: Pick<KeptScenes, "troupeId" | "sceneIds" | "cards">): SceneSet {
  return { troupe: k.troupeId, scenes: new Set(k.sceneIds), cards: new Set(k.cards) };
}

/** Write what the app has now for a troupe's scenes, keeping what it had for those not on screen.
 * The scenes are the troupe's list's, and the cards those scenes hold, as the server last said. */
export async function saveScenes(client: QueryClient, userId: string, troupeId: string, shelf: Shelf = indexedShelf, keptAt?: number): Promise<KeptScenesSummary | null> {
  if (client.getQueryData<Me | null>(["me"])?.id !== userId) return null;
  const before = await shelf.get<KeptScenes>(scenesKey(userId, troupeId));
  // Every scene, as the All list last said, and any of the person's own made since.
  const all = client.getQueryData<{ id: string }[]>(["scenes", troupeId, false]);
  const mine = client.getQueryData<{ id: string }[]>(["scenes", troupeId, true]) ?? [];
  const sceneIds = [...new Set([...(all ? all.map((s) => s.id) : (before?.sceneIds ?? [])), ...mine.map((s) => s.id)])];
  const cards = [
    ...new Set(sceneIds.flatMap((id) => client.getQueryData<SceneOut>(["scene", id])?.characters ?? (before?.queries.find((q) => q.queryKey[0] === "scene" && q.queryKey[1] === id)?.state.data as SceneOut | undefined)?.characters ?? [])),
  ];
  const kept = setOf({ troupeId, sceneIds, cards });
  const now = dehydrate(client, { shouldDehydrateQuery: (q) => q.state.status === "success" && keepsSceneQuery(q.queryKey, kept) }).queries;
  const queries = new Map<string, Queries[number]>();
  for (const q of before?.queries ?? []) if (keepsSceneQuery(q.queryKey, kept)) queries.set(q.queryHash, q);
  for (const q of now) queries.set(q.queryHash, { ...q, promise: undefined });
  const plays = [...queries.values()].filter((q) => q.queryKey[0] === "play").map((q) => q.state.data as PlayView | undefined);
  const record: Omit<KeptScenes, "bytes"> = {
    troupeId,
    troupeName: client.getQueryData<{ name: string }>(["troupe", troupeId])?.name ?? before?.troupeName ?? "",
    keptAt: keptAt ?? before?.keptAt ?? Date.now(),
    savedAt: Date.now(),
    sceneIds,
    cards,
    npcs: plays.filter((p) => p?.kind === "npc").length,
    pcs: plays.filter((p) => p?.kind === "pc").length,
    queries: [...queries.values()],
  };
  const full: KeptScenes = { ...record, bytes: new Blob([JSON.stringify(record)]).size };
  await shelf.put(scenesKey(userId, troupeId), full);
  setKeptTroupes(userId, [...keptTroupes(userId), troupeId]);
  const found = summariseScenes(full);
  sceneSummaries.set(troupeId, found);
  told(undefined);
  return found;
}

/** Keep (or update) a troupe's scenes on this device: one request for all of them, then
 * each scene, card and stat block is put in the app's cache as its screen asks for it. */
export async function keepScenes(client: QueryClient, userId: string, troupeId: string, shelf: Shelf = indexedShelf): Promise<KeptScenesSummary | null> {
  const path = { params: { path: { troupe_id: troupeId } } };
  const [bundle] = await Promise.all([
    unwrap(api.GET("/api/troupes/{troupe_id}/scenes/kept", path)),
    client.fetchQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)), staleTime: 0 }),
  ]);
  client.setQueryData(["scenes", troupeId, false], bundle.scenes);
  client.setQueryData(
    ["scenes", troupeId, true],
    bundle.scenes.filter((s) => s.mine),
  );
  for (const scene of bundle.scenes) client.setQueryData(["scene", scene.id], scene);
  for (const card of bundle.cards) {
    client.setQueryData(["play", card.character_id], card.play);
    if (card.reference) client.setQueryData(["play-reference", card.character_id], card.reference);
  }
  return saveScenes(client, userId, troupeId, shelf, Date.now());
}

/** A troupe's kept scenes off the device. */
export async function removeScenes(userId: string, troupeId: string, shelf: Shelf = indexedShelf, storage: Storage | undefined = globalThis.localStorage): Promise<void> {
  setKeptTroupes(
    userId,
    keptTroupes(userId, storage).filter((t) => t !== troupeId),
    storage,
  );
  await shelf.remove(scenesKey(userId, troupeId));
  sceneSummaries.delete(troupeId);
  told(undefined);
}

async function removeAllScenes(userId: string, shelf: Shelf, storage: Storage | undefined) {
  for (const troupeId of keptTroupes(userId, storage)) await shelf.remove(scenesKey(userId, troupeId));
  setKeptTroupes(userId, [], storage);
  sceneSummaries.clear();
}
