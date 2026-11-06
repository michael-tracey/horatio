import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Button, Card } from "../../components/ui";

/** How many show before "Show all". */
const FIRST = 3;

/**
 * For its player, the published Player Nominations linked to the character (#470),
 * newest month first, without their authors. Nothing while there are none.
 */
export function NominationsAbout({ character }: { character: CharacterOut }) {
  const about = useQuery({
    queryKey: ["nominations-about", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/nominations", { params: { path: { character_id: character.id } } })),
  });
  const [all, setAll] = useState(false);
  const found = about.data ?? [];
  if (!found.length) return null;
  const shown = all ? found : found.slice(0, FIRST);
  return (
    <Card title={`Nominations about ${character.name}`} className="mb-4">
      <ul className="divide-y divide-ash">
        {shown.map((n) => (
          <li key={n.id} className="py-2">
            <p className="whitespace-pre-line wrap-anywhere">{n.text}</p>
            <p className="mt-0.5 text-xs text-mist">
              {n.troupe_name}, {n.month}
            </p>
          </li>
        ))}
      </ul>
      {found.length > FIRST && (
        <Button variant="ghost" className="mt-2" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${found.length}`}
        </Button>
      )}
    </Card>
  );
}
