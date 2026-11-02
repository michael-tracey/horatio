import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, CreationOut, SheetOut } from "../../../api/types";
import { useClanName } from "../../../components/ClanNames";
import { Button, ErrorText } from "../../../components/ui";
import { useAction, useUnavailable } from "../../../hooks";
import { EXTRA_IN_CLAN, either, inClanChoice, inClanOptions, sheetKey, whenTapped } from "./inClan";
import { movePick, strayMoves } from "./disciplines";
import { traitOf, type Picks } from "./logic";
import { rulesTroupe } from "../rules";

const swap = (from: string, to: string) => [
  { kind: "set" as const, category: EXTRA_IN_CLAN, name: from, detail: "", rating: 0, teacher: "" },
  { kind: "set" as const, category: EXTRA_IN_CLAN, name: to, detail: "", rating: 1, teacher: "" },
];

/**
 * The in-clan disciplines a character chooses: a Caitiff's three (p. 246), and the
 * one a merit adds (pp. 242, 248). The server says which it may choose from. Ones
 * other traits give show as held. Tapping one the rules refuse as things stand
 * never just greys out: it offers the swaps that would make room (rule 3 of #192).
 * The one picker is shown on Concept, under the merit on Merits, on Disciplines
 * while a choice is open, and from Review (#216).
 */
export function InClanPicker({ character, sheet, catalogue }: { character: CharacterOut; sheet: SheetOut; catalogue: CatalogueOut }) {
  const choice = inClanChoice(sheet);
  // What nothing chosen here could allow is not offered at all. Both are asked for the
  // sheet as it is now: an answer from before a merit was taken (Vestiges of
  // Greatness, which opens the uncommon ones) is never offered as now's.
  const now = `${sheetKey(sheet)}/${rulesTroupe(character) ?? ""}`;
  const barring = useUnavailable(character.id, EXTRA_IN_CLAN, true, { asIf: "empty" }, now);
  const refusing = useUnavailable(character.id, EXTRA_IN_CLAN, true, undefined, now);
  const barred = barring.data;
  const refusals = refusing.data;
  const refused = refusals ?? {};
  const [wanted, setWanted] = useState<string | null>(null);
  const path = { params: { path: { character_id: character.id } } };
  const toggle = useAction((body: { name: string; on: boolean }) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        ...path,
        body: { category: EXTRA_IN_CLAN, name: body.name, detail: "", rating: body.on ? 1 : 0, teacher: "" },
      }),
    ),
  );
  const chosen = choice.chosen.map((t) => t.name);
  const given = new Map(choice.given.map((t) => [t.name, t.granted_by]));
  // For the one tapped: which of those chosen it could take the place of. The server tries
  // them all in one request on the sheet as read; a whole cart judged for each was dozens of
  // queries apiece, and on a busy server the buttons waited seconds for them (#386).
  // Keyed by the sheet, so a change (the swap itself) never has it asked again under the old key.
  const swaps = useQuery({
    queryKey: ["in-clan-swaps", character.id, wanted, now],
    enabled: !!wanted && chosen.length > 0,
    meta: { bySheet: true },
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/making-room", { params: { ...path.params, query: { category: EXTRA_IN_CLAN, name: wanted! } } })),
  });
  const swapIn = useAction(async (from: string) => {
    const out = await unwrap(api.POST("/api/characters/{character_id}/cart", { ...path, body: { changes: swap(from, wanted!), dry_run: false } }));
    if (!out.applied) throw new Error(out.lines.map((l) => l.refused).filter(Boolean).join(" "));
    setWanted(null);
  });

  // The choices wait until the server has said what it refuses: a tap before then would
  // be sent as a plain choice, and fail, instead of offering the swaps. Meanwhile, and
  // if asking fails, the picker still shows, so a merit's notice never points at nothing.
  const loaded = !!barred && !!refusals;
  // Loaded, but the answer is the one from before the sheet changed: shown, held, and said so.
  const checking = !loaded || barring.isPlaceholderData || refusing.isPlaceholderData;
  const names = catalogue.traits.filter((t) => t.category === EXTRA_IN_CLAN).map((t) => t.name);
  const options = loaded ? inClanOptions(names, choice, barred) : [];
  if (loaded && !options.length && !choice.chooses) return null;
  if (!loaded && !choice.chooses) return null;
  // Held, too, while the refusals are asked again after a change (taking the merit that
  // adds a choice): a tap on the answer from before would offer swaps it doesn't need.
  const busy = toggle.isPending || swapIn.isPending || checking || barring.isFetching || refusing.isFetching;
  return (
    <fieldset className="flex flex-col gap-2 rounded-md border border-ash p-3">
      <legend className="px-1 text-sm text-parchment">
        In-clan disciplines{choice.chooses ? ` (${chosen.length} of ${choice.chooses})` : ""}
      </legend>
      {choice.lines.map((line) => (
        <p key={line} className="text-xs text-mist">
          {line}
        </p>
      ))}
      {checking &&
        (barring.error || refusing.error ? (
          <ErrorText error={barring.error ?? refusing.error} />
        ) : (
          <p className="text-sm text-mist">Checking which you can choose…</p>
        ))}
      <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
        {options.map((name) => {
          const from = given.get(name);
          const held = chosen.includes(name) || !!from;
          return (
            <label key={name} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={held}
                disabled={busy || !!from}
                onChange={(e) => {
                  if (!e.target.checked) return toggle.mutate({ name, on: false });
                  if (whenTapped(name, refused) === "swap") return setWanted(name);
                  setWanted(null);
                  toggle.mutate({ name, on: true });
                }}
              />
              <span>
                {name}
                {from && <span className="text-xs text-mist"> (from {from.join(", ")})</span>}
              </span>
            </label>
          );
        })}
      </div>
      {wanted && (
        <div role="group" aria-label={`Make room for ${wanted}`} className="flex flex-col gap-2 rounded-md border border-gold/40 bg-gold/10 p-3 text-sm">
          <p>{refused[wanted]}</p>
          {swaps.data?.length ? (
            <>
              <p className="text-mist">Swap one for {wanted}:</p>
              <div className="flex flex-wrap gap-2">
                {swaps.data.map((from) => (
                  <Button key={from} variant="secondary" disabled={busy} onClick={() => swapIn.mutate(from)}>
                    Swap {from} for {wanted}
                  </Button>
                ))}
              </div>
            </>
          ) : swaps.isFetching ? null : swaps.error ? (
            <ErrorText error={swaps.error} />
          ) : (
            <p className="text-mist">No swap makes room for it. Untick one to choose another.</p>
          )}
          <div>
            <Button variant="ghost" onClick={() => setWanted(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      <ErrorText error={toggle.error ?? swapIn.error} />
    </fieldset>
  );
}

/**
 * The in-clan discipline a clan leaves its player to choose (Angelis Ater: Potence,
 * Presence or Obfuscate, p. 72), kept as the clan's detail. The server says which clan
 * has one and what it is from (`creation.clan_choice`). Shown on Concept, on Disciplines
 * while it is open, and from Review.
 */
export function ClanChoice({ character, creation, catalogue }: { character: CharacterOut; creation: CreationOut; catalogue: CatalogueOut }) {
  const choice = creation.clan_choice;
  // The one tapped shows as chosen at once, while it is saved and the sheet read again.
  const [tapped, setTapped] = useState<string | null>(null);
  const named = useClanName();
  const choose = useAction((detail: string) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        params: { path: { character_id: character.id } },
        body: { category: "clan", name: choice!.clan, detail, rating: null, teacher: "" },
      }),
    ),
  );
  if (!choice) return null;
  const chosen = tapped ?? choice.chosen;
  const own = catalogue.traits.find((t) => t.category === "clan" && t.name === choice.clan)?.in_clan ?? [];
  const page = choice.page ? ` (p. ${choice.page})` : "";
  return (
    <fieldset className="flex flex-col gap-2 rounded-md border border-ash p-3">
      <legend className="px-1 text-sm text-parchment">In-clan choice{chosen ? "" : " (0 of 1)"}</legend>
      <p className="text-xs text-mist">
        {named(choice.clan)}: {own.length
 ? `${own.join(", ")}, and one of ` : "one of "}
        {either(choice.choices)}
        {page}.
      </p>
      <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
        {choice.choices.map((name) => (
          <label key={name} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name={`clan-choice-${character.id}`}
              checked={chosen === name}
              disabled={choose.isPending}
              onChange={() => {
                setTapped(name);
                choose.mutate(name, { onSettled: () => setTapped(null) });
              }}
            />
            <span>{name}</span>
          </label>
        ))}
      </div>
      <ErrorText error={choose.error} />
    </fieldset>
  );
}

