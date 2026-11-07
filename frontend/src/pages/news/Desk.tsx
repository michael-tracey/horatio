import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, unwrap } from "../../api/client";
import type { AgencyOut, PostOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem, MenuLink } from "../../components/ActionMenu";
import { DateInput } from "../../components/DateInput";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { deskSections, discordText, KINDS, scheduleProblem, suggestedTime, type Kind } from "./posts";
import { postPath, useAgencies, useDesk, usePublished } from "./queries";
import { Masthead } from "./Story";

/**
 * The news desk (#510): for storytellers and assistant storytellers, every proposal,
 * draft, scheduled and declined story, then what is published with how it went on
 * Discord; for a narrator, their own proposals. Each story's ⋯ does what can be done
 * with it now.
 */
export function Desk({ troupeId, kind, writes }: { troupeId: string; kind: Kind; writes: boolean }) {
  const words = KINDS[kind];
  const desk = useDesk(troupeId, kind);
  const published = usePublished(troupeId, kind);
  const agencies = useAgencies(troupeId);
  const agencyOf = (p: PostOut) => agencies.data?.find((a) => a.id === p.agency_id);
  if (desk.isPending) return <Loading />;
  if (desk.error) return <ErrorText error={desk.error} />;
  const sections = deskSections(desk.data.posts);
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <span className="flex flex-wrap items-center justify-between gap-2">
        <Link to=".." relative="path" className="text-sm text-mist underline hover:text-parchment">
          {words.title}, as players read it
        </Link>
        <Link to="../write" relative="path" className="inline-flex min-h-10 items-center rounded-md bg-blood px-4 text-sm font-medium text-parchment hover:bg-blood-bright">
          {writes ? `Write a ${words.noun}` : `Propose a ${words.noun}`}
        </Link>
      </span>
      {!writes && <p className="text-sm text-mist">Your proposals wait here for a storyteller or assistant storyteller to publish or decline. You can change one until then.</p>}
      {sections.length === 0 && !writes && (
        <Card>
          <Empty>No proposals waiting.</Empty>
        </Card>
      )}
      {sections.map((s) => (
        <Card key={s.status} title={!writes && s.status === "proposed" ? "Waiting" : s.title}>
          <ul className="divide-y divide-ash">
            {s.posts.map((p) => (
              <DeskRow key={p.id} post={p} agency={agencyOf(p)} writes={writes} kind={kind} />
            ))}
          </ul>
        </Card>
      ))}
      {writes && (
        <Card title="Published">
          {published.isPending ? (
            <Loading />
          ) : !published.data?.posts.length ? (
            <Empty>Nothing published yet.</Empty>
          ) : (
            <ul className="divide-y divide-ash">
              {published.data.posts.map((p) => (
                <DeskRow key={p.id} post={p} agency={agencyOf(p)} writes={writes} kind={kind} />
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}

type Opened = "schedule" | "unpublish" | "delete" | "decline";

/** One story on the desk: what it is and where it stands, and its actions behind ⋯. */
function DeskRow({ post, agency, writes, kind }: { post: PostOut; agency: AgencyOut | undefined; writes: boolean; kind: Kind }) {
  const words = KINDS[kind];
  const dates = useDates();
  const toast = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState<Opened | null>(null);
  const close = () => setOpen(null);
  const path = postPath(post.id);
  const run = useAction(async (what: "publish" | "unschedule" | "unpublish" | "duplicate" | "delete" | "retry" | "mark-sent") => {
    if (what === "publish") return unwrap(api.POST("/api/posts/{post_id}/publish", { ...path, body: { note: "" } }));
    if (what === "unschedule") return unwrap(api.POST("/api/posts/{post_id}/unschedule", path));
    if (what === "unpublish") return unwrap(api.POST("/api/posts/{post_id}/unpublish", path));
    if (what === "duplicate") return unwrap(api.POST("/api/posts/{post_id}/duplicate", path));
    if (what === "retry") return unwrap(api.POST("/api/posts/{post_id}/discord/retry", path));
    if (what === "mark-sent") return unwrap(api.POST("/api/posts/{post_id}/discord/mark-sent", path));
    await unwrap(api.DELETE("/api/posts/{post_id}", path));
    return null;
  });
  const done = (message: string) => () => {
    close();
    toast({ message });
  };
  const status =
    post.status === "scheduled" && post.publish_at
      ? `Goes out ${dates.deadline(post.publish_at)}`
      : post.status === "published" && post.published_at
        ? `Published ${dates.due(post.published_at)}`
        : post.status === "proposed"
          ? writes
            ? `Proposed by ${post.proposed_by ?? "a narrator"}`
            : "Waiting for the storytellers"
          : post.status === "declined"
            ? `Declined${post.note ? `: “${post.note}”` : ""}`
            : `Draft by ${post.author}`;
  const discord = writes ? discordText(post) : null;
  const failed = post.status === "published" && post.discord?.state === "failed";
  const editable = writes || post.status === "proposed";

  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="flex min-w-0 flex-col gap-1">
        <Masthead agency={agency} small />
        <Link to={`../${post.id}`} relative="path" className="font-display text-parchment hover:text-gold">
          {post.title}
        </Link>
        <span className="text-xs text-mist">{status}</span>
        {discord && <span className={`text-xs ${failed ? "text-blood-bright" : "text-mist"}`}>{discord}</span>}
        {failed && (
          <span className="flex flex-wrap gap-2">
            <Button variant="secondary" className="min-h-8 px-3" disabled={run.isPending} onClick={() => run.mutate("retry", { onSuccess: done("Trying Discord again.") })}>
              Retry
            </Button>
            <Button variant="ghost" className="min-h-8 px-3" disabled={run.isPending} onClick={() => run.mutate("mark-sent", { onSuccess: done("Marked as sent.") })}>
              Mark as sent
            </Button>
          </span>
        )}
        <ErrorText error={run.error} />
      </div>
      <ActionMenu label={`Actions for ${post.title}`} variant="ghost">
        <MenuGroup label="Open">
          <MenuLink to={`../${post.id}`}>Read</MenuLink>
          {editable && <MenuLink to={`../${post.id}/edit`}>{post.status === "scheduled" ? "Change" : "Edit"}</MenuLink>}
        </MenuGroup>
        {writes && (
          <MenuGroup label="Publish">
            {["draft", "proposed", "scheduled"].includes(post.status) && <MenuItem onSelect={() => run.mutate("publish", { onSuccess: done("Published.") })}>Publish now</MenuItem>}
            {["draft", "proposed"].includes(post.status) && <MenuItem onSelect={() => setOpen("schedule")}>Schedule…</MenuItem>}
            {post.status === "scheduled" && <MenuItem onSelect={() => run.mutate("unschedule", { onSuccess: done("Cancelled: it's a draft again.") })}>Cancel</MenuItem>}
            {post.status === "proposed" && <MenuItem onSelect={() => setOpen("decline")}>Decline…</MenuItem>}
            {post.status === "published" && (
              <MenuItem danger onSelect={() => setOpen("unpublish")}>
                Unpublish…
              </MenuItem>
            )}
          </MenuGroup>
        )}
        <MenuGroup label="Copy or remove">
          {writes && (
            <MenuItem
              onSelect={() =>
                run.mutate("duplicate", {
                  onSuccess: (copy) => {
                    toast({ message: "Copied as a new draft." });
                    if (copy) navigate(`../${copy.id}/edit`, { relative: "path" });
                  },
                })
              }
            >
              Duplicate
            </MenuItem>
          )}
          {post.status !== "published" && (writes || post.status !== "scheduled") && (
            <MenuItem danger onSelect={() => setOpen("delete")}>
              {post.status === "proposed" && !writes ? "Withdraw…" : "Delete…"}
            </MenuItem>
          )}
        </MenuGroup>
      </ActionMenu>
      <Dialog title={`Schedule “${post.title}”`} open={open === "schedule"} onClose={close}>
        <ScheduleForm post={post} onDone={done("Scheduled.")} />
      </Dialog>
      <Dialog title={`Decline “${post.title}”`} open={open === "decline"} onClose={close}>
        <DeclineForm post={post} onDone={done("Declined. The narrator is told.")} />
      </Dialog>
      <Dialog title={`Unpublish “${post.title}”?`} open={open === "unpublish"} onClose={close}>
        <Confirm
          text={`It goes from everyone's ${words.title} at once, and its Discord post is deleted. It comes back to your drafts, to publish again if you like.`}
          action="Unpublish"
          busy={run.isPending}
          onYes={() => run.mutate("unpublish", { onSuccess: done("Unpublished. It's a draft again.") })}
          onNo={close}
        />
      </Dialog>
      <Dialog title={`Delete “${post.title}”?`} open={open === "delete"} onClose={close}>
        <Confirm text={`The ${words.noun} is gone for good.`} action="Delete" busy={run.isPending} onYes={() => run.mutate("delete", { onSuccess: done("Deleted.") })} onNo={close} />
      </Dialog>
    </li>
  );
}

function Confirm({ text, action, busy, onYes, onNo }: { text: string; action: string; busy: boolean; onYes: () => void; onNo: () => void }) {
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p>{text}</p>
      <span className="flex flex-wrap gap-2">
        <Button variant="danger" disabled={busy} onClick={onYes}>
          {action}
        </Button>
        <Button variant="ghost" onClick={onNo}>
          Keep it
        </Button>
      </span>
    </div>
  );
}

/** Schedule from the desk: a date and time on the writer's own clock. */
function ScheduleForm({ post, onDone }: { post: PostOut; onDone: () => void }) {
  const dates = useDates();
  const [when, setWhen] = useState(() => suggestedTime(new Date(), dates.toInput));
  const at = when ? dates.fromInput(when) : null;
  const problem = scheduleProblem(when, at);
  const schedule = useAction(() => unwrap(api.POST("/api/posts/{post_id}/schedule", { ...postPath(post.id), body: { publish_at: at!.toISOString() } })));
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!problem) schedule.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label={`Publish at (${dates.zoneName(at ?? new Date())})`} hint="It goes out within a minute of then, in the app and on Discord.">
        <DateInput type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
      </Field>
      {problem && when && <p className="text-sm text-blood-bright">{problem}</p>}
      <ErrorText error={schedule.error} />
      <Button type="submit" disabled={!!problem || schedule.isPending} className="self-start">
        Schedule
      </Button>
    </form>
  );
}

function DeclineForm({ post, onDone }: { post: PostOut; onDone: () => void }) {
  const [note, setNote] = useState("");
  const decline = useAction(() => unwrap(api.POST("/api/posts/{post_id}/decline", { ...postPath(post.id), body: { note } })));
  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        decline.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <p>{post.proposed_by ?? "The narrator"} is told it was declined, with your note if you write one.</p>
      <Field label="Note (optional)">
        <textarea rows={3} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} className="min-h-10 w-full rounded-md border border-ash bg-night px-3 py-2 text-parchment focus:border-gold focus:outline-none" />
      </Field>
      <ErrorText error={decline.error} />
      <span className="flex gap-2">
        <Button type="submit" variant="danger" disabled={decline.isPending}>
          Decline
        </Button>
        <Badge>It can't be undone</Badge>
      </span>
    </form>
  );
}
