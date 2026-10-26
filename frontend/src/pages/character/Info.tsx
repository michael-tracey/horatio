import type { ReactNode } from "react";
import type { CatalogueOut } from "../../api/types";
import { InfoButton } from "../../components/InfoButton";
import { pageLabel } from "../../components/TraitInfo";
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
 * is, then the rules' description of the choice, its in-clan disciplines, the
 * player's note and the book page, where it has them. Nothing when there is
 * nothing to say. The sheet editor's title and the Play View's subheader both use it.
 */
export function ChoiceInfo({
  choice,
  shown,
  about,
}: {
  choice: { category: string; category_name: string; note: string };
  shown: string;
  /** The rules' entry for the choice. */
  about: { description?: string | null; page_reference?: string | null; in_clan?: string[] | null } | undefined;
}) {
  const what = choiceInfo(choice.category);
  const inClan = about?.in_clan?.length ? `In-clan disciplines: ${about.in_clan.join(", ")}.` : null;
  const lines: ReactNode[] = [about?.description, inClan, choice.note, pageLabel(about?.page_reference)].filter(Boolean);
  if (!what && lines.length === 0) return null;
  return (
    <InfoButton label={`About ${shown}`} className="ml-1">
      <span className="block text-gold">{choice.category_name}</span>
      {what && <span className="mt-1 block">{what}</span>}
      {lines.map((line, i) => (
        <span key={i} className="mt-1 block text-mist">
          {line}
        </span>
      ))}
    </InfoButton>
  );
}
