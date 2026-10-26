import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, SheetOut } from "../../../api/types";
import { Button, ErrorText } from "../../../components/ui";
import { useAction, useUnavailable } from "../../../hooks";
import { EXTRA_IN_CLAN, inClanChoice } from "./inClan";

const swap = (from: string, to: string) => [
  { kind: "set" as const, category: EXTRA_IN_CLAN, name: from, detail: "", rating: 0, teacher: "" },
  { kind: "set" as const, category: EXTRA_IN_CLAN, name: to, detail: "", rating: 1, teacher: "" },
];

/**
 * The in-clan disciplines a character chooses: a Caitiff's three (p. 246), and the
 * one a merit adds (pp. 242, 248). The server says which it may choose from. Ones
 * other traits give show as held. Tapping one the rules refuse as things stand
 * never just greys out: it offers the swaps that would make room (rule 3 of #192).
 */
export function InClanPicker({ character, sheet, catalogue }: { character: CharacterOut; sheet: SheetOut; catalogue: CatalogueOut }) {
  const choice = inClanChoice(sheet);
  // What nothing chosen here could allow is not offered at all.
  const barred = useUnavailable(character.id, EXTRA_IN_CLAN, true, { asIf: "empty" }).data;
  const refused = useUnavailable(character.id, EXTRA_IN_CLAN).data ?? {};
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
  // For the one tapped: which of those chosen it could take the place of, tried on the server.
  const swaps = useQuery({
    queryKey: ["in-clan-swaps", character.id, wanted, chosen],
    enabled: !!wanted && chosen.length > 0,
    queryFn: async () => {
      const tried = await Promise.all(
        chosen.map(async (from) => {
          const out = await unwrap(api.POST("/api/characters/{character_id}/cart", { ...path, body: { changes: swap(from, wanted!), dry_run: true } }));
          return out.lines.every((l) => !l.refused) ? from : null;
        }),
      );
      return tried.filter((n): n is string => !!n);
    },
  });
  const swapIn = useAction(async (from: string) => {
    const out = await unwrap(api.POST("/api/characters/{character_id}/cart", { ...path, body: { changes: swap(from, wanted!), dry_run: false } }));
    if (!out.applied) throw new Error(out.lines.map((l) => l.refused).filter(Boolean).join(" "));
    setWanted(null);
  });

  if (!barred) return null;
  const options = catalogue.traits.filter((t) => t.category === EXTRA_IN_CLAN && (chosen.includes(t.name) || given.has(t.name) || !(t.name in barred)));
  if (!options.length && !choice.chooses) return null;
  const busy = toggle.isPending || swapIn.isPending;
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
      <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
        {options.map((t) => {
          const from = given.get(t.name);
          const held = chosen.includes(t.name) || !!from;
          return (
            <label key={t.name} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={held}
                disabled={busy || !!from}
                onChange={(e) => {
                  if (!e.target.checked) return toggle.mutate({ name: t.name, on: false });
                  if (t.name in refused) return setWanted(t.name);
                  setWanted(null);
                  toggle.mutate({ name: t.name, on: true });
                }}
              />
              <span>
                {t.name}
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
          ) : swaps.isFetching ? null : (
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
