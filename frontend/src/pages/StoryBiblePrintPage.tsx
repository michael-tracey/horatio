import { useNavigate, useParams } from "react-router";
import { Markdown } from "../components/Markdown";
import { usePreferences } from "../hooks";
import { PAPERS, pageRule } from "../paper";
import { useTitle } from "../title";
import { StoryBibleParts, useStoryBible } from "./troupe/StoryBible";

/**
 * A troupe's story bible (#879), black on white, for its staff alone: printed apart
 * from the Setting Style Document players are handed, and refused to anyone else.
 */
export function StoryBiblePrintPage() {
  const { troupeId = "" } = useParams();
  const navigate = useNavigate();
  const paper = usePreferences().paper;
  const bible = useStoryBible(troupeId);
  useTitle(bible.data ? `Print · Story bible · ${bible.data.troupe}` : "Print");
  if (bible.isPending) return <p className="p-8 text-black">Loading…</p>;
  if (bible.error) return <p className="p-8 text-black">{bible.error.message}</p>;
  const b = bible.data;
  const width = { maxWidth: `${PAPERS[paper].width}in` };
  return (
    <div className="min-h-screen bg-neutral-200 py-6 text-black print:min-h-0 print:bg-white print:py-0">
      <style>{pageRule(paper, "0.5in")}</style>
      <div className="mx-auto mb-4 flex items-center justify-between gap-4 px-4 print:hidden" style={width}>
        <button onClick={() => navigate(-1)} className="text-sm underline">
          ← Back
        </button>
        <button onClick={() => window.print()} className="rounded bg-black px-4 py-1.5 text-sm text-white">
          Print
        </button>
      </div>
      <main className="mx-auto flex flex-col gap-6 bg-white p-4 shadow sm:p-[0.5in] print:p-0 print:shadow-none" style={width}>
        <header>
          <p className="mb-2 text-xs tracking-wide uppercase">Story bible · {b.troupe} · staff only</p>
          <h2 className="font-display text-2xl">{b.chronicle || b.troupe}</h2>
        </header>
        {b.notes.length > 0 && (
          <section className="flex flex-col gap-3" aria-label="Staff notes">
            <h3 className="text-base font-semibold">Staff notes</h3>
            {b.notes.map((n) => (
              <div key={n.id} className="break-inside-avoid">
                <h4 className="text-sm font-semibold">{n.title}</h4>
                {n.body && <Markdown text={n.body} />}
              </div>
            ))}
          </section>
        )}
        <StoryBibleParts bible={b} troupeId={troupeId} print />
      </main>
    </div>
  );
}
