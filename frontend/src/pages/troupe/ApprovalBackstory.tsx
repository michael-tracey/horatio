import { useState } from "react";
import { Badge, Button, ErrorText, Loading } from "../../components/ui";
import { Answers, BackstoryReview, BackstoryText, Thread, useBackstory, useBackstoryQuestions, useBackstoryStanding } from "../character/BackstoryTab";

/**
 * A joining character's backstory in its home troupe request, beside the rest:
 * where it stands, and, opened, the backstory itself, its answers to the troupe's
 * questions, the feedback so far, and sending it back or approving it.
 */
export function ApprovalBackstory({ characterId }: { characterId: string }) {
  const standing = useBackstoryStanding(characterId);
  const [open, setOpen] = useState(false);
  const backstory = useBackstory(characterId, open);
  const questions = useBackstoryQuestions(characterId, open);
  const s = standing.data;
  if (!s?.read) return null;
  const words = !s.written
    ? "not written yet"
    : s.approved
      ? "approved"
      : s.changed_since_approval
        ? "changed since it was approved"
        : s.state === "returned"
          ? "sent back to the player"
          : s.state === "resubmitted"
            ? "revised and resubmitted"
            : "not yet approved";

  return (
    <div className="mb-3 rounded-md border border-ash p-3" data-backstory>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          Backstory: <Badge tone={s.approved ? "mist" : "gold"}>{words}</Badge>
          {s.required && !s.approved && <span className="text-xs text-mist">Needed before accepting.</span>}
        </p>
        <Button variant="ghost" className="min-h-8 px-2" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide the backstory" : "Read the backstory"}
        </Button>
      </div>
      {open &&
        (backstory.isPending ? (
          <Loading />
        ) : backstory.error ? (
          <ErrorText error={backstory.error} />
        ) : (
          <div className="mt-3 flex flex-col gap-4">
            <BackstoryText backstory={backstory.data} />
            <Answers sets={questions.data?.sets ?? []} />
            {backstory.data.thread.length > 0 && <Thread backstory={backstory.data} />}
            {backstory.data.review && <BackstoryReview characterId={characterId} backstory={backstory.data} />}
          </div>
        ))}
    </div>
  );
}
