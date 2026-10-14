import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, CreationOut, SheetOut, SheetTraitOut } from "../../api/types";
import { Badge, Button, Card, Dots, Empty, ErrorText, Field, Input, Loading, Notice, Select } from "../../components/ui";
import { useAction, useUnavailable } from "../../hooks";

type TraitChange = { category: string; name: string; detail: string; rating: number | null };

function useSheet(characterId: string) {
  return useQuery({
    queryKey: ["sheet", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sheet", { params: { path: { character_id: characterId } } })),
  });
}

function useCatalogue(character: CharacterOut) {
  return useQuery({
    queryKey: ["catalogue", character.splat, character.home_troupe_id],
    queryFn: () =>
      unwrap(
        api.GET("/api/rules/{splat}", {
          params: { path: { splat: character.splat }, query: { troupe_id: character.home_troupe_id ?? undefined } },
        }),
      ),
    staleTime: 5 * 60_000,
  });
}

/** The sheet's traits, grouped as the rule set orders its categories. */
export function groupTraits(traits: SheetTraitOut[], catalogue: CatalogueOut | undefined) {
  const order = new Map(catalogue?.categories.map((c, i) => [c.key, i]));
  const groups = new Map<string, Map<string, SheetTraitOut[]>>();
  const sorted = [...traits].sort((a, b) => (order.get(a.category) ?? 99) - (order.get(b.category) ?? 99));
  for (const t of sorted) {
    const group = groups.get(t.group) ?? new Map<string, SheetTraitOut[]>();
    groups.set(t.group, group);
    const list = group.get(t.category_name) ?? [];
    group.set(t.category_name, [...list, t]);
  }
  return groups;
}

function useCreation(character: CharacterOut) {
  return useQuery({
    queryKey: ["creation", character.id],
    queryFn: () =>
      unwrap(api.GET("/api/characters/{character_id}/creation", { params: { path: { character_id: character.id } } })),
    enabled: !character.creation_complete,
  });
}

export function SheetTab({ character, mine }: { character: CharacterOut; mine: boolean }) {
  const sheet = useSheet(character.id);
  const catalogue = useCatalogue(character);
  const creation = useCreation(character);
  const [message, setMessage] = useState<string | null>(null);

  const swap = useAction(async (body: { category: string; from_name: string; to_name: string }) => {
    const result = await unwrap(
      api.POST("/api/characters/{character_id}/traits/change", { params: { path: { character_id: character.id } }, body }),
    );
    setMessage(`Spent ${result.cost} XP.`);
    return result;
  });
  const change = useAction(async (body: TraitChange) => {
    const result = await unwrap(
      api.PUT("/api/characters/{character_id}/traits", { params: { path: { character_id: character.id } }, body }),
    );
    setMessage(result.cost > 0 ? `Spent ${result.cost} XP.` : result.cost < 0 ? `Gained ${-result.cost} XP.` : null);
    return result;
  });

  if (sheet.isPending) return <Loading />;
  if (sheet.error) return <ErrorText error={sheet.error} />;
  const s = sheet.data;
  // Only a home troupe request locks the sheet: its differences must stay as they are.
  const movingHome = s.pending_approvals.some((a) => a.kind === "home_troupe_change");
  const locked = !mine || movingHome || s.status === "retired";
  const groups = groupTraits(s.traits, catalogue.data);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="flex flex-col gap-4">
        {mine && character.kind === "pc" && !character.creation_complete && creation.data && (
          <CreationPanel character={character} creation={creation.data} locked={locked} />
        )}
        {(character.creation_complete || !mine) && <TroupesCard character={character} sheet={s} mine={mine} />}
        {s.problems.length > 0 && (
          <Card title="Against the rules">
            <ul className="flex flex-col gap-1 text-sm">
              {s.problems.map((p) => (
                <li key={`${p.category}/${p.name}/${p.message}`} className={p.strength === "refuse" ? "text-blood-bright" : "text-mist"}>
                  {p.message}
                </li>
              ))}
            </ul>
          </Card>
        )}
        {groups.size === 0 && <Empty>The sheet is empty. Add traits from the panel{mine ? "" : " once the player does"}.</Empty>}
        {[...groups].map(([group, categories]) => (
          <Card key={group} title={group}>
            <div className="grid gap-4 sm:grid-cols-2">
              {[...categories].map(([category, traits]) => (
                <div key={category}>
                  <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{category}</h3>
                  <ul className="flex flex-col gap-1">
                    {traits.map((t) => (
                      <TraitRow
                        key={t.id}
                        trait={t}
                        locked={locked}
                        onChange={(rating) => change.mutate({ category: t.category, name: t.name, detail: t.detail, rating })}
                        swap={
                          character.creation_complete && catalogue.data
                            ? swapOptions(t, s.traits, catalogue.data)
                            : null
                        }
                        onSwap={(to) => swap.mutate({ category: t.category, from_name: t.name, to_name: to })}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Card>
        ))}
        <ErrorText error={change.error ?? swap.error} />
        {message && !change.error && !swap.error && <Notice>{message}</Notice>}
      </div>
      <aside className="flex flex-col gap-4">
        <Link
          to={`/print/characters/${character.id}`}
          className="inline-flex min-h-10 items-center justify-center rounded-md border border-ash bg-dusk px-4 text-sm hover:border-mist"
        >
          Print the sheet
        </Link>
        <Card title="Experience">
          <dl className="grid grid-cols-3 gap-2 text-center">
            <div>
              <dt className="text-xs text-mist">Available</dt>
              <dd className="font-display text-2xl text-gold">{s.xp.balance}</dd>
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
                    {l.category === "flaws" ? `${Math.min(l.used, l.limit)} of ${l.limit} XP paid` : `${l.used} of ${l.limit} points`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {/* A PC is built in the creation wizard; buying with experience comes after. NPCs use the quick builder. */}
        {!locked && catalogue.data && character.kind === "pc" && character.creation_complete && (
          <AddTrait character={character} catalogue={catalogue.data} onDone={setMessage} />
        )}
        {mine && movingHome && <Notice>The sheet is locked while the home troupe request waits. Withdraw it on the Troupes tab to edit.</Notice>}
      </aside>
    </div>
  );
}

/** For a trait in a category that can be swapped after creation (a focus): its cost
 * and the other choices the character does not hold yet. */
export function swapOptions(trait: SheetTraitOut, held: SheetTraitOut[], catalogue: CatalogueOut) {
  const cost = catalogue.categories.find((c) => c.key === trait.category)?.change_cost;
  if (cost == null) return null;
  const mine = new Set(held.filter((h) => h.category === trait.category).map((h) => h.name));
  const others = catalogue.traits.filter((t) => t.category === trait.category && !mine.has(t.name)).map((t) => t.name);
  return others.length ? { cost, others } : null;
}

function TraitRow({
  trait,
  locked,
  onChange,
  swap,
  onSwap,
}: {
  trait: SheetTraitOut;
  locked: boolean;
  onChange: (rating: number | null) => void;
  swap: { cost: number; others: string[] } | null;
  onSwap: (to: string) => void;
}) {
  const [swapping, setSwapping] = useState(false);
  const [to, setTo] = useState("");
  const pending = trait.pending_from !== null;
  if (swap && !locked) {
    return (
      <li className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>{trait.name}</span>
        {swapping ? (
          <span className="flex items-center gap-1">
            <Select aria-label={`Change ${trait.name} to`} value={to} onChange={(e) => setTo(e.target.value)} className="h-8 py-0">
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
    <li className="flex items-center justify-between gap-2 text-sm">
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
            {trait.granted_rating > 0 ? `+${trait.granted_rating}` : trait.granted_rating} from {trait.granted_by.join(", ")}
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
                title={trait.rating <= trait.min_rating ? "Accepted by the home troupe; only storytellers can take these dots away." : undefined}
                className="h-7 w-7 rounded border border-ash text-mist hover:border-mist hover:text-parchment disabled:opacity-30"
                disabled={pending || trait.rating <= trait.min_rating}
                onClick={() => onChange(trait.rating! - 1)}
              >
                −
              </button>
              <button
                aria-label={`Raise ${trait.name}`}
                className="h-7 w-7 rounded border border-ash text-mist hover:border-mist hover:text-parchment disabled:opacity-30"
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

function AddTrait({ character, catalogue, onDone }: { character: CharacterOut; catalogue: CatalogueOut; onDone: (m: string) => void }) {
  const [category, setCategory] = useState(catalogue.categories[0]?.key ?? "");
  const [name, setName] = useState("");
  const [detail, setDetail] = useState("");
  const [rating, setRating] = useState(1);
  const [quote, setQuote] = useState<number | null>(null);
  const cat = catalogue.categories.find((c) => c.key === category);
  const traits = useMemo(() => catalogue.traits.filter((t) => t.category === category), [catalogue, category]);
  const trait = traits.find((t) => t.name === name);
  const fixed = trait?.fixed_rating ?? null;
  const unavailable = useUnavailable(character.id, category).data ?? {};
  const body: TraitChange = { category, name, detail, rating: cat?.rated ? (fixed ?? rating) : null };

  const price = useAction(async () => {
    const q = await unwrap(api.POST("/api/characters/{character_id}/quote", { params: { path: { character_id: character.id } }, body }));
    setQuote(q.cost);
  });
  const buy = useAction(async () => {
    const result = await unwrap(api.PUT("/api/characters/{character_id}/traits", { params: { path: { character_id: character.id } }, body }));
    onDone(result.cost ? `Added ${name} for ${result.cost} XP.` : `Added ${name}.`);
    setName("");
    setDetail("");
    setQuote(null);
  });

  return (
    <Card title="Add a trait">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          buy.mutate(undefined);
        }}
      >
        <Field label="Category">
          <Select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setName("");
              setQuote(null);
            }}
          >
            {catalogue.categories.map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Trait">
          <Select
            required
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setQuote(null);
            }}
          >
            <option value="">Choose…</option>
            {traits.map((t) => (
              <option key={t.name} value={t.name} disabled={t.name in unavailable} title={unavailable[t.name]}>
                {t.name}
                {t.fixed_rating ? ` (${t.fixed_rating})` : ""}
                {t.name in unavailable ? " — not allowed" : ""}
              </option>
            ))}
          </Select>
        </Field>
        {trait?.description && <p className="text-xs leading-relaxed text-mist">{trait.description}</p>}
        {trait?.house_rule && <Notice>House rule: {trait.house_rule}</Notice>}
        {trait?.choices ? (
          <Field label="Which?" hint={`${name} gives one of these.`}>
            <Select required value={detail} onChange={(e) => setDetail(e.target.value)}>
              <option value="">Choose…</option>
              {trait.choices.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </Select>
          </Field>
        ) : (
          <Field label="Detail" hint="Optional: a specialisation, subject, or name.">
            <Input value={detail} onChange={(e) => setDetail(e.target.value)} />
          </Field>
        )}
        {cat?.rated && fixed === null && (
          <Field label="Rating">
            <Input
              type="number"
              min={1}
              max={cat.max_rating ?? undefined}
              value={rating}
              onChange={(e) => {
                setRating(Number(e.target.value));
                setQuote(null);
              }}
            />
          </Field>
        )}
        {quote !== null && <p className="text-sm">Costs {quote} XP.</p>}
        <ErrorText error={price.error ?? buy.error} />
        <div className="flex gap-2">
          {cat?.rated && (
            <Button type="button" variant="secondary" disabled={!name || price.isPending} onClick={() => price.mutate(undefined)}>
              Price it
            </Button>
          )}
          <Button type="submit" disabled={!name || buy.isPending}>
            {cat?.rated ? "Buy" : "Choose"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** The troupes the character is in: its home troupe, which holds the sheet, and any it visits. */
function TroupesCard({ character, sheet, mine }: { character: CharacterOut; sheet: SheetOut; mine: boolean }) {
  const withdraw = useAction((approvalId: string) =>
    unwrap(api.DELETE("/api/characters/{character_id}/disciplines/{approval_id}", { params: { path: { character_id: character.id, approval_id: approvalId } } })),
  );

  return (
    <Card title="Troupes">
      {!sheet.troupes.length ? (
        <p className="text-sm text-mist">
          {mine ? (
            <>
              In your vault, in no troupe. Ask a troupe to be its home on the{" "}
              <Link className="text-gold underline" to={`/characters/${character.id}/troupes`}>
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
              {t.home ? <Badge tone="gold">home</Badge> : <Badge>visiting</Badge>}
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
          Visiting only. To play here for downtimes and XP, ask for a home troupe on the{" "}
          <Link className="text-gold underline" to={`/characters/${character.id}/troupes`}>
            Troupes tab
          </Link>
          .
        </p>
      )}
      {sheet.pending_disciplines.length > 0 && (
        <div className="mt-3 border-t border-ash pt-3 text-sm">
          <p className="mb-2 text-mist">Disciplines waiting for the home troupe to approve. The XP is held, and refunded if they decline.</p>
          <ul className="flex flex-col gap-1">
            {sheet.pending_disciplines.map((d) => (
              <li key={d.approval_id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {d.name}
                  {d.detail && `: ${d.detail}`} {d.from_rating} → {d.to_rating} ({d.cost} XP)
                </span>
                {mine && (
                  <Button variant="ghost" onClick={() => withdraw.mutate(d.approval_id)} disabled={withdraw.isPending}>
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

function CreationPanel({ character, creation, locked }: { character: CharacterOut; creation: CreationOut; locked: boolean }) {
  const path = { params: { path: { character_id: character.id } } };
  const remove = useAction((body: { category: string; name: string; detail: string }) =>
    unwrap(api.POST("/api/characters/{character_id}/creation/picks/remove", { ...path, body })),
  );
  const finish = useAction(() => unwrap(api.POST("/api/characters/{character_id}/creation/complete", path)));
  const byCategory = new Map<string, CreationOut["pools"]>();
  for (const p of creation.pools) byCategory.set(p.category_name, [...(byCategory.get(p.category_name) ?? []), p]);
  const left = creation.pools.filter((p) => p.kind === "picks").reduce((n, p) => n + p.remaining, 0);

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
        Characters are built in the creation wizard, one step at a time. Experience can be spent once creation is
        finished.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        {[...byCategory].map(([category, pools]) => (
          <div key={category}>
            <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{category}</h3>
            <ul className="flex flex-col gap-1 text-sm">
              {pools.map((p) => (
                <li key={p.rating}>
                  <span className={p.remaining > 0 ? "text-gold" : "text-mist"}>
                    {p.kind === "points" ? `${p.used} of ${p.allowed} points` : `At ${p.rating}: ${p.used} of ${p.allowed}`}
                  </span>
                  {p.traits.map((t) => (
                    <span key={`${t.name}/${t.detail}`} className="ml-2 inline-flex items-center gap-1">
                      {t.name}
                      {t.detail && `: ${t.detail}`}
                      {!locked && (
                        <button
                          aria-label={`Take back the pick on ${t.name}`}
                          className="text-mist hover:text-blood-bright"
                          onClick={() => remove.mutate({ category: p.category, name: t.name, detail: t.detail })}
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
      <Button className="mt-4" disabled={locked || finish.isPending} onClick={() => finish.mutate(undefined)}>
        {left > 0 ? `Finish creation (${left} picks left)` : "Finish creation"}
      </Button>
    </Card>
  );
}
