import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useRulesAction } from "../../hooks";

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

/** What a change did, for the toast. */
export function feedingChangeText(before: Setting, after: Setting): string {
  if (after.feeding === "off") return "Feeding isn't tracked now. What was recorded is kept, for if you switch it back on.";
  if (before.feeding === "off") return "Feeding is tracked again, with what was recorded before.";
  const changed = RULES.filter((r) => before[r.key] !== after[r.key]);
  return changed.map((r) => `${r.label}: ${after[r.key] ? "on" : "off"}.`).join(" ") || "Saved.";
}

/**
 * How Horatio handles feeding between games, once it's on: as the core book has it (the
 * default), or with the optional Vol. 2 rules, each its own switch. Feeding is switched on
 * and off in the Features list above (#784); off only hides it: what was recorded stays and
 * comes back.
 */
export function FeedingSetting({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const toast = useToast();
  const save = useRulesAction(async ({ before, after }: { before: Setting; after: Setting }) => {
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

  return (
    <Card title="Feeding">
      <p className="mb-3 text-sm text-mist">
        How Horatio handles feeding between games. As the book has it, each clan needs a number of feeding actions a cycle, Herd and some traits change it, and staff
        answer full or half Blood for the next game. Feeding is switched on and off in the Features list.
      </p>
      {!canEdit ? (
        <p className="text-sm">
          {off ? "Not tracked." : played.length > 0 ? `With ${played.map((r) => r.label).join(", ")} (Vol. 2).` : "As the book has it."}
        </p>
      ) : (
        <div className="flex flex-col gap-3 text-sm">
          <fieldset className="flex flex-col gap-2" aria-label="Optional rules (Vol. 2)" disabled={off || save.isPending}>
            <p className="text-xs tracking-wide text-mist uppercase">Optional rules (Vol. 2)</p>
            {off && <p className="text-xs text-mist">Offered while feeding is on.</p>}
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
