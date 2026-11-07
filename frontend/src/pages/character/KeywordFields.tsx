import { useState } from "react";
import { Link } from "react-router";
import type { KeywordChoiceOut, LearningOut, TerritoryOut } from "../../api/types";
import { Badge, Button, Field, Input, Select } from "../../components/ui";
import { manualLink } from "../../manualLink";
import { dropped, keywordOf, textOf, withKeyword, withText } from "./keywords";

type Fields = Record<string, unknown> | undefined;

/**
 * What kind of action an answer is, chosen first (#509): the keywords its question
 * offers, each with what it is for. Once chosen it folds to its name, with Change.
 * Changing it keeps the description, and warns first of the fields it drops.
 */
export function KeywordChooser({
  name,
  offered,
  keywords,
  fields,
  onChange,
}: {
  /** Unique to the answer, for its radio buttons. */
  name: string;
  offered: KeywordChoiceOut[];
  /** Every keyword the form knows, for one chosen before that is retired since. */
  keywords: KeywordChoiceOut[];
  fields: Fields;
  onChange: (fields: Record<string, unknown>) => void;
}) {
  const key = keywordOf(fields);
  const current = keywords.find((k) => k.key === key);
  const [choosing, setChoosing] = useState(!current);
  const [pending, setPending] = useState<KeywordChoiceOut | null>(null);
  const choose = (keyword: KeywordChoiceOut) => {
    if (current && dropped(fields, keyword).length) {
      setPending(keyword);
      return;
    }
    onChange(withKeyword(fields, keyword));
    setChoosing(false);
  };

  if (!choosing && current)
    return (
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="gold">{current.name}</Badge>
          {offered.length > 1 && (
            <Button variant="ghost" className="min-h-8 px-2" aria-label={`Change ${current.name} to another kind of action`} onClick={() => setChoosing(true)}>
              Change
            </Button>
          )}
        </div>
        {current.explanation && <p className="text-xs text-mist">{current.explanation}</p>}
      </div>
    );

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-sm text-parchment">
        What kind of action is it?{" "}
        <Link to={manualLink("players", "keywords-what-kind-of-action")} className="text-xs text-mist underline hover:text-parchment">
          About keywords
        </Link>
      </legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {offered.map((k) => (
          <label
            key={k.key}
            className="flex cursor-pointer flex-col gap-1 rounded-md border border-ash p-3 hover:border-mist has-[:checked]:border-gold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-gold"
          >
            <span className="flex items-center gap-2">
              <input type="radio" name={name} value={k.key} checked={k.key === key} onChange={() => choose(k)} className="pointer-coarse:size-5" />
              <strong className="text-parchment">{k.name}</strong>
              {k.cost !== 1 && <span className="text-xs text-mist">{k.cost === 0 ? "costs no action" : `costs ${k.cost} actions`}</span>}
            </span>
            {k.explanation && <span className="text-xs text-mist">{k.explanation}</span>}
          </label>
        ))}
      </div>
      {pending && current && (
        <div role="alert" className="flex flex-col gap-2 rounded-md border border-gold/60 p-3 text-sm">
          <p>
            Changing it to {pending.name} drops {dropped(fields, pending).join(" and ")}. What you wrote stays.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              onClick={() => {
                onChange(withKeyword(fields, pending));
                setPending(null);
                setChoosing(false);
              }}
            >
              Change to {pending.name}
            </Button>
            <Button variant="ghost" onClick={() => setPending(null)}>
              Keep {current.name}
            </Button>
          </div>
        </div>
      )}
      {current && !pending && (
        <Button variant="ghost" className="self-start px-0" onClick={() => setChoosing(false)}>
          Keep {current.name}
        </Button>
      )}
    </fieldset>
  );
}

