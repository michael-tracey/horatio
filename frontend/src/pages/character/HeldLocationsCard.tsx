import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card } from "../../components/ui";
import { effectText } from "../quests/locationQuests";

/**
 * The locations the character controls, by name only, and what their qualities
 * give it: "Resources 1, from Ruby's Bar (Profitable)". Its player isn't told why
 * one is switched off; staff are. Shown only once it controls one.
 */
export function HeldLocationsCard({ characterId, mine }: { characterId: string; mine: boolean }) {
  const held = useQuery({
    queryKey: ["held-locations", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/held-locations", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
  const found = held.data?.locations ?? [];
  if (found.length === 0) return null;
  return (
    <Card dense title={mine ? "Locations" : "What its locations give"}>
      <ul aria-label="Locations held" className="flex flex-col gap-2 text-sm">
        {found.map((l) => (
          <li key={l.id}>
            <span className="text-parchment">{l.name}</span>
            {l.joint && <span className="text-mist"> · jointly</span>}
            {l.effects.length > 0 && (
              <ul className="mt-1 flex flex-col gap-0.5 pl-3">
                {l.effects.map((e, i) => (
                  <li key={i} className={e.on ? "" : "text-mist"}>
                    {effectText(l.name, e)}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
