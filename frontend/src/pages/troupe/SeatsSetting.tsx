import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * Which clans have a seat at the troupe's court (issue #267). Until staff choose,
 * the clans whose Primogen is held here do, or every clan where no one holds it.
 * On the Who's Who, characters of the others are under Other, each with who
 * represents them.
 */
export function SeatsSetting({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const seats = useQuery({ queryKey: ["seats", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/seats", path)) });
  const save = useAction((clans: string[] | null) => unwrap(api.PUT("/api/troupes/{troupe_id}/seats", { ...path, body: { clans } })));
  if (seats.isPending) return <Loading />;
  if (seats.error) return <ErrorText error={seats.error} />;
  const { clans, seated, chosen, primogen } = seats.data;
  const now = seated ?? clans;
  const toggle = (clan: string, on: boolean) => save.mutate(on ? [...now, clan] : now.filter((c) => c !== clan));
  return (
    <Card title="Seats at court">
      <p className="mb-2 text-sm text-mist">
        On the Who’s Who, characters of a clan without a seat are under Other, each with the clan or group that represents them. This is the court’s
        custom, not the sect’s rules.
      </p>
      <p className="mb-3 text-sm">
        {chosen
          ? "You chose these clans."
          : primogen.length > 0
            ? "Until you choose, the clans whose Primogen is held here have a seat."
            : "Until you choose, every clan has a seat, as no one holds Primogen here."}
      </p>
      <fieldset aria-label="Clans with a seat at court" className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-3">
        {clans.map((clan) => {
          const on = now.includes(clan);
          return (
            <label key={clan} className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={on}
                // At least one clan keeps a seat.
                disabled={save.isPending || (on && now.length === 1)}
                onChange={(e) => toggle(clan, e.target.checked)}
              />
              {clan}
            </label>
          );
        })}
      </fieldset>
      {chosen && (
        <Button variant="secondary" className="mt-3" disabled={save.isPending} onClick={() => save.mutate(null)}>
          Go back to who holds Primogen
        </Button>
      )}
      <ErrorText error={save.error} />
    </Card>
  );
}
