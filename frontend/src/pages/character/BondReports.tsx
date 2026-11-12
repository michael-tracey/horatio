import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BondReportOut, ReportTroupeOut } from "../../api/types";
import { partyIn, PLAYER_SOURCES, reportedText, reportLine, reportState } from "../../bonds";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import { Button, ErrorText, Field, Input, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { WhoPicker } from "../troupe/WhoPicker";

type Side = "thrall" | "regnant";

/**
 * A drink of vampire blood, reported by its player for their own character (#661):
 * which troupe, which way it went, who was on the other side, the night and a note.
 * What happens next follows the troupe's setting: it counts at once, or waits on the
 * storytellers or on the thrall's player.
 */
export function ReportDrinkForm({
  characterId,
  name,
  troupes,
  atGame,
  onDone,
}: {
  characterId: string;
  name: string;
  troupes: ReportTroupeOut[];
  // From the Play View: tonight, at a game, unless the player says otherwise.
  atGame?: boolean;
  onDone: () => void;
}) {
  const dates = useDates();
  const toast = useToast();
  const today = dates.toInput(new Date()).slice(0, 10);
  const [troupeId, setTroupeId] = useState(troupes[0]?.id ?? "");
  const [side, setSide] = useState<Side>("thrall");
  const [other, setOther] = useState({ who: "", name: "" });
  const [night, setNight] = useState(today);
  const [source, setSource] = useState<BondReportOut["source"]>(atGame ? "game" : "game");
  const [note, setNote] = useState("");
  const troupe = troupes.find((t) => t.id === troupeId) ?? troupes[0];
  const picked = partyIn(other.who, other.name);
  const otherName = other.who.startsWith("c:") ? (troupe?.characters.find((c) => `c:${c.id}` === other.who)?.name ?? "") : other.name.trim();
  const save = useAction(async () => {
    if (!picked || !troupe) return;
    const done = await unwrap(
      api.POST("/api/characters/{character_id}/bonds/reports", {
        params: { path: { character_id: characterId } },
        body: { troupe_id: troupe.id, side, other: picked, night, source, note },
      }),
    );
    toast({ message: reportedText(done.outcome, done.level ?? null, side === "thrall" ? name : otherName) });
    onDone();
  });
  if (!troupe) return null;
  return (
    <form
      aria-label="Report a drink"
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
      <fieldset className="flex flex-col gap-1">
        <legend className="mb-1 text-xs text-mist">Who drank</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name={`side-${characterId}`} checked={side === "thrall"} onChange={() => setSide("thrall")} />
          {name} drank someone&apos;s blood
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name={`side-${characterId}`} checked={side === "regnant"} onChange={() => setSide("regnant")} />
          Someone drank {name}&apos;s blood
        </label>
      </fieldset>
      <Field label={side === "thrall" ? "Whose blood" : "Who drank it"} hint="A character in the troupe, or type a name.">
        <WhoPicker characters={troupe.characters} who={other.who} name={other.name} onChange={(who, n) => setOther({ who, name: n })} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Field label="Night">
          <DateInput required value={night} onChange={(e) => setNight(e.target.value)} className="w-44" />
        </Field>
        <Field label="Where">
          <Select value={source} onChange={(e) => setSource(e.target.value as BondReportOut["source"])} className="w-44">
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
        {troupe.setting === "players_report"
          ? "The storytellers approve it before it counts."
          : side === "thrall"
            ? "It counts at once."
            : "It counts once the drinker's player confirms it, or the storytellers do for an NPC or a name."}{" "}
        The other player isn&apos;t told of a bond unless they&apos;re its regnant and know of it.
      </p>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !picked || !night}>
          Report the drink
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/**
 * A meeting between the character and the other side of a bond it is in, logged by its
 * player (#665): it keeps a lesser bond from ending. It counts at once where players
 * manage their bonds, and waits for the storytellers where they approve.
 */
export function ReportMeetingForm({
  characterId,
  bondId,
  name,
  other,
  setting,
  onDone,
}: {
  characterId: string;
  bondId: string;
  name: string;
  other: string;
  setting: string | null;
  onDone: () => void;
}) {
  const dates = useDates();
  const toast = useToast();
  const [night, setNight] = useState(dates.toInput(new Date()).slice(0, 10));
  const [source, setSource] = useState<BondReportOut["source"]>("downtime");
  const [note, setNote] = useState("");
  const save = useAction(async () => {
    const done = await unwrap(
      api.POST("/api/characters/{character_id}/bonds/{bond_id}/meetings", {
        params: { path: { character_id: characterId, bond_id: bondId } },
        body: { night, source, note },
      }),
    );
    toast({ message: done.outcome === "recorded" ? "Meeting recorded." : "Sent to the storytellers to approve." });
    onDone();
  });
  return (
    <form
      aria-label={`Log a meeting with ${other}`}
      className="mt-1 flex flex-col gap-3 rounded-md border border-ash p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">
        {name} and {other} met or spoke. Games you both checked in at count already.{" "}
        {setting === "players_report" ? "The storytellers approve it before it counts." : "It counts at once."}
      </p>
      <div className="flex flex-wrap gap-3">
        <Field label="Night">
          <DateInput required value={night} onChange={(e) => setNight(e.target.value)} className="w-44" />
        </Field>
        <Field label="Where">
          <Select value={source} onChange={(e) => setSource(e.target.value as BondReportOut["source"])} className="w-44">
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
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !night}>
          Log the meeting
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** The drinks its player reported for the character, and those waiting on them to confirm. */
export function BondReportList({ characterId, reports }: { characterId: string; reports: BondReportOut[] }) {
  const dates = useDates();
  const [declining, setDeclining] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const path = (id: string) => ({ params: { path: { character_id: characterId, report_id: id } } });
  const withdraw = useAction((id: string) => unwrap(api.POST("/api/characters/{character_id}/bonds/reports/{report_id}/withdraw", path(id))));
  const answer = useAction((a: { id: string; confirm: boolean; reason: string }) =>
    unwrap(api.POST("/api/characters/{character_id}/bonds/reports/{report_id}/answer", { ...path(a.id), body: { confirm: a.confirm, reason: a.reason } })),
  );
  if (reports.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      <ul aria-label="Drinks reported" className="flex flex-col gap-2 text-sm">
        {reports.map((r) => (
          <li key={r.id} aria-label={reportLine(r, dates.day(r.night))} className={r.can_confirm ? "rounded-md border border-gold/50 bg-gold/5 p-2" : ""}>
            <span className="block">
              {reportLine(r, dates.day(r.night))}
              {r.note && <span className="text-mist"> · {r.note}</span>}
            </span>
            <span className={`block text-xs ${r.status === "declined" ? "text-blood-bright" : "text-mist"}`}>
              {r.can_confirm ? `${r.regnant.name}'s player recorded this. Did it happen?` : reportState(r)}
            </span>
            {r.can_confirm && declining !== r.id && (
              <span className="mt-1 flex flex-wrap gap-2">
                <Button disabled={answer.isPending} onClick={() => answer.mutate({ id: r.id, confirm: true, reason: "" })}>
                  Confirm
                </Button>
                <Button variant="ghost" disabled={answer.isPending} onClick={() => setDeclining(r.id)}>
                  Decline
                </Button>
              </span>
            )}
            {r.can_confirm && declining === r.id && (
              <form
                aria-label={`Decline: ${reportLine(r, dates.day(r.night))}`}
                className="mt-1 flex flex-col gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  answer.mutate({ id: r.id, confirm: false, reason });
                  setDeclining(null);
                }}
              >
                <Field label="Why (optional)" hint={`${r.regnant.name}'s player sees it.`}>
                  <Input maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
                </Field>
                <span className="flex flex-wrap gap-2">
                  <Button type="submit" variant="danger" disabled={answer.isPending}>
                    Decline it
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setDeclining(null)}>
                    Cancel
                  </Button>
                </span>
              </form>
            )}
            {r.can_withdraw && (
              <button
                type="button"
                className="text-xs text-mist underline hover:text-parchment"
                disabled={withdraw.isPending}
                onClick={() => withdraw.mutate(r.id)}
              >
                Withdraw
              </button>
            )}
          </li>
        ))}
      </ul>
      <ErrorText error={withdraw.error ?? answer.error} />
    </div>
  );
}

