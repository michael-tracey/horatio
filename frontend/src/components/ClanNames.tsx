import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, type ReactNode } from "react";
import { useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { clanNamed, DEFAULT_CLAN_NAME, type ClanName } from "../clanNames";

const Named = createContext<ClanName>(DEFAULT_CLAN_NAME);

/**
 * What the clan stored as "Assamite" is called in what it holds (#430): set once for
 * the troupe or character a page is about (App's routes, a cycle's page, the rules
 * browser), and read with `useClanName` by whatever shows a trait, a clan or rules
 * text. Outside any troupe it is the default, Banu Haqim.
 */
export function ClanNames({ name, children }: { name: ClanName | null | undefined; children: ReactNode }) {
  return <Named.Provider value={name ?? DEFAULT_CLAN_NAME}>{children}</Named.Provider>;
}

/** What the troupe calls the clan; the default for no troupe, or while it loads. */
export function useTroupeClanName(troupeId: string | null | undefined): ClanName {
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId! } } })),
    enabled: !!troupeId,
  });
  return troupe.data?.assamite_name ?? DEFAULT_CLAN_NAME;
}

/** `ClanNames` for the troupe with this id, or for no troupe. */
export function TroupeClanNames({ troupeId, children }: { troupeId: string | null | undefined; children: ReactNode }) {
  return <ClanNames name={useTroupeClanName(troupeId)}>{children}</ClanNames>;
}

/**
 * A function showing a stored name or rules text as the troupe calls the clan:
 * "Assamite: Vizier" is "Banu Haqim: Vizier" in a troupe that calls it Banu Haqim.
 * For what is shown only: keys, values sent back and what was written in the past
 * (the log, XP and downtime results) keep the stored name.
 */
export function useClanName(): <T extends string | null | undefined>(text: T) => T {
  const name = useContext(Named);
  return useCallback(<T extends string | null | undefined>(text: T): T => (text ? (clanNamed(text, name) as T) : text), [name]);
}

/** `ClanNames` for the troupe a route names (`:troupeId`): App sets it around a troupe's pages. */
export function TroupeRouteClanNames({ children }: { children: ReactNode }) {
  const { troupeId } = useParams();
  return <TroupeClanNames troupeId={troupeId}>{children}</TroupeClanNames>;
}

/**
 * `ClanNames` for the character a route names (`:characterId`): as the troupe whose
 * rules it plays by calls the clan, which comes with the character. App sets it
 * around a character's pages.
 */
export function CharacterRouteClanNames({ children }: { children: ReactNode }) {
  const { characterId = "" } = useParams();
  const character = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}", { params: { path: { character_id: characterId } } })),
    enabled: !!characterId,
  });
  return <ClanNames name={character.data?.assamite_name}>{children}</ClanNames>;
}
