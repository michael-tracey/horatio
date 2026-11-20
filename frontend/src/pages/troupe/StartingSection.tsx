import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { StartingCategoryOut, StartingRule } from "../../api/types";
import { Explainer } from "../../components/Explainer";
import { Checkbox } from "../../components/Checkbox";
import { RadioList } from "../../components/RadioList";
import { SettingCard, SettingForm, useSettingForm } from "../../components/SettingCard";
import { Badge, Button, Card, ErrorText, Field, Input, Loading } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { ClanRarity } from "./ClanRarity";
import { DefaultBloodlines } from "./DefaultBloodlines";
import { troupeSettings } from "./features";
import { useHouseSplat } from "./HouseSplat";
import { SETTINGS } from "./settingsIndex";

/**
 * What new characters get free in each category: picks at a rating, or a budget
 * of points, how rare each clan is, and its default bloodline. A troupe's rules for a category replace all the rule set's for it,
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
      <Explainer id="rules-starting" title="How starting points work">
        <p className="text-sm">
          A new character places these during step-by-step creation: picks give a trait that many free dots. Merits are bought with
          the character's starting XP, up to their budget of points, and flaws add their points to it, up to theirs (p. 106).{" "}
          {canEdit ? "Change a category to play it differently here; going back uses the rule set's again." : ""}
        </p>
        <p className="mt-2 text-sm text-mist">
          Changes apply to characters being built for this troupe straight away. Characters already finished are not affected.
        </p>
      </Explainer>
      <Card title="Starting points">
        {picker && <div className="mb-2">{picker}</div>}
        <ul className="divide-y divide-ash">
          {starting.data.map((c) => (
            <CategoryRow key={c.key} troupeId={troupeId} splat={splat} category={c} canEdit={canEdit} />
          ))}
        </ul>
      </Card>
      <ClanRarity troupeId={troupeId} canEdit={canEdit} />
      <DefaultBloodlines troupeId={troupeId} canEdit={canEdit} />
      <p className="text-sm text-mist">
        Starting XP and the XP floor and ceiling are in Troupe settings, under{" "}
        <Link to={`/troupes/${troupeId}/${troupeSettings("xp")}`} className="underline hover:text-parchment">
          XP
        </Link>
        ; blood at the start of a game and diablerie under{" "}
        <Link to={`/troupes/${troupeId}/${troupeSettings("blood")}`} className="underline hover:text-parchment">
          Blood, diablerie and feeding
        </Link>
        ; Golconda in its{" "}
        <Link to={`/troupes/${troupeId}/${troupeSettings()}`} className="underline hover:text-parchment">
          Features
        </Link>
        .
      </p>
    </div>
  );
}

/** The XP this troupe usually gives: what awarding and new downtime cycles start at. */
export function ExperienceDefaults({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const t = troupe.data;
  const form = useSettingForm({ starting_xp: t?.starting_xp ?? 0, session_xp: t?.session_xp ?? 0, downtime_xp: t?.downtime_xp ?? 0 }, (body) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { ...path, body })),
  );
  if (!t) return null;
  if (!canEdit)
    return (
      <SettingCard setting={SETTINGS.experience} readOnly>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-mist">To start</dt>
          <dd>{t.starting_xp} XP</dd>
          <dt className="text-mist">For a game session</dt>
          <dd>{t.session_xp} XP</dd>
          <dt className="text-mist">For completing a downtime</dt>
          <dd>{t.downtime_xp} XP</dd>
        </dl>
      </SettingCard>
    );
  const number = (key: keyof typeof form.value, max: number) => (
    <Input type="number" min={0} max={max} required value={form.value[key]} onChange={(e) => form.set({ [key]: Number(e.target.value) })} className="w-24" />
  );
  return (
    <SettingCard setting={SETTINGS.experience}>
      <SettingForm form={form}>
        <div className="flex flex-wrap items-end gap-3">
          <Field label="To start">{number("starting_xp", 10000)}</Field>
          <Field label="For a game session">{number("session_xp", 100)}</Field>
          <Field label="For completing a downtime">{number("downtime_xp", 100)}</Field>
        </div>
      </SettingForm>
    </SettingCard>
  );
}

/** House rule: the blood a reset for the next game gives each character. */
export function StartingBlood({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const troupe = useQuery({ queryKey: ["troupe", troupeId], queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", path)) });
  const now = troupe.data?.starting_blood ?? null;
  const form = useSettingForm(
    { full: now === null, blood: now ?? 5 },
    ({ full, blood }) => unwrap(api.PUT("/api/troupes/{troupe_id}/starting-blood", { ...path, body: { blood: full ? null : blood } })),
    { rules: true },
  );
  if (!troupe.data) return null;
  if (!canEdit)
    return (
      <SettingCard setting={SETTINGS.startingBlood} readOnly>
        <p className="text-sm">{now === null ? "Full: the generation's most" : `${now} blood, or the generation's most if that is less`}</p>
      </SettingCard>
    );
  const { full, blood } = form.value;
  return (
    <SettingCard setting={SETTINGS.startingBlood}>
      <SettingForm form={form}>
        <RadioList
          label={SETTINGS.startingBlood.title}
          hideLabel
          value={full}
          options={[
            { value: true, label: "Full", hint: "The generation's most." },
            {
              value: false,
              label: "This much",
              hint: "Or the generation's most, if that is less.",
              children: (
                <Input
                  type="number"
                  min={0}
                  max={30}
                  aria-label="Starting blood"
                  value={blood}
                  disabled={full}
                  onChange={(e) => form.set({ blood: Number(e.target.value) })}
                  className="w-20"
                />
              ),
            },
          ]}
          onChange={(next) => form.set({ full: next })}
        />
      </SettingForm>
    </SettingCard>
  );
}

function CategoryRow({ troupeId, splat, category, canEdit }: { troupeId: string; splat: string; category: StartingCategoryOut; canEdit: boolean }) {
  const [editing, setEditing] = useState(false);
  const path = { params: { path: { troupe_id: troupeId, category: category.key }, query: { splat } } };
  const reset = useRulesAction(() => unwrap(api.DELETE("/api/troupes/{troupe_id}/creation/{category}", path)));
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="min-w-48 flex-1 text-sm">
          <span className="text-parchment">{category.name}</span>: {category.text}
          {category.house && <span className="block text-xs text-mist">The rule set's: {category.book_text}</span>}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {category.house && <Badge tone="gold">House rule</Badge>}
          {canEdit && !editing && (
            <Button variant="secondary" className="min-h-8 px-3" aria-label={`Edit starting ${category.name}`} onClick={() => setEditing(true)}>
              Edit
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
  const save = useRulesAction(async () => {
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
              <Checkbox
                label="in-clan only"
                checked={r.restriction === "in_clan"}
                onChange={(on) => update(i, { restriction: on ? "in_clan" : null })}
                className="text-mist"
              />
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
