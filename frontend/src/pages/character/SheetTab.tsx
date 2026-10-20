import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type {
  CatalogueOut,
  CharacterOut,
  CreationOut,
  SheetOut,
  SheetTraitOut,
} from "../../api/types";
import {
  Badge,
  Button,
  Card,
  Dots,
  Empty,
  ErrorText,
  Loading,
  Notice,
  Select,
} from "../../components/ui";
import { HEALTH_RULE, healthRows } from "../../health";
import { useAction } from "../../hooks";
import { AddTraitPanel } from "./AddTraitPanel";
import { rulesTroupe } from "./rules";
import {
  NEEDS_FIELD,
  SetField,
  SpecializationRow,
  useSpecializations,
} from "./Specializations";

type TraitChange = {
  category: string;
  name: string;
  detail: string;
  rating: number | null;
  teacher?: string;
};

function useSheet(characterId: string) {
  return useQuery({
    queryKey: ["sheet", characterId],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/sheet", {
          params: { path: { character_id: characterId } },
        }),
      ),
  });
}

function useCatalogue(character: CharacterOut) {
  return useQuery({
    queryKey: ["catalogue", character.splat, rulesTroupe(character)],
    queryFn: () =>
      unwrap(
        api.GET("/api/rules/{splat}", {
          params: {
            path: { splat: character.splat },
            query: { troupe_id: rulesTroupe(character) },
          },
        }),
      ),
    staleTime: 5 * 60_000,
  });
}

/** The sheet's traits, grouped as the rule set orders its categories. */
export function groupTraits(
  traits: SheetTraitOut[],
  catalogue: CatalogueOut | undefined,
) {
  const order = new Map(catalogue?.categories.map((c, i) => [c.key, i]));
  const groups = new Map<string, Map<string, SheetTraitOut[]>>();
  const sorted = [...traits].sort(
    (a, b) => (order.get(a.category) ?? 99) - (order.get(b.category) ?? 99),
  );
  for (const t of sorted) {
    const group = groups.get(t.group) ?? new Map<string, SheetTraitOut[]>();
    groups.set(t.group, group);
    const list = group.get(t.category_name) ?? [];
    group.set(t.category_name, [...list, t]);
  }
  return groups;
}

/** The sheet's parts in rule set order, with the categories each part can add
 * to: rated, bought (not derived, like health), and not a swapped choice (a focus). */
export function addableByGroup(catalogue: CatalogueOut | undefined) {
  const groups = new Map<string, string[]>();
  for (const c of catalogue?.categories ?? []) {
    if (!c.rated) continue;
    const list = groups.get(c.group) ?? [];
    groups.set(c.group, list);
    // Not added here: extra in-clan disciplines (chosen at creation) and Paths
    // (which come from their merits).
    if (
      !c.derived &&
      c.change_cost == null &&
      !c.specializes &&
      !["extra_in_clan_disciplines", "paths"].includes(c.key)
    )
      list.push(c.key);
  }
  return groups;
}

function useCreation(character: CharacterOut) {
  return useQuery({
    queryKey: ["creation", character.id],
    queryFn: () =>
      unwrap(
        api.GET("/api/characters/{character_id}/creation", {
          params: { path: { character_id: character.id } },
        }),
      ),
    enabled: !character.creation_complete,
  });
}

