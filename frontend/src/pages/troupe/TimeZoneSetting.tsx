import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { SettingCard, useSaveOnChange } from "../../components/SettingCard";
import { ErrorText } from "../../components/ui";
import { ZonePicker, zoneWords } from "../../components/ZonePicker";
import { zoneName } from "../../dates";
import { SETTINGS } from "./settingsIndex";

/** What the troupe uses with no zone of its own, in a line. */
export function zoneDefaultText(troupe: Pick<TroupeOut, "time_zone_default">): string {
  return `Left empty, it uses the lead storyteller's time zone: ${zoneWords(troupe.time_zone_default)}.`;
}

/**
 * The troupe's time zone (#1211), Settings › Time zone: where its games are entered on the
 * schedule and the day each falls on, for the directory's Day, and where its NPCs' items
 * expire. Its storytellers choose one from the IANA list, as each person does in Settings;
 * left empty, it is the lead storyteller's, then UTC. Its other running staff read it.
 */
export function TimeZoneSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useSaveOnChange(
    (zone: string | null) => unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { time_zone: zone ?? "" } })),
    { message: (zone) => `Time zone: ${zoneWords(zone ?? troupe.time_zone_default)}` },
  );
  const now = (
    <p className="text-sm">
      <span className="text-mist">Now:</span> {zoneWords(troupe.time_zone)} ({zoneName(new Date(), troupe.time_zone)})
      {!troupe.time_zone_set && <span className="text-mist"> (the lead storyteller's)</span>}
    </p>
  );
  if (!canEdit)
    return (
      <SettingCard setting={SETTINGS.timeZone} readOnly="The troupe's storytellers change this.">
        {now}
      </SettingCard>
    );
  return (
    <SettingCard setting={SETTINGS.timeZone}>
      <div className="flex flex-col gap-2">
        <ZonePicker
          saved={troupe.time_zone_set}
          onChoose={(zone) => save.mutate(zone)}
          placeholder="The lead storyteller's"
          clearText="Use the lead storyteller's"
          disabled={save.isPending}
          className=""
        />
        <p className="text-xs text-mist">{zoneDefaultText(troupe)}</p>
        {now}
        <ErrorText error={save.error} />
      </div>
    </SettingCard>
  );
}
