import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { RosterEntry, TitleOut, TitlesOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { EmptyState } from "../../components/EmptyState";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { SeatsSetting } from "./SeatsSetting";
import { pageLabel } from "../../components/TraitInfo";
import { aliasText, titleGives, titleGroups, titleStatusWords } from "./titleGroups";

/** The titles this troupe gives: those held first, then the vacant ones by sect,
 * folded away until asked for. Each with the status it gives and who holds it here. */
export function TitlesTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const titles = useQuery({ queryKey: ["titles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", path)) });
  const add = useAction((title: TitleForm) => unwrap(api.POST("/api/troupes/{troupe_id}/titles", { ...path, body: title })));
  const [showVacant, setShowVacant] = useState(false);
  if (titles.isPending) return <Loading />;
  if (titles.error) return <ErrorText error={titles.error} />;

  const flagged = titles.data.titles.flatMap((t) => t.holders.filter((h) => h.out_of_sect).map((h) => ({ title: t, holder: h })));
  const groups = titleGroups(titles.data.sects, titles.data.titles);
  const held = groups.flatMap(([, list]) => list.filter((t) => t.holders.length > 0));
  const vacant = groups
    .map(([sect, list]): [string | null, TitleOut[]] => [sect, list.filter((t) => t.holders.length === 0)])
    .filter(([, list]) => list.length > 0);
  const vacantCount = vacant.reduce((n, [, list]) => n + list.length, 0);
  return (
    <div className="flex flex-col gap-6">
      {flagged.length > 0 && (
        <Card title="Held out of sect">
          <p className="mb-2 text-sm text-mist">
            Given before titles had sects, or since the character changed sect. Each is kept until you take it on the Characters tab.
          </p>
          <ul className="flex flex-col gap-1 text-sm">
            {flagged.map(({ title, holder }) => (
              <li key={`${title.name}-${holder.character_id}`}>
                <Link to={`/characters/${holder.character_id}`} className="text-parchment hover:text-gold">
                  {holder.character_name}
                </Link>{" "}
                ({holder.sect ?? "no sect"}) holds {title.name}, a {title.sect} title.
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Card title="Held titles">
        {held.length === 0 ? (
          <EmptyState title="No one holds a title yet.">Give titles to characters on the Characters tab.</EmptyState>
        ) : (
          <TitleTable label="Held titles" troupeId={troupeId} titles={held} data={titles.data} held />
        )}
      </Card>
      {vacantCount > 0 && (
        <Card
          title="Vacant titles"
          actions={
            <Button variant="secondary" aria-expanded={showVacant} onClick={() => setShowVacant(!showVacant)}>
              {showVacant ? "Hide vacant" : `Show vacant (${vacantCount})`}
            </Button>
          }
        >
          {showVacant ? (
            <div className="flex flex-col gap-5">
              {vacant.map(([sect, list]) => (
                <section key={sect ?? ""}>
                  <h3 className="text-gold">{sect ? `${sect} titles` : "Titles of any sect"}</h3>
                  <TitleTable label={sect ? `${sect} titles` : "Titles of any sect"} troupeId={troupeId} titles={list} data={titles.data} />
                </section>
              ))}
            </div>
          ) : (
            <p className="text-sm text-mist">
              {vacantCount === 1 ? "1 title" : `${vacantCount} titles`} no one holds, of {vacant.map(([sect]) => sect ?? "any sect").join(", ")}.
            </p>
          )}
        </Card>
      )}
      {titles.data.court_order.length > 1 && <CourtOrder troupeId={troupeId} order={titles.data.court_order} />}
      <SeatsSetting troupeId={troupeId} />
      <Card title="Add a title">
        <TitleFields
          data={titles.data}
          initial={{ name: "", sect: null, status: [], unique: false }}
          naming
          pending={add.isPending}
          save="Add"
          onSave={(title, reset) =>
            add.mutate(title, {
              // A new title is held by no one, so it shows among the vacant ones.
              onSuccess: () => {
                reset();
                setShowVacant(true);
              },
            })
          }
        />
        <ErrorText error={add.error} />
        <p className="mt-3 text-xs text-mist">
          Give titles to characters on the Characters tab; players choose their own on their character's Status & Titles tab, unless the troupe keeps titles to
          staff. A title of a sect goes only to characters of that sect, and a title means nothing outside this troupe. Of a character's titles, only the
          active one gives status. What each status does is on the{" "}
          <Link to={`/troupes/${troupeId}/status`} className="text-parchment underline hover:text-gold">
            Status tab
          </Link>
          .
        </p>
      </Card>
    </div>
  );
}

type TitleForm = { name: string; sect: string | null; status: string[]; unique: boolean };

/** The troupe's own titles in their order on the Who's Who, after the rule set's,
 * each moved up or down one place. */
function CourtOrder({ troupeId, order }: { troupeId: string; order: string[] }) {
  const save = useAction((titles: string[]) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/court-order", { params: { path: { troupe_id: troupeId } }, body: { titles } })),
  );
  const move = (i: number, by: number) => {
    const next = [...order];
    [next[i], next[i + by]] = [next[i + by]!, next[i]!];
    save.mutate(next);
  };
  return (
    <Card title="Court order of our titles">
      <p className="mb-2 text-sm text-mist">On the Who’s Who, the court is in rank order: the rule set’s titles, then ours in this order.</p>
      <ol aria-label="Court order of our titles" className="flex flex-col gap-1 text-sm">
        {order.map((name, i) => (
          <li key={name} className="flex items-center gap-2">
            <span className="w-5 text-right text-mist tabular-nums">{i + 1}.</span>
            <span className="flex-1 text-parchment">{name}</span>
            <Button variant="ghost" className="min-h-8 px-2" aria-label={`Move ${name} up`} disabled={i === 0 || save.isPending} onClick={() => move(i, -1)}>
              ↑
            </Button>
            <Button
              variant="ghost"
              className="min-h-8 px-2"
              aria-label={`Move ${name} down`}
              disabled={i === order.length - 1 || save.isPending}
              onClick={() => move(i, 1)}
            >
              ↓
            </Button>
          </li>
        ))}
      </ol>
      <ErrorText error={save.error} />
    </Card>
  );
}

/** A column shown only on a wide screen; on a narrow one it folds in under the name. */
const WIDE = "hidden lg:table-cell";

/** Titles as a table: held ones with who holds each, vacant ones without. */
function TitleTable({ label, troupeId, titles, data, held = false }: { label: string; troupeId: string; titles: TitleOut[]; data: TitlesOut; held?: boolean }) {
  return (
    <table aria-label={label} className="w-full text-sm">
      {/* On a phone or a narrow window each row folds into a card, under the one heading. */}
      <thead className="max-lg:sr-only">
        <tr className="border-b border-ash text-left text-xs text-mist">
          <th className="py-2 pr-3 font-normal">Title</th>
          {held && <th className={`${WIDE} py-2 pr-3 font-normal`}>Holder</th>}
          <th className={`${WIDE} py-2 pr-3 font-normal`}>Sect</th>
          <th className={`${WIDE} py-2 pr-3 font-normal`}>Status it gives</th>
          <th className={`${WIDE} py-2 pr-3 font-normal`}>House rule</th>
          <th className={`${WIDE} py-2 pr-3 font-normal`}>One at a time</th>
          <th className="py-2 font-normal">
            <span className="sr-only">Actions</span>
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-ash">
        {titles.map((t) => (
          <TitleRow key={t.name} troupeId={troupeId} title={t} data={data} held={held} />
        ))}
      </tbody>
    </table>
  );
}

type Opened = "give" | "move" | "change" | "remove";

/** A title, what it gives, and who holds it, with what staff can do with it behind ⋯:
 * give it, move it or take it from a holder, and change or remove one the troupe added. */
function TitleRow({ troupeId, title, data, held }: { troupeId: string; title: TitleOut; data: TitlesOut; held: boolean }) {
  const [open, setOpen] = useState<Opened | null>(null);
  const close = () => setOpen(null);
  const toast = useToast();
  const client = useQueryClient();
  const target = { params: { path: { troupe_id: troupeId, name: title.name } } };
  const change = useAction(async (t: TitleForm) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/titles/{name}", { ...target, body: { sect: t.sect, status: t.status, unique: t.unique } }));
    close();
  });
  // Said and closed before the list is asked again, which takes the row away.
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}/titles/{name}", target));
    toast({ message: `${title.name} removed.` });
    close();
  });
  const take = useAction(async (holder: { character_id: string; character_name: string }) => {
    const roster = await client.fetchQuery(rosterQuery(troupeId));
    const entry = roster.find((e) => e.character_id === holder.character_id);
    if (!entry) throw new Error(`${holder.character_name} isn't on the troupe's list of characters.`);
    await setTitles(troupeId, entry.character_id, entry.titles.filter((n) => n !== title.name));
    toast({ message: `${title.name} taken from ${holder.character_name}.` });
  });
  const page = pageLabel(title.page);
  const alias = aliasText(title);
  const gives = [titleGives(titleStatusWords(title), title), page, title.note].filter(Boolean).join(" · ");
  const sect = title.sect ?? "Any sect";
  const holders = title.holders.map((h) => (
    <Link
      key={h.character_id}
      to={`/characters/${h.character_id}`}
      className={`block ${h.out_of_sect ? "text-blood-bright hover:text-parchment" : "text-parchment hover:text-gold"}`}
      title={h.out_of_sect ? `Out of sect: ${h.character_name} is ${h.sect ?? "of no sect"}` : undefined}
    >
      {h.character_name}
      {h.out_of_sect && ` (${h.sect ?? "no sect"})`}
      {h.active && <span className="text-xs text-mist"> · active</span>}
    </Link>
  ));
  const canGive = !held || !title.unique;
  return (
    <tr aria-label={title.name}>
      <td className="py-2.5 pr-3 align-top">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-medium text-parchment">{title.name}</span>
          {title.no_rules_yet && <Badge>No rules yet</Badge>}
          {!title.offered && <Badge tone="blood">Not a sect this troupe takes</Badge>}
          {title.house && (
            <Badge tone="gold" className="lg:hidden">
              House rule
            </Badge>
          )}
          {title.unique && <Badge className="lg:hidden">One at a time</Badge>}
        </span>
        {alias && <span className="block text-xs text-mist">{alias}</span>}
        {held && <span className="mt-0.5 block lg:hidden">{holders}</span>}
        <span className="mt-0.5 block text-xs text-mist lg:hidden">
          {sect} · {gives}
        </span>
      </td>
      {held && <td className={`${WIDE} py-2.5 pr-3 align-top`}>{holders}</td>}
      <td className={`${WIDE} py-2.5 pr-3 align-top whitespace-nowrap text-mist`}>{sect}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-xs text-mist`}>{gives}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top`}>{title.house && <Badge tone="gold">House rule</Badge>}</td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>{title.unique ? "Yes" : ""}</td>
      <td className="w-px py-1 text-right align-top">
        <ActionMenu label={`Actions for ${title.name}`} variant="ghost">
          <MenuGroup label="Who holds it">
            {held && <MenuItem onSelect={() => setOpen("move")}>Move to another holder…</MenuItem>}
            {canGive &&
              (title.offered ? (
                <MenuItem onSelect={() => setOpen("give")}>Give…</MenuItem>
              ) : (
                <MenuItem disabled>
                  Give…
                  <span className="block text-xs">The troupe doesn't take {title.sect ?? "its sect"}.</span>
                </MenuItem>
              ))}
            {title.holders.map((h) => (
              <MenuItem key={h.character_id} onSelect={() => take.mutate(h)}>
                Take from {h.character_name}
              </MenuItem>
            ))}
          </MenuGroup>
          {title.house && (
            <MenuGroup label="The troupe's own title">
              <MenuItem onSelect={() => setOpen("change")}>Change…</MenuItem>
              <MenuItem danger onSelect={() => setOpen("remove")}>
                Remove…
              </MenuItem>
            </MenuGroup>
          )}
        </ActionMenu>
        <ErrorText error={take.error} />
        {/* The dialogs sit here, as nothing but cells may sit in a row (Dialog sets its own text-left). */}
        <Dialog title={`Give ${title.name}`} open={open === "give"} onClose={close}>
          <PassTitle troupeId={troupeId} title={title} onDone={close} />
        </Dialog>
        <Dialog title={`Move ${title.name} to another holder`} open={open === "move"} onClose={close}>
          <PassTitle troupeId={troupeId} title={title} moving onDone={close} />
        </Dialog>
        <Dialog title={`Change ${title.name}`} open={open === "change"} onClose={close}>
          <TitleFields
            data={data}
            initial={{ name: title.name, sect: title.sect, status: title.status, unique: title.unique }}
            pending={change.isPending}
            save="Save"
            onSave={(t) => change.mutate(t)}
          />
          <ErrorText error={change.error} />
          <p className="mt-3 text-xs text-mist">The change is for everyone who holds it, from their next game.</p>
        </Dialog>
        <Dialog title={`Remove ${title.name}`} open={open === "remove"} onClose={close}>
          <p className="text-sm">
            Remove {title.name} from the troupe's titles? {title.holders.length ? "Anyone holding it loses it." : "No one holds it."}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
              Remove the title
            </Button>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
          </div>
          <ErrorText error={remove.error} />
        </Dialog>
      </td>
    </tr>
  );
}

