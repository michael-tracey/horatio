import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { LocationOut } from "../../api/types";
import { Button, ErrorText, Field, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { removalText } from "../quests/locationQuests";

/**
 * Staff take one level of a negative off a location, for what the book asks at
 * its rating: Resources dots for Damaged, Elite influence for Insolvent and
 * Shunned, Underworld influence for Compromised and Out of Code (Vol. II Issue 1,
 * pp. 127-129). The influence goes in the troupe's influence log. Given a repair
 * request, it answers that too.
 */
export function RemoveNegative({ troupeId, location: l, requestId, payer }: { troupeId: string; location: LocationOut; requestId?: string; payer?: string }) {
  const [name, setName] = useState(l.negatives[0]?.name ?? "");
  const [who, setWho] = useState(payer ?? l.controller?.id ?? "");
  const characters = useQuery({
    queryKey: ["quest-characters", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/quest-characters", { params: { path: { troupe_id: troupeId } } })),
  });
  const remove = useAction(() =>
    unwrap(
      api.POST("/api/locations/{location_id}/negatives/remove", {
        params: { path: { location_id: l.id } },
        body: { name, character_id: who, request_id: requestId ?? null },
      }),
    ),
  );
  if (l.negatives.length === 0) return <p className="text-sm text-mist">{l.name} has no negative qualities.</p>;
  const chosen = l.negatives.find((n) => n.name === name) ?? l.negatives[0]!;
  return (
    <form
      aria-label={`Remove a negative from ${l.name}`}
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        remove.mutate(undefined);
      }}
    >
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Negative">
          <Select value={chosen.name} onChange={(e) => setName(e.target.value)} className="w-auto">
            {l.negatives.map((n) => (
              <option key={n.name} value={n.name}>
                {n.name}, at ×{n.level}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Paid by">
          <Select value={who} onChange={(e) => setWho(e.target.value)} className="w-auto">
            <option value="">Choose a character</option>
            {characters.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Button type="submit" variant="secondary" disabled={!who || !characters.data || remove.isPending}>
          Remove one level
        </Button>
      </div>
      <p className="text-xs text-mist">
        It takes {removalText(chosen.name, l.rating)}, at {l.name}'s rating.
      </p>
      <ErrorText error={remove.error ?? characters.error} />
    </form>
  );
}
