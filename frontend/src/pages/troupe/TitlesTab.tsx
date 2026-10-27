import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TitleOut, TitlesOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useAction } from "../../hooks";
import { titleGroups, titleStatus } from "./titleGroups";

/** The titles this troupe gives, by sect: the rule set's and its own, each with the
 * status it gives and who holds it here. */
export function TitlesTab({ troupeId }: { troupeId: string }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const titles = useQuery({ queryKey: ["titles", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", path)) });
  const add = useAction((title: TitleForm) => unwrap(api.POST("/api/troupes/{troupe_id}/titles", { ...path, body: title })));
  if (titles.isPending) return <Loading />;
  if (titles.error) return <ErrorText error={titles.error} />;

  const flagged = titles.data.titles.flatMap((t) => t.holders.filter((h) => h.out_of_sect).map((h) => ({ title: t, holder: h })));
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
      {titleGroups(titles.data.sects, titles.data.titles).map(([sect, list]) => (
        <Card key={sect ?? ""} title={sect ? `${sect} titles` : "Titles of any sect"}>
          <ul className="divide-y divide-ash">
            {list.map((t) => (
              <TitleRow key={t.name} troupeId={troupeId} title={t} data={titles.data} />
            ))}
          </ul>
        </Card>
      ))}
      {titles.data.court_order.length > 1 && <CourtOrder troupeId={troupeId} order={titles.data.court_order} />}
      <Card title="Add a title">
        <TitleFields
          data={titles.data}
          initial={{ name: "", sect: null, status: [] }}
          naming
          pending={add.isPending}
          save="Add"
          onSave={(title, reset) => add.mutate(title, { onSuccess: reset })}
        />
        <ErrorText error={add.error} />
        <p className="mt-3 text-xs text-mist">
          Give titles to characters on the Characters tab. A title of a sect goes only to characters of that sect, and a title means nothing outside this troupe.
        </p>
      </Card>
    </div>
  );
}

type TitleForm = { name: string; sect: string | null; status: string[] };

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

/** A title, what it gives, and who holds it; one the troupe added can be changed or removed. */
function TitleRow({ troupeId, title, data }: { troupeId: string; title: TitleOut; data: TitlesOut }) {
  const [editing, setEditing] = useState(false);
  const target = { params: { path: { troupe_id: troupeId, name: title.name } } };
  const change = useAction((t: TitleForm) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/titles/{name}", { ...target, body: { sect: t.sect, status: t.status } })),
  );
  const remove = useAction(() => unwrap(api.DELETE("/api/troupes/{troupe_id}/titles/{name}", target)));
  const gives = titleStatus(title);
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2" aria-label={title.name}>
      <span className="font-medium text-parchment">{title.name}</span>
      {title.house && <Badge tone="gold">ours</Badge>}
      {!title.offered && <Badge tone="blood">not a sect this troupe takes</Badge>}
      <span className="text-xs text-mist">{gives ? `Gives ${gives}` : "Gives no status"}</span>
      <span className="ml-auto flex flex-wrap items-center justify-end gap-x-2 gap-y-1 text-sm">
        {title.holders.length ? (
          title.holders.map((h) => (
            <Link
              key={h.character_id}
              to={`/characters/${h.character_id}`}
              className={h.out_of_sect ? "text-blood-bright hover:text-parchment" : "text-parchment hover:text-gold"}
              title={h.out_of_sect ? `Out of sect: ${h.character_name} is ${h.sect ?? "of no sect"}` : undefined}
            >
              {h.character_name}
              {h.out_of_sect && ` (${h.sect ?? "no sect"})`}
            </Link>
          ))
        ) : (
          <span className="text-xs text-mist">No one</span>
        )}
        {title.house && (
          <>
            <button
              type="button"
              aria-label={`Change the title ${title.name}`}
              className="rounded border border-ash px-1.5 text-xs text-mist hover:border-gold hover:text-gold"
              onClick={() => setEditing(true)}
            >
              Change
            </button>
            <button
              type="button"
              aria-label={`Remove the title ${title.name}`}
              className="px-1 text-mist hover:text-blood-bright"
              onClick={() => {
                if (window.confirm(`Remove ${title.name}? Anyone holding it loses it.`)) remove.mutate(undefined);
              }}
            >
              ×
            </button>
          </>
        )}
      </span>
      <ErrorText error={remove.error} />
      <Dialog title={`Change ${title.name}`} open={editing} onClose={() => setEditing(false)}>
        <TitleFields
          data={data}
          initial={{ name: title.name, sect: title.sect, status: title.status }}
          pending={change.isPending}
          save="Save"
          onSave={(t) => change.mutate(t, { onSuccess: () => setEditing(false) })}
        />
        <ErrorText error={change.error} />
        <p className="mt-3 text-xs text-mist">The change is for everyone who holds it, from their next game.</p>
      </Dialog>
    </li>
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
      <div>
        <Button type="submit" disabled={(naming && !title.name.trim()) || pending}>
          {save}
        </Button>
      </div>
    </form>
  );
}
