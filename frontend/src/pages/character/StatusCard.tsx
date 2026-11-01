import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut, HeldOut, StatusAbout, StatusIn, StatusOut, SuppressionOut } from "../../api/types";
import { DateInput } from "../../components/DateInput";
import { EmptyState } from "../../components/EmptyState";
import { InfoButton } from "../../components/InfoButton";
import { PatronPicker } from "../../components/PatronPicker";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Button, Card, ErrorText, Field, Input, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { capText, derivedLines, endingText, NO_RULES_YET, outsiderText, suppressedText, takenText, typeOrder } from "./status";

export function useStatus(characterId: string) {
  return useQuery({
    queryKey: ["status", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/status", { params: { path: { character_id: characterId } } })),
  });
}

/** What a status does, as a line under its name. */
export function About({ about }: { about: StatusAbout | undefined }) {
  if (!about) return null;
  const page = pageLabel(about.page);
  return (
    <span className="block text-xs text-mist">
      {about.no_rules_yet && <span className="block">{NO_RULES_YET}</span>}
      {about.passive && <span className="block">Held: {about.passive}</span>}
      {about.spent && <span className="block">Spent: {about.spent}</span>}
      {about.censure && <span className="block">Censure: {about.censure}</span>}
      {page && <span className="block">{page}</span>}
    </span>
  );
}

/** A reason staff give for a change, asked for in place, then the change. */
export function WithReason({
  label,
  name = label,
  needed,
  onConfirm,
  pending,
}: {
  label: string;
  /** What the button is called to a screen reader, if more than `label`: "Remove Loyal". */
  name?: string;
  needed: boolean;
  onConfirm: (reason: string) => void;
  pending: boolean;
}) {
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  if (!needed) {
    return (
      <Button variant="ghost" className="min-h-8 px-2 text-xs" aria-label={name} disabled={pending} onClick={() => onConfirm("")}>
        {label}
      </Button>
    );
  }
  if (!asking) {
    return (
      <Button variant="ghost" className="min-h-8 px-2 text-xs" aria-label={name} onClick={() => setAsking(true)}>
        {label}
      </Button>
    );
  }
  return (
    <form
      className="flex flex-wrap items-center gap-1.5"
      onSubmit={(e) => {
        e.preventDefault();
        onConfirm(reason.trim());
      }}
    >
      <Input aria-label="Why, for the character's log" placeholder="Why, for the log" value={reason} onChange={(e) => setReason(e.target.value)} className="min-h-8 w-56 py-1 text-xs" />
      <Button type="submit" className="min-h-8 px-2 text-xs" aria-label={name} disabled={!reason.trim() || pending}>
        {label}
      </Button>
      <Button type="button" variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => setAsking(false)}>
        Cancel
      </Button>
    </form>
  );
}

/** A status's type as a badge: "Abiding", "Negative". */
function TypeBadge({ type }: { type: string }) {
  const tone = type === "Negative" ? "blood" : type === "Fleeting" ? "mist" : "gold";
  return <Badge tone={tone}>{type}</Badge>;
}

/**
 * One status the character holds, in a line: its name, type and where it comes
 * from, with any actions at the end. The name opens what the status does.
 */
function Line({
  name,
  type,
  source,
  about,
  actions,
  children,
}: {
  name: string;
  type: string;
  source: ReactNode;
  about: StatusAbout | undefined;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <li aria-label={name} className="flex flex-col gap-0.5 py-2">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5">
          {about ? (
            <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="text-left font-medium text-parchment hover:text-gold">
              {name}
            </button>
          ) : (
            <span className="font-medium text-parchment">{name}</span>
          )}
          <TypeBadge type={type} />
          <span className="text-xs text-mist">{source}</span>
        </span>
        {actions && <span className="flex flex-wrap gap-1">{actions}</span>}
      </div>
      {children}
      {open && <About about={about} />}
    </li>
  );
}

function HeldRow({ character, status, held }: { character: CharacterOut; status: StatusOut; held: HeldOut }) {
  const dates = useDates();
  const remove = useAction((reason: string) =>
    unwrap(
      api.POST("/api/characters/{character_id}/status/{held_id}/remove", {
        params: { path: { character_id: character.id, held_id: held.id } },
        body: { reason },
      }),
    ),
  );
  const where = [held.place, dates.day(held.given_on)].filter(Boolean).join(", ");
  return (
    <Line
      name={held.name}
      type={held.type}
      source={`from ${held.patron.words}`}
      about={status.about[held.name]}
      actions={
        held.can_remove && (
          <WithReason
            label="Remove"
            name={`Remove ${held.name}`}
            needed={status.acting === "staff" && character.kind === "pc"}
            pending={remove.isPending}
            onConfirm={(reason) => remove.mutate(reason)}
          />
        )
      }
    >
      <span className="text-xs text-mist">
        {where}
        {held.story && ` · ${held.story}`}
      </span>
      {held.ending && <span className="text-xs text-gold">{endingText(held.ending, dates.day)}.</span>}
      <ErrorText error={remove.error} />
    </Line>
  );
}

