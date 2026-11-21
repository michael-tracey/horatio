import { api, unwrap } from "../../api/client";
import { useToast } from "../../components/Toast";
import { ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { ANSWERS, answeredText, type Answer } from "./games";

/**
 * Coming, Maybe or Not coming to one of a troupe's games (#420): the answer is the
 * person's, whichever of their characters they bring. Tapping your answer again takes
 * it back. On the Games card, and on a character's Next card while its player hasn't
 * answered (#1109). `when` is the game's start, as the question and the toast say it.
 */
export function RsvpButtons({ troupeId, gameId, when, answer: given }: { troupeId: string; gameId: string; when: string; answer: Answer | null }) {
  const toast = useToast();
  const path = { params: { path: { troupe_id: troupeId, game_id: gameId } } };
  const answer = useAction(
    async (chosen: Answer | null) => {
      await unwrap(
        chosen === null
          ? api.DELETE("/api/troupes/{troupe_id}/games/{game_id}/rsvp", path)
          : api.PUT("/api/troupes/{troupe_id}/games/{game_id}/rsvp", { ...path, body: { answer: chosen } }),
      );
      toast({ message: answeredText(chosen, when) });
    },
    [["troupe-games", troupeId]],
  );
  // The answer being sent shows at once.
  const mine = answer.isPending ? answer.variables : given;

  return (
    <>
      <div role="group" aria-label={`Are you coming on ${when}?`} className="grid grid-cols-3 gap-2 sm:flex">
        {ANSWERS.map((a) => {
          const on = mine === a.answer;
          return (
            <button
              key={a.answer}
              type="button"
              aria-pressed={on}
              disabled={answer.isPending}
              onClick={() => answer.mutate(on ? null : a.answer)}
              className={`min-h-10 rounded-md border px-3 text-sm transition-colors pointer-coarse:min-h-11 disabled:opacity-60 ${
                on ? "border-gold bg-gold/15 text-gold" : "border-line text-parchment hover:border-mist"
              }`}
            >
              {a.label}
            </button>
          );
        })}
      </div>
      <ErrorText error={answer.error} />
    </>
  );
}
