import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import type { ClanWeaknessesOut } from "../../api/types";
import { RadioList } from "../../components/RadioList";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { ErrorText, Loading } from "../../components/ui";
import { pageText } from "./bookPage";
import { SETTINGS } from "./settingsIndex";

type Row = ClanWeaknessesOut["clans"][number];
type Book = Row["chosen"];

/** A weakness as an option: whose it is, then the line and its page. */
export function versionText(version: Row["versions"][number]): string {
  return `${version.weakness}${version.page ? ` (${pageText(version.page)})` : ""}`;
}

/** The clans the troupe plays by the core book's weakness, once `clan` is played by `book`. */
export function coreAfter(clans: Row[], clan: string, book: Book): string[] {
  return clans.filter((c) => (c.clan === clan ? book === "core" : c.chosen === "core")).map((c) => c.clan);
}

/** What a change did, for the toast. */
export function weaknessChangeText(clan: string, book: Book): string {
  return `The ${clan} here play by ${book === "core" ? "the core book's" : "Volume 2's"} weakness now.`;
}

/**
 * Which weakness the troupe plays for each clan the books differ on (#1127, #1197): the
 * Tremere's, which Volume 2 replaced (Vol. 2, p. 22), with Volume 2's the default, and the
 * Brujah's, which Volume 2's Lash Out reads as Beast traits counted (Vol. 2, p. 121), with
 * the core book's the default. Each default is what Horatio played before there was a
 * choice, so a troupe that never chooses goes on as before. Its bloodlines play as it
 * does. What the troupe's characters, creation, rules pages and Play View show and work
 * out follows at once.
 */
export function ClanWeaknesses({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const key = ["clan-weaknesses", troupeId];
  const found = useQuery({ queryKey: key, queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/clan-weaknesses", path)) });
  const save = useSaveOnChange(
    ({ core }: { clan: string; book: Book; core: string[] }) => unwrap(api.PUT("/api/troupes/{troupe_id}/clan-weaknesses", { ...path, body: { core } })),
    { rules: true, first: [key], message: ({ clan, book }) => weaknessChangeText(clan, book) },
  );
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const clans = found.data.clans;

  return (
    <SettingCard setting={SETTINGS.clanWeaknesses} readOnly={!canEdit}>
      <div className="flex flex-col gap-4 text-sm">
        {clans.map((row) => {
          const played = row.versions.find((v) => v.book === row.chosen);
          return !canEdit ? (
            <p key={row.clan}>
              The {row.clan} play by {row.chosen === "core" ? "the core book's" : "Volume 2's"} weakness here.{" "}
              {played && <span className="text-mist">{versionText(played)}</span>}
            </p>
          ) : (
            <RadioList
              key={row.clan}
              label={`The ${row.clan} weakness`}
              labelClassName="mb-1 text-sm text-parchment"
              value={row.chosen}
              options={row.versions.map((v) => ({
                value: v.book,
                label: (
                  <>
                    {v.label}'s
                    {v.book === row.default && <span className="text-mist"> (the default)</span>}
                  </>
                ),
                hint: versionText(v),
              }))}
              disabled={save.isPending}
              onChange={(book) => save.mutate({ clan: row.clan, book, core: coreAfter(clans, row.clan, book) })}
            />
          );
        })}
        <ErrorText error={save.error} />
      </div>
    </SettingCard>
  );
}
