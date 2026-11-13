import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { VaulderieOut, VaulderieTroupeOut } from "../../api/types";
import { partyIn, PLAYER_SOURCES } from "../../bonds";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { participantsText, ratingName, vaulderieState } from "../../vinculum";
import { emptyRow, ParticipantsPicker, participantsIn, type ParticipantRow } from "../troupe/ParticipantsPicker";
import { WhoPicker } from "../troupe/WhoPicker";

/** The character's Vinculum, as the viewer may know of it (#666). */
export function useVinculum(characterId: string) {
  return useQuery({
    queryKey: ["bonds", characterId, "vinculum"],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/vinculum", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
}

/**
 * On the Bonds card: the Vinculum ratings the character feels (both of a pair see
 * theirs; nobody else does), the Vaulderies its player reported, and where the troupe
 * lets players report them, a form to report one.
 */
export function VinculumPart({ characterId, name }: { characterId: string; name: string }) {
  const v = useVinculum(characterId).data;
  const [reporting, setReporting] = useState(false);
  if (!v || (v.ratings.length === 0 && v.report_to.length === 0 && v.reports.length === 0)) return null;
  return (
    <div className="mt-3 border-t border-ash pt-2">
      <p className="text-xs tracking-wide text-mist uppercase">Vinculum</p>
      {v.ratings.length > 0 ? (
        <ul aria-label="Vinculum" className="mt-1 flex flex-col gap-1 text-sm">
          {v.ratings.map((r) => (
            <li key={`${r.troupe_id}-${r.name}`}>
              {r.name}:{" "}
              <span className="text-mist">
                {r.rating}, {ratingName(r.rating).toLowerCase()}
              </span>
              {r.rating >= 2 && <span className="block text-xs text-mist">{r.effects.join(" ")}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-sm text-mist">No Vaulderies recorded.</p>
      )}
      {v.reports.length > 0 && <ReportedVaulderies characterId={characterId} reports={v.reports} />}
      {v.report_to.length > 0 && (
        <div className="mt-2">
          {reporting ? (
            <ReportVaulderieForm characterId={characterId} name={name} troupes={v.report_to} onDone={() => setReporting(false)} />
          ) : (
            <Button variant="secondary" onClick={() => setReporting(true)}>
              Report a Vaulderie
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function ReportedVaulderies({ characterId, reports }: { characterId: string; reports: VaulderieOut[] }) {
  const dates = useDates();
  const withdraw = useAction(async (id: string) => {
    await unwrap(
      api.POST("/api/characters/{character_id}/vaulderies/{vaulderie_id}/withdraw", {
        params: { path: { character_id: characterId, vaulderie_id: id } },
      }),
    );
  });
  return (
    <ul aria-label="Vaulderies reported" className="mt-2 flex flex-col gap-1 text-sm">
      {reports.map((r) => (
        <li key={r.id}>
          {dates.day(r.night)}: {participantsText(r)}
          <span className="block text-xs text-mist">{vaulderieState(r)}</span>
          {r.status === "pending" && (
            <button type="button" className="text-xs text-mist underline hover:text-parchment" onClick={() => withdraw.mutate(r.id)}>
              Withdraw
            </button>
          )}
        </li>
      ))}
      <ErrorText error={withdraw.error} />
    </ul>
  );
}

/**
 * A Vaulderie the character took part in, reported by its player: the others who took
 * part (the troupe's player characters, or names), whether the character itself was a
 * false Sabbat, who officiated, the night and a note. It waits for the storytellers.
 */
export function ReportVaulderieForm({
  characterId,
  name,
  troupes,
  onDone,
}: {
  characterId: string;
  name: string;
  troupes: VaulderieTroupeOut[];
  onDone: () => void;
}) {
  const dates = useDates();
  const toast = useToast();
  const [troupeId, setTroupeId] = useState(troupes[0]?.id ?? "");
  const [rows, setRows] = useState<ParticipantRow[]>([emptyRow()]);
  const [mine, setMine] = useState(false);
  const [officiant, setOfficiant] = useState({ who: "", name: "" });
  const [night, setNight] = useState(dates.toInput(new Date()).slice(0, 10));
  const [source, setSource] = useState<"game" | "downtime">("game");
  const [note, setNote] = useState("");
  const troupe = troupes.find((t) => t.id === troupeId) ?? troupes[0];
  const others = participantsIn(rows);
  const save = useAction(async () => {
    if (!troupe) return;
    await unwrap(
      api.POST("/api/characters/{character_id}/vaulderies", {
        params: { path: { character_id: characterId } },
        body: {
          troupe_id: troupe.id,
          night,
          others,
          false_sabbat: mine,
          officiant: partyIn(officiant.who, officiant.name),
          source,
          note,
        },
      }),
    );
    toast({ message: "Vaulderie reported: it waits for the storytellers." });
    onDone();
  });
  if (!troupe) return null;
  return (
    <form
      aria-label="Report a Vaulderie"
      className="flex flex-col gap-3 rounded-md border border-ash p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {troupes.length > 1 && (
        <Field label="Troupe">
          <Select value={troupe.id} onChange={(e) => setTroupeId(e.target.value)}>
            {troupes.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <label className="flex items-center gap-2 text-xs text-mist">
        <input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />
        {name} drank but gave no blood (a false Sabbat)
      </label>
      <ParticipantsPicker characters={troupe.characters} rows={rows} onChange={setRows} label={`Who else took part with ${name}`} />
      <Field label="Officiant (optional)" hint="A character in the troupe, or type a name.">
        <WhoPicker characters={troupe.characters} who={officiant.who} name={officiant.name} onChange={(who, n) => setOfficiant({ who, name: n })} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Field label="Night">
          <DateInput required value={night} onChange={(e) => setNight(e.target.value)} className="w-44" />
        </Field>
        <Field label="Where">
          <Select value={source} onChange={(e) => setSource(e.target.value as "game" | "downtime")} className="w-44">
            {PLAYER_SOURCES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Note (optional)">
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <p className="text-xs text-mist">
        The storytellers approve it before it counts, as it changes the others&apos; ratings and blood bonds too. Each who took part has their blood bonds lowered
        a step.
      </p>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || others.length < 1 || !night}>
          Report the Vaulderie
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
