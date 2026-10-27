import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BanOut, CharacterOut, HeldOut, StatusAbout, StatusOut } from "../../api/types";
import { InfoButton } from "../../components/InfoButton";
import { PatronPicker } from "../../components/PatronPicker";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Button, Card, ErrorText, Field, Input, Select, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { bySource, endingText } from "./status";

export function useStatus(characterId: string) {
  return useQuery({
    queryKey: ["status", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/status", { params: { path: { character_id: characterId } } })),
  });
}

/** What a status does, as a line under its name. */
function About({ about }: { about: StatusAbout | undefined }) {
  if (!about) return null;
  const page = pageLabel(about.page);
  return (
    <span className="block text-xs text-mist">
      {about.passive && <span className="block">Held: {about.passive}</span>}
      {about.spent && <span className="block">Spent: {about.spent}</span>}
      {about.censure && <span className="block">Censure: {about.censure}</span>}
      {page && <span className="block">{page}</span>}
    </span>
  );
}

/** A reason staff give for a change, asked for in place, then the change. */
function WithReason({
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
  const [open, setOpen] = useState(false);
  const where = [held.place, dates.day(held.given_on)].filter(Boolean).join(", ");
  return (
    <li className="flex flex-col gap-0.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>
          <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="text-left text-parchment hover:text-gold">
            {held.name}
          </button>
          <span className="text-mist"> from {held.patron.words}</span>
        </span>
        {held.can_remove && (
          <WithReason
            label="Remove"
            name={`Remove ${held.name}`}
            needed={status.acting === "staff" && character.kind === "pc"}
            pending={remove.isPending}
            onConfirm={(reason) => remove.mutate(reason)}
          />
        )}
      </div>
      <span className="text-xs text-mist">{where}</span>
      {held.ending && <span className="text-xs text-gold">{endingText(held.ending, dates.day)}.</span>}
      {held.story && <span className="text-xs text-mist">{held.story}</span>}
      {open && <About about={status.about[held.name]} />}
      <ErrorText error={remove.error} />
    </li>
  );
}

/** Today on this device, as a date input's value: "2026-10-27". */
function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function AddStatus({ character, status, onDone }: { character: CharacterOut; status: StatusOut; onDone: () => void }) {
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
  const add = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/status", {
        params: { path: { character_id: character.id } },
        body: {
          name,
          patron_id: patronId,
          patron_text: patronText,
          place,
          given_on: givenOn || null,
          story,
          reason,
          give_up: full ? giveUp || null : null,
          override: fleeting && status.disgraced && override,
        },
      }),
    );
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
      {fleeting && status.disgraced && (
        <p className="text-sm text-blood-bright">
          {character.name} holds Disgraced, and gains no status while it does.
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
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Where">
          <Input value={place} placeholder={status.troupe_name ?? "The troupe or domain"} onChange={(e) => setPlace(e.target.value)} />
        </Field>
        <Field label="When">
          <Input type="date" value={givenOn} onChange={(e) => setGivenOn(e.target.value)} />
        </Field>
      </div>
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

function BanRow({ character, status, ban }: { character: CharacterOut; status: StatusOut; ban: BanOut }) {
  const mark = useAction((body: { mark: "applies" | "exempt" | null; reason: string }) =>
    unwrap(api.PUT("/api/characters/{character_id}/status/bans", { params: { path: { character_id: character.id } }, body: { ban: ban.applies_to, ...body } })),
  );
  const how =
    ban.marked === false ? `exempt: ${ban.reason}` : ban.marked ? `staff say it applies: ${ban.reason}` : ban.by_sheet ? "the sheet shows it" : null;
  return (
    <li className="flex flex-col gap-0.5">
      <span>
        <Badge tone={ban.applies ? "blood" : "mist"}>{ban.level}</Badge> <span className={ban.applies ? "text-parchment" : "text-mist"}>{ban.applies_to}</span>
        {how && <span className="text-xs text-mist"> ({how})</span>}
      </span>
      {status.staff && (
        <span className="flex flex-wrap gap-1">
          {ban.applies && ban.marked !== false && (
            <WithReason label="Exempt" needed pending={mark.isPending} onConfirm={(reason) => mark.mutate({ mark: "exempt", reason })} />
          )}
          {!ban.applies && (
            <WithReason label="It applies" needed pending={mark.isPending} onConfirm={(reason) => mark.mutate({ mark: "applies", reason })} />
          )}
          {ban.marked !== null && (
            <Button variant="ghost" className="min-h-8 px-2 text-xs" disabled={mark.isPending} onClick={() => mark.mutate({ mark: null, reason: "" })}>
              As the sheet shows
            </Button>
          )}
        </span>
      )}
      <ErrorText error={mark.error} />
    </li>
  );
}

function Unresolved({ character, status, name }: { character: CharacterOut; status: StatusOut; name: string }) {
  const resolve = useAction((reason: string) =>
    unwrap(api.POST("/api/characters/{character_id}/status/resolve", { params: { path: { character_id: character.id } }, body: { name, reason } })),
  );
  return (
    <li className="flex flex-wrap items-center justify-between gap-2">
      <span>
        {name} <span className="text-xs text-mist">no title, social age or merit gives it now</span>
      </span>
      {status.staff && (
        <WithReason label="Take off" name={`Take off ${name}`} needed={character.kind === "pc"} pending={resolve.isPending} onConfirm={(reason) => resolve.mutate(reason)} />
      )}
      <ErrorText error={resolve.error} />
    </li>
  );
}

/**
 * The character's sect status (MET: VTM pp. 310-317): what its titles, social age
 * and merits give, the fleeting and negative status it holds with each one's
 * patron, and its bans. Who adds and removes held status is the home troupe's
 * Status on sheets setting.
 */
export function StatusCard({ character }: { character: CharacterOut }) {
  const status = useStatus(character.id);
  const [adding, setAdding] = useState(false);
  if (!status.data) return status.error ? <ErrorText error={status.error} /> : null;
  const s = status.data;
  const nothing = !s.accepted && !s.derived.length && !s.held.length && !s.unresolved.length;
  if (nothing) return null;
  const fleeting = s.held.filter((h) => h.type === "Fleeting");
  const negative = s.held.filter((h) => h.type === "Negative");
  const bans = s.bans.filter((b) => b.applies || s.staff);
  return (
    <Card
      dense
      title="Status"
      info={
        <InfoButton label="About Status">
          <span className="block">
            Status is what the sect thinks of the character (MET: VTM pp. 310-317). Titles, social age and merits give abiding and innate status; fleeting and
            negative status is held, each one with who gave it.
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
      <div className="flex flex-col gap-3 text-sm">
        {s.accepted ? (
          <p>
            {s.accepted} by the {s.sect}
            {s.disgraced && <span className="text-blood-bright">, and Disgraced: it gains no status</span>}.
          </p>
        ) : (
          <p className="text-mist">{s.sect ? `The ${s.sect} has no status in Horatio yet.` : "No sect: a character has status only in its sect."}</p>
        )}
        {s.derived.length > 0 && (
          <section aria-label="Status from titles, age and merits">
            <h3 className="text-xs tracking-wide text-mist uppercase">From titles, age and merits</h3>
            <ul className="mt-1 flex flex-col gap-1">
              {bySource(s.derived).map((g) => (
                <li key={g.key}>
                  <span className="text-gold">
                    {g.source}
                    {g.kind === "faction" && " faction"}
                  </span>
                  {g.troupe && g.troupe !== s.troupe_name && <span className="text-xs text-mist"> in {g.troupe}</span>}:{" "}
                  {g.status.map((d, i) => (
                    <span key={`${d.name}/${d.condition}`}>
                      {i > 0 && ", "}
                      {d.name}
                      {d.condition && <span className="text-xs text-mist"> ({d.condition})</span>}
                    </span>
                  ))}
                  {g.kind === "merit" && <span className="text-xs text-mist"> (innate)</span>}
                </li>
              ))}
            </ul>
          </section>
        )}
        {s.accepted && (
          <section aria-label="Fleeting status">
            <h3 className="text-xs tracking-wide text-mist uppercase">
              Fleeting: {fleeting.length} of {s.fleeting_cap}
            </h3>
            {fleeting.length ? (
              <ul className="mt-1 flex flex-col gap-2">
                {fleeting.map((h) => (
                  <HeldRow key={h.id} character={character} status={s} held={h} />
                ))}
              </ul>
            ) : (
              <p className="text-xs text-mist">None held.</p>
            )}
            {fleeting.length > s.fleeting_cap && (
              <p className="mt-1 text-xs text-blood-bright">Over the cap: only {s.fleeting_cap} count at a game. Give some up.</p>
            )}
          </section>
        )}
        {negative.length > 0 && (
          <section aria-label="Negative status">
            <h3 className="text-xs tracking-wide text-mist uppercase">Negative</h3>
            <ul className="mt-1 flex flex-col gap-2">
              {negative.map((h) => (
                <HeldRow key={h.id} character={character} status={s} held={h} />
              ))}
            </ul>
          </section>
        )}
        {s.unresolved.length > 0 && (
          <section aria-label="Status to resolve">
            <h3 className="text-xs tracking-wide text-mist uppercase">From before, for staff to resolve</h3>
            <ul className="mt-1 flex flex-col gap-1">
              {s.unresolved.map((name) => (
                <Unresolved key={name} character={character} status={s} name={name} />
              ))}
            </ul>
          </section>
        )}
        {bans.length > 0 && (
          <section aria-label="Status bans">
            <h3 className="text-xs tracking-wide text-mist uppercase">Status bans</h3>
            <p className="text-xs text-mist">A lesser ban cuts fleeting status to 3, a greater to 1 (MET: VTM p. 312).</p>
            <ul className="mt-1 flex flex-col gap-1.5">
              {bans.map((b) => (
                <BanRow key={b.applies_to} character={character} status={s} ban={b} />
              ))}
            </ul>
          </section>
        )}
        {adding && <AddStatus character={character} status={s} onDone={() => setAdding(false)} />}
      </div>
    </Card>
  );
}
