import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type {
  BondOut,
  BondReportOut,
  CharacterChoice,
  KnownBondOut,
} from "../../api/types";
import {
  BOND_PAGE,
  groupBonds,
  isOpen,
  levelName,
  partyIn,
  partyKey,
  PLAYER_SOURCES,
  reportLine,
  SOURCES,
  statusText,
  untold,
  watched,
  type BondSource,
} from "../../bonds";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import {
  Button,
  Card,
  Empty,
  ErrorText,
  Field,
  Input,
  Loading,
  Select,
  Textarea,
} from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { WhoPicker } from "./WhoPicker";

type By = "thrall" | "regnant";

function today(dates: ReturnType<typeof useDates>) {
  return dates.toInput(new Date()).slice(0, 10);
}

/**
 * The troupe's blood bonds, for its running staff: every bond, by thrall or by
 * regnant, with its drinks log. Staff record drinks, enter bonds that already stand,
 * break them, and say which are known to their regnants; approve or decline the
 * drinks players report, and change or take out any drink in a log (#661). Only shown
 * while the troupe tracks bonds.
 */
export function BondsTab({ troupeId }: { troupeId: string }) {
  const [by, setBy] = useState<By>("thrall");
  const [past, setPast] = useState(false);
  const [adding, setAdding] = useState<"drink" | "enter" | null>(null);
  // ?who=, from the web of bonds (#708): only that person's bonds.
  const [params, setParams] = useSearchParams();
  const who = params.get("who");
  const bonds = useQuery({
    queryKey: ["troupe-bonds", troupeId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/bonds", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
  });
  if (bonds.isPending) return <Loading />;
  if (bonds.error) return <ErrorText error={bonds.error} />;
  const theirs = who
    ? bonds.data.bonds.filter((b) => partyKey(b.thrall) === who || partyKey(b.regnant) === who)
    : bonds.data.bonds;
  const named = who ? theirs.flatMap((b) => [b.thrall, b.regnant]).find((p) => partyKey(p) === who)?.name : undefined;
  const shown = past ? theirs : theirs.filter(watched);
  const closed = theirs.length - theirs.filter(watched).length;
  const groups = groupBonds(shown, by);

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Blood bonds"
        actions={
          adding === null && (
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setAdding("drink")}>
                Record a drink
              </Button>
              <Button variant="secondary" onClick={() => setAdding("enter")}>
                Enter a bond
              </Button>
            </div>
          )
        }
      >
        <p className="mb-3 text-sm text-mist">
          Each separate night a character drinks a vampire&apos;s blood is one
          drink, up to a full bond at three, which wipes away every lesser bond
          they have ({BOND_PAGE}). The level comes from the drinks log. A
          thrall&apos;s player sees their own bonds; a regnant&apos;s player
          sees one only once it&apos;s marked known to them.
        </p>
        <p className="mb-3 text-sm text-mist">
          With time a full bond drops to two drinks after three months without
          drinking, a two-drink bond ends after six months without the two
          meeting, and a one-drink bond after a year (p. 296). Games both check
          in at count as meeting; log others, such as one in a downtime. A
          thrall&apos;s player learns of a change with the next downtime
          results.
        </p>
        {adding === "drink" && (
          <NewDrinkForm
            troupeId={troupeId}
            characters={bonds.data.characters}
            onDone={() => setAdding(null)}
          />
        )}
        {adding === "enter" && (
          <EnterForm
            troupeId={troupeId}
            characters={bonds.data.characters}
            onDone={() => setAdding(null)}
          />
        )}
      </Card>
      <KnownBonds troupeId={troupeId} />
      {who && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-mist">
          Showing only {named ?? "this person"}&apos;s bonds.
          <Button variant="ghost" onClick={() => setParams({})}>
            Show everyone&apos;s
          </Button>
        </p>
      )}
      {(bonds.data.reports ?? []).length > 0 && (
        <WaitingReports
          troupeId={troupeId}
          reports={bonds.data.reports ?? []}
        />
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="List bonds" className="flex gap-1">
          {(["thrall", "regnant"] as const).map((b) => (
            <Button
              key={b}
              variant={by === b ? "secondary" : "ghost"}
              aria-pressed={by === b}
              onClick={() => setBy(b)}
            >
              By {b}
            </Button>
          ))}
        </div>
        {closed > 0 && (
          <label className="flex items-center gap-2 text-sm text-mist">
            <input
              type="checkbox"
              checked={past}
              onChange={(e) => setPast(e.target.checked)}
            />
            Show ended and broken bonds ({closed})
          </label>
        )}
      </div>
      {groups.length === 0 ? (
        <Empty>No blood bonds yet.</Empty>
      ) : (
        groups.map((g) => (
          <section
            key={g.name}
            aria-label={g.name}
            className="rounded-lg border border-ash bg-dusk p-3 sm:p-4"
          >
            <h3 className="mb-2 text-base text-gold">
              {g.name}
              <span className="text-sm text-mist">
                {by === "thrall" ? ", bound to" : ", whose blood binds"}
              </span>
            </h3>
            <ul className="flex flex-col gap-3">
              {g.bonds.map((bond) => (
                <BondRow
                  key={bond.id}
                  troupeId={troupeId}
                  bond={bond}
                  by={by}
                />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

function BondRow({
  troupeId,
  bond,
  by,
}: {
  troupeId: string;
  bond: BondOut;
  by: By;
}) {
  const dates = useDates();
  const [doing, setDoing] = useState<
    "drink" | "meeting" | "break" | "fade" | null
  >(null);
  const [log, setLog] = useState(false);
  const path = { params: { path: { troupe_id: troupeId, bond_id: bond.id } } };
  const known = useAction((on: boolean) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/bonds/{bond_id}/known", {
        ...path,
        body: { known: on },
      }),
    ),
  );
  const clearKept = useAction(() =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds/{bond_id}/clear-kept", path),
    ),
  );
  const confirm = useAction(() =>
    unwrap(
      api.POST(
        "/api/troupes/{troupe_id}/bonds/{bond_id}/confirm-change",
        path,
      ),
    ),
  );
  const change = bond.next_change;
  const open = isOpen(bond);
  const label = `${bond.thrall.name} bound to ${bond.regnant.name}`;
  const other = by === "thrall" ? bond.regnant : bond.thrall;
  return (
    <li
      aria-label={label}
      className="flex flex-col gap-2 border-t border-ash pt-2 text-sm first:border-t-0 first:pt-0"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p>
          <span className="text-parchment">{other.name}</span>
          {other.kind === "npc" && <span className="text-mist"> (NPC)</span>}
          {other.kind === null && (
            <span className="text-mist"> (name only)</span>
          )}
          <span className={open ? "text-gold" : "text-mist"}>
            {" "}
            · {levelName(bond.level)}
          </span>
          {bond.status !== "active" && (
            <span className="text-mist"> · {statusText(bond)}</span>
          )}
          {bond.status === "fading" && bond.fades_on && (
            <span className="text-mist">
              : {bond.regnant.name} met Final Death, and it ends on{" "}
              {dates.day(bond.fades_on)}
            </span>
          )}
          {bond.last_drink && (
            <span className="text-mist">
              {" "}
              · last drink {dates.day(bond.last_drink)}
            </span>
          )}
          {bond.last_met && bond.last_met !== bond.last_drink && (
            <span className="text-mist">
              {" "}
              · last met {dates.day(bond.last_met)}
            </span>
          )}
        </p>
        {open && doing === null && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setDoing("drink")}>
              Add a drink
            </Button>
            {bond.status === "active" && (
              <Button variant="secondary" onClick={() => setDoing("meeting")}>
                Log a meeting
              </Button>
            )}
            {bond.status === "fading" && (
              <Button variant="secondary" onClick={() => setDoing("fade")}>
                Change the fade
              </Button>
            )}
            <Button variant="ghost" onClick={() => setDoing("break")}>
              Break
            </Button>
          </div>
        )}
      </div>
      {change && !change.due && (
        <p className="text-xs text-mist">
          {change.kind === "drop"
            ? `Drops to two drinks on ${dates.day(change.on)} unless ${bond.thrall.name} drinks again.`
            : `Ends on ${dates.day(change.on)} unless the two meet.`}
        </p>
      )}
      {change?.due && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-gold">
          <span>
            Due since {dates.day(change.on)}:{" "}
            {change.kind === "drop"
              ? "it drops to two drinks"
              : "it ends, the two kept apart"}{" "}
            (p. 296). Players report and staff approve here, so it waits for
            you.
          </span>
          <Button
            variant="secondary"
            disabled={confirm.isPending}
            onClick={() => confirm.mutate(undefined)}
          >
            Confirm
          </Button>
        </div>
      )}
      <ErrorText error={confirm.error} />
      {bond.status === "fading" && (
        <p className="text-xs text-mist">
          {bond.thrall.name}&apos;s player sees the bond as it was until it ends
          and they&apos;re told it has faded, with the next downtime results (p.
          296).
        </p>
      )}
      {untold(bond) && (
        <p className="text-xs text-gold">
          {bond.thrall.name}&apos;s player isn&apos;t told yet: their sheet
          still shows the bond until the next downtime results tell them it has
          faded.
        </p>
      )}
      {bond.kept_for_regnant && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-gold">
          <span>
            {bond.regnant.name}&apos;s player still sees this bond as it was:
            the regnant has no sense of the thrall&apos;s death.
          </span>
          <Button
            variant="ghost"
            disabled={clearKept.isPending}
            onClick={() => clearKept.mutate(undefined)}
          >
            Stop showing the regnant
          </Button>
        </div>
      )}
      <ErrorText error={clearKept.error} />
      {open && (
        <label className="flex items-center gap-2 text-mist">
          <input
            type="checkbox"
            checked={bond.known_to_regnant}
            disabled={known.isPending}
            onChange={(e) => known.mutate(e.target.checked)}
          />
          Known to {bond.regnant.name}: their player sees it
        </label>
      )}
      <ErrorText error={known.error} />
      {doing === "drink" && (
        <DrinkForm
          troupeId={troupeId}
          bond={bond}
          onDone={() => setDoing(null)}
        />
      )}
      {doing === "meeting" && (
        <MeetingForm
          troupeId={troupeId}
          bond={bond}
          onDone={() => setDoing(null)}
        />
      )}
      {doing === "break" && (
        <BreakForm
          troupeId={troupeId}
          bond={bond}
          onDone={() => setDoing(null)}
        />
      )}
      {doing === "fade" && (
        <FadeForm
          troupeId={troupeId}
          bond={bond}
          onDone={() => setDoing(null)}
        />
      )}
      <div>
        <button
          type="button"
          className="text-xs text-mist underline hover:text-parchment"
          aria-expanded={log}
          onClick={() => setLog(!log)}
        >
          {log ? "Hide the drinks log" : `Drinks log (${bond.entries.length})`}
        </button>
        {log && (
          <ol
            aria-label={`Drinks log of ${label}`}
            className="mt-1 flex flex-col gap-1 pl-3 text-xs"
          >
            {bond.entries.map((e) => (
              <EntryRow key={e.id} troupeId={troupeId} bond={bond} entry={e} />
            ))}
          </ol>
        )}
      </div>
    </li>
  );
}

/** The night, where it was told and a note: what every drink records. */
function DrinkFields({
  night,
  source,
  note,
  set,
}: {
  night: string;
  source: BondSource;
  note: string;
  set: (
    change: Partial<{ night: string; source: BondSource; note: string }>,
  ) => void;
}) {
  return (
    <>
      <div className="flex flex-wrap gap-3">
        <Field label="Night">
          <DateInput
            required
            value={night}
            onChange={(e) => set({ night: e.target.value })}
            className="w-44"
          />
        </Field>
        <Field label="Where it was told">
          <Select
            value={source}
            onChange={(e) => set({ source: e.target.value as BondSource })}
            className="w-44"
          >
            {SOURCES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Note (optional)">
        <Input
          maxLength={2000}
          value={note}
          onChange={(e) => set({ note: e.target.value })}
        />
      </Field>
    </>
  );
}

/**
 * Staff recording a drink, or entering a bond, while a full bond to someone else makes
 * the thrall immune (Errata, p. 295): the server refuses with why, and staff can give a
 * reason to record it anyway (#665).
 */
function immune(error: unknown): boolean {
  return error instanceof Error && error.message.includes("immune");
}

function Override({
  error,
  value,
  onChange,
}: {
  error: unknown;
  value: string;
  onChange: (value: string) => void;
}) {
  if (!immune(error) && !value) return null;
  return (
    <Field
      label="Reason to record it anyway"
      hint="A full bond makes the thrall immune to other bonds until it drops."
    >
      <Input
        maxLength={2000}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </Field>
  );
}

function useDrink(dates: ReturnType<typeof useDates>) {
  const [drink, setDrink] = useState<{
    night: string;
    source: BondSource;
    note: string;
  }>({ night: today(dates), source: "game", note: "" });
  return [
    drink,
    (change: Partial<typeof drink>) => setDrink({ ...drink, ...change }),
  ] as const;
}

/** The thrall and the regnant, each a character of the troupe's or a name only. */
function Sides({
  characters,
  thrall,
  regnant,
  setThrall,
  setRegnant,
}: {
  characters: CharacterChoice[];
  thrall: { who: string; name: string };
  regnant: { who: string; name: string };
  setThrall: (who: string, name: string) => void;
  setRegnant: (who: string, name: string) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Thrall" hint="Who drank: a character, or a name only.">
        <WhoPicker
          characters={characters}
          who={thrall.who}
          name={thrall.name}
          onChange={setThrall}
        />
      </Field>
      <Field label="Regnant" hint="The vampire whose blood it was.">
        <WhoPicker
          characters={characters}
          who={regnant.who}
          name={regnant.name}
          onChange={setRegnant}
        />
      </Field>
    </div>
  );
}

function NewDrinkForm({
  troupeId,
  characters,
  onDone,
}: {
  troupeId: string;
  characters: CharacterChoice[];
  onDone: () => void;
}) {
  const dates = useDates();
  const toast = useToast();
  const [thrall, setThrall] = useState({ who: "", name: "" });
  const [regnant, setRegnant] = useState({ who: "", name: "" });
  const [drink, setDrink] = useDrink(dates);
  const [override, setOverride] = useState("");
  const t = partyIn(thrall.who, thrall.name);
  const r = partyIn(regnant.who, regnant.name);
  const save = useAction(async () => {
    if (!t || !r) return;
    const bond = await unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds/drinks", {
        params: { path: { troupe_id: troupeId } },
        body: { thrall: t, regnant: r, ...drink, override },
      }),
    );
    toast({
      message: `${bond.thrall.name} to ${bond.regnant.name}: ${levelName(bond.level).toLowerCase()}.`,
    });
    onDone();
  });
  return (
    <form
      aria-label="Record a drink"
      className="flex flex-col gap-3 border-t border-ash pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Sides
        characters={characters}
        thrall={thrall}
        regnant={regnant}
        setThrall={(who, name) => setThrall({ who, name })}
        setRegnant={(who, name) => setRegnant({ who, name })}
      />
      <DrinkFields {...drink} set={setDrink} />
      <ErrorText error={save.error} />
      <Override error={save.error} value={override} onChange={setOverride} />
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          disabled={save.isPending || !t || !r || !drink.night}
        >
          Record the drink
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function EnterForm({
  troupeId,
  characters,
  onDone,
}: {
  troupeId: string;
  characters: CharacterChoice[];
  onDone: () => void;
}) {
  const dates = useDates();
  const [thrall, setThrall] = useState({ who: "", name: "" });
  const [regnant, setRegnant] = useState({ who: "", name: "" });
  const [level, setLevel] = useState(1);
  const [night, setNight] = useState(today(dates));
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState("");
  const t = partyIn(thrall.who, thrall.name);
  const r = partyIn(regnant.who, regnant.name);
  const save = useAction(async () => {
    if (!t || !r) return;
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds", {
        params: { path: { troupe_id: troupeId } },
        body: { thrall: t, regnant: r, level, night, reason, override },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label="Enter a bond"
      className="flex flex-col gap-3 border-t border-ash pt-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">
        A bond that already stands, such as one from before Horatio: it starts
        at its level, and later drinks add to it.
      </p>
      <Sides
        characters={characters}
        thrall={thrall}
        regnant={regnant}
        setThrall={(who, name) => setThrall({ who, name })}
        setRegnant={(who, name) => setRegnant({ who, name })}
      />
      <div className="flex flex-wrap gap-3">
        <Field label="Level">
          <Select
            value={level}
            onChange={(e) => setLevel(Number(e.target.value))}
            className="w-44"
          >
            {[1, 2, 3].map((l) => (
              <option key={l} value={l}>
                {levelName(l)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Since" hint="The night it stood at this level.">
          <DateInput
            required
            value={night}
            onChange={(e) => setNight(e.target.value)}
            className="w-44"
          />
        </Field>
      </div>
      <Field label="Reason">
        <Textarea
          rows={2}
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <ErrorText error={save.error} />
      <Override error={save.error} value={override} onChange={setOverride} />
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          disabled={save.isPending || !t || !r || !night || !reason.trim()}
        >
          Enter the bond
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DrinkForm({
  troupeId,
  bond,
  onDone,
}: {
  troupeId: string;
  bond: BondOut;
  onDone: () => void;
}) {
  const dates = useDates();
  const toast = useToast();
  const [drink, setDrink] = useDrink(dates);
  const [override, setOverride] = useState("");
  const save = useAction(async () => {
    const after = await unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds/{bond_id}/drinks", {
        params: { path: { troupe_id: troupeId, bond_id: bond.id } },
        body: { ...drink, override },
      }),
    );
    toast({
      message: `${after.thrall.name} to ${after.regnant.name}: ${levelName(after.level).toLowerCase()}.`,
    });
    onDone();
  });
  return (
    <form
      aria-label={`Add a drink: ${bond.thrall.name} from ${bond.regnant.name}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <DrinkFields {...drink} set={setDrink} />
      <ErrorText error={save.error} />
      <Override error={save.error} value={override} onChange={setOverride} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !drink.night}>
          Add the drink
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Log the two meeting, such as in a downtime: it keeps a lesser bond from ending (#665). */
function MeetingForm({
  troupeId,
  bond,
  onDone,
}: {
  troupeId: string;
  bond: BondOut;
  onDone: () => void;
}) {
  const dates = useDates();
  const [meeting, setMeeting] = useDrink(dates);
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds/{bond_id}/meetings", {
        params: { path: { troupe_id: troupeId, bond_id: bond.id } },
        body: meeting,
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Log a meeting: ${bond.thrall.name} and ${bond.regnant.name}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">
        Meeting or speaking keeps a lesser bond from ending; it changes no
        level. Games both checked in at count already.
      </p>
      <DrinkFields {...meeting} set={setMeeting} />
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !meeting.night}>
          Log the meeting
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function BreakForm({
  troupeId,
  bond,
  onDone,
}: {
  troupeId: string;
  bond: BondOut;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds/{bond_id}/break", {
        params: { path: { troupe_id: troupeId, bond_id: bond.id } },
        body: { reason },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Break ${bond.thrall.name}'s bond to ${bond.regnant.name}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field
        label="Reason"
        hint="Breaking a bond is hard, but it can be done (p. 296)."
      >
        <Textarea
          rows={2}
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          variant="danger"
          disabled={save.isPending || !reason.trim()}
        >
          Break the bond
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Move the day a fading bond ends, with a reason: today ends it now, as faded. */
function FadeForm({
  troupeId,
  bond,
  onDone,
}: {
  troupeId: string;
  bond: BondOut;
  onDone: () => void;
}) {
  const dates = useDates();
  const [ends, setEnds] = useState(bond.fades_on ?? today(dates));
  const [reason, setReason] = useState("");
  const save = useAction(async () => {
    await unwrap(
      api.PUT("/api/troupes/{troupe_id}/bonds/{bond_id}/fade", {
        params: { path: { troupe_id: troupeId, bond_id: bond.id } },
        body: { fades_on: ends, reason },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label={`Change the fade of ${bond.thrall.name}'s bond to ${bond.regnant.name}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="flex flex-wrap gap-3">
        <Field label="It ends on" hint="Today or before ends it now, as faded.">
          <DateInput
            required
            value={ends}
            onChange={(e) => setEnds(e.target.value)}
            className="w-44"
          />
        </Field>
        <Button
          type="button"
          variant="ghost"
          className="self-end"
          onClick={() => setEnds(today(dates))}
        >
          Today
        </Button>
      </div>
      <Field label="Reason">
        <Input
          maxLength={2000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          disabled={save.isPending || !ends || !reason.trim()}
        >
          Save the fade
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

type Entry = BondOut["entries"][number];

/** A line of a bond's log, which staff can change (its night and note) or take out with a reason. */
function EntryRow({
  troupeId,
  bond,
  entry: e,
}: {
  troupeId: string;
  bond: BondOut;
  entry: Entry;
}) {
  const dates = useDates();
  const [doing, setDoing] = useState<"change" | "remove" | null>(null);
  const [night, setNight] = useState(e.night);
  const [note, setNote] = useState(e.note);
  const [reason, setReason] = useState("");
  const path = {
    params: { path: { troupe_id: troupeId, bond_id: bond.id, entry_id: e.id } },
  };
  const change = useAction(async () => {
    await unwrap(
      api.PATCH("/api/troupes/{troupe_id}/bonds/{bond_id}/entries/{entry_id}", {
        ...path,
        body: { night, note },
      }),
    );
    setDoing(null);
  });
  const remove = useAction(async () => {
    await unwrap(
      api.POST(
        "/api/troupes/{troupe_id}/bonds/{bond_id}/entries/{entry_id}/remove",
        { ...path, body: { reason } },
      ),
    );
    setDoing(null);
  });
  const told = SOURCES.find((s) => s.value === e.source)?.label.toLowerCase();
  const what =
    e.kind === "entered"
      ? `entered at ${levelName(e.level ?? 1).toLowerCase()}`
      : e.kind === "dropped"
        ? "dropped to two drinks, three months without drinking"
        : e.kind === "meeting"
          ? `met, ${told}`
          : `a drink, ${told}`;
  return (
    <li aria-label={`${dates.day(e.night)}: ${what}`}>
      {dates.day(e.night)}: {what}
      {e.note && <span className="text-mist"> · {e.note}</span>}
      {e.recorded_by && (
        <span className="text-mist"> · by {e.recorded_by}</span>
      )}
      {doing === null && (
        <span className="ml-2 inline-flex gap-2">
          <button
            type="button"
            className="text-mist underline hover:text-parchment"
            onClick={() => setDoing("change")}
          >
            Change
          </button>
          <button
            type="button"
            className="text-mist underline hover:text-parchment"
            onClick={() => setDoing("remove")}
          >
            Take out
          </button>
        </span>
      )}
      {doing === "change" && (
        <form
          aria-label={`Change the night of ${dates.day(e.night)}`}
          className="mt-1 flex flex-col gap-2 rounded-md border border-ash p-2"
          onSubmit={(ev) => {
            ev.preventDefault();
            change.mutate(undefined);
          }}
        >
          <div className="flex flex-wrap gap-3">
            <Field label="Night">
              <DateInput
                required
                value={night}
                onChange={(ev) => setNight(ev.target.value)}
                className="w-44"
              />
            </Field>
            <Field label={e.kind === "entered" ? "Reason" : "Note"}>
              <Input
                maxLength={2000}
                value={note}
                onChange={(ev) => setNote(ev.target.value)}
              />
            </Field>
          </div>
          <ErrorText error={change.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={change.isPending || !night}>
              Save
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDoing(null)}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
      {doing === "remove" && (
        <form
          aria-label={`Take out the night of ${dates.day(e.night)}`}
          className="mt-1 flex flex-col gap-2 rounded-md border border-ash p-2"
          onSubmit={(ev) => {
            ev.preventDefault();
            remove.mutate(undefined);
          }}
        >
          <Field
            label="Reason"
            hint={
              bond.entries.length === 1
                ? "It's the only line in the log, so the bond goes too."
                : "The level is worked out again."
            }
          >
            <Input
              maxLength={2000}
              value={reason}
              onChange={(ev) => setReason(ev.target.value)}
            />
          </Field>
          <ErrorText error={remove.error} />
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="danger"
              disabled={remove.isPending || !reason.trim()}
            >
              Take it out
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDoing(null)}
            >
              Cancel
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

/**
 * Drinks players reported that are still waiting: on staff (also in Approvals) or on
 * a thrall's player. Staff can decide either kind here.
 */
const KNOWN_WHY: Record<KnownBondOut["why"], string> = {
  embrace: "from the Embrace",
  sire: "the sire on their sheet",
  domitor: "their domitor",
  retainer: "a ghoul Retainer",
};

/**
 * Bonds Horatio can work out but doesn't keep yet (#663): childer to the sires who
 * Embraced them or their sheets name (#739), ghouls to their domitors, and ghoul
 * Retainers to their vampires, from before the troupe tracked bonds. Staff look the
 * list over and add them all at once; once added there's nothing more to show. Bonds
 * made from now on are added as they happen.
 */
function KnownBonds({ troupeId }: { troupeId: string }) {
  const dates = useDates();
  const toast = useToast();
  const known = useQuery({
    queryKey: ["troupe-bonds", troupeId, "known"],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/bonds/known", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
  });
  const fill = useAction(
    () =>
      unwrap(
        api.POST("/api/troupes/{troupe_id}/bonds/known", {
          params: { path: { troupe_id: troupeId } },
        }),
      ),
    [["troupe-bonds", troupeId]],
  );
  if (!known.data || known.data.length === 0) return null;
  const count = known.data.length;
  return (
    <Card title="Fill in known bonds">
      <p className="mb-2 text-sm text-mist">
        Horatio knows of {count === 1 ? "a bond" : `${count} bonds`} from before
        the troupe tracked them: every childe has a one-drink bond to their sire
        ({BOND_PAGE}), and a ghoul, a ghoul Retainer too, is fully bound to the
        vampire they serve (MET: VTM p. 296). Add {count === 1 ? "it" : "them"}{" "}
        to the bonds here?
      </p>
      <ul aria-label="Known bonds" className="mb-3 flex flex-col gap-1 text-sm">
        {known.data.map((k) => (
          <li
            key={`${k.why}-${k.thrall.character_id ?? k.thrall.name}-${k.regnant.character_id ?? k.regnant.name}`}
          >
            {k.thrall.name} to {k.regnant.name}, {levelName(k.level)} from{" "}
            {dates.day(k.night)}{" "}
            <span className="text-mist">({KNOWN_WHY[k.why]})</span>
          </li>
        ))}
      </ul>
      <Button
        variant="secondary"
        disabled={fill.isPending}
        onClick={() =>
          fill.mutate(undefined, {
            onSuccess: (done) =>
              toast({
                message:
                  done.added.length === 1
                    ? "Added 1 bond."
                    : `Added ${done.added.length} bonds.`,
              }),
          })
        }
      >
        Add {count === 1 ? "this bond" : `these ${count} bonds`}
      </Button>
      <ErrorText error={fill.error} />
    </Card>
  );
}

function WaitingReports({
  troupeId,
  reports,
}: {
  troupeId: string;
  reports: BondReportOut[];
}) {
  return (
    <Card title="Drinks waiting">
      <ul aria-label="Drinks waiting" className="flex flex-col gap-3 text-sm">
        {reports.map((r) => (
          <WaitingReport key={r.id} troupeId={troupeId} report={r} />
        ))}
      </ul>
    </Card>
  );
}

function WaitingReport({
  troupeId,
  report: r,
}: {
  troupeId: string;
  report: BondReportOut;
}) {
  const dates = useDates();
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState("");
  const decide = useAction((approve: boolean) =>
    unwrap(
      api.POST("/api/troupes/{troupe_id}/bonds/reports/{report_id}/decide", {
        params: { path: { troupe_id: troupeId, report_id: r.id } },
        body: { approve, reason: approve ? "" : reason },
      }),
    ),
  );
  const line = reportLine(r, dates.day(r.night));
  const reporter = r.reported_as === "thrall" ? r.thrall.name : r.regnant.name;
  return (
    <li
      aria-label={line}
      className="flex flex-col gap-1 border-t border-ash pt-2 first:border-t-0 first:pt-0"
    >
      <span>
        {line},{" "}
        {PLAYER_SOURCES.find((s) => s.value === r.source)?.label.toLowerCase()}
        {r.note && <span className="text-mist"> · {r.note}</span>}
      </span>
      <span className="text-xs text-mist">
        Reported for {reporter}
        {r.reported_by && ` by ${r.reported_by}`} ·{" "}
        {r.waiting_on === "staff"
          ? "waiting for staff (also in Approvals)"
          : `waiting for ${r.thrall.name}'s player to confirm`}
      </span>
      {!declining ? (
        <span className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            disabled={decide.isPending}
            onClick={() => decide.mutate(true)}
          >
            Approve
          </Button>
          <Button
            variant="ghost"
            disabled={decide.isPending}
            onClick={() => setDeclining(true)}
          >
            Decline
          </Button>
        </span>
      ) : (
        <form
          aria-label={`Decline: ${line}`}
          className="flex flex-col gap-2"
          onSubmit={(ev) => {
            ev.preventDefault();
            decide.mutate(false);
          }}
        >
          <Field label="Why" hint="The player who reported it sees it.">
            <Input
              maxLength={2000}
              value={reason}
              onChange={(ev) => setReason(ev.target.value)}
            />
          </Field>
          <span className="flex flex-wrap gap-2">
            <Button type="submit" variant="danger" disabled={decide.isPending}>
              Decline it
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDeclining(false)}
            >
              Cancel
            </Button>
          </span>
        </form>
      )}
      <ErrorText error={decide.error} />
    </li>
  );
}