/** The troupe's characters, with the titles each holds here: the Characters tab's list. */
const rosterQuery = (troupeId: string) => ({
  queryKey: ["roster", troupeId],
  queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/characters", { params: { path: { troupe_id: troupeId } } })),
});

/** Give a character in the troupe exactly these titles, as the Characters tab does. */
const setTitles = (troupeId: string, characterId: string, titles: string[]) =>
  unwrap(api.PUT("/api/troupes/{troupe_id}/characters/{character_id}/titles", { params: { path: { troupe_id: troupeId, character_id: characterId } }, body: { titles } }));

/** Give a title to a character who can hold it (of its sect, or of any sect for a title of any), or,
 * `moving`, give it to one and take it from a holder: given first, so a refusal loses nothing. */
function PassTitle({ troupeId, title, moving = false, onDone }: { troupeId: string; title: TitleOut; moving?: boolean; onDone: () => void }) {
  const roster = useQuery(rosterQuery(troupeId));
  const toast = useToast();
  const [from, setFrom] = useState(title.holders[0]?.character_id ?? "");
  const [to, setTo] = useState("");
  const entries = roster.data ?? [];
  const holds = (e: RosterEntry) => e.titles.includes(title.name);
  const can = entries
    .filter((e) => !e.retired && !holds(e) && (title.sect === null || e.sect === title.sect))
    .sort((a, b) => a.character_name.localeCompare(b.character_name));
  const pass = useAction(async () => {
    const giving = entries.find((e) => e.character_id === to);
    if (!giving) return;
    await setTitles(troupeId, giving.character_id, [...giving.titles, title.name]);
    const taking = moving ? entries.find((e) => e.character_id === from) : undefined;
    if (taking) await setTitles(troupeId, taking.character_id, taking.titles.filter((n) => n !== title.name));
    toast({ message: taking ? `${title.name} moved from ${taking.character_name} to ${giving.character_name}.` : `${title.name} given to ${giving.character_name}.` });
    onDone();
  });
  if (roster.isPending) return <Loading />;
  if (roster.error) return <ErrorText error={roster.error} />;
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        pass.mutate(undefined);
      }}
    >
      {moving && title.holders.length > 1 && (
        <Field label="From">
          <Select value={from} onChange={(e) => setFrom(e.target.value)}>
            {title.holders.map((h) => (
              <option key={h.character_id} value={h.character_id}>
                {h.character_name}
              </option>
            ))}
          </Select>
        </Field>
      )}
      {moving && title.holders.length === 1 && <p className="text-sm text-mist">From {title.holders[0]!.character_name}.</p>}
      {can.length ? (
        <Field label="To" hint={title.sect ? `Characters of the ${title.sect} who don't hold it.` : "Characters who don't hold it."}>
          <Select value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="">Choose a character</option>
            {can.map((e) => (
              <option key={e.character_id} value={e.character_id}>
                {e.character_name}
              </option>
            ))}
          </Select>
        </Field>
      ) : (
        <Empty>{title.sect ? `No other ${title.sect} character here can hold it.` : "No other character here can hold it."}</Empty>
      )}
      <div>
        <Button type="submit" disabled={!to || pass.isPending}>
          {moving ? "Move" : "Give"}
        </Button>
      </div>
      <ErrorText error={pass.error} />
    </form>
  );
}

