import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { PriceOut, RulesBrowserOut, TraitCheckOut } from "../../api/types";
import { EmptyState, FilterBar } from "../../components/EmptyState";
import { HouseMark, HouseSummary } from "../../components/HouseMark";
import { PageRef } from "../../components/TraitInfo";
import { Badge, Button, Card, ErrorText, Input, Loading, PageTitle, Select } from "../../components/ui";
import { useSplats } from "../character/splats";
import { pageText } from "../troupe/bookPage";
import { PLAYED } from "../troupe/HouseRulesTab";
import { ownFirst } from "../troupeList";
import { CategoryMark, HouseWording } from "../../components/TroupeChange";
import {
  applyFilters,
  categoryPrices,
  clanChoices,
  entries,
  generalChecks,
  ratingChoices,
  ratingLabel,
  SECTIONS,
  sectionCounts,
  shownChecks,
  type Entry,
  type Filters,
} from "./rulesBrowser";

/** How many entries show at first, and how many more each tap: a phone draws a long list slowly. */
const PAGE = 50;

/** The rules hardly change: ask once a visit, and filter here. */
const STALE_MS = 60 * 60_000;

/**
 * Every trait, power, ritual, merit and flaw, with its book page and a short
 * summary, to search and filter: as the book has them, or as played in a troupe,
 * its house rules applied and marked. What is shown lives in the address, so a
 * link can open it on merits for a troupe.
 */