/** The fields the answer's keyword asks for, besides who it is aimed at and the description. */
export function KeywordFields({
  keyword,
  fields,
  territories,
  onChange,
}: {
  keyword: KeywordChoiceOut;
  fields: Fields;
  /** The domain's feeding territories, while they are played. */
  territories: TerritoryOut[];
  onChange: (fields: Record<string, unknown>) => void;
}) {
  const owed = !!textOf(fields, "owed_action_id");
  const set = (key: string, value: string) => onChange(withText(fields, key, value));
  const patrol = keyword.effect === "patrol";
  const offered = patrol ? territories.filter((t) => t.mine || t.id === textOf(fields, "territory")) : territories;
  const asks = (field: string) => keyword.fields.includes(field);
  const chosen = territories.find((t) => t.id === textOf(fields, "territory"));
  const poaching = !!chosen && !chosen.mine;
  if (!keyword.fields.some((f) => f !== "character")) return null;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {asks("territory") && (
        <Field
          label={patrol ? "Territory to patrol" : "Feed in a territory"}
          hint={
            patrol
              ? "One your character holds. Each Patrol action tests anyone poaching there (Vol. 2, p. 305)."
              : poaching
                ? `That is poaching: ${chosen.holders.length ? `${chosen.holders.join(", ")} may be patrolling it` : "if anyone holds it, they may be patrolling it"}.`
                : "Once a cycle, feeding in a territory stands in for a feeding action without spending one (Vol. 2, pp. 304-305)."
          }
        >
          <Select value={textOf(fields, "territory")} onChange={(e) => set("territory", e.target.value)}>
            <option value="">{patrol ? "Choose…" : "No territory"}</option>
            {offered.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({t.mine ? "yours" : t.holders.length ? `held by ${t.holders.join(", ")}` : t.held_by ? `held by ${t.held_by}` : "unassigned"})
              </option>
            ))}
          </Select>
        </Field>
      )}
      {asks("target") && (
        <Field label="Or something else" hint="A territory, a plot or a quest, if it isn't aimed at a character.">
          <Input value={textOf(fields, "subject")} onChange={(e) => set("subject", e.target.value)} />
        </Field>
      )}
      {asks("trait") && (
        <Field
          label="What to learn"
          hint={owed ? "Already taken from your actions: it costs nothing more." : "A discipline dot, a technique or an elder power."}
        >
          <Input value={textOf(fields, "learn")} disabled={owed} onChange={(e) => set("learn", e.target.value)} />
        </Field>
      )}
      {asks("teacher") && (
        <Field label="Teacher" hint="If any.">
          <Input value={textOf(fields, "teacher")} onChange={(e) => set("teacher", e.target.value)} />
        </Field>
      )}
      {asks("item") && (
        <Field label="The item wanted" hint="One item, with one quality.">
          <Input value={textOf(fields, "item")} onChange={(e) => set("item", e.target.value)} />
        </Field>
      )}
    </div>
  );
}

/**
 * Actions ready-made for the player to confirm (#509): what the character is learning,
 * already off its allowance, and keywords it takes each cycle that it has no action of yet.
 */
export function ReadyMade({
  learning,
  learn,
  required,
  onAdd,
}: {
  learning: LearningOut[];
  /** The Learn keyword, when the question offers it. */
  learn?: KeywordChoiceOut;
  required: KeywordChoiceOut[];
  onAdd: (fields: Record<string, unknown>) => void;
}) {
  if (!(learn && learning.length) && !required.length) return null;
  return (
    <ul aria-label="Ready-made actions" className="flex flex-col gap-2">
      {learn &&
        learning.map((l) => (
          <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-ash p-2 text-sm">
            <span>
              <Badge tone="gold">{learn.name}</Badge> {l.what}
              {l.teacher && ` from ${l.teacher}`} <span className="text-xs text-mist">· already taken from your actions</span>
            </span>
            <Button
              variant="secondary"
              aria-label={`Confirm learning ${l.what}`}
              onClick={() =>
                onAdd({
                  keyword: learn.key,
                  learn: l.what,
                  ...(l.teacher ? { teacher: l.teacher } : {}),
                  owed_action_id: l.id,
                })
              }
            >
              Confirm
            </Button>
          </li>
        ))}
      {required.map((k) => (
        <li key={k.key} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed border-gold/60 p-2 text-sm">
          <span>
            <Badge tone="gold">{k.name}</Badge> <span className="text-xs text-mist">· your character takes this each cycle</span>
          </span>
          <Button variant="secondary" aria-label={`Add a ${k.name} action`} onClick={() => onAdd({ keyword: k.key })}>
            Add it
          </Button>
        </li>
      ))}
    </ul>
  );
}
