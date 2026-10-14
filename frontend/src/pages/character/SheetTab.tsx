import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, CharacterOut, SheetOut, SheetTraitOut } from "../../api/types";
import { Badge, Button, Card, Dots, Empty, ErrorText, Field, Input, Loading, Notice, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";

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

export function SheetTab({ character, mine }: { character: CharacterOut; mine: boolean }) {
  const sheet = useSheet(character.id);
  const catalogue = useCatalogue(character);
  const [message, setMessage] = useState<string | null>(null);

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
  const locked = !mine || s.pending_approval !== null || s.status === "retired";
  const groups = groupTraits(s.traits, catalogue.data);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="flex flex-col gap-4">
        {mine && <ApprovalStatus character={character} sheet={s} />}
        {groups.size === 0 && <Empty>The sheet is empty. Add traits from the panel{mine ? "" : " once the player does"}.</Empty>}
        {[...groups].map(([group, categories]) => (
          <Card key={group} title={group}>
            <div className="grid gap-4 sm:grid-cols-2">
              {[...categories].map(([category, traits]) => (
                <div key={category}>
                  <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{category}</h3>
                  <ul className="flex flex-col gap-1">
                    {traits.map((t) => (
                      <TraitRow key={t.id} trait={t} locked={locked} onChange={(rating) => change.mutate({ category: t.category, name: t.name, detail: t.detail, rating })} />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Card>
        ))}
        <ErrorText error={change.error} />
        {message && !change.error && <Notice>{message}</Notice>}
      </div>
      <aside className="flex flex-col gap-4">
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
        </Card>
        {!locked && catalogue.data && <AddTrait character={character} catalogue={catalogue.data} onDone={setMessage} />}
        {mine && s.pending_approval && <Notice>The sheet is locked while changes wait for approval.</Notice>}
      </aside>
    </div>
  );
}

function TraitRow({ trait, locked, onChange }: { trait: SheetTraitOut; locked: boolean; onChange: (rating: number | null) => void }) {
  const changed = trait.approved_rating !== trait.rating;
  return (
    <li className="flex items-center justify-between gap-2 text-sm">
      <span className="min-w-0">
        <span className={changed ? "text-gold" : undefined}>{trait.name}</span>
        {trait.detail && <span className="text-mist">: {trait.detail}</span>}
      </span>
      {trait.rating !== null ? (
        <span className="flex shrink-0 items-center gap-2">
          <Dots value={trait.rating} approved={trait.approved_rating} />
          {!locked && (
            <span className="flex gap-1">
              <button
                aria-label={`Lower ${trait.name}`}
                className="h-7 w-7 rounded border border-ash text-mist hover:border-mist hover:text-parchment disabled:opacity-30"
                disabled={trait.rating <= (trait.approved_rating ?? 0) || trait.rating <= trait.free_rating}
                onClick={() => onChange(trait.rating! - 1)}
              >
                −
              </button>
              <button
                aria-label={`Raise ${trait.name}`}
                className="h-7 w-7 rounded border border-ash text-mist hover:border-mist hover:text-parchment"
                onClick={() => onChange(trait.rating! + 1)}
              >
                +
              </button>
            </span>
          )}
        </span>
      ) : (
        changed && <Badge tone="gold">new</Badge>
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
              <option key={t.name} value={t.name}>
                {t.name}
                {t.fixed_rating ? ` (${t.fixed_rating})` : ""}
              </option>
            ))}
          </Select>
        </Field>
        {trait?.description && <p className="text-xs leading-relaxed text-mist">{trait.description}</p>}
        {trait?.house_rule && <Notice>House rule: {trait.house_rule}</Notice>}
        <Field label="Detail" hint="Optional: a specialisation, subject, or name.">
          <Input value={detail} onChange={(e) => setDetail(e.target.value)} />
        </Field>
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

function ApprovalStatus({ character, sheet }: { character: CharacterOut; sheet: SheetOut }) {
  const [note, setNote] = useState("");
  const path = { params: { path: { character_id: character.id } } };
  const request = useAction(() => unwrap(api.POST("/api/characters/{character_id}/approval", { ...path, body: { note } })));
  const withdraw = useAction(() => unwrap(api.DELETE("/api/characters/{character_id}/approval", path)));

  if (sheet.pending_approval) {
    const kind = sheet.pending_approval.kind === "home_troupe_change" ? "Joining a home troupe" : "Sheet changes";
    return (
      <Card title="Waiting for approval">
        <p className="text-sm">{kind} are waiting for the storytellers.</p>
        {sheet.pending_approval.kind === "sheet_change" && (
          <Button variant="secondary" className="mt-3" onClick={() => withdraw.mutate(undefined)}>
            Withdraw to keep editing
          </Button>
        )}
        <ErrorText error={withdraw.error} />
      </Card>
    );
  }
  if (!sheet.approved) {
    return (
      <Notice>
        This is a draft. It is approved when it joins a home troupe —{" "}
        <Link className="text-gold underline" to={`/characters/${character.id}/troupes`}>
          choose one
        </Link>
        .
      </Notice>
    );
  }
  if (!sheet.pending_changes.length) return null;
  return (
    <Card title="Changes since approval">
      <ul className="mb-3 text-sm">
        {sheet.pending_changes.map((c) => (
          <li key={`${c.category}/${c.name}/${c.detail}`}>
            {c.name}
            {c.detail && `: ${c.detail}`} — {c.approved_rating ?? "new"} → {c.rating ?? "removed"}
          </li>
        ))}
      </ul>
      <Field label="A note for the storytellers">
        <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Button className="mt-3" onClick={() => request.mutate(undefined)} disabled={request.isPending}>
        Ask for approval
      </Button>
      <ErrorText error={request.error} />
    </Card>
  );
}
