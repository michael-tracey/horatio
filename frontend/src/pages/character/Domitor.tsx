import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useDeferredValue, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, DomitorOut, SheetOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { listed } from "./creation/notices";
import { CAITIFF, CAITIFF_CHOOSES, caitiffChoices, clansOf, disciplineDots, domitorBody, draftMissing, inClanOf, type DomitorDraft } from "./domitor";

/** A ghoul's domitor, as `GET /domitor` has it; null while it has none. */
export function useDomitor(character: CharacterOut, enabled = true) {
  return useQuery({
    queryKey: ["domitor", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/domitor", { params: { path: { character_id: character.id } } })),
    enabled,
  });
}

/** Who the domitor is, in a line, with its in-clan disciplines, which are the ghoul's. */
export function DomitorSummary({ domitor }: { domitor: DomitorOut }) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>
        Bound to{" "}
        {domitor.character_id ? (
          <Link className="text-gold underline" to={`/characters/${domitor.character_id}`}>
            {domitor.name}
          </Link>
        ) : (
          <span className="text-parchment">{domitor.name}</span>
        )}
        {domitor.clan && `, ${domitor.clan}`}
        {domitor.character_id ? "." : ", who is not in Horatio."}
      </p>
      <p className="text-mist">
        {domitor.in_clan.length ? `In-clan disciplines, the domitor's: ${listed(domitor.in_clan)}.` : "No in-clan disciplines yet."}
      </p>
    </div>
  );
}

/**
 * The domitor on a ghoul's sheet: who it is, and, until a home troupe accepts the
 * ghoul, a way for its player to bind it to another (p. 297).
 */
export function DomitorCard({ character, sheet, catalogue, canChange }: { character: CharacterOut; sheet: SheetOut; catalogue?: CatalogueOut; canChange: boolean }) {
  return (
    <Card dense title="Domitor">
      <DomitorPanel character={character} sheet={sheet} catalogue={catalogue} canChange={canChange} />
    </Card>
  );
}

/** Who the domitor is, and the way to choose one: open at once while there is none, if `openWhenNone`. */
export function DomitorPanel({
  character,
  sheet,
  catalogue,
  canChange,
  openWhenNone = false,
}: {
  character: CharacterOut;
  sheet: SheetOut;
  catalogue?: CatalogueOut;
  canChange: boolean;
  openWhenNone?: boolean;
}) {
  const domitor = useDomitor(character);
  const [changing, setChanging] = useState(false);
  if (domitor.isPending) return null;
  const open = canChange && !!catalogue && (changing || (openWhenNone && !domitor.data));
  return (
    <div className="flex flex-col gap-3">
      {domitor.data ? <DomitorSummary domitor={domitor.data} /> : !openWhenNone && <p className="text-sm text-mist">No domitor yet.</p>}
      <ErrorText error={domitor.error} />
      {canChange && catalogue && !open && (
        <Button variant="secondary" className="self-start" onClick={() => setChanging(true)}>
          {domitor.data ? "Change domitor" : "Choose domitor"}
        </Button>
      )}
      {open && <DomitorForm character={character} sheet={sheet} catalogue={catalogue} onDone={domitor.data ? () => setChanging(false) : undefined} />}
    </div>
  );
}

/**
 * Bind the ghoul to its domitor: a vampire PC or NPC its player can see, found by
 * name, or one not in Horatio, by name, clan and bloodline (for a Caitiff, the three
 * in-clan disciplines it chose, which staff check at approval). Discipline dots the
 * ghoul has already stay where they are, or all move to the new domitor's in-clan
 * disciplines (p. 297).
 */
