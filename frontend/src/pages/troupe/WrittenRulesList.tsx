import { useEffect } from "react";
import { Link } from "react-router";
import type { WrittenRuleOut } from "../../api/types";
import { Markdown } from "../../components/Markdown";
import { PageRef } from "../../components/TraitInfo";
import { rulesLink } from "../rules/rulesBrowser";
import { pageText } from "./bookPage";
import { bySection, ruleAnchor, sectionLabel } from "./writtenRules";

/**
 * A troupe's written house rules to read: a short contents list linking to each,
 * then each section's rules, their bodies in Markdown, with the trait or book page
 * each is about. `troupeId` links a rule's trait to the rules browser as played
 * there; without it (someone not signed in), the trait is named only.
 */
export function WrittenRulesList({ rules, troupeId }: { rules: WrittenRuleOut[]; troupeId?: string }) {
  const sections = bySection(rules);
  const headed = sections.length > 1 || sections.some((s) => s.section);
  // Arriving from a link to one rule, show it once the list is drawn.
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id.startsWith("written-rule-")) document.getElementById(id)?.scrollIntoView?.({ block: "start" });
  }, [rules.length]);

  return (
    <div className="flex flex-col gap-5">
      {rules.length > 1 && (
        <nav aria-label="Contents" className="text-sm">
          <ul className="flex flex-col gap-1.5">
            {sections.map((s) => (
              <li key={s.section}>
                {headed && <span className="font-sans text-xs tracking-wide text-mist uppercase">{sectionLabel(s.section)}</span>}
                <ul className="flex flex-col gap-0.5">
                  {s.rules.map((r) => (
                    <li key={r.id}>
                      <a href={`#${ruleAnchor(r.id)}`} className="text-gold underline hover:text-parchment">
                        {r.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </nav>
      )}
      {sections.map((s) => (
        <section key={s.section} className="flex flex-col gap-4 border-t border-ash pt-4 first:border-t-0 first:pt-0">
          {headed && <h3 className="text-base text-gold">{sectionLabel(s.section)}</h3>}
          {s.rules.map((r) => (
            <article key={r.id} id={ruleAnchor(r.id)} className="flex scroll-mt-20 flex-col gap-2" data-testid="written-rule">
              <h4 className="font-sans text-sm font-medium text-parchment">{r.title}</h4>
              {r.body.trim() && <Markdown text={r.body} />}
              <RuleAbout rule={r} troupeId={troupeId} />
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}

/** The trait and book page a rule is about, in a line under it. */
export function RuleAbout({ rule: r, troupeId }: { rule: WrittenRuleOut; troupeId?: string }) {
  if (!r.trait && !r.page) return null;
  const browse = r.trait && troupeId ? rulesLink([r.trait.category], troupeId, r.trait.splat) : null;
  return (
    <p className="text-xs text-mist">
      {r.trait && (
        <>
          About{" "}
          {browse ? (
            <Link to={`${browse}&q=${encodeURIComponent(r.trait.name)}`} className="underline hover:text-parchment">
              {r.trait.name}
            </Link>
          ) : (
            r.trait.name
          )}
          {r.page ? ", " : "."}
        </>
      )}
      {r.page && (
        <>
          {r.trait ? "see " : "See "}
          <PageRef page={r.page} text={pageText} />.
        </>
      )}
    </p>
  );
}