function Unresolved({ character, status, name }: { character: CharacterOut; status: StatusOut; name: string }) {
  const resolve = useAction((reason: string) =>
    unwrap(api.POST("/api/characters/{character_id}/status/resolve", { params: { path: { character_id: character.id } }, body: { name, reason } })),
  );
  return (
    <Line
      name={name}
      type={status.about[name]?.type ?? "Unresolved"}
      source="no title, social age or merit gives it now: for staff to resolve"
      about={status.about[name]}
      actions={
        status.staff && (
          <WithReason label="Take off" name={`Take off ${name}`} needed={character.kind === "pc"} pending={resolve.isPending} onConfirm={(reason) => resolve.mutate(reason)} />
        )
      }
    >
      <ErrorText error={resolve.error} />
    </Line>
  );
}

/** Today on this device, as a date input's value: "2026-10-27". */
function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Adding a fleeting or negative status, naming its patron. On the sheet it goes to the
 * character's status; at a game (`submit`, `atGame`) to the Play View, which keeps it
 * against the game and leaves out where and when: there, and today.
 */
export function AddStatus({
  character,
  status,
  onDone,
  submit,
  atGame = false,
}: {
  character: Pick<CharacterOut, "id" | "name" | "kind">;
  status: StatusOut;
  onDone: () => void;
  submit?: (body: StatusIn) => Promise<unknown>;
  atGame?: boolean;
}) {
  const [name, setName] = useState("");
  const [patronId, setPatronId] = useState<string | null>(null);
  const [patronText, setPatronText] = useState("");
  const [place, setPlace] = useState("");
  const [givenOn, setGivenOn] = useState(today);
  const [story, setStory] = useState("");
  const [reason, setReason] = useState("");
  const [giveUp, setGiveUp] = useState("");
  const [override, setOverride] = useState(false);
  const chosen = status.addable.find((s) => s.name === name);
  const fleeting = chosen?.type === "Fleeting";
  const full = fleeting && status.fleeting >= status.fleeting_cap;
  const asStaff = status.acting === "staff" && character.kind === "pc";
  const suppressed = fleeting && status.suppressed.length > 0;
  const add = useAction(async () => {
    const body: StatusIn = {
      name,
      patron_id: patronId,
      patron_text: patronText,
      place: atGame ? "" : place,
      given_on: atGame ? null : givenOn || null,
      story,
      reason,
      give_up: full ? giveUp || null : null,
      override: fleeting && (status.disgraced || suppressed) && override,
    };
    if (submit) await submit(body);
    else await unwrap(api.POST("/api/characters/{character_id}/status", { params: { path: { character_id: character.id } }, body }));
    onDone();
  });
  const ready = !!name && (!!patronId || !!patronText.trim()) && (!asStaff || !!reason.trim()) && (!full || !!giveUp);
  const groups = (["Fleeting", "Negative"] as const).map((type) => [type, status.addable.filter((s) => s.type === type)] as const);
  return (
    <form
      aria-label="Add status"
      className="mt-3 flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate(undefined);
      }}
    >
      <Field label="Status">
        <Select value={name} onChange={(e) => setName(e.target.value)}>
          <option value="">Choose a status</option>
          {groups.map(([type, list]) => (
            <optgroup key={type} label={type}>
              {list.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                  {s.sect !== "General" ? ` (${s.sect})` : ""}
                </option>
              ))}
            </optgroup>
          ))}
        </Select>
      </Field>
      {chosen && <About about={chosen} />}
      {chosen?.duration && <p className="text-xs text-gold">Lasts: {chosen.duration}</p>}
      {fleeting && (status.disgraced || suppressed) && (
        <p className="text-sm text-blood-bright">
          {status.disgraced
            ? `${character.name} holds Disgraced, and gains no status while it does.`
            : `${character.name}'s fleeting status is suppressed ${status.suppressed[0]!.text}, and it gains none meanwhile.`}
          {status.acting === "staff" && (
            <label className="mt-1 flex items-center gap-2 text-parchment">
              <input type="checkbox" checked={override} onChange={(e) => setOverride(e.target.checked)} />
              Give it anyway, as staff
            </label>
          )}
        </p>
      )}
      {full && (
        <Field
          label="Give one up for it"
          hint={`${character.name} holds ${status.fleeting} fleeting status, as many as it can (MET: VTM p. 312). The one given up is lost without being spent.`}
        >
          <Select value={giveUp} onChange={(e) => setGiveUp(e.target.value)}>
            <option value="">Choose one</option>
            {status.held
              .filter((h) => h.type === "Fleeting")
              .map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}, from {h.patron.words}
                </option>
              ))}
          </Select>
        </Field>
      )}
      <PatronPicker
        characterId={character.id}
        troupe={status.troupe_name}
        patronId={patronId}
        patronText={patronText}
        onChange={(id, text) => {
          setPatronId(id);
          setPatronText(text);
        }}
      />
      {!atGame && (
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Where">
            <Input value={place} placeholder={status.troupe_name ?? "The troupe or domain"} onChange={(e) => setPlace(e.target.value)} />
          </Field>
          <Field label="When">
            <DateInput value={givenOn} onChange={(e) => setGivenOn(e.target.value)} />
          </Field>
        </div>
      )}
      <Field label="The story (optional)">
        <Textarea rows={2} value={story} placeholder="For defending Elysium" onChange={(e) => setStory(e.target.value)} />
      </Field>
      {asStaff && (
        <Field label="Why, for the character's log">
          <Input value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={!ready || add.isPending}>
          Add status
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <ErrorText error={add.error} />
    </form>
  );
}