export function DomitorForm({ character, sheet, catalogue, onDone }: { character: CharacterOut; sheet: SheetOut; catalogue: CatalogueOut; onDone?: () => void }) {
  const path = { path: { character_id: character.id } };
  const [draft, setDraft] = useState<DomitorDraft>({ kind: "linked", choice: null });
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const found = useQuery({
    queryKey: ["domitor-choices", character.id, q],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/domitor/choices", { params: { ...path, query: { q } } })),
    enabled: draft.kind === "linked",
    placeholderData: (previous) => previous,
  });
  const held = disciplineDots(sheet);
  const total = held.reduce((n, t) => n + t.rating, 0);
  const [disciplines, setDisciplines] = useState<"keep" | "move">("keep");
  const [moved, setMoved] = useState<Record<string, number>>({});
  const inClan = inClanOf(draft, catalogue);
  const placed = Object.values(moved).reduce((n, r) => n + r, 0);
  const missing = draftMissing(draft) ?? (disciplines === "move" && placed !== total ? `Move all ${total} dots; ${placed} are placed.` : null);
  const client = useQueryClient();
  const save = useAction(async () => {
    const saved = await unwrap(api.PUT("/api/characters/{character_id}/domitor", { params: path, body: domitorBody(draft, disciplines, moved) }));
    // The save answers with the domitor as it now is: shown at once, not once every
    // query on the page has been asked again, which takes seconds on a busy server
    // (#334). A read still out from before the save would only bring the old one back.
    const key = ["domitor", character.id];
    await client.cancelQueries({ queryKey: key });
    client.setQueryData(key, saved);
    return saved;
  });
  const named = draft.kind === "named" ? draft : { kind: "named" as const, name: "", clan: "", three: ["", "", ""] };

  return (
    <form
      aria-label="Choose the domitor"
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: () => onDone?.() });
      }}
    >
      <fieldset className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <legend className="mb-1 text-mist">Where is the domitor?</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name="domitor-kind" checked={draft.kind === "linked"} onChange={() => setDraft({ kind: "linked", choice: null })} />
          A vampire in Horatio
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name="domitor-kind" checked={draft.kind === "named"} onChange={() => setDraft(named)} />
          Not in Horatio
        </label>
      </fieldset>
      {draft.kind === "linked" ? (
        <>
          <Field label="Find a vampire" hint="Your own vampires, and those in troupes whose sheets you see. Only those with a clan.">
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name…" />
          </Field>
          {found.data && found.data.length === 0 && <p className="text-sm text-mist">No vampire found.</p>}
          {found.data && found.data.length > 0 && (
            <ul aria-label="Vampires found" className="flex flex-col gap-1">
              {found.data.map((c) => (
                <li key={c.character_id}>
                  <label className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm ${draft.choice?.character_id === c.character_id ? "bg-ash/60" : "hover:bg-ash/40"}`}>
                    <input type="radio" name="domitor-choice" checked={draft.choice?.character_id === c.character_id} onChange={() => setDraft({ kind: "linked", choice: c })} />
                    <span className="text-parchment">{c.name}</span>
                    <span className="text-mist">
                      {c.clan} · {c.kind === "npc" ? "NPC" : "PC"}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          <ErrorText error={found.error} />
        </>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Domitor's name">
            <Input maxLength={200} value={named.name} onChange={(e) => setDraft({ ...named, name: e.target.value })} />
          </Field>
          <Field label="Domitor's clan">
            <Select value={named.clan} onChange={(e) => setDraft({ ...named, clan: e.target.value })}>
              <option value="">Choose…</option>
              {clansOf(catalogue).map((clan) => (
                <option key={clan}>{clan}</option>
              ))}
            </Select>
          </Field>
          {named.clan === CAITIFF &&
            Array.from({ length: CAITIFF_CHOOSES }, (_, i) => (
              <Field key={i} label={`Caitiff's in-clan discipline ${i + 1}`} hint={i === CAITIFF_CHOOSES - 1 ? "The three the domitor chose. Staff check them at approval." : undefined}>
                <Select value={named.three[i] ?? ""} onChange={(e) => setDraft({ ...named, three: named.three.map((d, j) => (j === i ? e.target.value : d)) })}>
                  <option value="">Choose…</option>
                  {caitiffChoices(catalogue).map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </Select>
              </Field>
            ))}
        </div>
      )}
      {inClan.length > 0 && <p className="text-sm text-mist">{character.name}'s in-clan disciplines would be the domitor's: {listed(inClan)}.</p>}
      {total > 0 && (
        <fieldset className="flex flex-col gap-2 text-sm">
          <legend className="mb-1 text-mist">
            {character.name}'s {total} discipline {total === 1 ? "dot" : "dots"} ({listed(held.map((t) => `${t.name} ${t.rating}`))})
          </legend>
          <label className="flex items-center gap-2">
            <input type="radio" name="domitor-dots" checked={disciplines === "keep"} onChange={() => setDisciplines("keep")} />
            Keep them where they are
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name="domitor-dots" checked={disciplines === "move"} onChange={() => setDisciplines("move")} />
            Move them all to the new domitor's in-clan disciplines
          </label>
          {disciplines === "move" && (
            <div className="grid gap-2 pl-6 sm:grid-cols-3">
              {inClan.map((name) => (
                <Field key={name} label={name}>
                  <Select value={moved[name] ?? 0} onChange={(e) => setMoved({ ...moved, [name]: Number(e.target.value) })}>
                    {Array.from({ length: 6 }, (_, n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </div>
          )}
        </fieldset>
      )}
      {missing && <p className="text-xs text-mist">{missing}</p>}
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={!!missing || save.isPending}>
          Save domitor
        </Button>
        {onDone && (
          <Button type="button" variant="ghost" onClick={onDone}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
