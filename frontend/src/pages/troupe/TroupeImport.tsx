import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeEntryOut, TroupeImportOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Button, Card, ErrorText, Input, Loading, Notice } from "../../components/ui";
import { useAction } from "../../hooks";
import { asForm, ReviewParts } from "../character/Backup";
import { OUTCOMES, importSummary, outcomeText } from "../character/backup";

/** What staff chose for one character file, as the server takes it. */
type Decision = { choice?: "skip" | "replace" | "copy"; player?: string; carried_xp?: number };

const MATCHED: Record<NonNullable<TroupeEntryOut["matched_by"]>, string> = {
  email: "Found by the email in the file.",
  handle: "Found by the handle in the file.",
  chosen: "As you chose.",
};

/**
 * Import characters and NPCs (#567), from the troupe's character list: a troupe's
 * export (a .zip) or character files, reviewed first. NPCs come in as the troupe's;
 * player characters go to their players, found by the email or handle in the file
 * (or as staff choose), or are held as NPCs to give later. One with the name of a
 * character here waits for staff to skip it, replace it or add a copy.
 */
export function TroupeImportPage({ troupeId }: { troupeId: string }) {
  const [files, setFiles] = useState<File[]>([]);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [done, setDone] = useState<TroupeImportOut | null>(null);
  const toast = useToast();
  const path = { params: { path: { troupe_id: troupeId } } };
  const form = () => {
    const body = new FormData();
    for (const file of files) body.append("files", file);
    body.append("decisions", JSON.stringify(decisions));
    return body;
  };
  const review = useQuery({
    queryKey: ["troupe-import", troupeId, files.map((f) => `${f.name}:${f.size}:${f.lastModified}`).join("|"), JSON.stringify(decisions)],
    queryFn: () => unwrap(api.POST("/api/troupes/{troupe_id}/character-imports/review", { ...path, body: form() as never, ...asForm })),
    enabled: files.length > 0 && !done,
    placeholderData: (previous) => previous,
    retry: false,
    staleTime: Infinity,
  });
  const apply = useAction(() => unwrap(api.POST("/api/troupes/{troupe_id}/character-imports", { ...path, body: form() as never, ...asForm })), [["roster", troupeId]]);
  const decide = (key: string, change: Decision) => setDecisions((d) => ({ ...d, [key]: { ...d[key], ...change } }));
  const back = (
    <Link to={`/troupes/${troupeId}/characters`} className="underline hover:text-parchment">
      Back to the characters
    </Link>
  );

  if (done) {
    return (
      <Card title="Imported">
        <div className="flex flex-col gap-3 text-sm">
          <p role="status">{importSummary(done.entries)}.</p>
          <ul className="divide-y divide-ash">
            {done.entries.map((e) => (
              <li key={e.key} className="flex flex-wrap items-center justify-between gap-2 py-2">
                {e.character_id ? (
                  <Link to={`/characters/${e.character_id}`} className="text-parchment underline hover:text-gold">
                    {e.name}
                  </Link>
                ) : (
                  <span className="text-mist">{e.name ?? e.key}</span>
                )}
                <span className="text-xs text-mist">{outcomeText(e, done.can_give)}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-mist">{back}</p>
        </div>
      </Card>
    );
  }

  const found = review.data;
  const waiting = found?.entries.filter((e) => e.outcome === "undecided") ?? [];
  const coming = found?.entries.filter((e) => ["new", "given", "held", "replaced"].includes(e.outcome)) ?? [];
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <Card title="Import characters and NPCs">
        <div className="flex flex-col gap-3">
          <p className="text-sm text-mist">
            Bring in a troupe's export from Horatio (a .zip), or character files. NPCs come in as the troupe's. Player characters go to their players, found by the email or handle in
            the file, or are held as NPCs to give later. Nothing is saved until you import.
          </p>
          <ChooseFiles
            files={files}
            onChoose={(chosen) => {
              setDecisions({});
              setFiles(chosen);
            }}
          />
          <p className="text-xs text-mist">{back}</p>
        </div>
      </Card>
      {files.length > 0 && review.error && <ErrorText error={review.error} />}
      {files.length > 0 && !found && !review.error && <Loading label="Reading the files…" />}
      {found && (
        <Card title="Review">
          <div className={`flex flex-col gap-4 ${review.isFetching ? "opacity-60" : ""}`} aria-busy={review.isFetching}>
            {!found.can_give && <Notice>Storytellers give player characters to their players, so each one here is held as an NPC for them to give.</Notice>}
            <ul className="flex flex-col gap-3" aria-label="Characters to import">
              {found.entries.map((entry) => (
                <EntryCard key={entry.key} entry={entry} canGive={found.can_give} decision={decisions[entry.key] ?? {}} onDecide={(change) => decide(entry.key, change)} />
              ))}
            </ul>
            <div className="flex flex-col gap-2 border-t border-ash pt-4">
              <p className="text-sm" role="status">
                {importSummary(found.entries)}.
              </p>
              {waiting.length > 0 && <p className="text-xs text-blood-bright">Choose what to do with {waiting.map((e) => e.name).join(", ")} first.</p>}
              <ErrorText error={apply.error} />
              <div>
                <Button
                  disabled={apply.isPending || review.isFetching || waiting.length > 0 || coming.length === 0}
                  onClick={() =>
                    apply.mutate(undefined, {
                      onSuccess: (result) => {
                        toast({ message: `Imported ${importSummary(result.entries)}` });
                        setDone(result);
                      },
                    })
                  }
                >
                  {apply.isPending ? "Importing…" : `Import ${coming.length} ${coming.length === 1 ? "character" : "characters"}`}
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

function ChooseFiles({ files, onChoose }: { files: File[]; onChoose: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <input
        ref={input}
        type="file"
        multiple
        accept=".zip,application/zip,.json,application/json"
        aria-label="Files to import"
        className="sr-only"
        onChange={(e) => {
          const chosen = [...(e.target.files ?? [])];
          e.target.value = "";
          if (chosen.length) onChoose(chosen);
        }}
      />
      <Button variant="secondary" onClick={() => input.current?.click()}>
        {files.length ? "Choose other files…" : "Choose files…"}
      </Button>
      {files.length > 0 && <span className="min-w-0 break-words text-sm text-mist">{files.map((f) => f.name).join(", ")}</span>}
    </div>
  );
}

function EntryCard({ entry, canGive, decision, onDecide }: { entry: TroupeEntryOut; canGive: boolean; decision: Decision; onDecide: (change: Decision) => void }) {
  const name = entry.name ?? entry.key;
  const outcome = OUTCOMES[entry.outcome];
  const readable = entry.name !== null;
  return (
    <li className="rounded-lg border border-ash p-3 text-sm" aria-label={name}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="break-words text-parchment">{name}</span>
          {entry.kind && <Badge>{entry.kind === "pc" ? "Player character" : "NPC"}</Badge>}
        </span>
        <Badge tone={outcome.tone}>{outcome.label}</Badge>
      </div>
      <p className={`mt-1 text-xs ${entry.outcome === "cannot" || entry.outcome === "undecided" ? "text-blood-bright" : "text-mist"}`}>{outcomeText(entry, canGive)}</p>
      {entry.retired && <p className="mt-1 text-xs text-mist">Retired where it came from: it comes in retired.</p>}
      {readable && entry.kind === "pc" && canGive && <PlayerChoice entry={entry} decision={decision} onDecide={onDecide} />}
      {entry.outcome === "given" && (
        <label className="mt-2 flex flex-wrap items-center gap-2 text-xs text-mist">
          Unspent XP to carry over
          <Input
            type="number"
            min={0}
            className="h-8 w-24"
            defaultValue={decision.carried_xp ?? entry.carried_xp}
            onBlur={(e) => {
              const value = Math.max(0, Math.floor(Number(e.target.value) || 0));
              if (value !== (decision.carried_xp ?? entry.carried_xp)) onDecide({ carried_xp: value });
            }}
          />
          <span>{entry.unspent} unspent in the file</span>
        </label>
      )}
      {entry.duplicate && (
        <fieldset className="mt-2 flex flex-col gap-1">
          <legend className="text-xs text-mist">
            Already here: {entry.duplicate.name}, {entry.duplicate.whose}
          </legend>
          {(
            [
              ["skip", "Skip it"],
              ...(entry.can_replace ? [["replace", "Replace it"] as const] : []),
              ["copy", "Add a copy"],
            ] as const
          ).map(([choice, label]) => (
            <label key={choice} className="flex items-center gap-2 text-sm">
              <input type="radio" name={`choice-${entry.key}`} checked={(decision.choice ?? entry.choice) === choice} onChange={() => onDecide({ choice })} />
              {label}
            </label>
          ))}
        </fieldset>
      )}
      {entry.review && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-mist hover:text-parchment">What comes in</summary>
          <div className="mt-2 flex flex-col gap-3">
            {entry.review.warnings.map((w) => (
              <Notice key={w}>{w}</Notice>
            ))}
            {entry.review.xp && (
              <p className="text-xs text-mist">
                XP in the file: {entry.review.xp.earned} earned, {entry.review.xp.spent} spent, {entry.unspent} unspent. Its sheet cost {entry.review.xp.sheet_there} there and
                costs {entry.review.xp.sheet_here} at this troupe's prices.
              </p>
            )}
            <ReviewParts review={entry.review} />
          </div>
        </details>
      )}
    </li>
  );
}

/** Whom a player character goes to: the player found, another by handle, or no one yet. */
function PlayerChoice({ entry, decision, onDecide }: { entry: TroupeEntryOut; decision: Decision; onDecide: (change: Decision) => void }) {
  const current = decision.player ?? entry.player?.handle ?? "";
  const note = entry.player && entry.matched_by ? MATCHED[entry.matched_by] : entry.file_player ? `The file names ${entry.file_player}, who isn't found here.` : "The file names no player.";
  return (
    <div className="mt-2 flex flex-col gap-1">
      <label className="flex flex-wrap items-center gap-2 text-xs text-mist">
        Give to
        <Input
          className="h-8 w-48"
          defaultValue={current}
          placeholder="Hold as an NPC"
          aria-label={`Player for ${entry.name}`}
          onBlur={(e) => {
            const value = e.target.value.trim().replace(/^@/, "");
            if (value !== current) onDecide({ player: value });
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
      </label>
      <p className="text-xs text-mist">{note} Leave it empty to hold it as an NPC and give it later.</p>
    </div>
  );
}
