import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Card, Input, Notice, PageTitle } from "../../components/ui";
import { useMe } from "../../hooks";
import { helpPath } from "../../manualLink";
import { MANUAL } from "../../manual/content";
import { CONTENTS, inOrder, search, type Heading, type Page } from "../../manual/manual";
import { ManualMarkdown } from "../../manual/ManualMarkdown";

/** The manual's part for the reader: the custodian's, troupe staff's, or the players'. */
function useYourPart(): string {
  const me = useMe();
  const custodian = !!me.data?.is_custodian;
  const troupes = useQuery({ queryKey: ["troupes"], queryFn: () => unwrap(api.GET("/api/troupes")), enabled: !!me.data && !custodian });
  if (custodian) return "custodian";
  if (troupes.data?.some((t) => t.my_role)) return "running-a-troupe";
  return "players";
}

/**
 * The user manual, from docs/manual: `/help` is its contents and search, and
 * `/help/:page` one part, with a list of its sections. Readable signed out.
 */
export function HelpPage() {
  const { page = CONTENTS } = useParams();
  const found = MANUAL.pages.get(page);
  return <div className="help-page">{!found ? <NoSuchPage name={page} /> : page === CONTENTS ? <Contents page={found} /> : <Topic page={found} />}</div>;
}

/** Scroll to the heading the address names, on opening the page and whenever the `#` changes. */
function useScrollToAnchor(page: string, anchor: string | null) {
  useEffect(() => {
    if (anchor) document.getElementById(anchor)?.scrollIntoView();
    else window.scrollTo(0, 0);
  }, [page, anchor]);
}

function useAnchor(): string | null {
  const { hash } = useLocation();
  if (!hash || hash === "#") return null;
  try {
    return decodeURIComponent(hash.slice(1));
  } catch {
    return hash.slice(1);
  }
}