function SuppressedRow({ character, suppressed, staff }: { character: CharacterOut; suppressed: SuppressionOut; staff: boolean }) {
  const dates = useDates();
  const lift = useAction((reason: string) =>
    unwrap(
      api.POST("/api/characters/{character_id}/status/suppressions/{suppression_id}/lift", {
        params: { path: { character_id: character.id, suppression_id: suppressed.id! } },
        body: { reason },
      }),
    ),
  );
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 text-xs text-blood-bright">
      <span>{suppressedText(suppressed, dates.day)}</span>
      {suppressed.id && staff && <WithReason label="Give it back" needed={false} pending={lift.isPending} onConfirm={(reason) => lift.mutate(reason)} />}
      <ErrorText error={lift.error} />
    </li>
  );
}

/** Staff strip the fleeting status unspent (MET: VTM p. 314), for the rest of the game or for defying a Commander. */
function Suppress({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const [kind, setKind] = useState<"game" | "commander">("commander");
  const [reason, setReason] = useState("");
  const suppress = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/status/suppress", { params: { path: { character_id: character.id } }, body: { kind, reason } }));
    onDone();
  });
  return (
    <form
      aria-label="Suppress fleeting status"
      className="mt-2 flex flex-col gap-2 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        suppress.mutate(undefined);
      }}
    >
      <p className="text-xs text-mist">Its fleeting status is neither carried into a game nor gained meanwhile, and comes back on its own (MET: VTM p. 314).</p>
      <Field label="For how long">
        <Select value={kind} onChange={(e) => setKind(e.target.value as "game" | "commander")}>
          <option value="commander">2 games or a month: defied a Commander</option>
          <option value="game">The rest of the game</option>
        </Select>
      </Field>
      <Field label="Why, for the character's log">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="flex gap-2">
        <Button type="submit" disabled={!reason.trim() || suppress.isPending}>
          Suppress
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
      <ErrorText error={suppress.error} />
    </form>
  );
}

/**
 * Why the character holds no sect status, and what would give it some. Said
 * once, here: the Titles card beside it doesn't repeat it.
 */
function NoStatus({ character, sect }: { character: CharacterOut; sect: string | null }) {
  if (sect) return <EmptyState title={`The ${sect} has no status in Horatio yet.`} />;
  return (
    <EmptyState title={`${character.name} has no sect, so holds no status.`}>
      Status, and a sect's titles, come with a sect.{" "}
      {character.kind === "npc"
        ? "Choose one on the Sheet."
        : character.creation_complete
          ? "A sect is chosen while a character is built: ask the storytellers if this one should have one."
          : "Choose one on the Sheet, in the Concept step."}
    </EmptyState>
  );
}

