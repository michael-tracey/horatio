import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { CycleNominationsOut, CycleOut, ReviewedOut } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { excerpt } from "./nominations";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** On a phone or a narrow window, a cell folds into the row's first. */
const WIDE = "hidden lg:table-cell";

/**
 * A cycle's Player Nominations (#470), for its running staff to review: each one in
 * a submitted downtime with who wrote it, to remove (with a reason only staff see),
 * star for the footer, or lightly edit; and Publish once the cycle is past Due, then
 * Publish more for those written since.
 */
export function NominationsReview({ cycle }: { cycle: CycleOut }) {
  const key = ["cycle-nominations", cycle.id];
  const found = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/api/cycles/{cycle_id}/nominations", { params: { path: { cycle_id: cycle.id } } })),
  });
  if (found.isPending) return <Loading />;
  if (found.error) return <ErrorText error={found.error} />;
  const n = found.data;
  return (
    <div className="flex flex-col gap-6">
      <PublishCard cycle={cycle} found={n} />
      {n.nominations.length === 0 ? (
        <Empty>No nominations yet. They show here once a player submits their downtime.</Empty>
      ) : (
        <Card title="Nominations">
          <table aria-label="Player Nominations" className="w-full text-sm">
            <thead className="max-lg:sr-only">
              <tr className="border-b border-ash text-left text-xs text-mist">
                <th className="py-2 pr-3 font-normal">Nomination</th>
                <th className={`${WIDE} py-2 pr-3 font-normal`}>Written by</th>
                <th className="py-2 font-normal">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ash">
              {n.nominations.map((r) => (
                <Row key={r.id} cycleId={cycle.id} row={r} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

/** The counts, and Publish: once the cycle is past Due, once only, then Publish more for any written since. */
function PublishCard({ cycle, found: n }: { cycle: CycleOut; found: CycleNominationsOut }) {
  const dates = useDates();
  const toast = useToast();
  const publish = useAction(() => unwrap(api.POST("/api/cycles/{cycle_id}/nominations/publish", { params: { path: { cycle_id: cycle.id } } })));
  const published = n.published_at !== null && n.published_at !== undefined;
  const press = () =>
    publish.mutate(undefined, {
      onSuccess: (done) => toast({ message: `Published ${plural(done.count, "nomination", "nominations")}.` }),
    });
  return (
    <Card title="Player Nominations">
      <p className="text-sm">
        {n.written} written · {n.removed} removed · {n.starred} starred
      </p>
      <p className="mt-1 text-sm text-mist">
        Players never see who wrote them. Removed ones are kept here, and can be put back. Starred ones rotate at the foot of the troupe’s pages once published.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        {!published ? (
          <>
            <Button disabled={!n.past_due || n.waiting === 0 || publish.isPending} onClick={press}>
              Publish nominations
            </Button>
            <span className="text-sm text-mist">
              {!n.past_due
                ? `They can be published once the cycle is past Due, ${dates.due(cycle.closes_at)}.`
                : n.waiting === 0
                  ? "There are none to publish yet."
                  : `Publishes ${plural(n.waiting, "nomination", "nominations")} to the troupe’s players, shuffled and without names, and tells them.`}
            </span>
          </>
        ) : (
          <>
            <Badge tone="gold">Published {dates.dateTime(n.published_at!)}</Badge>
            {n.waiting > 0 && (
              <Button variant="secondary" disabled={publish.isPending} onClick={press}>
                Publish {n.waiting} more
              </Button>
            )}
            {n.waiting > 0 && <span className="text-sm text-mist">Written since they were published.</span>}
          </>
        )}
      </div>
      <ErrorText error={publish.error} />
    </Card>
  );
}

function Row({ cycleId, row: r }: { cycleId: string; row: ReviewedOut }) {
  const client = useQueryClient();
  const [open, setOpen] = useState<"edit" | "remove" | null>(null);
  const close = () => setOpen(null);
  // Each change answers with the whole tab, so the counts move with it.
  const done = (found: CycleNominationsOut) => client.setQueryData(["cycle-nominations", cycleId], found);
  const path = { params: { path: { nomination_id: r.id } } };
  const star = useAction((starred: boolean) => unwrap(api.PUT("/api/nominations/{nomination_id}/star", { ...path, body: { starred } })));
  const restore = useAction(() => unwrap(api.POST("/api/nominations/{nomination_id}/restore", path)));
  const author = `${r.character_name} (${r.player_name})`;
  const badges = (
    <>
      {r.removed && <Badge tone="blood">Removed</Badge>}
      {r.starred && <Badge tone="gold">★ Starred</Badge>}
      {r.edited && <Badge>Edited by staff</Badge>}
      {r.published && <Badge>Published</Badge>}
    </>
  );
  return (
    <tr className={r.removed ? "text-mist" : undefined}>
      <td className="py-2.5 pr-3 align-top">
        <p className={r.removed ? "whitespace-pre-line wrap-anywhere line-through decoration-mist/60" : "whitespace-pre-line wrap-anywhere"}>{r.text}</p>
        <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-mist">
          {r.about && <span className="mr-1">About {r.about.name}</span>}
          {badges}
        </p>
        {r.removed && r.removed_reason && <p className="mt-1 text-xs text-mist">Why: {r.removed_reason}</p>}
        <p className="mt-1 text-xs text-mist lg:hidden">By {author}</p>
        <ErrorText error={star.error ?? restore.error} />
      </td>
      <td className={`${WIDE} py-2.5 pr-3 align-top text-mist`}>
        {r.character_name}
        <span className="block text-xs">
          {r.player_name} @{r.player_handle}
        </span>
      </td>
      <td className="w-px py-1 text-right align-top">
        <ActionMenu label={`Actions for “${excerpt(r.text)}”`} variant="ghost">
          <MenuGroup label="Review">
            <MenuItem onSelect={() => star.mutate(!r.starred, { onSuccess: done })}>{r.starred ? "Unstar" : "Star"}</MenuItem>
            <MenuItem onSelect={() => setOpen("edit")}>Edit…</MenuItem>
          </MenuGroup>
          <MenuGroup label="Remove">
            {r.removed ? (
              <MenuItem onSelect={() => restore.mutate(undefined, { onSuccess: done })}>Put back</MenuItem>
            ) : (
              <MenuItem onSelect={() => setOpen("remove")}>Remove…</MenuItem>
            )}
          </MenuGroup>
        </ActionMenu>
        <Dialog title="Edit the nomination" open={open === "edit"} onClose={close}>
          <EditForm row={r} onDone={(found) => (done(found), close())} />
        </Dialog>
        <Dialog title="Remove the nomination" open={open === "remove"} onClose={close}>
          <RemoveForm row={r} onDone={(found) => (done(found), close())} />
        </Dialog>
      </td>
    </tr>
  );
}

function EditForm({ row: r, onDone }: { row: ReviewedOut; onDone: (found: CycleNominationsOut) => void }) {
  const [text, setText] = useState(r.text);
  const save = useAction(() => unwrap(api.PUT("/api/nominations/{nomination_id}/text", { params: { path: { nomination_id: r.id } }, body: { text } })));
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <Field label="Nomination" hint="A light edit, such as a typo, or a real name the player asked to keep private. It's marked as edited by staff.">
        <Textarea rows={5} maxLength={1000} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div>
        <Button type="submit" disabled={save.isPending || !text.trim()}>
          Save
        </Button>
      </div>
    </form>
  );
}

function RemoveForm({ row: r, onDone }: { row: ReviewedOut; onDone: (found: CycleNominationsOut) => void }) {
  const [reason, setReason] = useState("");
  const remove = useAction(() => unwrap(api.POST("/api/nominations/{nomination_id}/remove", { params: { path: { nomination_id: r.id } }, body: { reason } })));
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        remove.mutate(undefined, { onSuccess: onDone });
      }}
    >
      <p className="text-sm whitespace-pre-line wrap-anywhere">{r.text}</p>
      <p className="text-sm text-mist">
        {r.published ? "It's published: removing it takes it away from the troupe's players at once." : "It won't be published."} It's kept here, and can be put back.
      </p>
      <Field label="Reason (optional)" hint="Only staff see it.">
        <Input value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={remove.error} />
      <div>
        <Button type="submit" variant="danger" disabled={remove.isPending}>
          Remove
        </Button>
      </div>
    </form>
  );
}
