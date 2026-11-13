import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterChoice, TroupeVinculumOut, VaulderieOut } from "../../api/types";
import { partyIn, SOURCES, type BondSource } from "../../bonds";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { matrix, participantsText, RATING_RULES, ratingName, vaulderieState, VINCULUM_PAGE } from "../../vinculum";
import { emptyRow, ParticipantsPicker, participantsIn, type ParticipantRow } from "./ParticipantsPicker";
import { WhoPicker } from "./WhoPicker";

/**
 * A Sabbat troupe's Vinculum (#666), on its Bonds screen for its running staff: record
 * Vaulderies, decide those players report, enter background ties, and see every rating
 * as a matrix, for everyone or one Vaulderie's circle, to see a pack. Recording a
 * Vaulderie lowers each participant's blood bonds a step (the Errata's p. 434).
 */
export function VinculumSection({ troupeId }: { troupeId: string }) {
  const [adding, setAdding] = useState<"vaulderie" | "tie" | null>(null);
  const [circle, setCircle] = useState<string>("");
  const [past, setPast] = useState(false);
  const data = useQuery({
    queryKey: ["troupe-bonds", troupeId, "vinculum"],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/vinculum", { params: { path: { troupe_id: troupeId } } })),
  });
  if (data.isPending) return <Loading />;
  if (data.error) return <ErrorText error={data.error} />;
  const v = data.data;
  const waiting = v.vaulderies.filter((x) => x.status === "pending");
  const logged = v.vaulderies.filter((x) => x.status !== "pending" && (past || x.status === "recorded"));
  const hidden = v.vaulderies.filter((x) => x.status !== "pending" && x.status !== "recorded").length;
  return (
    <section aria-label="The Vinculum" className="flex flex-col gap-4">
      <Card
        title="The Vinculum"
        actions={
          adding === null && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setAdding("vaulderie")}>
                Record a Vaulderie
              </Button>
              <Button variant="secondary" onClick={() => setAdding("tie")}>
                Enter a background tie
              </Button>
            </div>
          )
        }
      >
        <p className="mb-2 text-sm text-mist">
          Ratings come from the Vaulderies two shared, each night counted once ({VINCULUM_PAGE}). Both feel the same rating, except toward a false Sabbat, who
          drank but gave no blood. Taking part in a Vaulderie lowers all of a character&apos;s blood bonds this troupe keeps a step, once a night.
        </p>
        <ul className="mb-3 list-disc pl-5 text-xs text-mist">
          {RATING_RULES.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
        {adding === "vaulderie" && <VaulderieForm troupeId={troupeId} characters={v.characters} onDone={() => setAdding(null)} />}
        {adding === "tie" && <TieForm troupeId={troupeId} characters={v.characters} onDone={() => setAdding(null)} />}
      </Card>
      {waiting.length > 0 && (
        <Card title="Vaulderies waiting">
          <ul className="flex flex-col gap-3">
            {waiting.map((x) => (
              <WaitingVaulderie key={x.id} troupeId={troupeId} vaulderie={x} />
            ))}
          </ul>
        </Card>
      )}
      <Card title="Ratings">
        {v.people.length === 0 ? (
          <Empty>No Vaulderies recorded yet.</Empty>
        ) : (
          <Matrix data={v} circle={circle} setCircle={setCircle} />
        )}
      </Card>
      <Card title="Vaulderie log">
        {hidden > 0 && (
          <label className="mb-2 flex items-center gap-2 text-sm text-mist">
            <input type="checkbox" checked={past} onChange={(e) => setPast(e.target.checked)} />
            Show those declined or taken out ({hidden})
          </label>
        )}
        {logged.length === 0 ? (
          <Empty>No Vaulderies recorded yet.</Empty>
        ) : (
          <ul aria-label="Vaulderie log" className="flex flex-col gap-2 text-sm">
            {logged.map((x) => (
              <LoggedVaulderie key={x.id} troupeId={troupeId} vaulderie={x} />
            ))}
          </ul>
        )}
        {v.ties.length > 0 && <Ties troupeId={troupeId} ties={v.ties} />}
      </Card>
    </section>
  );
}