function Contents({ page }: { page: Page }) {
  const yours = useYourPart();
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const anchor = useAnchor();
  useScrollToAnchor(page.name, anchor);
  const hits = useMemo(() => search(MANUAL, query), [query]);
  const yourPage = MANUAL.pages.get(yours);
  const searching = query.trim().length > 0;

  return (
    <>
      <PageTitle subtitle="How to use Horatio: for players, troupe staff and the custodian.">Help</PageTitle>
      <div className="flex flex-col gap-6">
        <div className="print:hidden">
          <Input
            type="search"
            aria-label="Search the manual"
            placeholder="Search the manual…"
            value={query}
            onChange={(e) => setParams(e.target.value ? { q: e.target.value } : {}, { replace: true })}
            className="w-full"
          />
        </div>
        {searching ? (
          <section aria-label="Search results" className="flex flex-col gap-3">
            <p className="text-sm text-mist" role="status">
              {hits.length === 0 ? `Nothing in the manual matches “${query.trim()}”.` : hits.length === 1 ? "1 result" : `${hits.length} results`}
            </p>
            {hits.length > 0 && (
              <ol className="flex flex-col divide-y divide-ash rounded-lg border border-ash bg-dusk">
                {hits.map((hit) => (
                  <li key={hit.to} className="p-3 sm:p-4">
                    <Link to={hit.to} className="text-gold underline hover:text-parchment">
                      {hit.section.pageTitle}
                      {hit.section.heading && <> › {hit.section.heading}</>}
                    </Link>
                    {hit.snippet.length > 0 && (
                      <p className="mt-1 text-sm text-mist">
                        {hit.snippet.map((part, i) =>
                          part.match ? (
                            <mark key={i} className="rounded-sm bg-gold/25 text-parchment">
                              {part.text}
                            </mark>
                          ) : (
                            part.text
                          ),
                        )}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
        ) : (
          <>
            {yourPage && (
              <Card className="border-gold/40 print:hidden">
                <p className="text-sm">
                  Start with{" "}
                  <Link to={helpPath(yourPage.name)} className="font-semibold text-gold underline hover:text-parchment">
                    {yourPage.title}
                  </Link>
                  {yours === "custodian" ? ": you're the custodian." : yours === "running-a-troupe" ? ": you're on a troupe's staff." : "."} Every part is open
                  to everyone.
                </p>
              </Card>
            )}
            <article className="flex flex-col gap-3 text-sm leading-relaxed break-words sm:text-base">
              <ManualMarkdown page={page.name} blocks={withoutTitle(page)} images={MANUAL.images} highlight={yours} />
            </article>
          </>
        )}
      </div>
    </>
  );
}

function withoutTitle(page: Page) {
  const [first, ...rest] = page.blocks;
  return first?.t === "heading" && first.level === 1 ? rest : page.blocks;
}

function Topic({ page }: { page: Page }) {
  const anchor = useAnchor();
  useScrollToAnchor(page.name, anchor);
  const sections = page.headings.filter((h) => h.level === 2);
  const missing = anchor && !page.headings.some((h) => h.id === anchor);

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-2 text-sm text-mist print:hidden">
        <Link to={"/help"} className="underline hover:text-parchment">
          Help
        </Link>{" "}
        › {page.title}
      </nav>
      <PageTitle>{page.title}</PageTitle>
      {missing && (
        <div className="mb-6 print:hidden">
          <Notice>
            There's no section “{anchor}” on this page: it may have been renamed. Pick one from {sections.length ? "the list of sections" : "the page"}, or{" "}
            <Link to={"/help"} className="text-gold underline">
              search the manual
            </Link>
            .
          </Notice>
        </div>
      )}
      <div className={sections.length ? "lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-8" : undefined}>
        {sections.length > 0 && (
          <>
            <aside className="hidden lg:block print:hidden">
              <nav aria-label="On this page" className="sticky top-4 text-sm">
                <h2 className="mb-2 text-xs tracking-wide text-mist uppercase">On this page</h2>
                <SectionList sections={sections} page={page.name} current={anchor} />
              </nav>
            </aside>
            <details className="mb-6 rounded-lg border border-ash bg-dusk p-3 text-sm lg:hidden print:hidden" open={!!missing}>
              <summary className="cursor-pointer text-parchment">On this page ({sections.length})</summary>
              <nav aria-label="On this page" className="mt-2">
                <SectionList sections={sections} page={page.name} current={anchor} />
              </nav>
            </details>
          </>
        )}
        <article className="flex min-w-0 lg:col-start-2 flex-col gap-3 text-sm leading-relaxed break-words sm:text-base">
          <ManualMarkdown page={page.name} blocks={withoutTitle(page)} images={MANUAL.images} />
        </article>
      </div>
      <p className="mt-10 border-t border-ash pt-4 text-sm print:hidden">
        <Link to={"/help"} className="text-gold underline hover:text-parchment">
          Back to Help
        </Link>
      </p>
    </>
  );
}

function SectionList({ sections, page, current }: { sections: Heading[]; page: string; current: string | null }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {sections.map((h) => (
        <li key={h.id}>
          <Link
            to={helpPath(page, h.id)}
            aria-current={current === h.id ? "location" : undefined}
            className={current === h.id ? "text-parchment" : "text-mist hover:text-parchment"}
          >
            {h.text}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function NoSuchPage({ name }: { name: string }) {
  return (
    <>
      <PageTitle>Help</PageTitle>
      <Card>
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-parchment">There's no help page called “{name}”.</p>
          <p className="text-mist">It may have been renamed. These are the parts of the manual:</p>
          <ul className="flex flex-col gap-1.5">
            {inOrder(MANUAL)
              .filter((p) => p.name !== CONTENTS)
              .map((p) => (
                <li key={p.name}>
                  <Link to={helpPath(p.name)} className="text-gold underline hover:text-parchment">
                    {p.title}
                  </Link>
                </li>
              ))}
          </ul>
          <p>
            <Link to={"/help"} className="text-gold underline hover:text-parchment">
              Search the manual
            </Link>
          </p>
        </div>
      </Card>
    </>
  );
}
