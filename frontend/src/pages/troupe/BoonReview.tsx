import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { BoonOut, CharacterChoice } from "../../api/types";
import { FLAG_NAMES, flagBody, flagText, kindName, owes, partyName, type BoonFlag } from "../../boons";
import { useToast } from "../../components/Toast";
import { Badge, Button, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

/**
 * The review queue (#687): every boon waiting for review, as its troupe holds the
 * boons its players report, and every boon with a flag raised: a name that links to
 * no character, a likely duplicate, or a flag for a ruling. Each opens as in the
 * ledger, with its review below.
 */
export function BoonReviewQueue({ troupeId, detail }: { troupeId: string; detail: (boonId: string) => ReactNode }) {
  const dates = useDates();
  const [open, setOpen] = useState<string | null>(null);
  const queue = useQuery({
    queryKey: ["boon-review", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boon-review", { params: { path: { troupe_id: troupeId } } })),
  });
  if (queue.isPending) return <Loading />;
  if (queue.error) return <ErrorText error={queue.error} />;
  const { boons } = queue.data;
  if (boons.length === 0) return <Empty>Nothing waits for review, and no boon is flagged.</Empty>;
  return (
    <ul aria-label="Boons to review" className="flex flex-col gap-2">
      {boons.map((boon) => (
        <li key={boon.id} aria-label={`To review: ${owes(boon)}, ${kindName(boon.kind).toLowerCase()}`} className="rounded-lg border border-ash bg-dusk p-3 text-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p>
                <span className="text-parchment">{partyName(boon.debtor)}</span>
                <span className="text-mist"> owes </span>
                <span className="text-parchment">{partyName(boon.creditor)}</span>
                <span className="text-mist"> · </span>
                <span className="text-gold">{kindName(boon.kind)}</span>
                <span className="text-mist"> · {dates.day(boon.made_on)}</span>
              </p>
              {boon.reason && <p className="text-mist">{boon.reason}</p>}
              <ul className="mt-1 flex flex-col gap-0.5 text-xs">
                {(boon.flags ?? []).map((f) => (
                  <li key={f.id} className="text-gold">
                    {flagText(f, boon)}
                  </li>
                ))}
              </ul>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {boon.state === "pending" && <Badge tone="mist">Waits for review</Badge>}
              {(boon.flags ?? []).map((f) => (
                <Badge key={f.id} tone="gold">
                  {FLAG_NAMES[f.kind]}
                </Badge>
              ))}
              <Button variant="ghost" aria-expanded={open === boon.id} onClick={() => setOpen(open === boon.id ? null : boon.id)}>
                {open === boon.id ? "Close" : "Review"}
              </Button>
            </div>
          </div>
          {open === boon.id && detail(boon.id)}
        </li>
      ))}
    </ul>
  );
}

type Doing = "accept" | "reject" | "flag" | null;

/**
 * A boon's review, in its detail (#687): accept or reject it while it waits for
 * review (an edit first, from its own buttons); its flags still raised, each to clear,
 * and a name to link to a character; and a flag to raise by hand for a ruling.
 */
export function ReviewPanel({ troupeId, boon, characters }: { troupeId: string; boon: BoonOut; characters: CharacterChoice[] }) {
  const [doing, setDoing] = useState<Doing>(null);
  const flags = boon.flags ?? [];
  const done = () => setDoing(null);
  return (
    <div className="flex flex-col gap-2" role="group" aria-label="Review">
      {boon.state === "pending" && (
        <p className="text-sm">
          <Badge tone="mist">Waits for review</Badge> <span className="text-mist">Reported by a player. Accept it to make it stand, after an edit if it needs one.</span>
        </p>
      )}
      {flags.length > 0 && (
        <ul aria-label="Flags" className="flex flex-col gap-2">
          {flags.map((f) => (
            <FlagRow key={f.id} troupeId={troupeId} boon={boon} flag={f} characters={characters} />
          ))}
        </ul>
      )}
      {doing === null ? (
        <div className="flex flex-wrap gap-2">
          {boon.state === "pending" && (
            <>
              <Button variant="primary" onClick={() => setDoing("accept")}>
                Accept
              </Button>
              <Button variant="ghost" onClick={() => setDoing("reject")}>
                Don&apos;t accept
              </Button>
            </>
          )}
          {boon.state !== "void" && (
            <Button variant="ghost" onClick={() => setDoing("flag")}>
              Flag for review
            </Button>
          )}
        </div>
      ) : (
        <NoteAction troupeId={troupeId} boon={boon} doing={doing} onDone={done} />
      )}
    </div>
  );
}

const DOING: Record<Exclude<Doing, null>, { label: string; field: string; hint: string; required: boolean; button: string }> = {
  accept: { label: "Accept", field: "Note (optional)", hint: "Goes in its log.", required: false, button: "Accept it" },
  reject: {
    label: "Don't accept",
    field: "Why",
    hint: "The player who reported it sees this. It stays in the ledger as void.",
    required: true,
    button: "Don't accept it",
  },
  flag: { label: "Flag for review", field: "What needs a ruling", hint: "Goes in its log, and it waits in the review queue until the flag is cleared.", required: true, button: "Flag it" },
};

function NoteAction({ troupeId, boon, doing, onDone }: { troupeId: string; boon: BoonOut; doing: Exclude<Doing, null>; onDone: () => void }) {
  const toast = useToast();
  const [note, setNote] = useState("");
  const what = DOING[doing];
  const save = useAction(async () => {
    const path = { params: { path: { troupe_id: troupeId, boon_id: boon.id } } };
    if (doing === "accept") await unwrap(api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/accept", { ...path, body: { note } }));
    else if (doing === "reject") await unwrap(api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/reject", { ...path, body: { reason: note } }));
    else await unwrap(api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/flags", { ...path, body: { note } }));
    toast({ message: doing === "accept" ? `Accepted: ${owes(boon)}.` : doing === "reject" ? `Not accepted: ${owes(boon)}.` : `Flagged: ${owes(boon)}.` });
    onDone();
  });
  return (
    <form
      aria-label={`${what.label}: ${owes(boon)}`}
      className="flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field label={what.field} hint={what.hint}>
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant={doing === "reject" ? "danger" : "primary"} disabled={save.isPending || (what.required && !note.trim())}>
          {what.button}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** A flag still raised: what it says, a way to clear it, and, for a name, a way to link it to a character. */
function FlagRow({ troupeId, boon, flag, characters }: { troupeId: string; boon: BoonOut; flag: BoonFlag; characters: CharacterChoice[] }) {
  const toast = useToast();
  const [linking, setLinking] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [note, setNote] = useState("");
  const [character, setCharacter] = useState("");
  const [everywhere, setEverywhere] = useState(true);
  const name = flag.side === "debtor" ? boon.debtor.name : boon.creditor.name;
  const clear = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/boon-flags/{flag_id}/clear", {
        params: { path: { troupe_id: troupeId, flag_id: flag.id } },
        body: { note },
      }),
    );
    toast({ message: "Flag cleared." });
  });
  const link = useAction(async () => {
    if (!flag.side || !character) return;
    const done = await unwrap(
      api.POST("/api/troupes/{troupe_id}/boons/{boon_id}/link", {
        params: { path: { troupe_id: troupeId, boon_id: boon.id } },
        body: { side: flag.side, character_id: character, everywhere, note },
      }),
    );
    const who = characters.find((c) => c.id === character)?.name ?? "the character";
    toast({ message: `Linked ${name} to ${who} on ${done.linked === 1 ? "1 boon" : `${done.linked} boons`}${done.skipped ? `; ${done.skipped} skipped, where ${who} is the other side` : ""}.` });
  });
  return (
    <li className="rounded-md border border-gold/40 p-2 text-sm">
      <p>
        <Badge tone="gold">{FLAG_NAMES[flag.kind]}</Badge> <span>{flagBody(flag, boon)}</span>
      </p>
      {!linking && !clearing && (
        <div className="mt-2 flex flex-wrap gap-2">
          {flag.kind === "unmatched" && (
            <Button variant="secondary" onClick={() => setLinking(true)}>
              Link to a character
            </Button>
          )}
          <Button variant="ghost" onClick={() => setClearing(true)}>
            Clear the flag
          </Button>
        </div>
      )}
      {linking && (
        <form
          aria-label={`Link ${name} to a character`}
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            link.mutate(undefined);
          }}
        >
          <Field label={`Who ${name} is`}>
            <Select value={character} onChange={(e) => setCharacter(e.target.value)} required>
              <option value="">Choose…</option>
              {characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={everywhere} onChange={(e) => setEverywhere(e.target.checked)} />
            On every boon that names {name}
          </label>
          <Field label="Note (optional)">
            <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <ErrorText error={link.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={link.isPending || !character}>
              Link the name
            </Button>
            <Button type="button" variant="ghost" onClick={() => setLinking(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {clearing && (
        <form
          aria-label={`Clear: ${FLAG_NAMES[flag.kind]}`}
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            clear.mutate(undefined);
          }}
        >
          <Field label="Note (optional)" hint={flag.kind === "unmatched" ? "The name is right as it is: someone from another domain, say." : undefined}>
            <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
          </Field>
          <ErrorText error={clear.error} />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={clear.isPending}>
              Clear it
            </Button>
            <Button type="button" variant="ghost" onClick={() => setClearing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}
