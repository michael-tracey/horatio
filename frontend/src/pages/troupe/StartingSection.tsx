import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { StartingCategoryOut, StartingRule } from "../../api/types";
import { Badge, Button, Card, ErrorText, Input, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { DiablerieFlaws } from "./DiablerieFlaws";
import { useHouseSplat } from "./HouseSplat";
import { XpRangeCard } from "./XpRange";

/**
 * What new characters get free in each category: picks at a rating, or a budget
 * of points. A troupe's rules for a category replace all the rule set's for it,
 * for characters built for this troupe or homed in it while still being built.
 */
export function StartingSection({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  // Starting points are kept for each splat; the rest of this page is the troupe's.
  const { splat, picker } = useHouseSplat(troupeId);
  const starting = useQuery({
    queryKey: ["starting", troupeId, splat],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/creation", { params: { path: { troupe_id: troupeId }, query: { splat } } })),
  });
  if (starting.isPending) return <Loading />;
  if (starting.error) return <ErrorText error={starting.error} />;
  return (
    <div className="flex flex-col gap-6">
      <Card title="How starting points work">
        <p className="text-sm">
          A new character places these in the creation wizard: picks give a trait that many free dots, and a budget of points
          buys merits (or is paid back by flaws) at their value.{" "}
          {canEdit ? "Change a category to play it differently here; going back uses the rule set's again." : ""}
        </p>
        <p className="mt-2 text-sm text-mist">
          Changes apply to characters being built for this troupe straight away. Characters already finished are not affected.
        </p>
      </Card>
      <Card title="Starting points">
        {picker && <div className="mb-2">{picker}</div>}
        <ul className="divide-y divide-ash">
          {starting.data.map((c) => (
            <CategoryRow key={c.key} troupeId={troupeId} splat={splat} category={c} canEdit={canEdit} />
          ))}
        </ul>
      </Card>
      <ExperienceDefaults troupeId={troupeId} canEdit={canEdit} />
      <XpRangeCard
        troupeId={troupeId}
        canEdit={false}
        link={
          canEdit && (
            <Link to={`/troupes/${troupeId}`} className="text-sm text-mist underline hover:text-parchment">
              Set them on About
            </Link>
          )
        }
      />
      <StartingBlood troupeId={troupeId} canEdit={canEdit} />
      <DiablerieFlaws troupeId={troupeId} canEdit={canEdit} />
    </div>
  );
}

/** The XP this troupe usually gives: what awarding and new downtime cycles start at. */
function ExperienceDefaults({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ starting_xp: 30, session_xp: 8, downtime_xp: 2 });
  const save = useAction(async () => {
    await unwrap(api.PATCH("/api/troupes/{troupe_id}", { ...path, body: form }));
    setEditing(false);
  });
  if (!troupe.data) return null;
  const t = troupe.data;
  return (
    <Card
      title="Experience"
      actions={
        canEdit &&
        !editing && (
          <Button
            variant="ghost"
            className="min-h-8 px-2"
            onClick={() => {
              setForm({ starting_xp: t.starting_xp, session_xp: t.session_xp, downtime_xp: t.downtime_xp });
              setEditing(true);
            }}
          >
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        What this troupe usually gives. Awarding XP starts at the session amount, and each new downtime cycle at the completion amount; either can be changed
        there. The XP floor and ceiling start from the starting XP.
      </p>
      {editing ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            To start
            <Input type="number" min={0} max={10000} required value={form.starting_xp} onChange={(e) => setForm({ ...form, starting_xp: Number(e.target.value) })} className="w-24" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            For a game session
            <Input type="number" min={0} max={100} required value={form.session_xp} onChange={(e) => setForm({ ...form, session_xp: Number(e.target.value) })} className="w-24" />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            For completing a downtime
            <Input type="number" min={0} max={100} required value={form.downtime_xp} onChange={(e) => setForm({ ...form, downtime_xp: Number(e.target.value) })} className="w-24" />
          </label>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <ErrorText error={save.error} />
        </form>
      ) : (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-mist">To start</dt>
          <dd>{t.starting_xp} XP</dd>
          <dt className="text-mist">For a game session</dt>
          <dd>{t.session_xp} XP</dd>
          <dt className="text-mist">For completing a downtime</dt>
          <dd>{t.downtime_xp} XP</dd>
        </dl>
      )}
    </Card>
  );
}

/** House rule: the blood a reset for the next game gives each character. */
function StartingBlood({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const [editing, setEditing] = useState(false);
  const [full, setFull] = useState(true);
  const [blood, setBlood] = useState(5);
  const save = useAction(async () => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/starting-blood", { ...path, body: { blood: full ? null : blood } }));
    setEditing(false);
  });
  if (!troupe.data) return null;
  const t = troupe.data;
  const text = t.starting_blood === null ? "Full: the generation's most" : `${t.starting_blood} blood, or the generation's most if that is less`;
  return (
    <Card
      title="Blood at the start of a game"
      actions={
        canEdit &&
        !editing && (
          <Button
            variant="ghost"
            className="min-h-8 px-2"
            aria-label="Change starting blood"
            onClick={() => {
              setFull(t.starting_blood === null);
              setBlood(t.starting_blood ?? 5);
              setEditing(true);
            }}
          >
            Change
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">What resetting a character's Play View for the next game puts their blood back to.</p>
      {editing ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input type="radio" name="starting-blood" checked={full} onChange={() => setFull(true)} />
            Full
          </label>
          <label className="flex min-h-10 items-center gap-2 text-sm">
            <input type="radio" name="starting-blood" checked={!full} onChange={() => setFull(false)} />
            This much:
            <Input
              type="number"
              min={0}
              max={30}
              aria-label="Starting blood"
              value={blood}
              disabled={full}
              onChange={(e) => setBlood(Number(e.target.value))}
              className="w-20"
            />
          </label>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
          <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
            Cancel
          </Button>
          <ErrorText error={save.error} />
        </form>
      ) : (
        <p className="text-sm">{text}</p>
      )}
    </Card>
  );
}

function CategoryRow({ troupeId, splat, category, canEdit }: { troupeId: string; splat: string; category: StartingCategoryOut; canEdit: boolean }) {
  const [editing, setEditing] = useState(false);
  const path = { params: { path: { troupe_id: troupeId, category: category.key }, query: { splat } } };
  const reset = useAction(() => unwrap(api.DELETE("/api/troupes/{troupe_id}/creation/{category}", path)));
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-48 flex-1 text-sm">
          <span className="text-parchment">{category.name}</span>: {category.text}
          {category.house && <span className="block text-xs text-mist">The rule set's: {category.book_text}</span>}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {category.house && <Badge tone="gold">this troupe</Badge>}
          {canEdit && !editing && (
            <Button variant="ghost" className="min-h-8 px-2" aria-label={`Change starting ${category.name}`} onClick={() => setEditing(true)}>
              Change
            </Button>
          )}
          {canEdit && category.house && !editing && (
            <Button variant="ghost" className="min-h-8 px-2" aria-label={`Use the rule set's starting ${category.name}`} onClick={() => reset.mutate(undefined)}>
              Use the rule set's
            </Button>
          )}
        </span>
      </div>
      <ErrorText error={reset.error} />
      {editing && <StartingEditor troupeId={troupeId} splat={splat} category={category} onClose={() => setEditing(false)} />}
    </li>
  );
}

type Row = { rating: string; picks: string; points: string; restriction: string | null; when: StartingRule["when"]; when_text: string | null };

function StartingEditor({ troupeId, splat, category, onClose }: { troupeId: string; splat: string; category: StartingCategoryOut; onClose: () => void }) {
  const points = category.book.some((r) => r.points !== null);
  // Start from the rules as played, so the book's restrictions and conditions carry over.
  const [rows, setRows] = useState<Row[]>(
    category.rules.map((r) => ({
      rating: r.rating?.toString() ?? "",
      picks: r.picks?.toString() ?? "",
      points: r.points?.toString() ?? "",
      restriction: r.restriction ?? null,
      when: r.when ?? null,
      when_text: r.when_text ?? null,
    })),
  );
  const update = (i: number, change: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...change } : r)));
  const save = useAction(async () => {
    await unwrap(
      api.PUT("/api/troupes/{troupe_id}/creation/{category}", {
        params: { path: { troupe_id: troupeId, category: category.key }, query: { splat } },
        body: {
          rules: rows.map((r) =>
            points
              ? { points: Number(r.points) }
              : { rating: Number(r.rating), picks: Number(r.picks), restriction: r.restriction, when: r.when },
          ),
        },
      }),
    );
    onClose();
  });
  const name = category.name.toLowerCase();

  return (
    <form
      className="mt-3 flex flex-col gap-3 rounded-md border border-ash bg-night/40 p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      {points ? (
        <label className="flex items-center gap-2 text-sm">
          <Input
            type="number"
            min={1}
            aria-label={`Points for ${name}`}
            value={rows[0]?.points ?? ""}
            onChange={(e) => setRows([{ ...(rows[0] ?? { rating: "", picks: "", restriction: null, when: null, when_text: null }), points: e.target.value }])}
            className="w-20"
          />
          points
        </label>
      ) : (
        <>
          {rows.map((r, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 text-sm">
              <Input type="number" min={1} aria-label={`Picks, row ${i + 1}`} value={r.picks} onChange={(e) => update(i, { picks: e.target.value })} className="w-16" />
              at
              <Input
                type="number"
                min={1}
                max={category.max_rating ?? undefined}
                aria-label={`Dots, row ${i + 1}`}
                value={r.rating}
                onChange={(e) => update(i, { rating: e.target.value })}
                className="w-16"
              />
              dots
              <label className="flex items-center gap-1.5 text-mist">
                <input type="checkbox" checked={r.restriction === "in_clan"} onChange={(e) => update(i, { restriction: e.target.checked ? "in_clan" : null })} />
                in-clan only
              </label>
              {r.when_text && <Badge>{r.when_text}</Badge>}
              <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove row ${i + 1}`} onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                Remove
              </Button>
            </div>
          ))}
          <div>
            <Button
              type="button"
              variant="secondary"
              className="min-h-8"
              onClick={() => setRows([...rows, { rating: "1", picks: "1", points: "", restriction: null, when: null, when_text: null }])}
            >
              Add picks
            </Button>
          </div>
        </>
      )}
      <ErrorText error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending || rows.length === 0}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
