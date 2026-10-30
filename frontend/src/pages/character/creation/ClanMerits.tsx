import { api, unwrap } from "../../../api/client";
import type { CatalogueOut, CharacterOut, ClanMeritOut } from "../../../api/types";
import { ErrorText, Select } from "../../../components/ui";
import { useAction } from "../../../hooks";
import { clanMeritWhy } from "./clanMerits";

/**
 * The merits the clan gives from the merit points, on Merits & flaws: ticked and fixed,
 * as the clan's rather than picks, each saying why. One that asks for a choice (a
 * Koldun's other path) asks for it here.
 */
export function ClanMerits({ character, merits, catalogue }: { character: CharacterOut; merits: ClanMeritOut[]; catalogue: CatalogueOut }) {
  const choose = useAction(({ name, detail }: { name: string; detail: string }) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/traits/detail", {
        params: { path: { character_id: character.id } },
        body: { category: "merits", name, detail },
      }),
    ),
  );
  if (!merits.length) return null;
  return (
    <section aria-label="From the clan" className="flex flex-col gap-1">
      <h4 className="text-xs text-mist">From the clan</h4>
      <ul className="flex flex-col gap-1">
        {merits.map((m) => {
          const choices = catalogue.traits.find((t) => t.category === "merits" && t.name === m.name)?.choices;
          return (
            <li key={m.name} className="flex items-start gap-2 rounded bg-ash/60 px-2 py-1.5 text-sm">
              <input type="checkbox" className="mt-1" checked disabled aria-label={`${m.name}, given by the clan`} />
              <span className="min-w-0">
                <span className="text-parchment">{m.name}</span> <span className="text-gold">({m.points})</span>
                <span className="mt-0.5 block text-xs text-mist">{clanMeritWhy(m)}</span>
                {!!choices?.length && (
                  <Select
                    aria-label={`${m.name}: which?`}
                    className="mt-1 h-8 w-auto py-0"
                    value={m.detail}
                    disabled={choose.isPending}
                    onChange={(e) => choose.mutate({ name: m.name, detail: e.target.value })}
                  >
                    <option value="">Which?</option>
                    {choices.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </Select>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <ErrorText error={choose.error} />
    </section>
  );
}
