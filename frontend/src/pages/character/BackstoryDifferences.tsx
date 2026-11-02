import type { BackstoryLineOut } from "../../api/types";

/**
 * How one text differs from another, line by line: what changed since it was
 * approved, for staff, or a draft against a newer version, for its writer.
 */
export function Differences({
  lines,
  title = "Changed since it was approved",
  label = title === "Changed since it was approved" ? "Changes since it was approved" : title,
  added = "Added",
  removed = "Removed",
}: {
  lines: BackstoryLineOut[];
  title?: string;
  label?: string;
  /** What an added or removed line is, as a screen reader says it, and in the key. */
  added?: string;
  removed?: string;
}) {
  const custom = added !== "Added";
  return (
    <div className="mb-4">
      <h3 className="mb-1 font-sans text-xs tracking-wide text-mist uppercase">{title}</h3>
      {custom && (
        <p className="mb-1 flex flex-wrap gap-3 text-xs text-mist">
          <span>
            <span className="bg-gold/15 px-1 text-parchment">+</span> {added}
          </span>
          <span>
            <span className="bg-blood/20 px-1">−</span> {removed}
          </span>
        </p>
      )}
      <div className="overflow-x-auto rounded-md border border-ash bg-night p-2 font-mono text-xs" aria-label={label}>
        {lines.map((line, i) =>
          line.change === "skipped" ? (
            <p key={i} className="py-1 text-mist italic">
              … {line.count} unchanged lines …
            </p>
          ) : (
            <p
              key={i}
              className={`whitespace-pre-wrap ${line.change === "added" ? "bg-gold/15 text-parchment" : line.change === "removed" ? "bg-blood/20 text-mist line-through" : "text-mist"}`}
            >
              <span aria-hidden>{line.change === "added" ? "+ " : line.change === "removed" ? "− " : "  "}</span>
              <span className="sr-only">{line.change === "added" ? `${added}: ` : line.change === "removed" ? `${removed}: ` : ""}</span>
              {line.text || " "}
            </p>
          ),
        )}
      </div>
    </div>
  );
}