/**
 * In the Play View at a game: drinks waiting on the player to confirm, and a way to
 * report one in a few taps. Nothing shows unless the character's troupe lets players
 * report drinks, or one waits on them. Reporting needs a connection.
 */
export function PlayBondReports({ characterId, name, online }: { characterId: string; name: string; online: boolean }) {
  const [open, setOpen] = useState(false);
  const bonds = useQuery({
    queryKey: ["bonds", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/bonds", { params: { path: { character_id: characterId } } })),
    retry: false,
  });
  const b = bonds.data;
  if (!b) return null;
  const asking = (b.reports ?? []).filter((r) => r.can_confirm);
  const troupes = b.report_to ?? [];
  if (asking.length === 0 && troupes.length === 0) return null;
  return (
    <section aria-label="Blood bonds" className="mb-3 flex flex-col gap-2">
      <BondReportList characterId={characterId} reports={asking} />
      {troupes.length > 0 &&
        (open ? (
          <ReportDrinkForm characterId={characterId} name={name} troupes={troupes} atGame onDone={() => setOpen(false)} />
        ) : (
          <div>
            <Button variant="secondary" disabled={!online} onClick={() => setOpen(true)}>
              Report a drink of vampire blood
            </Button>
            {!online && <span className="ml-2 text-xs text-mist">Needs a connection.</span>}
          </div>
        ))}
    </section>
  );
}
