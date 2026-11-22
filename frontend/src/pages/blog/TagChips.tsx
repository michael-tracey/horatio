import type { BlogTagOut } from "../../api/types";

/**
 * The blog's tags as chips, as MotifTags' look (#1156): each one on or off, pressed
 * when on. The custodian's queue saves each press at once; the writing page keeps
 * them with the rest of the article until it is saved (#1157).
 */
export function TagChips({ tags, chosen, onToggle, disabled = false, label = "Tags" }: { tags: BlogTagOut[]; chosen: string[]; onToggle: (id: string) => void; disabled?: boolean; label?: string }) {
  return (
    <ul aria-label={label} className="flex flex-wrap gap-2">
      {tags.map((t) => {
        const on = chosen.includes(t.id);
        return (
          <li key={t.id}>
            <button
              type="button"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => onToggle(t.id)}
              className={`min-h-8 rounded-full border px-3 text-sm ${on ? "border-gold bg-gold/10 text-gold" : "border-ash text-parchment hover:border-mist"}`}
            >
              {t.name}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
