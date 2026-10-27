import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { CatalogueOut, EffectBlock, EffectChoicesOut, HousePreviewOut, HouseTraitIn, PoolChange, PoolChoiceOut } from "../../api/types";
import { Button, ErrorText, Input, Select } from "../../components/ui";
import {
  BLOCK_TYPES,
  EXTRA_IN_CLAN,
  HEALTH,
  PRICE_KINDS,
  STRENGTHS,
  checkCategories,
  clanFamilies,
  dotCategories,
  hasRating,
  newBlock,
  poolChoices,
  poolGroups,
  retype,
  sects,
  signed,
  traitNames,
  typeOf,
  type BlockType,
} from "./houseEffects";

function Labelled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-36 flex-col gap-1 text-sm">
      <span aria-hidden className="text-mist">
        {label}
      </span>
      {children}
    </div>
  );
}

function numbers(from: number, to: number): number[] {
  return Array.from({ length: to - from + 1 }, (_, i) => from + i);
}

/** Names chosen from a list: each with × to take it off, and a picker to add another. */
function TraitList({
  label,
  name,
  options,
  names,
  onChange,
}: {
  label: string;
  /** The accessible name's start: "Effect 1". */
  name: string;
  options: string[];
  names: string[];
  onChange: (names: string[]) => void;
}) {
  const left = options.filter((o) => !names.includes(o));
  return (
    <div className="flex flex-col gap-1 text-sm sm:col-span-2">
      <span className="text-mist">{label}</span>
      {names.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label={`${name}: ${label}`}>
          {names.map((n) => (
            <li key={n} className="inline-flex items-center gap-1 rounded border border-ash px-2 py-0.5 text-parchment">
              {n}
              <button type="button" className="text-mist hover:text-parchment" aria-label={`${name}: take ${n} off`} onClick={() => onChange(names.filter((x) => x !== n))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {left.length > 0 && (
        <Select aria-label={`${name}: add a trait`} value="" onChange={(e) => e.target.value && onChange([...names, e.target.value])} className="sm:w-72">
          <option value="">Add…</option>
          {left.map((o) => (
            <option key={o}>{o}</option>
          ))}
        </Select>
      )}
    </div>
  );
}

/** The pools to choose from, in their groups. */
function PoolOptions({ pools }: { pools: PoolChoiceOut[] }) {
  return (
    <>
      {poolGroups(pools).map(([group, list]) => (
        <optgroup key={group} label={group}>
          {list.map((p) => (
            <option key={p.key} value={p.key}>
              {p.label}
            </option>
          ))}
        </optgroup>
      ))}
    </>
  );
}

/** Pools chosen from the Play View's: each with × to take it off, and a picker to add another. */
function PoolList({ name, options, pools, onChange }: { name: string; options: PoolChoiceOut[]; pools: string[]; onChange: (pools: string[]) => void }) {
  const left = options.filter((o) => !pools.includes(o.key));
  const label = (key: string) => options.find((o) => o.key === key)?.label ?? key;
  return (
    <div className="flex flex-col gap-1 text-sm sm:col-span-2">
      <span className="text-mist">Which pools</span>
      {pools.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label={`${name}: pools`}>
          {pools.map((key) => (
            <li key={key} className="inline-flex items-center gap-1 rounded border border-ash px-2 py-0.5 text-parchment">
              {label(key)}
              <button type="button" className="text-mist hover:text-parchment" aria-label={`${name}: take ${label(key)} off`} onClick={() => onChange(pools.filter((x) => x !== key))}>
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      {left.length > 0 && (
        <Select aria-label={`${name}: add a pool`} value="" onChange={(e) => e.target.value && onChange([...pools, e.target.value])} className="sm:w-72">
          <option value="">Add…</option>
          <PoolOptions pools={left} />
        </Select>
      )}
    </div>
  );
}

const AMOUNTS = [5, 4, 3, 2, 1, -1, -2, -3, -4, -5];

/** What a switch changes while it is on: a pool or an attribute's pools, each by an amount. */
function ChangesList({ name, options, changes, onChange }: { name: string; options: PoolChoiceOut[]; changes: PoolChange[]; onChange: (changes: PoolChange[]) => void }) {
  const set = (i: number, change: Partial<PoolChange>) => onChange(changes.map((c, j) => (j === i ? { ...c, ...change } : c)));
  return (
    <div className="flex flex-col gap-2 text-sm sm:col-span-2">
      <span className="text-mist">While it is on</span>
      <ul className="flex flex-col gap-2">
        {changes.map((c, i) => (
          <li key={i} className="flex flex-wrap items-center gap-2">
            <Select aria-label={`${name}: change ${i + 1} amount`} value={c.amount} onChange={(e) => set(i, { amount: Number(e.target.value) })} className="w-20">
              {AMOUNTS.map((n) => (
                <option key={n} value={n}>
                  {signed(n)}
                </option>
              ))}
            </Select>
            <span className="text-mist">on</span>
            <Select aria-label={`${name}: change ${i + 1} pool`} value={c.pool} onChange={(e) => set(i, { pool: e.target.value })} className="sm:w-72">
              <option value="">Choose…</option>
              <PoolOptions pools={options} />
            </Select>
            {changes.length > 1 && (
              <button type="button" className="text-mist hover:text-parchment" aria-label={`${name}: take change ${i + 1} off`} onClick={() => onChange(changes.filter((_, j) => j !== i))}>
                ×
              </button>
            )}
          </li>
        ))}
      </ul>
      {changes.length < 10 && (
        <div>
          <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`${name}: add a change`} onClick={() => onChange([...changes, { pool: "", amount: 1 }])}>
            Add a change
          </Button>
        </div>
      )}
    </div>
  );
}

const HERD = [
  { factor: 1, label: "Once, as usual" },
  { factor: 2, label: "Twice" },
  { factor: 3, label: "Three times" },
  { factor: 0, label: "For nothing" },
];

/**
 * One effect block as a form: what it does, then the traits, amounts and lists that
 * say how. The server checks it and says, under it, why it cannot be used.
 */
function BlockForm({
  index,
  block,
  catalogue,
  choices,
  self,
  problem,
  onChange,
  onRemove,
}: {
  index: number;
  block: EffectBlock;
  catalogue: CatalogueOut;
  choices: EffectChoicesOut | undefined;
  self: { category: string; name: string };
  problem?: string;
  onChange: (block: EffectBlock) => void;
  onRemove: () => void;
}) {
  const type = typeOf(block);
  const name = `Effect ${index + 1}`;
  const set = (fields: Partial<EffectBlock>) => onChange({ ...block, ...fields });
  const names = block.names ?? [];
  const has = (key: string) => catalogue.categories.some((c) => c.key === key);
  const offered = BLOCK_TYPES.filter((b) => (b.type !== "in_clan" || has(EXTRA_IN_CLAN)) && (b.type !== "health" || has(HEALTH)));
  const categoryName = catalogue.categories.find((c) => c.key === block.category)?.name.toLowerCase() ?? "traits";
  const top = catalogue.categories.find((c) => c.key === block.category)?.max_rating ?? 10;

  let body: ReactNode = null;
  if (type === "free" || type === "picks" || type === "raise" || type === "price") {
    const whole = block.category === "merits" || block.category === "flaws";
    body = (
      <>
        <Labelled label="Kind of trait">
          <Select aria-label={`${name}: kind of trait`} value={block.category} onChange={(e) => set({ category: e.target.value, names: [], detail: "" })}>
            {dotCategories(catalogue, type).map((c) => (
              <option key={c.key} value={c.key}>
                {c.name}
              </option>
            ))}
          </Select>
        </Labelled>
        {type === "price" && (
          <Labelled label="How">
            <Select aria-label={`${name}: how it is priced`} value={block.kind} onChange={(e) => set({ kind: e.target.value as EffectBlock["kind"] })}>
              {PRICE_KINDS.map((k) => (
                <option key={k.kind} value={k.kind}>
                  {k.label}
                </option>
              ))}
            </Select>
          </Labelled>
        )}
        <TraitList
          name={name}
          label={
            type === "free"
              ? `Which ${categoryName} (with more than one, the player chooses which)`
              : type === "picks"
                ? `The ${categoryName} to pick from`
                : type === "raise" || block.kind === "cost_percent"
                  ? `Which ${categoryName} (none: all of them)`
                  : `Which ${categoryName}`
          }
          options={traitNames(catalogue, block.category, self)}
          names={names}
          onChange={(n) => set({ names: n })}
        />
        {type === "picks" && (
          <Labelled label="How many the player picks">
            <Select aria-label={`${name}: how many the player picks`} value={block.count} onChange={(e) => set({ count: Number(e.target.value) })}>
              {numbers(1, Math.max(1, names.length)).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
          </Labelled>
        )}
        {(type === "free" || type === "picks") && !whole && (
          <Labelled label={type === "picks" ? "Free dots each" : "Free dots"}>
            <Select aria-label={`${name}: free dots`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
              {numbers(1, Math.min(top, 10)).map((n) => (
                <option key={n} value={n}>
                  {n === 1 ? "The first dot" : `The first ${n} dots`}
                </option>
              ))}
            </Select>
          </Labelled>
        )}
        {type === "raise" && (
          <Labelled label="How much higher">
            <Select aria-label={`${name}: how much higher`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
              {numbers(1, 5).map((n) => (
                <option key={n} value={n}>
                  +{n}
                </option>
              ))}
            </Select>
          </Labelled>
        )}
        {block.kind === "cost_percent" && (
          <Labelled label="Percent of the usual price">
            <Input
              aria-label={`${name}: percent of the usual price`}
              type="number"
              min={0}
              max={500}
              step={5}
              value={block.amount}
              onChange={(e) => set({ amount: Number(e.target.value) })}
            />
          </Labelled>
        )}
        {(type === "raise" || type === "price") && names.length > 0 && (
          <Labelled label="Only one field (optional)">
            <Input aria-label={`${name}: only one field`} placeholder="Singing" maxLength={100} value={block.detail} onChange={(e) => set({ detail: e.target.value })} />
          </Labelled>
        )}
      </>
    );
  } else if (type === "pool") {
    body = (
      <>
        <PoolList name={name} options={poolChoices(choices, type)} pools={block.pools ?? []} onChange={(pools) => set({ pools })} />
        <Labelled label="Bonus">
          <Select aria-label={`${name}: bonus`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
            {AMOUNTS.map((n) => (
              <option key={n} value={n}>
                {signed(n)}
              </option>
            ))}
          </Select>
        </Labelled>
        <Labelled label="Only when (optional)">
          <Input aria-label={`${name}: only when`} placeholder="against Telepathy" maxLength={200} value={block.when} onChange={(e) => set({ when: e.target.value })} />
        </Labelled>
      </>
    );
  } else if (type === "switch") {
    body = (
      <>
        <ChangesList name={name} options={poolChoices(choices, type)} changes={block.changes ?? []} onChange={(changes) => set({ changes })} />
        <Labelled label="What else it does (optional)">
          <Input aria-label={`${name}: what else it does`} placeholder="Lasts one scene." maxLength={300} value={block.note} onChange={(e) => set({ note: e.target.value })} />
        </Labelled>
      </>
    );
  } else if (type === "uses") {
    body = (
      <Labelled label="Uses a game">
        <Select aria-label={`${name}: uses a game`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
          {numbers(1, 10).map((n) => (
            <option key={n} value={n}>
              {n === 1 ? "1 use" : `${n} uses`}
            </option>
          ))}
        </Select>
      </Labelled>
    );
  } else if (type === "downtime") {
    body = (
      <>
        <Labelled label="Kind of action">
          <Select aria-label={`${name}: kind of action`} value={block.action_kind} onChange={(e) => set({ action_kind: e.target.value })}>
            {(choices?.action_kinds ?? []).map((k) => (
              <option key={k.key} value={k.key}>
                {k.name}
              </option>
            ))}
          </Select>
        </Labelled>
        <Labelled label="Each downtime">
          <Select aria-label={`${name}: how many`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
            {AMOUNTS.map((n) => (
              <option key={n} value={n}>
                {n > 0 ? `${n} more` : `${-n} fewer`}
              </option>
            ))}
          </Select>
        </Labelled>
      </>
    );
  } else if (type === "feeding") {
    body = (
      <>
        <Labelled label="Feeding actions needed">
          <Select aria-label={`${name}: feeding actions needed`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
            {[-3, -2, -1, 0, 1, 2, 3].map((n) => (
              <option key={n} value={n}>
                {n === 0 ? "As usual" : n > 0 ? `${n} more` : `${-n} fewer`}
              </option>
            ))}
          </Select>
        </Labelled>
        <Labelled label="Each dot of Herd counts">
          <Select aria-label={`${name}: each dot of Herd counts`} value={block.herd_factor} onChange={(e) => set({ herd_factor: Number(e.target.value) })}>
            {HERD.map((h) => (
              <option key={h.factor} value={h.factor}>
                {h.label}
              </option>
            ))}
          </Select>
        </Labelled>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" checked={block.always_half} onChange={(e) => set({ always_half: e.target.checked })} />
          Never more than half Blood after feeding
        </label>
      </>
    );
  } else if (type === "in_clan") {
    body = (
      <TraitList name={name} label="The disciplines it can add (one of them)" options={traitNames(catalogue, EXTRA_IN_CLAN)} names={names} onChange={(n) => set({ names: n })} />
    );
  } else if (type === "health") {
    body = (
      <>
        <TraitList name={name} label="Health levels" options={traitNames(catalogue, HEALTH)} names={names} onChange={(n) => set({ names: n })} />
        <Labelled label="Change">
          <Select aria-label={`${name}: change`} value={block.amount} onChange={(e) => set({ amount: Number(e.target.value) })}>
            {[3, 2, 1, -1, -2, -3].map((n) => (
              <option key={n} value={n}>
                {n > 0 ? `${n} more each` : `${-n} fewer each`}
              </option>
            ))}
          </Select>
        </Labelled>
      </>
    );
  } else {
    const ratingShown = block.test === "trait" && block.name && hasRating(catalogue, block.category, block.name);
    body = (
      <>
        <Labelled label={type === "requires" ? "Requires" : "Not with"}>
          <Select aria-label={`${name}: what it asks about`} value={block.test} onChange={(e) => set({ test: e.target.value as EffectBlock["test"], names: [], name: "" })}>
            <option value="clan">A clan</option>
            <option value="sect">A sect</option>
            <option value="trait">A trait</option>
          </Select>
        </Labelled>
        {block.test === "clan" && (
          <TraitList name={name} label="Clans (a clan includes its bloodlines)" options={clanFamilies(catalogue)} names={names} onChange={(n) => set({ names: n })} />
        )}
        {block.test === "sect" && <TraitList name={name} label="Sects" options={sects(catalogue)} names={names} onChange={(n) => set({ names: n })} />}
        {block.test === "trait" && (
          <>
            <Labelled label="Kind of trait">
              <Select aria-label={`${name}: kind of trait`} value={block.category} onChange={(e) => set({ category: e.target.value, name: "", rating: 1 })}>
                {checkCategories(catalogue).map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Labelled>
            <Labelled label="Trait">
              <Select aria-label={`${name}: trait`} value={block.name} onChange={(e) => set({ name: e.target.value })}>
                <option value="">Choose…</option>
                {traitNames(catalogue, block.category, self).map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </Select>
            </Labelled>
            {ratingShown && (
              <Labelled label="At least">
                <Select aria-label={`${name}: at least`} value={block.rating ?? 1} onChange={(e) => set({ rating: Number(e.target.value) })}>
                  {numbers(1, Math.min(top, 10)).map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </Labelled>
            )}
          </>
        )}
        <Labelled label="How strictly">
          <Select aria-label={`${name}: how strictly`} value={block.strength} onChange={(e) => set({ strength: e.target.value as EffectBlock["strength"] })}>
            {STRENGTHS.map((s) => (
              <option key={s.strength} value={s.strength}>
                {s.label}
              </option>
            ))}
          </Select>
        </Labelled>
      </>
    );
  }

  return (
    <li className="flex flex-col gap-3 rounded-md border border-ash p-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <Labelled label={name}>
          <Select aria-label={`${name}: what it does`} value={type} onChange={(e) => onChange(retype(block, e.target.value as BlockType))} className="sm:w-80">
            {offered.map((b) => (
              <option key={b.type} value={b.type}>
                {b.label}
              </option>
            ))}
          </Select>
        </Labelled>
        <Button type="button" variant="ghost" className="min-h-8 px-2" aria-label={`Remove effect ${index + 1}`} onClick={onRemove}>
          Remove
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">{body}</div>
      {problem && <p className="text-xs text-blood-bright">{problem}</p>}
    </li>
  );
}

/** The blocks of a house merit or flaw: what it does on the sheet. */
export function EffectsEditor({
  blocks,
  catalogue,
  choices,
  self,
  problems,
  onChange,
}: {
  blocks: EffectBlock[];
  catalogue: CatalogueOut | undefined;
  choices: EffectChoicesOut | undefined;
  self: { category: string; name: string };
  problems: Map<number, string>;
  onChange: (blocks: EffectBlock[]) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm text-mist">What it does, on the sheet, at a game and between games</legend>
      {blocks.length === 0 && <p className="text-xs text-mist">Nothing yet: it does what its description says, for you to rule on at the table.</p>}
      {catalogue && (
        <ul className="flex flex-col gap-2">
          {blocks.map((b, i) => (
            <BlockForm
              key={i}
              index={i}
              block={b}
              catalogue={catalogue}
              choices={choices}
              self={self}
              problem={problems.get(i)}
              onChange={(next) => onChange(blocks.map((x, j) => (j === i ? next : x)))}
              onRemove={() => onChange(blocks.filter((_, j) => j !== i))}
            />
          ))}
        </ul>
      )}
      {blocks.length < 20 && (
        <div>
          <Button type="button" variant="secondary" onClick={() => onChange([...blocks, newBlock("free")])}>
            Add an effect
          </Button>
        </div>
      )}
    </fieldset>
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setShown(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return shown;
}

/** The server's try of the merit as it is being made, on a new character or one of the troupe's. */
export function useHousePreview(troupeId: string, body: HouseTraitIn, houseTraitId: string | null, characterId: string) {
  const key = JSON.stringify({ body, houseTraitId, characterId });
  const asked = useDebounced(key, 300);
  return useQuery({
    queryKey: ["house-trait-preview", troupeId, asked],
    queryFn: () => {
      const { body: trait, houseTraitId: house, characterId: character } = JSON.parse(asked) as {
        body: HouseTraitIn;
        houseTraitId: string | null;
        characterId: string;
      };
      return unwrap(
        api.POST("/api/troupes/{troupe_id}/house-traits/preview", {
          params: { path: { troupe_id: troupeId } },
          body: { trait, house_trait_id: house, character_id: character || null },
        }),
      );
    },
    enabled: body.name.trim().length > 0,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

const STRICTLY: Record<string, string> = {
  refuse: "",
  complete: " Creation waits on it.",
  review: " Otherwise it waits on staff approval.",
  note: " A note only.",
};

/** "A character with this would…": what the server found trying it on a sheet. */
export function HousePreview({
  preview,
  error,
  characterId,
  onCharacter,
}: {
  preview: HousePreviewOut | undefined;
  error: unknown;
  characterId: string;
  onCharacter: (id: string) => void;
}) {
  return (
    <section aria-label="Preview" className="flex flex-col gap-2 rounded-md border border-gold/40 bg-gold/5 p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-gold">A character with this would…</h3>
        <Select aria-label="Try it on" value={characterId} onChange={(e) => onCharacter(e.target.value)} className="sm:w-64">
          <option value="">A new character</option>
          {preview?.samples.map((s) => (
            <option key={s.character_id} value={s.character_id}>
              {s.name}
              {s.kind === "npc" ? " (NPC)" : ""}
            </option>
          ))}
        </Select>
      </div>
      <ErrorText error={error} />
      {!preview && !error && <p className="text-xs text-mist">Give it a name to try it.</p>}
      {preview && (
        <>
          {preview.summary && <p className="text-parchment">What it does: {preview.summary}</p>}
          {preview.choosing && <p className="text-xs text-mist">Tried on {preview.sample}, as if the player chose {preview.choosing}.</p>}
          {!preview.choosing && <p className="text-xs text-mist">Tried on {preview.sample}.</p>}
          {preview.changes.length === 0 && preview.checks.length === 0 && (
            <p className="text-xs text-mist">Nothing changes on the sheet: it does what its description says.</p>
          )}
          {preview.changes.length > 0 && (
            <ul className="list-disc pl-5">
              {preview.changes.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
          {preview.checks.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {preview.checks.map((c) => (
                <li key={c.text} className={c.met ? "text-parchment" : "text-blood-bright"}>
                  <span aria-hidden>{c.met ? "✓ " : "✗ "}</span>
                  {c.met ? "Met: " : "Not met: "}
                  {c.text}
                  {STRICTLY[c.strength]}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
