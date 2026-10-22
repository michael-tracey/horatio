import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card } from "../../components/ui";
import { useDates } from "../../dates";
import { lastsText } from "../../influenceEffects";

/** Attacks and Boosts holding on the character's influence now, and when they end. Shown only while there are any. */
export function InfluenceEffects({ characterId }: { characterId: string }) {
  const dates = useDates();
  const effects = useQuery({
    queryKey: ["influence-effects", "character", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/influence-effects", { params: { path: { character_id: characterId } } })),
  });
  if (!effects.data?.length) return null;
  return (
    <Card dense title="Influence changed">
      <ul className="flex flex-col gap-1 text-sm">
        {effects.data.map((e) => (
          <li key={`${e.kind}/${e.type}/${e.starts_at}`}>
            <span className={e.kind === "attack" ? "text-blood-bright" : "text-gold"}>{e.text}</span>
            <span className="text-mist">
              {" "}
              ({e.kind === "attack" ? "attacked" : "boosted"}), {lastsText(e, dates)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
