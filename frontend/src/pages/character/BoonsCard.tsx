import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import { BOON_PAGE, countsText } from "../../boons";
import { InfoButton } from "../../components/InfoButton";
import { Card } from "../../components/ui";

/**
 * The boons still standing a character owes and is owed, by kind, for the running
 * staff of each troupe whose boon ledger they keep (#685), with a link to that
 * ledger narrowed to the character. Players see nothing here yet (#686). Shown only
 * to staff, and only while a troupe keeps a ledger.
 */
export function BoonsCard({ characterId }: { characterId: string }) {
  const boons = useQuery({
    queryKey: ["character-boons", characterId],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/boons", {
          params: { path: { character_id: characterId } },
        }),
      ),
    retry: false,
  });
  const troupes = boons.data?.troupes ?? [];
  if (troupes.length === 0) return null;
  return (
    <Card
      dense
      title="Boons"
      info={
        <InfoButton label="About boons">
          <span className="block">The debts characters owe each other, registered with the Harpy: trivial, minor, major, blood or life.</span>
          <span className="mt-1 block text-mist">{BOON_PAGE}</span>
        </InfoButton>
      }
    >
      <ul className="flex flex-col gap-2 text-sm">
        {troupes.map((t) => (
          <li key={t.troupe_id} aria-label={`Boons in ${t.troupe_name}`}>
            {troupes.length > 1 && <p className="text-xs tracking-wide text-mist uppercase">{t.troupe_name}</p>}
            <p>
              <span className="text-mist">Owes: </span>
              {countsText(t.owes)}
            </p>
            <p>
              <span className="text-mist">Is owed: </span>
              {countsText(t.owed)}
            </p>
            <Link to={`/troupes/${t.troupe_id}/boons?character=${characterId}`} className="text-mist underline hover:text-parchment">
              In the boon ledger
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
