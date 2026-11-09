import { Input, Select } from "../../components/ui";
import { FIELD_PLACEHOLDER } from "./fields";

/**
 * A trait's detail that names one of its choices, split into the choice and the field
 * after it: "Performance: Singing" for Artist's Blessing (#312). A detail that names no
 * choice is all choice.
 */
export function choiceParts(detail: string, choices: string[]): { choice: string; field: string } {
  if (choices.includes(detail)) return { choice: detail, field: "" };
  const at = detail.indexOf(":");
  const choice = at === -1 ? "" : detail.slice(0, at).trim();
  return choices.includes(choice) ? { choice, field: detail.slice(at + 1).trimStart() } : { choice: detail, field: "" };
}

/** The detail a choice and its field make: "Performance: Singing", or "Performance" without one. */
export function choiceDetail(choice: string, field: string): string {
  return field.trim() ? `${choice}: ${field}` : choice;
}

/** The choices split into those preferred (on the sheet already) and the rest, each in its order. */
export function preferredFirst(choices: string[], preferred: string[]): { first: string[]; rest: string[] } {
  const wanted = new Set(preferred);
  return { first: choices.filter((c) => wanted.has(c)), rest: choices.filter((c) => !wanted.has(c)) };
}

/**
 * The choice a trait asks for in its detail (Personal Cult: which background), and for a
 * choice of skill bought once per field (Crafts, Performance), the field with it: a free
 * Performance skill is a Performance: Singing (p. 92). `fields` names those skills.
 */
export function ChoiceSelect({
  choices,
  value,
  onChange,
  fields,
  label,
  placeholder = "Choose…",
  className,
  required,
  preferred = [],
}: {
  choices: string[];
  value: string;
  onChange: (detail: string) => void;
  fields: Set<string>;
  label?: string;
  placeholder?: string;
  className?: string;
  required?: boolean;
  /** Choices to list first, under their own heading: those on the sheet already. */
  preferred?: string[];
}) {
  const { choice, field } = choiceParts(value, choices);
  const { first, rest } = preferredFirst(choices, preferred);
  return (
    <span className="flex min-w-0 flex-wrap items-center gap-2">
      <Select aria-label={label} required={required} className={className} value={choice} onChange={(e) => onChange(choiceDetail(e.target.value, fields.has(e.target.value) ? field : ""))}>
        <option value="">{placeholder}</option>
        {first.length > 0 ? (
          <>
            <optgroup label="On the sheet">
              {first.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </optgroup>
            <optgroup label="Others">
              {rest.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </optgroup>
          </>
        ) : (
          choices.map((c) => <option key={c}>{c}</option>)
        )}
      </Select>
      {fields.has(choice) && (
        <Input
          aria-label={`${choice} field`}
          required={required}
          placeholder={FIELD_PLACEHOLDER}
          className={className}
          value={field}
          onChange={(e) => onChange(choiceDetail(choice, e.target.value))}
        />
      )}
    </span>
  );
}