/**
 * After a swap on the picker, the starting dots on the discipline swapped out are
 * kept, not dropped (rule 4 of #192): offered here to move to the new in-clan one at
 * a tap, at the same rating. `picks` are the Disciplines step's, as tapped so far.
 */
export function MoveStartingDots({ character, creation, picks }: { character: CharacterOut; creation: CreationOut; picks: Picks }) {
  const move = useAction((next: Picks) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/creation/categories/{category}", {
        params: { path: { character_id: character.id, category: "disciplines" } },
        body: { picks: Object.entries(next).map(([key, rating]) => ({ name: traitOf(key), rating, detail: "" })) },
      }),
    ),
  );
  const moves = strayMoves(creation).filter((m) => m.from in picks && m.to.length);
  if (!moves.length) return null;
  return (
    <div role="group" aria-label="Starting dots to move" className="flex flex-col gap-2 rounded-md border border-gold/40 bg-gold/10 p-3 text-sm">
      {moves.map((m) => (
        <div key={m.from} className="flex flex-col gap-1">
          <p>
            Your starting {m.rating === 1 ? "dot" : "dots"} in {m.from} can move to {m.to.length === 1 ? m.to[0] : "another in-clan discipline"}, at {m.rating}.
          </p>
          <div className="flex flex-wrap gap-2">
            {m.to.map((to) => (
              <Button key={to} variant="secondary" disabled={move.isPending} onClick={() => move.mutate(movePick(picks, m.from, to))}>
                Move the {m.rating === 1 ? "dot" : "dots"} from {m.from} to {to}
              </Button>
            ))}
          </div>
        </div>
      ))}
      <ErrorText error={move.error} />
    </div>
  );
}
