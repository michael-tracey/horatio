import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { GettingReadyOut, ReadyStep } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { troupeSettings } from "./features";

/** The id of the profile on the troupe's Overview, which the first steps link to. */
export const PROFILE_ANCHOR = "profile";

export type ReadyLine = { step: ReadyStep; label: string; done: boolean; text: string; to: string };

/** What each step is called, says while to do and once done, and where it is done, under the troupe. */
const STEPS: Record<ReadyStep, { label: string; todo: string; done: string; to: string }> = {
  profile: {
    label: "Profile",
    todo: "Describe the troupe, and add a portrait and when and where you play, for players choosing a troupe.",
    done: "Described, with a profile for players choosing a troupe.",
    to: `#${PROFILE_ANCHOR}`,
  },
  features: {
    label: "Features",
    todo: "Switch on what the troupe uses: boons, blood bonds, quests and more.",
    done: "Chosen: the troupe has them otherwise than a new one starts.",
    to: `/${troupeSettings()}`,
  },
  joining: {
    label: "Who may join",
    todo: "Choose the splats and sects player characters may join from.",
    done: "Chosen: not every vampire of any sect.",
    to: `/${troupeSettings("joining")}`,
  },
  starting: {
    label: "Starting points and XP",
    todo: "Set the XP characters start with and earn, and the points they're built with.",
    done: "Set otherwise than a new troupe starts.",
    to: `/${troupeSettings("xp")}`,
  },
  house_rules: {
    label: "House rules",
    todo: "None yet: everything plays as the book has it. Change what you play differently.",
    done: "Some rules play differently from the book.",
    to: "/house-rules/checks",
  },
  staff: {
    label: "Staff",
    todo: "Only the lead storyteller so far. Add storytellers, assistants and narrators to share the work.",
    done: "Others share the work with the lead storyteller.",
    to: "/staff",
  },
  first_game: {
    label: "First game",
    todo: "Add it under Edit profile, in When it plays, so players can say they're coming.",
    done: "Games are on the calendar.",
    to: `#${PROFILE_ANCHOR}`,
  },
  players: {
    label: "Invite players",
    todo: "Send players the troupe's link: they make a character for it, or bring one, and ask to join.",
    done: "Players have characters here, or have asked to join.",
    to: "/players",
  },
};

/** The steps in the order the server gives them, each with its words and where it is done. */
export function readyLines(ready: GettingReadyOut, base: string): ReadyLine[] {
  return ready.steps.map(({ step, done }) => {
    const s = STEPS[step];
    return { step, label: s.label, done, text: done ? s.done : s.todo, to: `${base}${s.to}` };
  });
}

export function useGettingReady(troupeId: string) {
  return useQuery({
    queryKey: ["getting-ready", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/getting-ready", { params: { path: { troupe_id: troupeId } } })),
  });
}

/** Hide the card from the Overview, or bring it back. */
function useHide(troupeId: string) {
  return useAction((hidden: boolean) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/getting-ready", { params: { path: { troupe_id: troupeId } }, body: { hidden } })),
  );
}

const LIST_LABEL = "Getting your troupe ready";

/** "3 of 8 done", gold once every step is. */
function DoneBadge({ lines }: { lines: ReadyLine[] }) {
  const done = lines.filter((l) => l.done).length;
  return <Badge tone={done === lines.length ? "gold" : "mist"}>{`${done} of ${lines.length} done`}</Badge>;
}

/** The steps in order, each ticked or not, and a link to where it is done. */
function ReadyList({ lines }: { lines: ReadyLine[] }) {
  return (
    <ol className="divide-y divide-ash" aria-label={LIST_LABEL}>
      {lines.map((line) => (
        <li key={line.step}>
          <Link to={line.to} className="flex items-start gap-3 py-2.5 text-sm hover:text-gold">
            <Tick done={line.done} />
            <span className="min-w-0 flex-1">
              <span className="text-parchment">{line.label}</span>
              <span className="sr-only">{line.done ? ": done." : ": to do."}</span>
              <span className="block text-mist">{line.text}</span>
            </span>
            <span aria-hidden className="text-mist">
              ›
            </span>
          </Link>
        </li>
      ))}
    </ol>
  );
}

function Tick({ done }: { done: boolean }) {
  return (
    <span
      aria-hidden
      className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-xs ${
        done ? "border-gold/60 bg-gold/15 text-gold" : "border-line text-transparent"
      }`}
    >
      ✓
    </span>
  );
}

/**
 * Getting your troupe ready (#1049), on the Overview for its lead storyteller and
 * storytellers, until they hide it: how many steps are done and the next one, the
 * whole list folded away to keep the page short on a phone. Each step ticks itself
 * from what the troupe holds; Customise › Setup brings the card back.
 */
export function GettingReadyCard({ troupeId }: { troupeId: string }) {
  const ready = useGettingReady(troupeId);
  const hide = useHide(troupeId);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  if (ready.isPending || ready.error || ready.data.hidden) return null;
  const lines = readyLines(ready.data, `/troupes/${troupeId}`);
  const next = lines.find((l) => !l.done);
  return (
    <Card
      title={LIST_LABEL}
      className="md:col-span-2"
      actions={
        <div className="flex items-center gap-2">
          <DoneBadge lines={lines} />
          <Button
            variant="ghost"
            className="min-h-8 px-2"
            disabled={hide.isPending}
            onClick={() => hide.mutate(true, { onSuccess: () => toast({ message: "Hidden. Bring it back from Customise › Setup." }) })}
          >
            Hide
          </Button>
        </div>
      }
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
        {next ? (
          <p className="min-w-0">
            <span className="text-mist">Next: </span>
            <Link to={next.to} className="text-parchment underline decoration-ash hover:text-gold">
              {next.label}
            </Link>
            <span className="text-mist">. {next.text}</span>
          </p>
        ) : (
          <p className="text-mist">Every step is done. Hide this once you no longer need it.</p>
        )}
        <Button variant="ghost" className="min-h-8 px-2" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Fold the steps" : "Every step"}
        </Button>
      </div>
      {open && (
        <div className="mt-2">
          <ReadyList lines={lines} />
        </div>
      )}
      <ErrorText error={hide.error} />
    </Card>
  );
}

/**
 * The same steps on Customise › Setup, every one shown, where its storytellers bring
 * the card back to the Overview, or hide it.
 */
export function GettingReadySetup({ troupeId, canEdit }: { troupeId: string; canEdit: boolean }) {
  const ready = useGettingReady(troupeId);
  const hide = useHide(troupeId);
  const toast = useToast();
  if (ready.isPending) return <Loading />;
  if (ready.error) return <ErrorText error={ready.error} />;
  const lines = readyLines(ready.data, `/troupes/${troupeId}`);
  const hidden = ready.data.hidden;
  return (
    <Card title={LIST_LABEL} actions={<DoneBadge lines={lines} />}>
      <ReadyList lines={lines} />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-ash pt-3 text-sm">
        <p className="text-mist">{hidden ? "Hidden from the Overview." : "On the Overview for the lead storyteller and storytellers."}</p>
        {canEdit && (
          <Button
            variant="secondary"
            disabled={hide.isPending}
            onClick={() =>
              hide.mutate(!hidden, { onSuccess: () => toast({ message: hidden ? "Back on the Overview." : "Hidden from the Overview." }) })
            }
          >
            {hidden ? "Show on the Overview" : "Hide from the Overview"}
          </Button>
        )}
      </div>
      <ErrorText error={hide.error} />
    </Card>
  );
}
