import type { LinesVeils } from "../api/types";

/** Whether there is anything to show. */
export function hasLinesVeils(value: LinesVeils | null | undefined): value is LinesVeils {
  return !!value && (value.lines.length > 0 || value.veils.length > 0);
}

/**
 * A player's lines and veils in a line or two, where staff (or, if the player
 * shares them, other players) look someone up. Never printed. Shows nothing when
 * there are none, or when the server keeps them back.
 */
export function LinesVeilsNote({ value, who, className = "text-xs" }: { value: LinesVeils | null | undefined; who: string; className?: string }) {
  if (!hasLinesVeils(value)) return null;
  return (
    <dl aria-label={`Lines and veils of ${who}`} className={`flex flex-col gap-0.5 print:hidden ${className}`}>
      {value.lines.length > 0 && (
        <div>
          <dt className="inline font-medium text-blood-bright">Lines: </dt>
          <dd className="inline">{value.lines.join(", ")}</dd>
        </div>
      )}
      {value.veils.length > 0 && (
        <div>
          <dt className="inline font-medium text-gold">Veils: </dt>
          <dd className="inline">{value.veils.join(", ")}</dd>
        </div>
      )}
    </dl>
  );
}