export function SheetTab({
  character,
  mine,
}: {
  character: CharacterOut;
  mine: boolean;
}) {
  const sheet = useSheet(character.id);
  const catalogue = useCatalogue(character);
  const creation = useCreation(character);
  const [message, setMessage] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const kinds = useSpecializations(character.id);

  const swap = useAction(
    async (body: { category: string; from_name: string; to_name: string }) => {
      const result = await unwrap(
        api.POST("/api/characters/{character_id}/traits/change", {
          params: { path: { character_id: character.id } },
          body,
        }),
      );
      setMessage(`Spent ${result.cost} XP.`);
      return result;
    },
  );
  const change = useAction(async (body: TraitChange) => {
    const result = await unwrap(
      api.PUT("/api/characters/{character_id}/traits", {
        params: { path: { character_id: character.id } },
        body: { teacher: "", ...body },
      }),
    );
    setMessage(
      result.cost > 0
        ? `Spent ${result.cost} XP.`
        : result.cost < 0
          ? `Gained ${-result.cost} XP.`
          : null,
    );
    return result;
  });

  if (sheet.isPending) return <Loading />;
  if (sheet.error) return <ErrorText error={sheet.error} />;
  const s = sheet.data;
  // Only a home troupe request locks the sheet: its differences must stay as they are.
  const movingHome = s.pending_approvals.some(
    (a) => a.kind === "home_troupe_change",
  );
  const locked = !mine || movingHome || s.status === "retired";
  // Identity (clan, sect...) is shown with the name, in the page title.
  // Specialisations show under their skill or background, not as traits of their own,
  // and health levels as boxes in a part of their own.
  const specCategories = new Set(
    catalogue.data?.categories.filter((c) => c.specializes).map((c) => c.key),
  );
  const groups = groupTraits(
    s.traits.filter(
      (t) =>
        t.rating !== null &&
        !specCategories.has(t.category) &&
        t.category !== "health_levels",
    ),
    catalogue.data,
  );
  const kindOf = (t: SheetTraitOut) =>
    kinds.data?.find(
      (k) => k.parent_category === t.category && k.parent_name === t.name,
    );
  const addable = addableByGroup(catalogue.data);
  const canAdd =
    !locked &&
    character.kind === "pc" &&
    character.creation_complete &&
    !!catalogue.data;
  // Every part that holds traits, then parts the player can add to.
  // Only categories with something left to add (all three attributes are always held).
  const heldNames = new Set(s.traits.map((t) => `${t.category}/${t.name}`));
  for (const [group, keys] of addable) {
    addable.set(
      group,
      keys.filter((key) =>
        catalogue.data?.traits.some(
          (t) => t.category === key && !heldNames.has(`${key}/${t.name}`),
        ),
      ),
    );
  }
  const parts = [...addable.keys()].filter(
    (g) => groups.has(g) || (canAdd && (addable.get(g)?.length ?? 0) > 0),
  );
  const single = (group: string) => (groups.get(group)?.size ?? 0) === 1;
  // Small parts (a few traits in one category) sit side by side; the rest span the width.
  const wide = (group: string) => {
    const categories = groups.get(group);
    const count = [...(categories?.values() ?? [])].reduce(
      (n, ts) => n + ts.length,
      0,
    );
    const specialised = [...(categories?.values() ?? [])].some((ts) => ts.some((t) => kindOf(t)));
    return adding === group || specialised || (categories?.size ?? 0) > 1 || count > 5;
  };
  const pointsOf = (t: SheetTraitOut) =>
    catalogue.data?.traits.find(
      (c) => c.category === t.category && c.name === t.name,
    )?.fixed_rating ?? null;
  const derived = new Set(
    catalogue.data?.categories.filter((c) => c.derived).map((c) => c.key),
  );
  // Health sits after the part its category belongs to (with willpower), or last.
  const health = s.traits.some((t) => t.category === "health_levels") ? (
    <HealthLevels key="health_levels" traits={s.traits} />
  ) : null;
  const healthAfter = catalogue.data?.categories.find(
    (c) => c.key === "health_levels",
  )?.group;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_18rem]">
      <div className="flex flex-col gap-3">
        {mine &&
          character.kind === "pc" &&
          !character.creation_complete &&
          creation.data && (
            <CreationPanel
              character={character}
              creation={creation.data}
              locked={locked}
            />
          )}
        {s.problems.length > 0 && (
          <Card dense title="Against the rules">
            <ul className="flex flex-col gap-1 text-sm">
              {s.problems.map((p) => (
                <li
                  key={`${p.category}/${p.name}/${p.message}`}
                  className={
                    p.strength === "refuse" ? "text-blood-bright" : "text-mist"
                  }
                >
                  {p.message}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {parts.length === 0 && (
          <Empty>
            The sheet is empty{mine ? "" : " until the player builds it"}.
          </Empty>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          {parts.map((group) => [
            <Card
              key={group}
              dense
              className={wide(group) ? "md:col-span-2" : undefined}
              title={group}
              actions={
                canAdd && (addable.get(group)?.length ?? 0) > 0 ? (
                  <Button
                    variant="ghost"
                    aria-expanded={adding === group}
                    onClick={() => setAdding(adding === group ? null : group)}
                  >
                    {adding === group ? "Close" : "Add"}
                  </Button>
                ) : undefined
              }
            >
              {adding === group && catalogue.data && (
                <AddTraitPanel
                  character={character}
                  catalogue={catalogue.data}
                  categories={addable.get(group) ?? []}
                  held={s.traits}
                  onDone={setMessage}
                  onClose={() => setAdding(null)}
                />
              )}
              {!groups.has(group) && (
                <p className="text-sm text-mist">None yet.</p>
              )}
              {[...(groups.get(group)?.values() ?? [])].some((ts) => ts.some((t) => t.category === "disciplines")) &&
                s.primary_paths.map((p) => (
                  <PrimaryPathRow key={p.discipline} characterId={character.id} primary={p} locked={locked} />
                ))}
              <div className={wide(group) && !single(group) ? "grid gap-x-6 gap-y-2 sm:grid-cols-2" : "flex flex-col gap-2"}>
                {[
                  ...(groups.get(group) ?? new Map<string, SheetTraitOut[]>()),
                ].map(([category, traits]) => (
                  <div key={category}>
                    {category.toLowerCase() !== group.toLowerCase() && (
                      <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">
                        {category}
                      </h3>
                    )}
                    {/* A long list of one kind (skills) flows into two columns. */}
                    <ul className={wide(group) && single(group) ? "gap-x-6 sm:columns-2 [&>li]:break-inside-avoid" : "flex flex-col"}>
                      {traits.map((t) => [
                        <TraitRow
                          key={t.id}
                          trait={t}
                          locked={locked || derived.has(t.category)}
                          points={pointsOf(t)}
                          onChange={(rating) =>
                            change.mutate({
                              category: t.category,
                              name: t.name,
                              detail: t.detail,
                              rating,
                            })
                          }
                          swap={
                            character.creation_complete && catalogue.data
                              ? swapOptions(t, s.traits, catalogue.data)
                              : null
                          }
                          onSwap={(to) =>
                            swap.mutate({
                              category: t.category,
                              from_name: t.name,
                              to_name: to,
                            })
                          }
                        />,
                        kindOf(t) && (
                          <SpecializationRow
                            key={`${t.id}/specs`}
                            character={character}
                            kind={kindOf(t)!}
                            editable={mine && !locked && s.status !== "retired"}
                          />
                        ),
                        mine &&
                          !locked &&
                          t.category === "skills" &&
                          NEEDS_FIELD.has(t.name) &&
                          !t.detail && (
                            <SetField
                              key={`${t.id}/field`}
                              character={character}
                              trait={t}
                            />
                          ),
                      ])}
                    </ul>
                  </div>
                ))}
              </div>
            </Card>,
            group === healthAfter && health,
          ])}
          {!parts.includes(healthAfter ?? "") && health}
        </div>
        <ErrorText error={change.error ?? swap.error} />
        {message && !change.error && !swap.error && <Notice>{message}</Notice>}
      </div>
      <aside className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-2">
          <Link
            to={`/play/characters/${character.id}`}
            className="inline-flex min-h-10 items-center justify-center rounded-md bg-blood px-4 text-sm font-medium text-parchment hover:bg-blood-bright"
          >
            Play
          </Link>
          <Link
            to={`/print/characters/${character.id}`}
            className="inline-flex min-h-10 items-center justify-center rounded-md border border-ash bg-dusk px-4 text-sm hover:border-mist"
          >
            Print the sheet
          </Link>
        </div>
        <Card dense title="Experience">
          <dl className="grid grid-cols-3 gap-2 text-center">
            <div>
              <dt className="text-xs text-mist">Available</dt>
              <dd className="font-display text-2xl text-gold">
                {s.xp.balance}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-mist">Earned</dt>
              <dd className="text-lg">{s.xp.earned}</dd>
            </div>
            <div>
              <dt className="text-xs text-mist">Spent</dt>
              <dd className="text-lg">{s.xp.spent}</dd>
            </div>
          </dl>
          {s.limits.length > 0 && (
            <ul className="mt-3 border-t border-ash pt-2 text-xs text-mist">
              {s.limits.map((l) => (
                <li key={l.category} className="flex justify-between">
                  <span>{l.name}</span>
                  <span className={l.used >= l.limit ? "text-gold" : undefined}>
                    {l.category === "flaws"
                      ? `${Math.min(l.used, l.limit)} of ${l.limit} XP paid`
                      : `${l.used} of ${l.limit} points`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {(character.creation_complete || !mine) && (
          <TroupesCard character={character} sheet={s} mine={mine} />
        )}
        {mine && movingHome && (
          <Notice>
            The sheet is locked while the home troupe request waits. Withdraw it
            on the Troupes tab to edit.
          </Notice>
        )}
      </aside>
    </div>
  );
}

/** For a trait in a category that can be swapped after creation (a focus): its cost
 * and the other choices the character does not hold yet. */
export function swapOptions(
  trait: SheetTraitOut,
  held: SheetTraitOut[],
  catalogue: CatalogueOut,
) {
  const cost = catalogue.categories.find(
    (c) => c.key === trait.category,
  )?.change_cost;
  if (cost == null) return null;
  const mine = new Set(
    held.filter((h) => h.category === trait.category).map((h) => h.name),
  );
  const others = catalogue.traits
    .filter((t) => t.category === trait.category && !mine.has(t.name))
    .map((t) => t.name);
  return others.length ? { cost, others } : null;
}

function TraitRow({
  trait,
  locked,
  onChange,
  swap,
  onSwap,
  points = null,
}: {
  trait: SheetTraitOut;
  locked: boolean;
  /** A merit or flaw's fixed point value: shown instead of dots. */
  points?: number | null;
  onChange: (rating: number | null) => void;
  swap: { cost: number; others: string[] } | null;
  onSwap: (to: string) => void;
}) {
  const [swapping, setSwapping] = useState(false);
  const [to, setTo] = useState("");
  const pending = trait.pending_from !== null;
  if (points !== null) {
    return (
      <li className="flex min-h-7 items-center justify-between gap-2 text-sm">
        <span className="min-w-0">
          {trait.name}
          {trait.detail && <span className="text-mist">: {trait.detail}</span>}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <Badge tone="gold">{points}</Badge>
          {!locked &&
            trait.rating !== null &&
            trait.rating > trait.min_rating && (
              <button
                aria-label={`Remove ${trait.name}`}
                className="h-6 w-6 rounded border border-ash text-xs leading-none text-mist hover:border-mist hover:text-parchment"
                onClick={() => onChange(0)}
              >
                ×
              </button>
            )}
        </span>
      </li>
    );
  }
  if (swap && !locked) {
    return (
      <li className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>{trait.name}</span>
        {swapping ? (
          <span className="flex items-center gap-1">
            <Select
              aria-label={`Change ${trait.name} to`}
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="h-8 py-0"
            >
              <option value="">Change to…</option>
              {swap.others.map((o) => (
                <option key={o}>{o}</option>
              ))}
            </Select>
            <Button
              variant="secondary"
              disabled={!to}
              onClick={() => {
                onSwap(to);
                setSwapping(false);
              }}
            >
              {swap.cost} XP
            </Button>
          </span>
        ) : (
          <Button variant="ghost" onClick={() => setSwapping(true)}>
            Change
          </Button>
        )}
      </li>
    );
  }
  return (
    <li className="flex min-h-7 items-center justify-between gap-2 text-sm">
      <span className="min-w-0">
        <span className={pending ? "text-gold" : undefined}>{trait.name}</span>
        {trait.detail && <span className="text-mist">: {trait.detail}</span>}
        {pending && (
          <span className="ml-2">
            <Badge tone="gold">awaiting approval</Badge>
          </span>
        )}
        {trait.granted_rating !== 0 && trait.granted_by.length > 0 && (
          <span className="ml-2 text-xs text-mist">
            {trait.granted_rating > 0
              ? `+${trait.granted_rating}`
              : trait.granted_rating}{" "}
            from {trait.granted_by.join(", ")}
          </span>
        )}
      </span>
      {trait.rating !== null && (
        <span className="flex shrink-0 items-center gap-2">
          <Dots value={trait.rating} pendingFrom={trait.pending_from} />
          {!locked && (
            <span className="flex gap-1">
              <button
                aria-label={`Lower ${trait.name}`}
                title={
                  trait.rating <= trait.min_rating
                    ? "Accepted by the home troupe; only storytellers can take these dots away."
                    : undefined
                }
                className="h-6 w-6 rounded border border-ash text-xs leading-none text-mist hover:border-mist hover:text-parchment disabled:opacity-30"
                disabled={pending || trait.rating <= trait.min_rating}
                onClick={() => onChange(trait.rating! - 1)}
              >
                −
              </button>
              <button
                aria-label={`Raise ${trait.name}`}
                className="h-6 w-6 rounded border border-ash text-xs leading-none text-mist hover:border-mist hover:text-parchment disabled:opacity-30"
                disabled={pending}
                onClick={() => onChange(trait.rating! + 1)}
              >
                +
              </button>
            </span>
          )}
        </span>
      )}
    </li>
  );
}

/**
 * Health levels as boxes, laid out like the example BNS sheet: a row of boxes
 * per level, for ticking damage in play. Health is worked out from the rest of
 * the sheet, so nothing here is saved.
 */
function HealthLevels({ traits }: { traits: SheetTraitOut[] }) {
  return (
    <Card dense title="Health Levels">
      <p className="mb-2 text-xs text-mist">{HEALTH_RULE}</p>
      <ul className="flex flex-col gap-1.5 text-sm">
        {healthRows(traits).map(({ name, boxes, trait }) => (
          <li key={name} className="flex min-h-6 flex-wrap items-center gap-x-3 gap-y-1">
            <span className="w-24 shrink-0">{name}</span>
            <span role="img" aria-label={`${name}: ${boxes} boxes`} className="flex flex-wrap gap-1">
              {Array.from({ length: boxes }, (_, i) => (
                <span key={i} className="h-4 w-4 rounded-sm border border-parchment/70" />
              ))}
            </span>
            {trait && trait.granted_rating !== 0 && trait.granted_by.length > 0 && (
              <span className="ml-auto text-xs text-mist">
                {trait.granted_rating > 0 ? `+${trait.granted_rating}` : trait.granted_rating} from{" "}
                {trait.granted_by.join(", ")}
              </span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** The troupes the character is in: its home troupe, which holds the sheet, and any it visits. */
function TroupesCard({
  character,
  sheet,
  mine,
}: {
  character: CharacterOut;
  sheet: SheetOut;
  mine: boolean;
}) {
  const withdraw = useAction((approvalId: string) =>
    unwrap(
      api.DELETE("/api/characters/{character_id}/disciplines/{approval_id}", {
        params: {
          path: { character_id: character.id, approval_id: approvalId },
        },
      }),
    ),
  );

  return (
    <Card dense title="Troupes">
      {!sheet.troupes.length ? (
        <p className="text-sm text-mist">
          {mine ? (
            <>
              In your vault, in no troupe. Ask a troupe to be its home on the{" "}
              <Link
                className="text-gold underline"
                to={`/characters/${character.id}/troupes`}
              >
                Troupes tab
              </Link>
              ; once it accepts, the character plays there.
            </>
          ) : (
            "In no troupe."
          )}
        </p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {sheet.troupes.map((t) => (
            <li key={t.troupe_id} className="flex flex-wrap items-center gap-2">
              <span>{t.troupe_name}</span>
              {t.home ? (
                <Badge tone="gold">home</Badge>
              ) : (
                <Badge>visiting</Badge>
              )}
              {t.waiting && <Badge tone="blood">waiting to be accepted</Badge>}
              {t.titles.map((title) => (
                <Badge key={title} tone="gold">
                  {title}
                </Badge>
              ))}
            </li>
          ))}
        </ul>
      )}
      {sheet.home_troupe_id === null && sheet.troupes.length > 0 && mine && (
        <p className="mt-2 text-xs text-mist">
          Visiting only. To play here for downtimes and XP, ask for a home
          troupe on the{" "}
          <Link
            className="text-gold underline"
            to={`/characters/${character.id}/troupes`}
          >
            Troupes tab
          </Link>
          .
        </p>
      )}
      {sheet.pending_disciplines.length > 0 && (
        <div className="mt-3 border-t border-ash pt-3 text-sm">
          <p className="mb-2 text-mist">
            Waiting for the home troupe to approve. The XP is held, and refunded
            if they decline.
          </p>
          <ul className="flex flex-col gap-1">
            {sheet.pending_disciplines.map((d) => (
              <li
                key={d.approval_id}
                className="flex flex-wrap items-center justify-between gap-2"
              >
                <span>
                  {d.name}
                  {d.detail && `: ${d.detail}`} {d.from_rating} → {d.to_rating}{" "}
                  ({d.cost} XP)
                </span>
                {mine && (
                  <Button
                    variant="ghost"
                    onClick={() => withdraw.mutate(d.approval_id)}
                    disabled={withdraw.isPending}
                  >
                    Withdraw
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      <ErrorText error={withdraw.error} />
    </Card>
  );
}

function CreationPanel({
  character,
  creation,
  locked,
}: {
  character: CharacterOut;
  creation: CreationOut;
  locked: boolean;
}) {
  const path = { params: { path: { character_id: character.id } } };
  const remove = useAction(
    (body: { category: string; name: string; detail: string }) =>
      unwrap(
        api.POST("/api/characters/{character_id}/creation/picks/remove", {
          ...path,
          body,
        }),
      ),
  );
  const finish = useAction(() =>
    unwrap(api.POST("/api/characters/{character_id}/creation/complete", path)),
  );
  const byCategory = new Map<string, CreationOut["pools"]>();
  for (const p of creation.pools)
    byCategory.set(p.category_name, [
      ...(byCategory.get(p.category_name) ?? []),
      p,
    ]);
  const left = creation.pools
    .filter((p) => p.kind === "picks")
    .reduce((n, p) => n + p.remaining, 0);

  return (
    <Card
      title="Character creation"
      actions={
        <Link to={`/characters/${character.id}/create`}>
          <Button tabIndex={-1}>Open the creation wizard</Button>
        </Link>
      }
    >
      <p className="mb-3 text-sm text-mist">
        Characters are built in the creation wizard, one step at a time.
        Experience can be spent once creation is finished.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {[...byCategory].map(([category, pools]) => (
          <div key={category}>
            <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">
              {category}
            </h3>
            <ul className="flex flex-col gap-1 text-sm">
              {pools.map((p) => (
                <li key={p.rating}>
                  <span className={p.remaining > 0 ? "text-gold" : "text-mist"}>
                    {p.kind === "points"
                      ? `${p.used} of ${p.allowed} points`
                      : `At ${p.rating}: ${p.used} of ${p.allowed}`}
                  </span>
                  {p.traits.map((t) => (
                    <span
                      key={`${t.name}/${t.detail}`}
                      className="ml-2 inline-flex items-center gap-1"
                    >
                      {t.name}
                      {t.detail && `: ${t.detail}`}
                      {!locked && (
                        <button
                          aria-label={`Take back the pick on ${t.name}`}
                          className="text-mist hover:text-blood-bright"
                          onClick={() =>
                            remove.mutate({
                              category: p.category,
                              name: t.name,
                              detail: t.detail,
                            })
                          }
                        >
                          ×
                        </button>
                      )}
                    </span>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <ErrorText error={remove.error ?? finish.error} />
      <Button
        className="mt-4"
        disabled={locked || finish.isPending}
        onClick={() => finish.mutate(undefined)}
      >
        {left > 0 ? `Finish creation (${left} picks left)` : "Finish creation"}
      </Button>
    </Card>
  );
}

type PrimaryPath = SheetOut["primary_paths"][number];

/**
 * Which path of a discipline is primary: no other may go above it. A clan with
 * an in-clan path has it as primary; otherwise the player names the first path
 * that reached 2 dots, which must be the highest (MET: VTM p. 187).
 */
function PrimaryPathRow({ characterId, primary, locked }: { characterId: string; primary: PrimaryPath; locked: boolean }) {
  const name = useAction((path: string | null) =>
    unwrap(
      api.PUT("/api/characters/{character_id}/primary-path", {
        params: { path: { character_id: characterId } },
        body: { discipline: primary.discipline, path },
      }),
    ),
  );
  const short = (path: string) => path.replace(`${primary.discipline}: `, "");
  return (
    <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
      <span className="text-mist">Primary path of {primary.discipline}:</span>
      {primary.native || locked ? (
        <span className="text-parchment">
          {primary.path ? short(primary.path) : "not named"}
          {primary.native && <span className="text-mist"> (in-clan)</span>}
        </span>
      ) : (
        <Select
          aria-label={`Primary path of ${primary.discipline}`}
          value={primary.path ?? ""}
          onChange={(e) => name.mutate(e.target.value || null)}
          className="min-h-8 w-auto py-1 text-sm"
        >
          <option value="">Not named</option>
          {primary.options.map((o) => (
            <option key={o} value={o}>
              {short(o)}
            </option>
          ))}
        </Select>
      )}
      {!primary.native && !primary.path && (
        <span className="text-xs text-mist">Name the first path that reached 2 dots; no other path can go above it.</span>
      )}
      <ErrorText error={name.error} />
    </div>
  );
}
