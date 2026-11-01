import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

type Setting = { feeding: TroupeOut["feeding"]; resonance: boolean };

const MODES: { value: "off" | "book"; label: string; meaning: string }[] = [
  {
    value: "off",
    label: "Don't track feeding",
    meaning: "No Feeding section on the downtime form, no Feeding tab on a cycle, nothing in the results, and no half Blood at the next game.",
  },
  {
    value: "book",
    label: "Book feeding",
    meaning: "Each clan needs a number of feeding actions a cycle, Herd and some traits change it, and staff answer full or half Blood for the next game.",
  },
];

/** What a change did, for the toast. */
export function feedingChangeText(before: Setting, after: Setting): string {
  if (after.feeding === "off") return "Feeding isn't tracked now. What was recorded is kept, for if you switch it back on.";
  if (before.feeding === "off") return "Feeding is tracked again, with what was recorded before.";
  return after.resonance ? "Blood Resonance is on." : "Blood Resonance is off.";
}

/**
 * How far Horatio handles feeding between games: not at all, as the core book has it
 * (the default), or with the optional Vol. 2 rules, each its own switch. Switching
 * feeding off only hides it: what was recorded stays and comes back.
 */
export function FeedingSetting({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const toast = useToast();
  const save = useAction(async ({ before, after }: { before: Setting; after: Setting }) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/feeding", { ...path, body: after }));
    toast({ message: feedingChangeText(before, after) });
  });
  if (!troupe.data) return null;
  const now: Setting = { feeding: troupe.data.feeding ?? "book", resonance: troupe.data.feeding_resonance ?? false };
  const off = now.feeding === "off";
  const change = (after: Partial<Setting>) => save.mutate({ before: now, after: { ...now, ...after } });
  const mode = MODES.find((m) => m.value === now.feeding) ?? MODES[1]!;

  return (
    <Card title="Feeding">
      <p className="mb-3 text-sm text-mist">
        How far Horatio handles feeding between games. Switching it off hides feeding everywhere; whatever was recorded is kept, and comes back if it is switched on again.
      </p>
      {!canEdit ? (
        <p className="text-sm">
          {mode.label}. <span className="text-mist">{mode.meaning}</span>
          {!off && now.resonance && <span className="mt-1 block">With Blood Resonance (Vol. 2, pp. 294-297).</span>}
        </p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <fieldset className="flex flex-col gap-2" disabled={save.isPending}>
            <legend className="sr-only">How Horatio handles feeding</legend>
            {MODES.map((m) => (
              <label key={m.value} className="flex items-start gap-2">
                <input type="radio" name="feeding" className="mt-1" checked={now.feeding === m.value} onChange={() => change({ feeding: m.value })} />
                <span>
                  {m.label}
                  {m.value === "book" && <span className="text-mist"> (the default)</span>}
                  <span className="block text-xs text-mist">{m.meaning}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <fieldset className="flex flex-col gap-2 border-t border-ash pt-3" aria-label="Optional rules (Vol. 2)" disabled={off || save.isPending}>
            <p className="text-xs tracking-wide text-mist uppercase">Optional rules (Vol. 2)</p>
            {off && <p className="text-xs text-mist">Offered while feeding is tracked.</p>}
            <label className={`flex items-start gap-2 ${off ? "opacity-60" : ""}`}>
              <input type="checkbox" className="mt-1" checked={now.resonance} onChange={(e) => change({ resonance: e.target.checked })} />
              <span>
                Blood Resonance
                <span className="block text-xs text-mist">
                  Players name the humor they hunt for; staff answer with the Resonance fed on and any Dyscrasia, a one-time benefit for the next game (pp. 294-297).
                </span>
              </span>
            </label>
          </fieldset>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