/**
 * The character's sect status (MET: VTM pp. 310-317), as a list of what it holds
 * now, a line each: Accepted by its sect, the abiding and innate status its active
 * title, social age and merits give, and the fleeting and negative status it holds
 * with each one's patron. Who adds and removes held status is the home troupe's
 * Status on sheets setting. It is the main column of the character page's Status &
 * Titles tab, beside its titles.
 */
export function StatusCard({ character }: { character: CharacterOut }) {
  const status = useStatus(character.id);
  const [adding, setAdding] = useState(false);
  const [suppressing, setSuppressing] = useState(false);
  if (!status.data) return status.error ? <ErrorText error={status.error} /> : null;
  const s = status.data;
  const nothing = !s.accepted && !s.outsider_sect && !s.derived.length && !s.held.length && !s.unresolved.length;
  if (nothing)
    return (
      <Card dense title="Status">
        <NoStatus character={character} sect={s.sect} />
      </Card>
    );
  const fleeting = s.held.filter((h) => h.type === "Fleeting");
  const held = [...s.held].sort((a, b) => typeOrder(a.type) - typeOrder(b.type));
  const derived = derivedLines(s.derived, s.troupe_name);
  const lost = derivedLines(s.lost, s.troupe_name);
  const counted = s.accepted || s.outsider_sect;
  return (
    <Card
      dense
      title="Status"
      info={
        <InfoButton label="About Status">
          <span className="block">
            Status is what the sect thinks of the character (MET: VTM pp. 310-317). The active title, social age and merits give abiding and innate status;
            fleeting and negative status is held, each one with who gave it. Tap a status to see what it does.
          </span>
          <span className="mt-1 block">
            {s.setting === "staff"
              ? `In ${s.troupe_name ?? "the home troupe"}, only staff add or remove status.`
              : "Players add and remove their own character's fleeting and negative status, naming who gave it."}
          </span>
        </InfoButton>
      }
      actions={
        s.acting &&
        !adding && (
          <Button variant="ghost" onClick={() => setAdding(true)}>
            Add status
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-2 text-sm">
        {s.outsider_sect && !s.accepted && <p>{outsiderText(s)}</p>}
        {!counted && <NoStatus character={character} sect={s.sect} />}
        {s.disgraced && <p className="text-blood-bright">{character.name} holds Disgraced, and gains no status while it does.</p>}
        {s.taken_by && <p className="text-blood-bright">{takenText(character.name, s.taken_by)}</p>}
        {counted && (
          <p className="text-xs text-mist">
            <span>
              Fleeting: {fleeting.length} of {s.fleeting_cap}
            </span>
            {capText(s.cap_why) && <span> · {capText(s.cap_why)}</span>}
          </p>
        )}
        {fleeting.length > s.fleeting_cap && <p className="text-xs text-blood-bright">Over the cap: only {s.fleeting_cap} count at a game. Give some up.</p>}
        {s.suppressed.length > 0 && (
          <ul className="flex flex-col gap-1">
            {s.suppressed.map((x) => (
              <SuppressedRow key={x.id ?? x.kind} character={character} suppressed={x} staff={s.staff} />
            ))}
          </ul>
        )}
        <ul aria-label="Status held" className="flex flex-col divide-y divide-ash/60">
          {s.accepted && <Line name={s.accepted} type="Accepted" source={`by the ${s.sect}`} about={s.about[s.accepted]} />}
          {derived.map((d) => (
            <Line key={`${d.type}/${d.name}`} name={d.name} type={d.type} source={`from ${d.sources.join(" and ")}`} about={s.about[d.name]} />
          ))}
          {lost.map((d) => (
            <Line key={`lost/${d.type}/${d.name}`} name={d.name} type={d.type} source={`lost while ${s.taken_by}: from ${d.sources.join(" and ")}`} about={s.about[d.name]} />
          ))}
          {held.map((h) => (
            <HeldRow key={h.id} character={character} status={s} held={h} />
          ))}
          {s.unresolved.map((name) => (
            <Unresolved key={name} character={character} status={s} name={name} />
          ))}
        </ul>
        {counted && !fleeting.length && <p className="text-xs text-mist">No fleeting status held.</p>}
        {s.staff &&
          counted &&
          (suppressing ? (
            <Suppress character={character} onDone={() => setSuppressing(false)} />
          ) : (
            <Button variant="ghost" className="min-h-8 self-start px-2 text-xs" onClick={() => setSuppressing(true)}>
              Suppress fleeting status…
            </Button>
          ))}
        {adding && <AddStatus character={character} status={s} onDone={() => setAdding(false)} />}
      </div>
    </Card>
  );
}
