import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { api, unwrap } from "../api/client";
import { usePreferences } from "../hooks";
import { PAPERS, pageRule } from "../paper";
import { clanText, sections, type Section } from "./troupe/whosWho";

/**
 * A troupe's Who's Who on paper, for a game-night binder: every section, black on
 * white, one line per character, on the person's paper size.
 */
export function WhosWhoPrintPage() {
  const { troupeId = "" } = useParams();
  const paper = usePreferences().paper;
  const whosWho = useQuery({
    queryKey: ["whos-who", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/whos-who", { params: { path: { troupe_id: troupeId } } })),
  });
  if (whosWho.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (whosWho.error) return <p className="p-8 text-black">{whosWho.error.message}</p>;
  const data = whosWho.data;
  const width = { maxWidth: `${PAPERS[paper].width}in` };
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      <style>{pageRule(paper, "0.45in")}</style>
      <div className="mx-auto mb-4 flex items-center justify-between gap-4 px-4 print:hidden" style={width}>
        <Link to={`/troupes/${troupeId}/whos-who`} className="text-sm underline">
          ← Back
        </Link>
        <span className="flex items-center gap-3">
          <span className="text-sm text-neutral-600">For {PAPERS[paper].name}</span>
          <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
            Print
          </button>
        </span>
      </div>
      <main className="mx-auto bg-white p-[0.45in] shadow print:p-0 print:shadow-none" style={width}>
        <h1 className="mb-4 font-display text-2xl">Who’s Who · {data.troupe_name}</h1>
        {sections(data).map((s) => (
          <PrintedSection key={s.id} section={s} />
        ))}
      </main>
    </div>
  );
}

function PrintedSection({ section }: { section: Section }) {
  return (
    <section aria-label={section.title} className="mb-5 break-inside-auto">
      <h2 className="mb-1 border-b border-black text-lg font-semibold break-after-avoid">{section.title}</h2>
      {/* The same columns in every section, so they line up down the page. */}
      <table className="w-full table-fixed text-left text-[9pt] leading-snug">
        <colgroup>
          <col className="w-[18%]" />
          <col className="w-[18%]" />
          <col className="w-[16%]" />
          <col className="w-[18%]" />
          <col />
        </colgroup>
        <thead>
          <tr className="border-b border-neutral-400">
            <th className="py-0.5 pr-2 font-semibold">Character</th>
            <th className="py-0.5 pr-2 font-semibold">Clan</th>
            <th className="py-0.5 pr-2 font-semibold">Player</th>
            <th className="py-0.5 pr-2 font-semibold">{section.kind === "other" ? "Represented by" : "Titles"}</th>
            <th className="py-0.5 font-semibold">{section.kind === "departed" ? "Why they left" : "Others see"}</th>
          </tr>
        </thead>
        <tbody>
          {section.entries.map((e) => (
            <tr key={e.character_id} className="border-b border-neutral-200 align-top break-inside-avoid">
              <td className="py-0.5 pr-2">
                <span className="font-semibold">{e.name}</span>
                {e.pronouns && ` (${e.pronouns})`}
                {e.visiting && <span className="block text-neutral-600">{e.visiting_from ? `Visiting from ${e.visiting_from}` : "Visiting"}</span>}
              </td>
              <td className="py-0.5 pr-2">
                {clanText(e.clan)}, {e.social_age}
              </td>
              <td className="py-0.5 pr-2">
                {e.player_name ?? "NPC"}
                {e.player_pronouns && ` (${e.player_pronouns})`}
              </td>
              <td className="py-0.5 pr-2">{section.kind === "other" ? (e.represented_by ?? "Nobody yet") : e.titles.join(", ")}</td>
              <td className="py-0.5">
                {section.kind === "departed"
                  ? e.left_reason
                  : [...e.visible, ...e.bans, ...e.negative.map((n) => `Negative status: ${n}`)].map((line) => (
                      <span key={line} className="block">
                        {line}
                      </span>
                    ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
