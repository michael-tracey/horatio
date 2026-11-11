import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BondOut, CharacterChoice } from "../../api/types";
import { BOND_PAGE, groupBonds, isOpen, levelName, partyIn, SOURCES, statusText, type BondSource } from "../../bonds";
import { DateInput } from "../../components/DateInput";
import { useToast } from "../../components/Toast";
import { Button, Card, Empty, ErrorText, Field, Input, Loading, Select, Textarea } from "../../components/ui";
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
 * break them, and say which are known to their regnants. Only shown while the troupe
 * tracks bonds.
 */
export function BondsTab({ troupeId }: { troupeId: string }) {
  const [by, setBy] = useState<By>("thrall");
  const [past, setPast] = useState(false);
  const [adding, setAdding] = useState<"drink" | "enter" | null>(null);
  const bonds = useQuery({
    queryKey: ["troupe-bonds", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/bonds", { params: { path: { troupe_id: troupeId } } })),
  });
  if (bonds.isPending) return <Loading />;
  if (bonds.error) return <ErrorText error={bonds.error} />;
  const shown = past ? bonds.data.bonds : bonds.data.bonds.filter(isOpen);
  const closed = bonds.data.bonds.length - bonds.data.bonds.filter(isOpen).length;
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
          Each separate night a character drinks a vampire&apos;s blood is one drink, up to a full bond at three, which wipes away every lesser bond they have (
          {BOND_PAGE}). The level comes from the drinks log. A thrall&apos;s player sees their own bonds; a regnant&apos;s player sees one only once it&apos;s
          marked known to them.
        </p>
        {adding === "drink" && <NewDrinkForm troupeId={troupeId} characters={bonds.data.characters} onDone={() => setAdding(null)} />}
        {adding === "enter" && <EnterForm troupeId={troupeId} characters={bonds.data.characters} onDone={() => setAdding(null)} />}
      </Card>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="List bonds" className="flex gap-1">
          {(["thrall", "regnant"] as const).map((b) => (
            <Button key={b} variant={by === b ? "secondary" : "ghost"} aria-pressed={by === b} onClick={() => setBy(b)}>
              By {b}
            </Button>
          ))}
        </div>
        {closed > 0 && (
          <label className="flex items-center gap-2 text-sm text-mist">
            <input type="checkbox" checked={past} onChange={(e) => setPast(e.target.checked)} />
            Show ended and broken bonds ({closed})
          </label>
        )}
      </div>
      {groups.length === 0 ? (
        <Empty>No blood bonds yet.</Empty>
      ) : (
        groups.map((g) => (
          <section key={g.name} aria-label={g.name} className="rounded-lg border border-ash bg-dusk p-3 sm:p-4">
            <h3 className="mb-2 text-base text-gold">
              {g.name}
              <span className="text-sm text-mist">{by === "thrall" ? ", bound to" : ", whose blood binds"}</span>
            </h3>
            <ul className="flex flex-col gap-3">
              {g.bonds.map((bond) => (
                <BondRow key={bond.id} troupeId={troupeId} bond={bond} by={by} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}

function BondRow({ troupeId, bond, by }: { troupeId: string; bond: BondOut; by: By }) {
  const dates = useDates();
  const [doing, setDoing] = useState<"drink" | "break" | null>(null);
  const [log, setLog] = useState(false);
  const path = { params: { path: { troupe_id: troupeId, bond_id: bond.id } } };
  const known = useAction((on: boolean) => unwrap(api.PUT("/api/troupes/{troupe_id}/bonds/{bond_id}/known", { ...path, body: { known: on } })));
  const open = isOpen(bond);
  const label = `${bond.thrall.name} bound to ${bond.regnant.name}`;
  const other = by === "thrall" ? bond.regnant : bond.thrall;
  return (
    <li aria-label={label} className="flex flex-col gap-2 border-t border-ash pt-2 text-sm first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p>
          <span className="text-parchment">{other.name}</span>
          {other.kind === "npc" && <span className="text-mist"> (NPC)</span>}
          {other.kind === null && <span className="text-mist"> (name only)</span>}
          <span className={open ? "text-gold" : "text-mist"}> · {levelName(bond.level)}</span>
          {bond.status !== "active" && <span className="text-mist"> · {statusText(bond)}</span>}
          {bond.last_drink && <span className="text-mist"> · last drink {dates.day(bond.last_drink)}</span>}
        </p>
        {open && doing === null && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => setDoing("drink")}>
              Add a drink
            </Button>
            <Button variant="ghost" onClick={() => setDoing("break")}>
              Break
            </Button>
          </div>
        )}
      </div>
      {open && (
        <label className="flex items-center gap-2 text-mist">
          <input type="checkbox" checked={bond.known_to_regnant} disabled={known.isPending} onChange={(e) => known.mutate(e.target.checked)} />
          Known to {bond.regnant.name}: their player sees it
        </label>
      )}
      <ErrorText error={known.error} />
      {doing === "drink" && <DrinkForm troupeId={troupeId} bond={bond} onDone={() => setDoing(null)} />}
      {doing === "break" && <BreakForm troupeId={troupeId} bond={bond} onDone={() => setDoing(null)} />}
      <div>
        <button type="button" className="text-xs text-mist underline hover:text-parchment" aria-expanded={log} onClick={() => setLog(!log)}>
          {log ? "Hide the drinks log" : `Drinks log (${bond.entries.length})`}
        </button>
        {log && (
          <ol aria-label={`Drinks log of ${label}`} className="mt-1 flex flex-col gap-1 pl-3 text-xs">
            {bond.entries.map((e) => (
              <li key={e.id}>
                {dates.day(e.night)}:{" "}
                {e.kind === "entered" ? `entered at ${levelName(e.level ?? 1).toLowerCase()}` : `a drink, ${SOURCES.find((s) => s.value === e.source)?.label.toLowerCase()}`}
                {e.note && <span className="text-mist"> · {e.note}</span>}
                {e.recorded_by && <span className="text-mist"> · by {e.recorded_by}</span>}
              </li>
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
  set: (change: Partial<{ night: string; source: BondSource; note: string }>) => void;
}) {
  return (
    <>
      <div className="flex flex-wrap gap-3">
        <Field label="Night">
          <DateInput required value={night} onChange={(e) => set({ night: e.target.value })} className="w-44" />
        </Field>
        <Field label="Where it was told">
          <Select value={source} onChange={(e) => set({ source: e.target.value as BondSource })} className="w-44">
            {SOURCES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Field label="Note (optional)">
        <Input maxLength={2000} value={note} onChange={(e) => set({ note: e.target.value })} />
      </Field>
    </>
  );
}

function useDrink(dates: ReturnType<typeof useDates>) {
  const [drink, setDrink] = useState<{ night: string; source: BondSource; note: string }>({ night: today(dates), source: "game", note: "" });
  return [drink, (change: Partial<typeof drink>) => setDrink({ ...drink, ...change })] as const;
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
        <WhoPicker characters={characters} who={thrall.who} name={thrall.name} onChange={setThrall} />
      </Field>
      <Field label="Regnant" hint="The vampire whose blood it was.">
        <WhoPicker characters={characters} who={regnant.who} name={regnant.name} onChange={setRegnant} />
      </Field>
    </div>
  );
}

function NewDrinkForm({ troupeId, characters, onDone }: { troupeId: string; characters: CharacterChoice[]; onDone: () => void }) {
  const dates = useDates();
  const toast = useToast();
  const [thrall, setThrall] = useState({ who: "", name: "" });
  const [regnant, setRegnant] = useState({ who: "", name: "" });
  const [drink, setDrink] = useDrink(dates);
  const t = partyIn(thrall.who, thrall.name);
  const r = partyIn(regnant.who, regnant.name);
  const save = useAction(async () => {
    if (!t || !r) return;
    const bond = await unwrap(api.POST("/api/troupes/{troupe_id}/bonds/drinks", { params: { path: { troupe_id: troupeId } }, body: { thrall: t, regnant: r, ...drink } }));
    toast({ message: `${bond.thrall.name} to ${bond.regnant.name}: ${levelName(bond.level).toLowerCase()}.` });
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
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !t || !r || !drink.night}>
          Record the drink
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function EnterForm({ troupeId, characters, onDone }: { troupeId: string; characters: CharacterChoice[]; onDone: () => void }) {
  const dates = useDates();
  const [thrall, setThrall] = useState({ who: "", name: "" });
  const [regnant, setRegnant] = useState({ who: "", name: "" });
  const [level, setLevel] = useState(1);
  const [night, setNight] = useState(today(dates));
  const [reason, setReason] = useState("");
  const t = partyIn(thrall.who, thrall.name);
  const r = partyIn(regnant.who, regnant.name);
  const save = useAction(async () => {
    if (!t || !r) return;
    await unwrap(api.POST("/api/troupes/{troupe_id}/bonds", { params: { path: { troupe_id: troupeId } }, body: { thrall: t, regnant: r, level, night, reason } }));
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
      <p className="text-xs text-mist">A bond that already stands, such as one from before Horatio: it starts at its level, and later drinks add to it.</p>
      <Sides
        characters={characters}
        thrall={thrall}
        regnant={regnant}
        setThrall={(who, name) => setThrall({ who, name })}
        setRegnant={(who, name) => setRegnant({ who, name })}
      />
      <div className="flex flex-wrap gap-3">
        <Field label="Level">
          <Select value={level} onChange={(e) => setLevel(Number(e.target.value))} className="w-44">
            {[1, 2, 3].map((l) => (
              <option key={l} value={l}>
                {levelName(l)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Since" hint="The night it stood at this level.">
          <DateInput required value={night} onChange={(e) => setNight(e.target.value)} className="w-44" />
        </Field>
      </div>
      <Field label="Reason">
        <Textarea rows={2} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={save.isPending || !t || !r || !night || !reason.trim()}>
          Enter the bond
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function DrinkForm({ troupeId, bond, onDone }: { troupeId: string; bond: BondOut; onDone: () => void }) {
  const dates = useDates();
  const toast = useToast();
  const [drink, setDrink] = useDrink(dates);
  const save = useAction(async () => {
    const after = await unwrap(api.POST("/api/troupes/{troupe_id}/bonds/{bond_id}/drinks", { params: { path: { troupe_id: troupeId, bond_id: bond.id } }, body: drink }));
    toast({ message: `${after.thrall.name} to ${after.regnant.name}: ${levelName(after.level).toLowerCase()}.` });
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

function BreakForm({ troupeId, bond, onDone }: { troupeId: string; bond: BondOut; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const save = useAction(async () => {
    await unwrap(api.POST("/api/troupes/{troupe_id}/bonds/{bond_id}/break", { params: { path: { troupe_id: troupeId, bond_id: bond.id } }, body: { reason } }));
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
      <Field label="Reason" hint="Breaking a bond is hard, but it can be done (p. 296).">
        <Textarea rows={2} maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="danger" disabled={save.isPending || !reason.trim()}>
          Break the bond
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
