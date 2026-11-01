import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

export type Setting = { feeding: TroupeOut["feeding"]; resonance: boolean; territories: boolean; rack: boolean };

type Rule = "resonance" | "territories" | "rack";

/** The optional Vol. 2 rules, each its own switch. */
export const RULES: { key: Rule; label: string; meaning: string }[] = [
  {
    key: "resonance",
    label: "Blood Resonance",
    meaning: "Players name the humor they hunt for; staff answer with the Resonance fed on and any Dyscrasia, a one-time benefit for the next game (pp. 294-297).",
  },
  {
    key: "territories",
    label: "Feeding territories",
    meaning: "Areas only the characters the domain's Authority names may feed in, Small to Large. Their holders patrol them, and staff test anyone poaching there (pp. 304-307).",
  },
  {
    key: "rack",
    label: "The Rack (advanced feeding)",
    meaning: "Each character takes one vessel, a Feeding Card, from the cycle's Rack instead of spending feeding actions; Herd deals extra cards (pp. 298-303). Needs Blood Resonance, as each vessel carries one.",
  },
];

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
  const changed = RULES.filter((r) => before[r.key] !== after[r.key]);
  return changed.map((r) => `${r.label}: ${after[r.key] ? "on" : "off"}.`).join(" ") || "Saved.";
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
  const now: Setting = {
    feeding: troupe.data.feeding ?? "book",
    resonance: troupe.data.feeding_resonance ?? false,
    territories: troupe.data.feeding_territories ?? false,
    rack: troupe.data.feeding_rack ?? false,
  };
  const off = now.feeding === "off";
  const change = (after: Partial<Setting>) => save.mutate({ before: now, after: { ...now, ...after } });
  // The Rack builds on Blood Resonance: switching that off switches the Rack off too.
  const toggle = (rule: Rule, on: boolean) => change(rule === "resonance" && !on ? { resonance: false, rack: false } : { [rule]: on });
  const played = RULES.filter((r) => now[r.key]);
  const mode = MODES.find((m) => m.value === now.feeding) ?? MODES[1]!;

  return (
    <Card title="Feeding">
      <p className="mb-3 text-sm text-mist">
        How far Horatio handles feeding between games. Switching it off hides feeding everywhere; whatever was recorded is kept, and comes back if it is switched on again.
      </p>
      {!canEdit ? (
        <p className="text-sm">
          {mode.label}. <span className="text-mist">{mode.meaning}</span>
          {!off && played.length > 0 && <span className="mt-1 block">With {played.map((r) => r.label).join(", ")} (Vol. 2).</span>}
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
            {RULES.map((r) => {
              const blocked = r.key === "rack" && !now.resonance;
              return (
                <label key={r.key} className={`flex items-start gap-2 ${off || blocked ? "opacity-60" : ""}`}>
                  <input type="checkbox" className="mt-1" checked={now[r.key]} disabled={blocked} onChange={(e) => toggle(r.key, e.target.checked)} />
                  <span>
                    {r.label}
                    <span className="block text-xs text-mist">{r.meaning}</span>
                  </span>
                </label>
              );
            })}
          </fieldset>
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