/** A title's name (when adding it), its sect, and the abiding status it gives: of
 * that sect, or general status. */
function TitleFields({
  data,
  initial,
  naming = false,
  pending,
  save,
  onSave,
}: {
  data: TitlesOut;
  initial: TitleForm;
  naming?: boolean;
  pending: boolean;
  save: string;
  onSave: (title: TitleForm, reset: () => void) => void;
}) {
  const [title, setTitle] = useState(initial);
  const choicesFor = (sect: string | null) => data.status_choices.filter((c) => c.sect === "General" || c.sect === sect);
  const choices = choicesFor(title.sect);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(title, () => setTitle(initial));
      }}
    >
      <div className="flex flex-wrap gap-3">
        {naming && (
          <Field label="Name">
            <Input placeholder="Master of Elysium" value={title.name} onChange={(e) => setTitle({ ...title, name: e.target.value })} />
          </Field>
        )}
        <Field label="Sect">
          <Select
            value={title.sect ?? ""}
            onChange={(e) => {
              const sect = e.target.value || null;
              const kept = choicesFor(sect).map((c) => c.name);
              setTitle({ ...title, sect, status: title.status.filter((s) => kept.includes(s)) });
            }}
          >
            <option value="">Any sect</option>
            {data.sects.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1 text-sm text-mist">Abiding status it gives{title.sect ? ` (${title.sect} or general)` : " (general)"}</legend>
        {choices.length ? (
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {choices.map((c) => (
              <label key={c.name} className="flex items-center gap-1.5 text-sm">
                <input
                  type="checkbox"
                  checked={title.status.includes(c.name)}
                  onChange={(e) =>
                    setTitle({ ...title, status: e.target.checked ? [...title.status, c.name] : title.status.filter((s) => s !== c.name) })
                  }
                />
                {c.name}
              </label>
            ))}
          </div>
        ) : (
          <Empty>None.</Empty>
        )}
      </fieldset>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={title.unique} onChange={(e) => setTitle({ ...title, unique: e.target.checked })} />
        Only one character holds it at a time
        <span className="text-xs text-mist">(players can't choose it while someone does)</span>
      </label>
      <div>
        <Button type="submit" disabled={(naming && !title.name.trim()) || pending}>
          {save}
        </Button>
      </div>
    </form>
  );
}
