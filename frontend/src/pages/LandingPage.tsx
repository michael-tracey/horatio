import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../api/client";
import type { BlogPublicSummaryOut, PublicTroupeOut } from "../api/types";
import { Avatar } from "../components/Avatar";
import { LinkButton } from "../components/LinkButton";
import { Pager } from "../components/Pager";
import { TroupePill } from "../components/TroupePill";
import { Card, Empty, Loaded, PageTitle } from "../components/ui";
import { manualLink } from "../manualLink";
import { ArticleCard } from "./blog/BlogPage";
import { excerpt } from "./troupeList";

// As many as the API puts on a page (public_troupes.PAGE_SIZE).
export const TROUPES_PAGE_SIZE = 12;
// The articles shown: at most two featured, then the newest.
const ARTICLES = 4;
const FEATURED = 2;

/** The articles to show: the first featured ones, then the newest others, each once. */
export function articlesShown(featured: BlogPublicSummaryOut[], newest: BlogPublicSummaryOut[]): BlogPublicSummaryOut[] {
  const shown: BlogPublicSummaryOut[] = [];
  for (const a of [...featured.slice(0, FEATURED), ...newest]) if (!shown.some((s) => s.slug === a.slug)) shown.push(a);
  return shown.slice(0, ARTICLES);
}

/** What Horatio is, in the About page's words, and the ways in. */
function WhatItIs() {
  return (
    <Card title="What Horatio is">
      <div className="flex flex-col gap-3 text-sm leading-relaxed">
        <p>
          Horatio keeps a LARP troupe's characters, experience, downtimes and game nights in one place: players build and play their characters, and storytellers run
          the troupe around them.
        </p>
        <p>
          It is free, and its code is open source. The rules it follows come from <em>Mind's Eye Theatre: Vampire The Masquerade</em>, published by By Night Studios; you
          still need the books to play.
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-3 pt-1">
          <LinkButton to="/sign-up">Create an account</LinkButton>
          <LinkButton to="/sign-in" variant="secondary">
            Sign in
          </LinkButton>
          <span className="flex flex-wrap gap-x-4 gap-y-1">
            <Link to="/about" className="text-gold underline hover:text-parchment">
              About Horatio
            </Link>
            <Link to={manualLink()} className="text-gold underline hover:text-parchment">
              User manual
            </Link>
          </span>
        </div>
      </div>
    </Card>
  );
}

/** A few of the blog's articles: its featured ones first, then the newest (#1158). */
function FromTheBlog() {
  // The blog's own first page, which it then has at once (BlogPage's key).
  const found = useQuery({
    queryKey: ["blog-public", "articles", null, 1],
    queryFn: () => unwrap(api.GET("/api/blog/public/articles", { params: { query: { page: 1 } } })),
  });
  return (
    <section aria-labelledby="landing-blog">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="landing-blog" className="text-lg text-gold">
          From the blog
        </h2>
        <Link to="/blog" className="text-sm text-gold underline hover:text-parchment">
          Read the blog
        </Link>
      </div>
      <p className="mb-3 text-sm text-mist">Essays by the staff of troupes on Horatio: on playing, running a game, and the tricks of both.</p>
      <Loaded query={found}>
        {(page) => {
          const shown = articlesShown(page.featured, page.articles);
          return shown.length ? (
            <ul aria-label="Articles" className="grid gap-4 sm:grid-cols-2">
              {shown.map((a) => (
                <ArticleCard key={a.slug} article={a} />
              ))}
            </ul>
          ) : (
            <Empty>No articles yet.</Empty>
          );
        }}
      </Loaded>
    </section>
  );
}

/** A troupe in the list: its portrait, name, abbreviation, where it plays and the start of its description. */
function TroupeRow({ troupe: t }: { troupe: PublicTroupeOut }) {
  const about = excerpt(t.description);
  return (
    <Link to={`/t/${t.id}`} className="group flex items-start gap-3 py-3">
      <Avatar name={t.name} picture={t.portrait} size="sm" />
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="min-w-0 font-medium break-words text-parchment group-hover:text-gold">{t.name}</span>
          {/* The name is just before it: only the eye needs it again. */}
          {t.abbreviation !== t.name && (
            <span aria-hidden="true" className="contents">
              <TroupePill name={t.name} abbreviation={t.abbreviation} />
            </span>
          )}
          {t.place && <span className="text-xs text-mist">{t.place}</span>}
        </span>
        {about && <span className="line-clamp-2 text-sm text-mist">{about}</span>}
      </span>
    </Link>
  );
}

/** The troupes whose profiles are public and still running, by name, a page at a time. */
function FindATroupe() {
  const [page, setPage] = useState(1);
  const found = useQuery({
    queryKey: ["public-troupes", page],
    queryFn: () => unwrap(api.GET("/api/public/troupes", { params: { query: { page } } })),
    placeholderData: keepPreviousData,
  });
  return (
    <Card title="Find a troupe">
      <p className="mb-2 text-sm text-mist">Troupes that show their profile to anyone. Open one to see where and when it plays, and how to join it.</p>
      <Loaded query={found}>
        {(found) =>
          found.total === 0 ? (
            <Empty>No troupe shows its profile to everyone yet.</Empty>
          ) : (
            <div className="flex flex-col gap-3">
              {found.troupes.length ? (
                <ul aria-label="Troupes" className="divide-y divide-ash">
                  {found.troupes.map((t) => (
                    <li key={t.id}>
                      <TroupeRow troupe={t} />
                    </li>
                  ))}
                </ul>
              ) : (
                <Empty>There are no more troupes. Go back a page.</Empty>
              )}
              <Pager label="Pages of troupes" page={found.page} size={TROUPES_PAGE_SIZE} shown={found.troupes.length} total={found.total} onPage={setPage} />
            </div>
          )
        }
      </Loaded>
    </Card>
  );
}

/**
 * The landing page (#1164), at / for people signed out: what Horatio is, a few of the
 * blog's articles, the troupes anyone may find, and Create an account and Sign in.
 * Someone signed in goes on to Characters (Home).
 */
export function LandingPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8">
      <PageTitle title="Welcome" subtitle="Character sheets, downtimes and game nights for Mind's Eye Theatre LARP troupes.">
        Welcome to Horatio
      </PageTitle>
      <WhatItIs />
      <FromTheBlog />
      <FindATroupe />
    </div>
  );
}
