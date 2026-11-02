import type { CatalogueOut, CategoryOut, EquipmentOut } from "../../api/types";
import { Button, Input, Select } from "../../components/ui";
import { useClanName } from "../../components/ClanNames";
import { blank, COMPARE, isGroup, matchOf, OP_LABELS, STATUSES, WHATS, type Condition, type EquipmentMatch, type Group, type Item, type Op, type What } from "./filters";

/** What the builder offers: the troupe's rules, its titles, the players and characters in its list, and equipment's kinds and qualities. */
export type Choices = {
  catalogue: CatalogueOut;
  titles: string[];
  players: { id: string; name: string }[];
  characters: { id: string; name: string }[];
  equipment: EquipmentOut | undefined;
};

/**
 * Build a filter out of conditions, each a row of dropdowns, in a group that
 * matches all or any of them. The top group can hold sub-groups (one level), so
 * "Occult below 3, and (Tremere or Giovanni)" can be said.
 */
export function FilterBuilder({ value, onChange, choices }: { value: Group; onChange: (group: Group) => void; choices: Choices }) {
  return <GroupEditor group={value} onChange={onChange} choices={choices} depth={0} />;
}

function GroupEditor({
  group,
  onChange,
  onRemove,
  choices,
  depth,
}: {
  group: Group;
  onChange: (group: Group) => void;
  onRemove?: () => void;
  choices: Choices;
  depth: number;
}) {
  const setItem = (i: number, item: Item) => onChange({ ...group, items: group.items.map((x, j) => (j === i ? item : x)) });
  const removeItem = (i: number) => onChange({ ...group, items: group.items.filter((_, j) => j !== i) });
  const label = depth === 0 ? "Show characters matching" : "Group: matching";

  return (
    <div className={depth > 0 ? "rounded-md border border-ash/80 bg-night/40 p-3" : ""}>
      <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-mist">{label}</span>
        <Select aria-label={depth === 0 ? "Match" : "Group match"} value={group.match} onChange={(e) => onChange({ ...group, match: e.target.value as Group["match"] })} className="h-8 w-auto py-0">
          <option value="all">all of these (and)</option>
          <option value="any">any of these (or)</option>
        </Select>
        {onRemove && (
          <Button type="button" variant="ghost" className="ml-auto min-h-8" onClick={onRemove}>
            Remove group
          </Button>
        )}
      </div>
      <ul className="flex flex-col gap-2">
        {group.items.map((item, i) => (
          <li key={i}>
            {isGroup(item) ? (
              <GroupEditor group={item} onChange={(g) => setItem(i, g)} onRemove={() => removeItem(i)} choices={choices} depth={depth + 1} />
            ) : (
              <ConditionEditor condition={item} onChange={(c) => setItem(i, c)} onRemove={() => removeItem(i)} choices={choices} />
            )}
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          className="min-h-8"
          aria-label={depth > 0 ? "Add a condition to this group" : undefined}
          onClick={() => onChange({ ...group, items: [...group.items, blank("trait")] })}
        >
          + Condition
        </Button>
        {depth === 0 && (
          <Button
            type="button"
            variant="secondary"
            className="min-h-8"
            onClick={() => onChange({ ...group, items: [...group.items, { match: "any", items: [blank("choice")] }] })}
          >
            + Group
          </Button>
        )}
      </div>
    </div>
  );
}

const small = "h-8 w-auto py-0 text-sm";

/** Categories offered as choices first: the unrated ones (clan, sect…), morality paths and focuses. */
function isChoice(c: CategoryOut): boolean {
  return !c.rated || c.key === "paths" || c.key.startsWith("focus_");
}

function ConditionEditor({ condition: c, onChange, onRemove, choices }: { condition: Condition; onChange: (c: Condition) => void; onRemove: () => void; choices: Choices }) {
  const { catalogue } = choices;
  const named = useClanName();
  const categories = catalogue.categories.filter((k) => catalogue.traits.some((t) => t.category === k.key));
  const traitsIn = (key: string) => catalogue.traits.filter((t) => t.category === key);
  const set = (change: Partial<Condition>) => onChange({ ...c, ...change });
  const ops = (list: Op[]) => (
    <Select aria-label="How" value={c.op} onChange={(e) => set({ op: e.target.value as Op })} className={small}>
      {list.map((op) => (
        <option key={op} value={op}>
          {OP_LABELS[op]}
        </option>
      ))}
    </Select>
  );
  const number = (
    <Input
      aria-label="Number"
      type="number"
      value={typeof c.value === "number" ? c.value : ""}
      onChange={(e) => set({ value: e.target.value === "" ? null : Number(e.target.value) })}
      className="h-8 w-20 py-0 text-sm"
    />
  );

  let fields: React.ReactNode = null;
  if (c.what === "status") {
    fields = (
      <>
        {ops(["is", "is_not"])}
        <Select aria-label="Status" value={String(c.value ?? "")} onChange={(e) => set({ value: e.target.value })} className={small}>
          {Object.entries(STATUSES).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </Select>
      </>
    );
  } else if (c.what === "trait") {
    const [category = "", name = ""] = (c.which ?? "").split("/");
    const traits = traitsIn(category);
    // Merits and flaws are held or not; rated traits compare their rating too.
    const onlyHeld = (traits.length > 0 && traits.every((t) => t.fixed_rating)) || !categories.find((k) => k.key === category)?.rated;
    fields = (
      <>
        <Select aria-label="Category" value={category} onChange={(e) => set({ which: `${e.target.value}/` })} className={small}>
          <option value="">Category…</option>
          {categories.map((k) => (
            <option key={k.key} value={k.key}>
              {k.name}
            </option>
          ))}
        </Select>
        {category && (
          <Select
            aria-label="Trait"
            value={name}
            onChange={(e) => {
              const fixed = traits.find((t) => t.name === e.target.value)?.fixed_rating;
              set({ which: `${category}/${e.target.value}`, ...(fixed ? { op: "has", value: null } : {}) });
            }}
            className={small}
          >
            <option value="">Trait…</option>
            {traits.map((t) => (
              <option key={t.name} value={t.name}>
                {named(t.name)}
              </option>
            ))}
          </Select>
        )}
        {ops(onlyHeld ? ["has", "lacks"] : [...COMPARE, "has", "lacks"])}
        {c.op !== "has" && c.op !== "lacks" && number}
      </>
    );
  } else if (c.what === "choice") {
    const which = c.which ?? "clan";
    const chosen = Array.isArray(c.value) ? c.value : [];
    const options = traitsIn(which)
      .map((t) => t.name)
      .filter((n) => (c.op === "family" ? !n.includes(":") : true));
    fields = (
      <>
        <Select aria-label="Category" value={which} onChange={(e) => set({ which: e.target.value, op: "is", value: [] })} className={small}>
          <optgroup label="Choices">
            {categories.filter(isChoice).map((k) => (
              <option key={k.key} value={k.key}>
                {k.name}
              </option>
            ))}
          </optgroup>
          <optgroup label="Holds any of">
            {categories
              .filter((k) => !isChoice(k))
              .map((k) => (
                <option key={k.key} value={k.key}>
                  {k.name}
                </option>
              ))}
          </optgroup>
        </Select>
        {ops(which === "clan" ? ["is", "is_not", "family"] : ["is", "is_not"])}
        {chosen.map((v) => (
          <span key={v} className="inline-flex h-8 items-center gap-1 rounded-full border border-gold/50 px-2 text-xs text-gold">
            {named(v)}
            <button type="button" aria-label={`Remove ${named(v)}`} className="text-mist hover:text-parchment" onClick={() => set({ value: chosen.filter((x) => x !== v) })}>
              ×
            </button>
          </span>
        ))}
        <Select aria-label={chosen.length ? "Or" : "Value"} value="" onChange={(e) => e.target.value && set({ value: [...chosen, e.target.value] })} className={small}>
          <option value="">{chosen.length ? "or…" : "Choose…"}</option>
          {options
            .filter((n) => !chosen.includes(n))
            .map((n) => (
              <option key={n} value={n}>
                {named(n)}
              </option>
            ))}
        </Select>
      </>
    );
  } else if (c.what === "title") {
    fields = (
      <>
        <Select aria-label="How" value={c.op} onChange={(e) => set({ op: e.target.value as Op })} className={small}>
          <option value="has">holds</option>
          <option value="lacks">does not hold</option>
        </Select>
        <Select aria-label="Title" value={String(c.value ?? "")} onChange={(e) => set({ value: e.target.value || null })} className={small}>
          <option value="">any title</option>
          {choices.titles.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </Select>
      </>
    );
  } else if (c.what === "player") {
    fields = (
      <>
        {ops(["is", "is_not"])}
        <Select aria-label="Player" value={String(c.value ?? "")} onChange={(e) => set({ value: e.target.value || null })} className={small}>
          <option value="">Player…</option>
          {choices.players.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
      </>
    );
  } else if (c.what === "character") {
    const chosen = Array.isArray(c.value) ? c.value : [];
    const nameOf = (id: string) => choices.characters.find((x) => x.id === id)?.name ?? "someone";
    fields = (
      <>
        {ops(["is", "is_not"])}
        {chosen.map((id) => (
          <span key={id} className="inline-flex h-8 items-center gap-1 rounded-full border border-gold/50 px-2 text-xs text-gold">
            {nameOf(id)}
            <button type="button" aria-label={`Remove ${nameOf(id)}`} className="text-mist hover:text-parchment" onClick={() => set({ value: chosen.filter((x) => x !== id) })}>
              ×
            </button>
          </span>
        ))}
        <Select aria-label={chosen.length ? "Or" : "Character"} value="" onChange={(e) => e.target.value && set({ value: [...chosen, e.target.value] })} className={small}>
          <option value="">{chosen.length ? "or…" : "Choose…"}</option>
          {choices.characters
            .filter((x) => !chosen.includes(x.id))
            .map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
        </Select>
      </>
    );
  } else if (c.what === "equipment") {
    fields = <EquipmentFields condition={c} onChange={onChange} rules={choices.equipment} />;
  } else if (c.what === "xp") {
    fields = (
      <>
        <Select aria-label="Experience" value={c.which ?? "earned"} onChange={(e) => set({ which: e.target.value })} className={small}>
          <option value="earned">earned</option>
          <option value="unspent">unspent</option>
        </Select>
        {ops(COMPARE)}
        {number}
      </>
    );
  } else {
    fields = (
      <>
        <Select aria-label="Category" value={c.which ?? ""} onChange={(e) => set({ which: e.target.value })} className={small}>
          {categories.map((k) => (
            <option key={k.key} value={k.key}>
              {k.name}
            </option>
          ))}
        </Select>
        {ops(COMPARE)}
        {number}
      </>
    );
  }

  return (
    <fieldset className="flex flex-wrap items-center gap-2 rounded-md border border-ash/60 px-2 py-1.5">
      <legend className="sr-only">Condition</legend>
      <Select aria-label="What" value={c.what} onChange={(e) => onChange(blank(e.target.value as What))} className={small}>
        {Object.entries(WHATS).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
          </option>
        ))}
      </Select>
      {fields}
      <button type="button" aria-label="Remove condition" onClick={onRemove} className="ml-auto grid h-8 w-8 place-items-center rounded text-mist hover:bg-ash hover:text-parchment">
        ×
      </button>
    </fieldset>
  );
}

/**
 * An equipment condition: has or lacks an item it holds of a kind, with a quality
 * (only those of the kind chosen are offered) and its detail, special or not, with
 * words in its name. Left empty, any item.
 */
function EquipmentFields({ condition: c, onChange, rules }: { condition: Condition; onChange: (c: Condition) => void; rules: EquipmentOut | undefined }) {
  const m = matchOf(c);
  const setMatch = (change: Partial<EquipmentMatch>) => onChange({ ...c, value: { ...m, ...change } });
  const qualities = rules?.qualities ?? [];
  const ofKind = (kind: string | null | undefined) => qualities.filter((q) => !kind || q.kind === kind);
  const names = [...new Set(ofKind(m.kind).map((q) => q.name))].sort((a, b) => a.localeCompare(b));
  const prompt = ofKind(m.kind).find((q) => q.name === m.quality)?.detail_prompt;
  return (
    <>
      <Select aria-label="How" value={c.op} onChange={(e) => onChange({ ...c, op: e.target.value as Op })} className={small}>
        <option value="has">holds</option>
        <option value="lacks">does not hold</option>
      </Select>
      <Select
        aria-label="Kind of item"
        value={m.kind ?? ""}
        onChange={(e) => {
          const kind = e.target.value || null;
          // A quality the new kind doesn't have goes.
          const keeps = !m.quality || ofKind(kind).some((q) => q.name === m.quality);
          setMatch({ kind, ...(keeps ? {} : { quality: null, detail: "" }) });
        }}
        className={small}
      >
        <option value="">any kind</option>
        {rules?.kinds.map((k) => (
          <option key={k.key} value={k.key}>
            {k.name.toLowerCase()}
          </option>
        ))}
      </Select>
      <Select aria-label="Quality" value={m.quality ?? ""} onChange={(e) => setMatch({ quality: e.target.value || null, detail: "" })} className={small}>
        <option value="">with any quality</option>
        {names.map((n) => (
          <option key={n} value={n}>
            {n}
          </option>
        ))}
      </Select>
      {prompt && (
        <Input
          aria-label={`${m.quality} detail`}
          placeholder={`${prompt} (optional)`}
          value={m.detail ?? ""}
          onChange={(e) => setMatch({ detail: e.target.value })}
          className="h-8 w-40 py-0 text-sm"
        />
      )}
      <Input aria-label="Name contains" placeholder="name contains…" value={m.name ?? ""} onChange={(e) => setMatch({ name: e.target.value })} className="h-8 w-36 py-0 text-sm" />
      <label className="flex items-center gap-1 text-sm text-mist">
        <input type="checkbox" checked={!!m.special} onChange={(e) => setMatch({ special: e.target.checked })} />
        special only
      </label>
    </>
  );
}
