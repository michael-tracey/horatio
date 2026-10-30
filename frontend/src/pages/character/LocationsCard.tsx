import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { Card } from "../../components/ui";

/**
 * For staff: how many locations the character controls, of how many it may, and
 * which, in the troupes they keep locations for. Shown only once it controls one;
 * its player never sees it.
 */
export function LocationsCard({ characterId }: { characterId: string }) {
  const control = useQuery({
    queryKey: ["character-locations", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/locations", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
  if (!control.data || (control.data.locations.length === 0 && control.data.elsewhere === 0)) return null;
  const c = control.data;
  return (
    <Card dense title="Locations">
      <p className={`text-sm ${c.over ? "text-blood-bright" : ""}`}>
        Controls {c.controls} of {c.limit} {c.limit === 1 ? "location" : "locations"}
        {c.over ? ", over the limit" : ""}. <span className="text-mist">The limit: {c.why}.</span>
      </p>
      <ul className="mt-2 flex flex-col gap-1 text-sm">
        {c.locations.map((l) => (
          <li key={l.id}>
            <Link to={`/troupes/${l.troupe_id}/locations/${l.id}`} className="text-gold hover:text-parchment">
              {l.name}
            </Link>
            {l.joint && <span className="text-mist"> · jointly</span>}
            {l.not_counted && <span className="text-mist"> · not counted: {l.not_counted}</span>}
          </li>
        ))}
      </ul>
      {c.elsewhere > 0 && <p className="mt-1 text-xs text-mist">And {c.elsewhere} in troupes you don't keep locations for.</p>}
    </Card>
  );
}