export function RulesPage() {
  const [params, setParams] = useSearchParams();
  // What is shown is kept here, and copied to the address for Back and for links:
  // read back from the address, a box typed in fast would lose letters while the
  // router catches up.
  const [shownBy, setShownBy] = useState<Record<string, string>>(() => Object.fromEntries(params));
  const set = (changes: Record<string, string>) => setShownBy((now) => ({ ...now, ...changes }));
  useEffect(() => {
    const next = new URLSearchParams(Object.entries(shownBy).filter(([, value]) => value));
    if (next.toString() !== new URLSearchParams(window.location.search).toString()) setParams(next, { replace: true });
  }, [shownBy, setParams]);
  const splat = shownBy.splat || "vampire";
  const troupeId = shownBy.troupe ?? "";
  const filters: Filters = {
    section: shownBy.category ?? "",
    query: shownBy.q ?? "",
    clan: shownBy.clan ?? "",
    rating: shownBy.rating ? Number(shownBy.rating) : null,
    barred: shownBy.barred === "1",
  };

  const splats = useSplats();
  // A key of its own, as the Troupes page has: a list asked for earlier lacks a troupe made since.
  const troupes = useQuery({ queryKey: ["troupes", "rules"], queryFn: () => unwrap(api.GET("/api/troupes")) });
  const rules = useQuery({
    queryKey: ["rules-browser", splat, troupeId],
    queryFn: () =>
      unwrap(api.GET("/api/rules/{splat}/browse", { params: { path: { splat }, query: { troupe_id: troupeId || undefined } } })),
    staleTime: STALE_MS,
    gcTime: STALE_MS,
    placeholderData: keepPreviousData,
  });
  const data = rules.data;
  const all = useMemo(() => (data ? entries(data) : []), [data]);
  const shown = applyFilters(all, filters);
  const counts = sectionCounts(all, filters);
  const ratings = filters.section ? ratingChoices(all, filters.section) : [];
  const barredCount = all.filter((e) => e.barred && (!filters.section || e.section === filters.section)).length;
  const filtering = !!(filters.section || filters.query || filters.clan || filters.rating != null);

  // How many show: back to one page whenever the filters change.
  const filterKey = JSON.stringify([splat, troupeId, filters]);
  const [more, setMore] = useState<{ key: string; limit: number }>({ key: filterKey, limit: PAGE });
  const limit = more.key === filterKey ? more.limit : PAGE;

  return (
    <>
      <PageTitle subtitle="Every trait, power, ritual, merit and flaw, with its book page and a short summary. Choose a troupe to see it as played there.">
        Rules
      </PageTitle>
      <div className="flex flex-col gap-4">
        <div className="flex items-end gap-3">
          <label className="flex min-w-0 flex-1 flex-col gap-1 text-sm sm:max-w-72">
            <span className="text-mist">As played in</span>
            <Select value={troupeId} onChange={(e) => set({ troupe: e.target.value, barred: "" })}>
              <option value="">The book, without house rules</option>
              {ownFirst(troupes.data ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </label>
          {(splats.data?.length ?? 0) > 1 && (
            <label className="flex w-32 shrink-0 flex-col gap-1 text-sm sm:w-40">
              <span className="text-mist">Rules for</span>
              <Select value={splat} onChange={(e) => set({ splat: e.target.value === "vampire" ? "" : e.target.value, clan: "" })}>
                {splats.data?.map((s) => (
                  <option key={s.splat} value={s.splat}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </label>
          )}
        </div>
        {data?.troupe_name && troupeId && (
          <p className="text-sm text-mist">
            As played in {data.troupe_name}: its house rules are applied, each marked <Badge tone="gold">House rule</Badge>.{" "}
            <Link to={`/troupes/${troupeId}/house-rules`} className="underline hover:text-parchment">
              What it changes
            </Link>
          </p>
        )}

        <FilterBar count={all.length} filtering={filtering}>
          <div className="flex flex-col gap-3">
            <Input
              type="search"
              aria-label="Search the rules"
              placeholder="Search names and summaries…"
              value={filters.query}
              onChange={(e) => set({ q: e.target.value })}
            />
            <nav aria-label="Categories" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0">
              <Chip label="Everything" pressed={!filters.section} onClick={() => set({ category: "", rating: "" })} />
              {SECTIONS.filter((s) => data?.catalogue.categories.some((c) => s.categories.includes(c.key))).map((s) => (
                <Chip
                  key={s.key}
                  label={s.label}
                  count={counts.get(s.key) ?? 0}
                  pressed={filters.section === s.key}
                  onClick={() => set({ category: s.key, rating: "" })}
                />
              ))}
            </nav>
            <div className="flex flex-wrap gap-2">
              <Select aria-label="Clan" value={filters.clan} onChange={(e) => set({ clan: e.target.value })} className="w-auto">
                <option value="">Any clan</option>
                {data &&
                  clanChoices(data).map((c) => (
                    <option key={c} value={c}>
                      For {c}
                    </option>
                  ))}
              </Select>
              {ratings.length > 1 && (
                <Select
                  aria-label={ratingLabel(filters.section)}
                  value={filters.rating ?? ""}
                  onChange={(e) => set({ rating: e.target.value })}
                  className="w-auto"
                >
                  <option value="">{`Any ${ratingLabel(filters.section).toLowerCase()}`}</option>
                  {ratings.map((r) => (
                    <option key={r} value={r}>
                      {ratingLabel(filters.section)} {r}
                    </option>
                  ))}
                </Select>
              )}
              {barredCount > 0 && (
                <label className="flex min-h-10 items-center gap-2 text-sm text-mist">
                  <input type="checkbox" checked={filters.barred} onChange={(e) => set({ barred: e.target.checked ? "1" : "" })} />
                  Show the {barredCount} not allowed in {data?.troupe_name}
                </label>
              )}
            </div>
          </div>
        </FilterBar>

        <ErrorText error={rules.error} />
        {rules.isPending ? (
          <Loading />
        ) : data && shown.length === 0 ? (
          <Card>
            <EmptyState
              title={filters.query.trim() ? `Nothing matches “${filters.query.trim()}”.` : "Nothing matches."}
              action={
                <Button variant="secondary" onClick={() => set({ q: "", category: "", clan: "", rating: "" })}>
                  Clear the search and filters
                </Button>
              }
            >
              Try fewer words, or every category.
            </EmptyState>
          </Card>
        ) : (
          data && (
            <>
              <p className="text-sm text-mist" aria-live="polite">
                {shown.length === 1 ? "1 found" : `${shown.length} found`}
              </p>
              <Results data={data} shown={shown.slice(0, limit)} />
              {shown.length > limit && (
                <Button variant="secondary" className="self-start" onClick={() => setMore({ key: filterKey, limit: limit + PAGE })}>
                  Show {Math.min(PAGE, shown.length - limit)} more
                </Button>
              )}
            </>
          )
        )}
      </div>
    </>
  );
}

/** The entries under a heading for each category, with what the whole category costs and the rules it keeps. */
function Results({ data, shown }: { data: RulesBrowserOut; shown: Entry[] }) {
  const parts: { category: string; entries: Entry[] }[] = [];
  for (const e of shown) {
    const last = parts[parts.length - 1];
    if (last?.category === e.category) last.entries.push(e);
    else parts.push({ category: e.category, entries: [e] });
  }
  return (
    <>
      {parts.map((part, n) => {
        const category = data.catalogue.categories.find((c) => c.key === part.category);
        const prices = categoryPrices(data, part.category);
        const general = generalChecks(data, part.category);
        return (
          <Card key={`${part.category}/${n}`} title={category?.name ?? part.category} dense>
            {(prices.length > 0 || general.length > 0) && (
              <div className="mb-2 flex flex-col gap-1 border-b border-ash pb-2 text-xs text-mist">
                {prices.length > 0 && <Prices prices={prices} label="Costs" />}
                {general.length > 0 && (
                  <details>
                    <summary className="cursor-pointer hover:text-parchment">
                      Rules for every {(category?.name ?? "one").toLowerCase().replace(/s$/, "")} ({general.length})
                    </summary>
                    <Checks checks={general} />
                  </details>
                )}
              </div>
            )}
            <ul className="divide-y divide-ash">
              {part.entries.map((e) => (
                <EntryRow key={e.key} entry={e} troupe={data.troupe_name} />
              ))}
            </ul>
          </Card>
        );
      })}
    </>
  );
}

function EntryRow({ entry: e, troupe }: { entry: Entry; troupe: string | null }) {
  const t = e.trait;
  const checks = shownChecks(e);
  const power = !t;
  return (
    <li className={`flex flex-col gap-1 py-2.5 text-sm ${power ? "pl-3 sm:pl-5" : ""}`} data-testid="rules-entry">
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h3 className="font-sans text-sm text-parchment">{e.name}</h3>
        {e.rating && <span className="text-xs text-gold">{e.rating}</span>}
        {e.requirement && <Badge>{e.requirement}</Badge>}
        {t?.kind && t.kind !== e.requirement && <span className="text-xs text-mist">{t.kind}</span>}
        {t?.house && <HouseMark label={t.house.label} />}
        <CategoryMark change={t?.changed} />
        {e.barred && (
          <>
            <Badge tone="blood">{e.banned ? `Banned in ${troupe}` : `Not allowed in ${troupe}`}</Badge>
            <Badge tone="gold">House rule</Badge>
          </>
        )}
        {e.page && (
          <span className="text-xs text-mist">
            <PageRef page={e.page} text={pageText} />
          </span>
        )}
      </div>
      {e.summary && <p className="text-mist">{e.summary}</p>}
      <HouseWording change={t?.changed} />
      {t?.house && (
        <>
          <HouseSummary summary={t.description ? t.house.summary : null} />
          <span className="text-xs text-mist">{t.house.availability === "staff" ? "Given by the storytellers only." : "Available when building for the troupe."}</span>
        </>
      )}
      {e.barred?.text && <p className="text-xs text-mist">House rule: {e.barred.text}</p>}
      {t?.house_rule && (
        <p className="text-xs text-mist">
          <Badge tone="gold">House rule</Badge> {t.house_rule}
        </p>
      )}
      {t?.attribute && <p className="text-xs text-mist">Usually tested with {t.attribute}.</p>}
      {t?.in_clan && t.in_clan.length > 0 && <p className="text-xs text-mist">In-clan: {t.in_clan.join(", ")}.</p>}
      {t?.weakness && (
        <p className="text-xs text-mist">
          Weakness: {t.weakness}
          {t.weakness_page && ` ${pageText(t.weakness_page)}`}
        </p>
      )}
      {e.rarity && (
        <p className="text-xs text-mist">
          Rarity: {e.rarity.text}
          {e.rarity.page && ` ${pageText(e.rarity.page)}`}
          {e.rarity.house && (
            <>
              {" "}
              <Badge tone="gold">House rule</Badge>
            </>
          )}
        </p>
      )}
      {e.prices.length > 0 && (
        <div className="text-xs text-mist">
          <Prices prices={e.prices} label="Costs" />
        </div>
      )}
      {checks.length > 0 && (
        <div className="text-xs text-mist">
          <Checks checks={checks} />
        </div>
      )}
    </li>
  );
}

/** Prices in words, each house price marked with the book's beside it. */
function Prices({ prices, label }: { prices: PriceOut[]; label: string }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {prices.map((p, n) => (
        <li key={n}>
          {label}
          {p.when && ` (${p.when})`}: <span className={p.house ? "text-gold" : "text-parchment"}>{p.price}</span>
          {p.house && (
            <>
              {" "}
              <Badge tone="gold">House rule</Badge>
              {p.book && ` By the book: ${p.book}.`}
              {p.text && ` ${p.text}`}
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Checks in the words a player meets when one refuses a change, with how the troupe plays any it changed. */
function Checks({ checks }: { checks: TraitCheckOut[] }) {
  return (
    <ul className="flex flex-col gap-0.5">
      {checks.map((c) => (
        <li key={c.key} className={c.house === "off" ? "line-through decoration-mist/60" : undefined}>
          {c.message}
          {c.page && (
            <>
              {" "}
              <PageRef page={c.page} text={pageText} />
            </>
          )}
          {c.house && (
            <span className="no-underline">
              {" "}
              <Badge tone="gold">House rule</Badge> {PLAYED[c.house] ?? c.house}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** A category to show, drawn like the Add panel's chips, with how many it holds. */
function Chip({ label, count, pressed, onClick }: { label: string; count?: number; pressed: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`shrink-0 rounded-full border px-3 py-1 text-sm whitespace-nowrap pointer-coarse:py-2 ${
        pressed ? "border-gold/60 bg-gold/10 text-parchment" : "border-ash text-mist hover:text-parchment"
      }`}
    >
      {label}
      {count != null && (
        <>
          {" "}
          <span className="text-gold">{count}</span>
        </>
      )}
    </button>
  );
}
