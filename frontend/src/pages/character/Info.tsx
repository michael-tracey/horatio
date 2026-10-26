import type { ReactNode } from "react";
import type { CatalogueOut, SheetTraitOut } from "../../api/types";
import { InfoButton } from "../../components/InfoButton";
import { categoryInfo, choiceInfo, partInfo } from "./categoryInfo";

function Lines({ about, facts }: { about: string; facts: string[] }) {
  return (
    <>
      <span className="block">{about}</span>
      {facts.map((f) => (
        <span key={f} className="mt-1 block text-mist">
          {f}
        </span>
      ))}
    </>
  );
}

/** The ⓘ beside a part of the sheet's title (Skills, Backgrounds…); nothing for a part with no copy. */
export function PartInfo({ part, catalogue }: { part: string; catalogue: CatalogueOut | undefined }) {
  const info = partInfo(part, catalogue);
  if (!info) return null;
  return (
    <InfoButton label={`About ${part}`}>
      <Lines {...info} />
    </InfoButton>
  );
}

/** The ⓘ beside a category's heading within a part (Merits, Flaws); nothing for one with no copy. */
export function CategoryInfo({ category, name, catalogue }: { category: string; name: string; catalogue: CatalogueOut | undefined }) {
  const info = categoryInfo(category, catalogue);
  if (!info) return null;
  return (
    <InfoButton label={`About ${name}`}>
      <Lines {...info} />
    </InfoButton>
  );
}

/**
 * The ⓘ beside a choice in the page title (clan, archetype…): what the choice
 * is, then the choice's own description and note where it has them. Nothing
 * when there is nothing to say.
 */
export function ChoiceInfo({ choice, shown, catalogue }: { choice: SheetTraitOut; shown: string; catalogue: CatalogueOut | undefined }) {
  const about = choiceInfo(choice.category);
  const trait = catalogue?.traits.find((t) => t.category === choice.category && t.name === choice.name);
  const inClan = trait?.in_clan?.length ? `In-clan disciplines: ${trait.in_clan.join(", ")}.` : null;
  const lines: ReactNode[] = [trait?.description, inClan, choice.note].filter(Boolean);
  if (!about && lines.length === 0) return null;
  return (
    <InfoButton label={`About ${shown}`} className="ml-1">
      <span className="block text-gold">{choice.category_name}</span>
      {about && <span className="mt-1 block">{about}</span>}
      {lines.map((line, i) => (
        <span key={i} className="mt-1 block text-mist">
          {line}
        </span>
      ))}
    </InfoButton>
  );
}
