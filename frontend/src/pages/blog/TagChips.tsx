import type { BlogTagOut } from "../../api/types";
import { withRetired } from "./blog";

/**
 * The blog's tags as chips, as MotifTags' look (#1156): each one on or off, pressed
 * when on. The custodian's queue saves each press at once; the writing page keeps
 * them with the rest of the article until it is saved (#1157). A retired tag the
 * article has (`had`) shows after the rest, marked so (#1161): it can be taken off,
 * but isn't offered to put back.
 */
export function TagChips({
  tags,
  chosen,
  onToggle,
  had,
  disabled = false,
  label = "Tags",
}: {
  tags: BlogTagOut[];
  chosen: string[];
  onToggle: (id: string) => void;
  had?: BlogTagOut[];
  disabled?: boolean;
  label?: string;
}) {
  const shown = withRetired(tags, had).filter(({ tag, retired }) => !retired || chosen.includes(tag.id));
  return (
    <ul aria-label={label} className="flex flex-wrap gap-2">
      {shown.map(({ tag: t, retired }) => {
        const on = chosen.includes(t.id);
        return (
          <li key={t.id}>
            <button
              type="button"
              aria-pressed={on}
              disabled={disabled}
              title={retired ? "Retired: taking it off is for good." : undefined}
              onClick={() => onToggle(t.id)}
              className={`min-h-8 rounded-full border px-3 text-sm ${on ? "border-gold bg-gold/10 text-gold" : "border-ash text-parchment hover:border-mist"}`}
            >
              {t.name}
              {retired && <span className="ml-1 text-xs text-mist">(retired)</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
