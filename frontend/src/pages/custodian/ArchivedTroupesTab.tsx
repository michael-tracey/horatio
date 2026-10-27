import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { Dialog } from "../../components/Dialog";
import { Badge, Button, Card, Empty, ErrorText, Field, Loading, Notice, Textarea } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

type ArchivedTroupe = components["schemas"]["ArchivedTroupeOut"];
type ArchivedCharacter = components["schemas"]["ArchivedCharacter"];

/**
 * Troupes that have been archived, latest first: when, by whom and why, and the
 * characters each had then. Each can be read (its page and log stay open to the
 * custodian) and reopened. One archived before archiving settled its characters
 * can be settled here.
 */
export function ArchivedTroupesTab() {
  const troupes = useQuery({ queryKey: ["archived-troupes"], queryFn: () => unwrap(api.GET("/api/troupes/archived")) });
  if (troupes.isPending) return <Loading />;
  if (troupes.error) return <ErrorText error={troupes.error} />;
  if (!troupes.data.length) return <Empty>No troupe is archived.</Empty>;
  return (
    <ul className="flex flex-col gap-4" aria-label="Archived troupes">
      {troupes.data.map((t) => (
        <ArchivedCard key={t.id} troupe={t} />
      ))}
    </ul>
  );
}

function ArchivedCard({ troupe: t }: { troupe: ArchivedTroupe }) {
  const dates = useDates();
  const [acting, setActing] = useState<"reopen" | "settle" | null>(null);
  const home = t.characters.filter((c) => c.kind === "pc" && c.home);
  const visiting = t.characters.filter((c) => c.kind === "pc" && !c.home);
  const npcs = t.characters.filter((c) => c.kind === "npc");

  return (
    <li>
      <Card
        title={t.name}
        actions={
          <div className="flex flex-wrap gap-2">
            <Link to={`/troupes/${t.id}`} className="inline-flex min-h-10 items-center px-2 text-sm text-gold hover:underline">
              Open
            </Link>
            <Link to={`/troupes/${t.id}/log`} className="inline-flex min-h-10 items-center px-2 text-sm text-gold hover:underline">
              Log
            </Link>
            {t.unsettled && (
              <Button variant="secondary" onClick={() => setActing("settle")}>
                Settle…
              </Button>
            )}
            <Button variant="secondary" onClick={() => setActing("reopen")}>
              Reopen…
            </Button>
          </div>
        }
      >
        <div className="flex flex-col gap-3 text-sm">
          <p className="text-mist">
            Archived {dates.dateTime(t.archived_at)}
            {t.archived_by_id && t.archived_by_name && (
              <>
                {" by "}
                <Link to={`/players/${t.archived_by_id}`} className="text-gold hover:underline">
                  {t.archived_by_name}
                </Link>
              </>
            )}
            . Lead storyteller: {t.lead_name}.
          </p>
          {t.reason && (
            <p className="border-l-2 border-ash pl-3 whitespace-pre-line">
              <span className="sr-only">Reason: </span>
              {t.reason}
            </p>
          )}
          {t.unsettled && (
            <Notice>
              Archived before archiving settled its characters: some are still in it, with nowhere to ask for approvals or downtimes. Settle it to let them go.
            </Notice>
          )}
          <Characters title="Home to" characters={home} />
          <Characters title="Visiting" characters={visiting} />
          <Characters title="NPCs" characters={npcs} />
          {!t.characters.length && <p className="text-mist">It had no characters.</p>}
        </div>
      </Card>
      <Dialog title={acting === "settle" ? `Settle ${t.name}` : `Reopen ${t.name}`} open={acting !== null} onClose={() => setActing(null)}>
        {acting && <Act troupe={t} what={acting} onDone={() => setActing(null)} />}
      </Dialog>
    </li>
  );
}

function Characters({ title, characters }: { title: string; characters: ArchivedCharacter[] }) {
  if (!characters.length) return null;
  return (
    <div>
      <h3 className="text-xs tracking-wide text-mist uppercase">{title}</h3>
      <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
        {characters.map((c) => (
          <li key={c.character_id} className="flex items-center gap-1">
            <Link to={`/characters/${c.character_id}`} className="text-parchment hover:text-gold">
              {c.name}
            </Link>
            {c.kind === "pc" && <span className="text-mist">({c.player_name})</span>}
            {c.kind === "pc" && !c.left && <Badge tone="blood">Still in it</Badge>}
          </li>
        ))}
      </ul>
    </div>
  );
}

const WHAT = {
  reopen: {
    says: "Reopening gives the troupe back to its staff, with its NPCs and history. The characters it let go do not come back: their players are told they can ask it to accept them again.",
    button: "Reopen troupe",
  },
  settle: {
    says: "Settling does what archiving does now: the characters it is home to are left with no home troupe, visits end, an open downtime cycle ends unanswered, and games under way end. Their players are told.",
    button: "Settle troupe",
  },
};

function Act({ troupe, what, onDone }: { troupe: ArchivedTroupe; what: "reopen" | "settle"; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const act = useAction(async () => {
    const options = { params: { path: { troupe_id: troupe.id } }, body: { reason: reason.trim() } };
    if (what === "reopen") await unwrap(api.POST("/api/troupes/{troupe_id}/reopen", options));
    else await unwrap(api.POST("/api/troupes/{troupe_id}/settle", options));
    onDone();
  });
  return (
    <form
      className="flex flex-col gap-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        act.mutate(undefined);
      }}
    >
      <p>{WHAT[what].says}</p>
      <Field label="Reason" hint="Those affected see this, and it goes in the troupe's log.">
        <Textarea rows={2} required maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <ErrorText error={act.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={act.isPending || !reason.trim()}>
          {WHAT[what].button}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
