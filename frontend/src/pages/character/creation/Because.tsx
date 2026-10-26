import { Fragment } from "react";
import { Link } from "react-router";
import type { TraitRefOut } from "../../../api/types";
import { stepFor, type StepRef } from "./notices";

/**
 * The traits a refusal is because of, each with the step that holds it, linking there
 * (#192, rule 5): "Because of Archaic (Merits & flaws)." A trait held on this very
 * step is named without a link.
 */
export function Because({ characterId, refs, steps, step }: { characterId: string; refs: TraitRefOut[]; steps: StepRef[]; step: StepRef }) {
  const named = refs.filter((r) => !!r.name);
  if (!named.length) return null;
  return (
    <>
      {" "}
      Because of{" "}
      {named.map((r, i) => {
        const at = stepFor(steps, r.category);
        return (
          <Fragment key={`${r.category}/${r.name}`}>
            {i > 0 && ", "}
            {r.name}
            {at && at.key !== step.key && (
              <>
                {" "}
                (
                <Link className="text-gold underline" to={`/characters/${characterId}/create/${at.key}`}>
                  {at.title}
                </Link>
                )
              </>
            )}
          </Fragment>
        );
      })}
      .
    </>
  );
}
