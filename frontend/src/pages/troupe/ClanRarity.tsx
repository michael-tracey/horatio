import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { ClanRarityOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Button, Card, ErrorText, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";

const RARITIES = ["common", "uncommon", "rare", "restricted"] as const;

/** What each rarity costs a character (MET: VTM p. 237). */
const COST: Record<string, string> = {
  common: "no merit",
  uncommon: "Uncommon Clan, 2 points",
  rare: "Rare Clan, 4 points",
  restricted: "Restricted Clan, 6 points",
};

/** A clan's rarity by the book, for the troupe's setting or each sect's. */
export function bookRarity(row: ClanRarityOut["clans"][number], setting: string | null): string {
  if (setting) return row.book[setting] ?? "restricted";
  const sects = Object.entries(row.book);
  if (sects.length && sects.every(([, r]) => r === sects[0]![1])) return sects[0]![1];
  return sects.map(([sect, r]) => `${r} (${sect})`).join(", ");
}

/**
 * House rule: how rare each clan is in the troupe's setting (#313). A character built
 * here takes the rarity merit its clan's rarity names, from its merit points; a
 * bloodline is as rare as its clan. By default each clan goes by the book for the
 * setting's sect: the troupe's one sect, or each character's own.
 */
export function ClanRarity({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const rarity = useQuery({ queryKey: ["clan-rarity", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/clan-rarity", path)) });
  const [editing, setEditing] = useState<Record<string, string> | null>(null);
  const named = useClanName();
  const save = useAction(async (rarities: Record<string, string>) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/clan-rarity", { ...path, body: { rarities: rarities as Record<string, (typeof RARITIES)[number]> } }));
    setEditing(null);
  });
  if (rarity.isPending) return <Loading />;
  if (rarity.error) return <ErrorText error={rarity.error} />;
  const { clans, setting, sects } = rarity.data;
  const own = Object.fromEntries(clans.filter((c) => c.house).map((c) => [c.clan, c.house!]));
  return (
    <Card
      title="Clan rarity"
      actions={
        canEdit &&
        editing === null && (
          <Button variant="secondary" className="min-h-8 px-3" aria-label="Change clan rarity" onClick={() => setEditing(own)}>
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        How rare each clan is in your setting. A character built here takes the matching merit from its merit points: {COST.uncommon}, {COST.rare}, or{" "}
        {COST.restricted} (MET: VTM p. 237). A bloodline is as rare as its clan, and takes its bloodline merit as well.{" "}
        {setting
          ? `Unless you say otherwise, a clan is as rare as the book has it for the ${setting} setting.`
          : `Unless you say otherwise, a clan is as rare as the book has it for each character's sect (${sects.join(", ")}).`}{" "}
        Finished characters keep the merits they have.
      </p>
      {editing === null ? (
        <ul className="flex flex-col divide-y divide-ash text-sm">
          {clans.map((c) => (
            <li key={c.clan} className="flex flex-wrap justify-between gap-x-3 py-1">
              <span>{named(c.clan)}</span>
              <span className={c.house ? "text-parchment" : "text-mist"}>{c.house ? `${c.house} (house rule)` : bookRarity(c, setting)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(editing);
          }}
        >
          <ul className="flex flex-col divide-y divide-ash text-sm">
            {clans.map((c) => (
              <li key={c.clan} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-1">
                <span>{named(c.clan)}</span>
                <Select
                  aria-label={`${named(c.clan)} rarity`}
                  className="h-9 w-auto py-0"
                  value={editing[c.clan] ?? ""}
                  onChange={(e) => {
                    const next = { ...editing };
                    if (e.target.value) next[c.clan] = e.target.value;
                    else delete next[c.clan];
                    setEditing(next);
                  }}
                >
                  <option value="">By the book: {bookRarity(c, setting)}</option>
                  {RARITIES.map((r) => (
                    <option key={r} value={r}>
                      {r[0]!.toUpperCase() + r.slice(1)}
                    </option>
                  ))}
                </Select>
              </li>
            ))}
          </ul>
          <ErrorText error={save.error} />
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
