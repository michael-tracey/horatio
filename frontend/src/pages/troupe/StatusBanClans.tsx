import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { ClanBansOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Checkbox } from "../../components/Checkbox";
import { CardHeading } from "../../components/Headings";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { Badge, Button, ErrorText } from "../../components/ui";
import { SETTINGS } from "./settingsIndex";

type Ban = ClanBansOut["bans"][number];

/** Whether two lists name the same clans, in any order. */
export function sameClans(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((c) => b.includes(c));
}

/** The clans with one ticked or unticked, in order. */
export function toggled(clans: readonly string[], clan: string, on: boolean): string[] {
  return on ? [...new Set([...clans, clan])].sort() : clans.filter((c) => c !== clan);
}

/** What the ban's clans mean, in a sentence. */
export function banHint(ban: Ban): string {
  const level = ban.level === "greater" ? "a greater" : "a lesser";
  return ban.outside
    ? `A ${ban.sect} character of none of these clans is under ${level} status ban.`
    : `A ${ban.sect} character of one of these clans is under ${level} status ban.`;
}

/**
 * House rule: the clans each sect's status bans on clans name here (#553): the
 * Camarilla's pillar clans and its known Caitiff, and the Sabbat's antitribu under a
 * lesser or greater ban. Each defaults to the rule set's: for the pillar clans,
 * Volume II's (no Brujah, no Gangrel). A bloodline goes with its clan.
 */
export function StatusBanClans({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const bans = useQuery({
    queryKey: ["status-ban-clans", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/status-ban-clans", path)),
  });
  const save = useSaveOnChange((body: { key: string; clans: string[] }) => unwrap(api.PUT("/api/troupes/{troupe_id}/status-ban-clans", { ...path, body })), { rules: true });
  if (!bans.data) return <ErrorText error={bans.error} />;
  if (!bans.data.bans.length) return null;
  return (
    <SettingCard
      setting={SETTINGS.statusBans}
      readOnly={!canEdit}
    >
      <div className="flex flex-col gap-4">
        {bans.data.bans.map((ban) => (
          <BanClans key={ban.key} ban={ban} allClans={bans.data.all_clans} canEdit={canEdit} pending={save.isPending} onSave={(clans) => save.mutate({ key: ban.key, clans })} />
        ))}
      </div>
      <ErrorText error={save.error} />
    </SettingCard>
  );
}

function BanClans({
  ban,
  allClans,
  canEdit,
  pending,
  onSave,
}: {
  ban: Ban;
  allClans: string[];
  canEdit: boolean;
  pending: boolean;
  onSave: (clans: string[]) => void;
}) {
  const named = useClanName();
  const own = !sameClans(ban.clans, ban.book);
  const presets = ban.presets.length ? ban.presets : own ? [{ name: "As the book", clans: ban.book, page: null }] : [];
  const title = `${ban.sect}: ${ban.label}`;
  return (
    <section aria-label={title} className="text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <CardHeading>{title}</CardHeading>
        <Badge tone={own ? "gold" : "mist"}>{ban.level === "greater" ? "Greater" : "Lesser"}</Badge>
      </div>
      <p className="mt-1">{ban.applies_to ? named(ban.applies_to) : "No such ban here: it names no clans."}</p>
      {own && <p className="text-xs text-mist">The book&apos;s: {named(ban.book_applies_to)}</p>}
      {canEdit && (
        <details className="mt-2">
          <summary className="cursor-pointer text-mist hover:text-parchment">Edit the clans</summary>
          <fieldset className="mt-2 flex flex-col gap-2" disabled={pending}>
            <legend className="mb-1 text-xs text-mist">
              {banHint(ban)} Tick none for no such ban here.
            </legend>
            {presets.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {presets.map((p) => (
                  <Button
                    key={p.name}
                    variant="ghost"
                    className="min-h-8 px-2 text-xs"
                    disabled={sameClans(p.clans, ban.clans)}
                    onClick={() => onSave([...p.clans])}
                  >
                    {p.name}
                  </Button>
                ))}
              </div>
            )}
            {presets.some((p) => p.page) && (
              <p className="text-xs text-mist">
                {presets
                  .filter((p) => p.page)
                  .map((p) => `${p.name}: ${p.page}`)
                  .join(" · ")}
              </p>
            )}
            <div className="grid grid-cols-2 gap-x-3 gap-y-1">
              {allClans.map((clan) => (
                <Checkbox key={clan} label={named(clan)} checked={ban.clans.includes(clan)} onChange={(on) => onSave(toggled(ban.clans, clan, on))} />
              ))}
            </div>
          </fieldset>
        </details>
      )}
    </section>
  );
}