function Matrix({ data, circle, setCircle }: { data: TroupeVinculumOut; circle: string; setCircle: (c: string) => void }) {
  const dates = useDates();
  const counted = data.vaulderies.filter((x) => x.status === "recorded");
  const shown = matrix(data, circle || null);
  return (
    <div className="flex flex-col gap-2">
      {counted.length > 0 && (
        <Field label="Show">
          <Select value={circle} onChange={(e) => setCircle(e.target.value)} className="max-w-full sm:w-96">
            <option value="">Everyone</option>
            {counted.map((x) => (
              <option key={x.id} value={x.id}>
                {dates.day(x.night)}: {participantsText(x)}
              </option>
            ))}
          </Select>
        </Field>
      )}
      <div className="max-w-full overflow-x-auto">
        <table className="text-sm" aria-label="Vinculum ratings">
          <caption className="mb-1 text-left text-xs text-mist">Each row&apos;s rating toward each column.</caption>
          <thead>
            <tr>
              <th scope="col" className="p-1 text-left text-xs text-mist">
                Felt by
              </th>
              {shown.people.map((p) => (
                <th key={p.key} scope="col" className="p-1 text-left text-xs font-normal text-mist">
                  {p.who.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.people.map((row) => (
              <tr key={row.key} className="border-t border-ash/60">
                <th scope="row" className="p-1 text-left font-normal text-parchment">
                  {row.who.name}
                </th>
                {shown.people.map((col) => {
                  const r = row.key === col.key ? null : shown.rating(row.key, col.key);
                  return (
                    <td
                      key={col.key}
                      className="p-1 text-center"
                      title={r ? `${row.who.name} toward ${col.who.name}: ${r}, ${ratingName(r).toLowerCase()}` : undefined}
                    >
                      {r === null ? <span className="text-ash">·</span> : r === 0 ? <span className="text-mist">–</span> : r}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VaulderieForm({ troupeId, characters, onDone }: { troupeId: string; characters: CharacterChoice[]; onDone: () => void }) {
  const dates = useDates();
  const toast = useToast();
  const [rows, setRows] = useState<ParticipantRow[]>([emptyRow(), emptyRow()]);
  const [officiant, setOfficiant] = useState({ who: "", name: "" });
  const [night, setNight] = useState(dates.toInput(new Date()).slice(0, 10));
  const [source, setSource] = useState<BondSource>("game");
  const [note, setNote] = useState("");
  const people = participantsIn(rows);
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/vaulderies", {
        params: { path: { troupe_id: troupeId } },
        body: { night, participants: people, officiant: partyIn(officiant.who, officiant.name), source, note },
      }),
    );
    toast({ message: "Vaulderie recorded." });
    onDone();
  });
  return (
    <form
      aria-label="Record a Vaulderie"
      className="flex flex-col gap-3 rounded-md border border-ash p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <ParticipantsPicker characters={characters} rows={rows} onChange={setRows} />
      <Field label="Officiant (optional)" hint="A character in the troupe, or type a name.">
        <WhoPicker characters={characters} who={officiant.who} name={officiant.name} onChange={(who, name) => setOfficiant({ who, name })} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Field label="Night">
          <DateInput required value={night} onChange={(e) => setNight(e.target.value)} className="w-44" />
        </Field>
        <Field label="Where">
          <Select value={source} onChange={(e) => setSource(e.target.value as BondSource)} className="w-44">
            {SOURCES.map((s) => (
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
        <Button type="submit" disabled={save.isPending || people.length < 2 || !night}>
          Record the Vaulderie
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function TieForm({ troupeId, characters, onDone }: { troupeId: string; characters: CharacterChoice[]; onDone: () => void }) {
  const dates = useDates();
  const [one, setOne] = useState({ who: "", name: "" });
  const [other, setOther] = useState({ who: "", name: "" });
  const [rating, setRating] = useState(1);
  const [night, setNight] = useState(dates.toInput(new Date()).slice(0, 10));
  const [reason, setReason] = useState("");
  const a = partyIn(one.who, one.name);
  const b = partyIn(other.who, other.name);
  const save = useAction(async () => {
    if (!a || !b) return;
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/vinculum/ties", {
        params: { path: { troupe_id: troupeId } },
        body: { one: a, other: b, rating, night, reason },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label="Enter a background tie"
      className="flex flex-col gap-3 rounded-md border border-ash p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">
        Two who shared Vaulderies before Horatio, at the rating it stood at on a night (p. 435). It thins with time as Vaulderies would.
      </p>
      <Field label="One">
        <WhoPicker characters={characters} who={one.who} name={one.name} onChange={(who, name) => setOne({ who, name })} />
      </Field>
      <Field label="The other">
        <WhoPicker characters={characters} who={other.who} name={other.name} onChange={(who, name) => setOther({ who, name })} />
      </Field>
      <div className="flex flex-wrap gap-3">
        <Field label="Rating">
          <Select value={String(rating)} onChange={(e) => setRating(Number(e.target.value))} className="w-44">
            {[1, 2, 3, 4, 5].map((r) => (
              <option key={r} value={r}>
                {r}: {ratingName(r)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="As of">
          <DateInput required value={night} onChange={(e) => setNight(e.target.value)} className="w-44" />
        </Field>
      </div>
      <Field label="Reason">
        <Input required maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !a || !b || !reason.trim()}>
          Enter the tie
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function VaulderieLine({ vaulderie }: { vaulderie: VaulderieOut }) {
  const dates = useDates();
  return (
    <>
      <span className="text-parchment">{dates.day(vaulderie.night)}</span>: {participantsText(vaulderie)}
      {vaulderie.officiant && <span className="text-mist"> · officiated by {vaulderie.officiant.name}</span>}
      {vaulderie.note && <span className="text-mist"> · {vaulderie.note}</span>}
      {vaulderie.recorded_by && <span className="text-mist"> · by {vaulderie.recorded_by}</span>}
    </>
  );
}

function WaitingVaulderie({ troupeId, vaulderie }: { troupeId: string; vaulderie: VaulderieOut }) {
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const decide = useAction(async (approve: boolean) => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/vaulderies/{vaulderie_id}/decide", {
        params: { path: { troupe_id: troupeId, vaulderie_id: vaulderie.id } },
        body: { approve, reason },
      }),
    );
  });
  return (
    <li className="text-sm" aria-label={`Vaulderie of ${vaulderie.night}`}>
      <VaulderieLine vaulderie={vaulderie} />
      {declining ? (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <Field label="Why">
            <Input value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <Button disabled={decide.isPending || !reason.trim()} onClick={() => decide.mutate(false)}>
            Decline
          </Button>
          <Button variant="ghost" onClick={() => setDeclining(false)}>
            Cancel
          </Button>
        </div>
      ) : (
        <div className="mt-1 flex flex-wrap gap-2">
          <Button variant="secondary" disabled={decide.isPending} onClick={() => decide.mutate(true)}>
            Approve
          </Button>
          <Button variant="ghost" onClick={() => setDeclining(true)}>
            Decline…
          </Button>
        </div>
      )}
      <ErrorText error={decide.error} />
    </li>
  );
}

function LoggedVaulderie({ troupeId, vaulderie }: { troupeId: string; vaulderie: VaulderieOut }) {
  const [removing, setRemoving] = useState(false);
  const [reason, setReason] = useState("");
  const remove = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/vaulderies/{vaulderie_id}/remove", {
        params: { path: { troupe_id: troupeId, vaulderie_id: vaulderie.id } },
        body: { reason },
      }),
    );
    setRemoving(false);
  });
  return (
    <li>
      <VaulderieLine vaulderie={vaulderie} />
      {vaulderie.status !== "recorded" && <span className="block text-xs text-mist">{vaulderieState(vaulderie)}</span>}
      {vaulderie.status === "recorded" &&
        (removing ? (
          <div className="mt-1 flex flex-wrap items-end gap-2">
            <Field label="Why take it out">
              <Input value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} />
            </Field>
            <Button disabled={remove.isPending || !reason.trim()} onClick={() => remove.mutate(undefined)}>
              Take it out
            </Button>
            <Button variant="ghost" onClick={() => setRemoving(false)}>
              Cancel
            </Button>
          </div>
        ) : (
          <button type="button" className="ml-2 text-xs text-mist underline hover:text-parchment" onClick={() => setRemoving(true)}>
            Take out
          </button>
        ))}
      <ErrorText error={remove.error} />
    </li>
  );
}

function Ties({ troupeId, ties }: { troupeId: string; ties: TroupeVinculumOut["ties"] }) {
  const dates = useDates();
  const remove = useAction(async (tieId: string) => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/vinculum/ties/{tie_id}/remove", {
        params: { path: { troupe_id: troupeId, tie_id: tieId } },
        body: { reason: "Taken out by staff" },
      }),
    );
  });
  return (
    <div className="mt-3 border-t border-ash pt-2">
      <p className="mb-1 text-xs tracking-wide text-mist uppercase">Background ties</p>
      <ul className="flex flex-col gap-1 text-sm">
        {ties.map((t) => (
          <li key={t.id}>
            {t.one.name} and {t.other.name}: {t.rating} as of {dates.day(t.night)}
            <span className="text-mist"> · {t.reason}</span>
            <button type="button" className="ml-2 text-xs text-mist underline hover:text-parchment" onClick={() => remove.mutate(t.id)}>
              Take out
            </button>
          </li>
        ))}
      </ul>
      <ErrorText error={remove.error} />
    </div>
  );
}
