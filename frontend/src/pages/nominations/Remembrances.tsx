import { useQuery } from "@tanstack/react-query";
import { api, ApiError, unwrap } from "../../api/client";
import type { CharacterOut, CharacterRemembrancesOut } from "../../api/types";
import { Button, Card, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/** A character's remembrances, or null for someone who can't read them. */
function useRemembrances(characterId: string) {
  return useQuery({
    queryKey: ["remembrances", characterId],
    queryFn: async () => {
      try {
        return await unwrap(api.GET("/api/characters/{character_id}/remembrances", { params: { path: { character_id: characterId } } }));
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
  });
}

/**
 * Whether there is anything of them to show: those published, which stay whatever
 * the setting; and while the troupe uses them, that they are asked for or open, or
 * that the caller may open them.
 */
export function shownAt(r: CharacterRemembrancesOut | null | undefined): boolean {
  return !!r && (r.months.length > 0 || (r.on && (r.state !== "none" || r.can_open)));
}

/** Where the cycle that asks stands, in a sentence. */
function asking(r: CharacterRemembrancesOut, name: string): string {
  const where = r.cycle_name ? `in ${r.cycle_name}’s downtime` : "in the next downtime cycle that opens";
  if (r.state === "open") return `The troupe is asked for memories of ${name} ${where}.`;
  if (r.state === "asked") return `${name}’s player asked for remembrances.${r.can_open ? ` Opened now, they’re asked for ${where}.` : ""}`;
  return `Opened now, the troupe is asked for memories of ${name} ${where}.`;
}

/**
 * A retired character's remembrances (#471): whether they're open and in which
 * cycle, Open remembrances for the home troupe's running staff, and the memories
 * published, newest month first, without names.
 */
export function RemembrancesPanel({ characterId, name }: { characterId: string; name: string }) {
  const found = useRemembrances(characterId);
  const open = useAction(() => unwrap(api.POST("/api/characters/{character_id}/remembrances/open", { params: { path: { character_id: characterId } } })));
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const r = found.data;
  if (!shownAt(r)) return <p className="text-sm text-mist">No remembrances of {name}.</p>;
  return (
    <div className="flex flex-col gap-3">
      {r!.on && (r!.state !== "none" || r!.can_open) && <p className="text-sm text-mist">{asking(r!, name)}</p>}
      {r!.can_open && (
        <div>
          <Button variant="secondary" disabled={open.isPending} onClick={() => open.mutate(undefined)}>
            Open remembrances
          </Button>
          <ErrorText error={open.error} />
        </div>
      )}
      {r!.months.length === 0
        ? r!.state === "open" && <p className="text-sm text-mist">None published yet.</p>
        : r!.months.map((m) => (
            <section key={m.cycle_id} aria-label={`Remembrances of ${name}, ${m.month}`}>
              <h3 className="text-sm text-gold">{m.month}</h3>
              <ul className="divide-y divide-ash">
                {m.memories.map((memory) => (
                  <li key={memory.id} className="py-2">
                    <p className="whitespace-pre-line wrap-anywhere">{memory.text}</p>
                    {memory.edited && <p className="mt-0.5 text-xs text-mist">Edited by staff</p>}
                  </li>
                ))}
              </ul>
            </section>
          ))}
    </div>
  );
}

/** On a retired character's page, for its player and staff: its remembrances, kept for good. Nothing while there are none to show. */
export function RemembrancesCard({ character }: { character: CharacterOut }) {
  const found = useRemembrances(character.id);
  if (!shownAt(found.data)) return null;
  return (
    <Card dense className="mb-4" title="Remembrances">
      <RemembrancesPanel characterId={character.id} name={character.name} />
    </Card>
  );
}
