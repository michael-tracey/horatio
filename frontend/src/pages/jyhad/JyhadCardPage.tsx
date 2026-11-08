import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { useClanName } from "../../components/ClanNames";
import { usePreferences } from "../../hooks";
import { pageRule } from "../../paper";
import { downloadCard } from "./draw";
import { JyhadCard } from "./JyhadCard";

const TEXT_LENGTH = 300;
const FLAVOUR_LENGTH = 120;

/** Paradox's notice, word for word, as the Dark Pack Agreement asks (as on About). */
const PARADOX =
  "Portions of the materials are the copyrights and trademarks of Paradox Interactive AB, and are used with permission. All rights reserved. For more information please visit worldofdarkness.com.";

// The card at its real size in print, larger on screen, as wide as a phone allows.
// The page is the reader's paper (#104), so nothing scales the card to fit.
const SIZING = `
.jyhad-card { --mm: clamp(3.78px, calc((100vw - 32px) / 63), 6px); }
@media print { .jyhad-card { --mm: 1mm; } }
`;

/**
 * A character's Jyhad card (#537), found by tapping its clan symbol seven times,
 * or from the ⋯ on the troupe's Characters list for its staff: the card, Print (at
 * its real size, 63 × 88 mm) and Download image, and for its player (staff, for an
 * NPC) its text and flavour line to write. Never official: it says so on its face.
 */
export function JyhadCardPage() {
  const { characterId = "" } = useParams();
  const [params] = useSearchParams();
  const troupeId = params.get("troupe");
  const named = useClanName();
  const prefs = usePreferences();
  const client = useQueryClient();
  const key = ["jyhad-card", characterId];
  const card = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/jyhad-card", { params: { path: { character_id: characterId } } })),
  });
  const [typed, setTyped] = useState<{ text: string; flavour: string } | null>(null);
  const save = useMutation({
    mutationFn: (body: { text: string; flavour: string }) =>
      unwrap(api.PUT("/api/characters/{character_id}/jyhad-card/text", { params: { path: { character_id: characterId } }, body })),
    onSuccess: (saved) => {
      client.setQueryData(key, saved);
      setTyped(null);
    },
  });
  const [making, setMaking] = useState(false);
  const back = troupeId ? `/troupes/${troupeId}/characters` : `/characters/${characterId}`;

  if (card.isPending) return <p className="p-8">Loading…</p>;
  if (card.error) return <p className="p-8">{card.error.message}</p>;
  const c = card.data;
  const words = typed ?? { text: c.text, flavour: c.flavour };
  const clanName = named(c.clan);

  return (
    <div className="jyhad-card min-h-screen bg-night px-4 py-6 text-parchment print:min-h-0 print:bg-white print:p-0">
      <style>{SIZING + pageRule(prefs.paper, "12mm")}</style>
      <div className="mx-auto flex max-w-xl flex-col items-center gap-5">
        <div className="flex w-full flex-wrap items-center justify-between gap-3 print:hidden">
          <Link to={back} className="text-sm text-mist underline hover:text-parchment">
            ← Back
          </Link>
          {!c.missing && (
            <span className="flex gap-2">
              <button type="button" onClick={() => window.print()} className="rounded-md border border-ash bg-dusk px-4 py-1.5 text-sm hover:border-mist">
                Print
              </button>
              <button
                type="button"
                disabled={making}
                onClick={() => {
                  setMaking(true);
                  downloadCard(c, clanName, words.text, words.flavour).finally(() => setMaking(false));
                }}
                className="rounded-md bg-blood px-4 py-1.5 text-sm hover:bg-blood-bright disabled:opacity-60"
              >
                {making ? "Making the image…" : "Download image"}
              </button>
            </span>
          )}
        </div>
        {c.missing ? (
          <p className="text-mist">{c.missing}</p>
        ) : (
          <>
            <JyhadCard card={c} clanName={clanName} text={words.text} flavour={words.flavour} />
            {c.can_write && (
              <form
                className="flex w-full flex-col gap-3 print:hidden"
                onSubmit={(e) => {
                  e.preventDefault();
                  save.mutate(words);
                }}
              >
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-mist">Card text</span>
                  <textarea
                    rows={3}
                    maxLength={TEXT_LENGTH}
                    value={words.text}
                    onChange={(e) => setTyped({ ...words, text: e.target.value })}
                    className="rounded-md border border-ash bg-dusk px-3 py-2 text-parchment"
                  />
                  <span className="text-xs text-mist">
                    What the card does, if you like, in a VTES card's words. {words.text.length}/{TEXT_LENGTH}
                  </span>
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  <span className="text-mist">Flavour line</span>
                  <input
                    maxLength={FLAVOUR_LENGTH}
                    value={words.flavour}
                    onChange={(e) => setTyped({ ...words, flavour: e.target.value })}
                    className="rounded-md border border-ash bg-dusk px-3 py-2 text-parchment italic"
                  />
                </label>
                {save.error && <p className="text-sm text-blood-bright">{save.error.message}</p>}
                <div className="flex justify-end">
                  <button type="submit" disabled={save.isPending || typed === null} className="rounded-md bg-blood px-4 py-1.5 text-sm hover:bg-blood-bright disabled:opacity-60">
                    Save text
                  </button>
                </div>
              </form>
            )}
          </>
        )}
        <p className="text-xs leading-relaxed text-mist print:hidden">
          Just for fun: not a real card, nothing to do with play, and not official. The look is Horatio's own, after a <em>Vampire: The Eternal Struggle</em> crypt
          card. The clan and discipline symbols are from{" "}
          <a href="https://static.krcg.org/" target="_blank" rel="noreferrer" className="text-gold hover:underline">
            KRCG
          </a>
          , under Paradox Interactive's Dark Pack Agreement. {PARADOX}
        </p>
      </div>
    </div>
  );
}
