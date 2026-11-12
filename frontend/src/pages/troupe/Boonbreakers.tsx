import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BoonbreakerOut, CharacterChoice } from "../../api/types";
import { appealText, BREAKER_PAGE, kindName, owes, voidsText } from "../../boons";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Loading, Select } from "../../components/ui";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

/**
 * Boonbreakers (#717; MET: VTM pp. 397-398), for the troupe's running staff and a
 * Harpy with the full ledger: declare someone a Boonbreaker, seeing first which of
 * their boons it makes void; record each appeal for mercy; and on mercy, choose which
 * voided boons stand again.
 */
export function Boonbreakers({ troupeId, characters }: { troupeId: string; characters: CharacterChoice[] }) {
  const [declaring, setDeclaring] = useState(false);
  const marks = useQuery({
    queryKey: ["boonbreakers", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/boonbreakers", { params: { path: { troupe_id: troupeId } } })),
  });
  const standing = marks.data?.marks.filter((m) => !m.lifted_at) ?? [];
  const lifted = marks.data?.marks.filter((m) => m.lifted_at) ?? [];
  return (
    <Card
      title="Boonbreakers"
      actions={
        !declaring && (
          <Button variant="ghost" onClick={() => setDeclaring(true)}>
            Declare a Boonbreaker
          </Button>
        )
      }
    >
      <p className="text-sm text-mist">
        Someone who refused to pay a boon after the Harpy gave them the chance ({BREAKER_PAGE}). Every open boon they owe or are owed here is made void, and
        they hold Disgraced while the mark stands. Mercy lifts it.
      </p>
      {declaring && <DeclareForm troupeId={troupeId} characters={characters} onDone={() => setDeclaring(false)} />}
      {marks.isPending ? (
        <Loading />
      ) : marks.error ? (
        <ErrorText error={marks.error} />
      ) : standing.length === 0 && lifted.length === 0 ? (
        !declaring && <Empty>No Boonbreakers.</Empty>
      ) : (
        <ul aria-label="Boonbreakers" className="mt-3 flex flex-col gap-2">
          {[...standing, ...lifted].map((m) => (
            <Mark key={m.id} troupeId={troupeId} mark={m} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function DeclareForm({ troupeId, characters, onDone }: { troupeId: string; characters: CharacterChoice[]; onDone: () => void }) {
  const [characterId, setCharacterId] = useState("");
  const [refused, setRefused] = useState("");
  const [note, setNote] = useState("");
  const preview = useQuery({
    queryKey: ["boonbreaker-preview", troupeId, characterId],
    queryFn: () =>
      unwrap(
        api.GET("/api/troupes/{troupe_id}/boonbreakers/preview", {
          params: { path: { troupe_id: troupeId }, query: { character_id: characterId } },
        }),
      ),
    enabled: Boolean(characterId),
  });
  const owedByThem = preview.data?.boons.filter((b) => b.debtor.character_id === characterId) ?? [];
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/boonbreakers", {
        params: { path: { troupe_id: troupeId } },
        body: { character_id: characterId, note, refused_boon_id: refused || null },
      }),
    );
    onDone();
  });
  return (
    <form
      aria-label="Declare a Boonbreaker"
      className="mt-3 flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Field label="Who">
        <Select
          value={characterId}
          onChange={(e) => {
            setCharacterId(e.target.value);
            setRefused("");
          }}
        >
          <option value="">Choose a character</option>
          {characters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
      {characterId &&
        (preview.isPending ? (
          <Loading />
        ) : preview.error ? (
          <ErrorText error={preview.error} />
        ) : (
          <>
            <p role="status" className="text-sm text-parchment">
              {voidsText(preview.data)}
            </p>
            {preview.data.boons.length > 0 && (
              <ul aria-label="Boons it makes void" className="ml-4 list-disc text-xs text-mist">
                {preview.data.boons.map((b) => (
                  <li key={b.id}>
                    {owes(b)}, {kindName(b.kind).toLowerCase()}
                    {b.reason && `: ${b.reason}`}
                  </li>
                ))}
              </ul>
            )}
            {owedByThem.length > 0 && (
              <Field label="The boon they refused (optional)">
                <Select value={refused} onChange={(e) => setRefused(e.target.value)}>
                  <option value="">Not in the ledger</option>
                  {owedByThem.map((b) => (
                    <option key={b.id} value={b.id}>
                      {owes(b)}, {kindName(b.kind).toLowerCase()}
                      {b.reason && `: ${b.reason}`}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
          </>
        ))}
      <Field label="What they refused, and when" hint="It goes in the log of every boon this makes void.">
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="danger" disabled={save.isPending || !characterId || !note.trim() || preview.isPending}>
          Declare them a Boonbreaker
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Mark({ troupeId, mark }: { troupeId: string; mark: BoonbreakerOut }) {
  const dates = useDates();
  const [appealing, setAppealing] = useState(false);
  const standing = !mark.lifted_at;
  return (
    <li aria-label={`${mark.character.name}, Boonbreaker`} className="rounded-lg border border-ash bg-dusk p-3 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p>
            <span className="text-parchment">{mark.character.name}</span>
            <span className="text-mist">
              {" "}
              · declared {dates.dateTime(mark.declared_at)}
              {mark.declared_as && ` by ${mark.declared_as}`}
            </span>
          </p>
          <p className="text-mist">{mark.note}</p>
          {mark.refused && (
            <p className="text-xs text-mist">
              Refused: {owes(mark.refused)}, {kindName(mark.refused.kind).toLowerCase()}
            </p>
          )}
          <p className="text-xs text-mist">
            {mark.voided.length} {mark.voided.length === 1 ? "boon" : "boons"} made void
            {mark.restored.length > 0 && `, ${mark.restored.length} restored`}
            {mark.disgraced ? " · holds Disgraced for it" : standing ? " · holds no status, so no Disgraced" : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {standing ? <Badge tone="blood">Boonbreaker</Badge> : <Badge>Mercy</Badge>}
          {standing && !appealing && (
            <Button variant="ghost" onClick={() => setAppealing(true)}>
              Record an appeal
            </Button>
          )}
        </div>
      </div>
      {mark.appeals.length > 0 && (
        <ol aria-label={`Appeals of ${mark.character.name}`} className="mt-2 flex flex-col gap-1 text-xs">
          {mark.appeals.map((a, i) => (
            <li key={i}>
              <span className="text-parchment">{appealText(a)}</span>
              <span className="text-mist"> · {dates.day(a.on)}</span>
              {a.note && <span> · {a.note}</span>}
              {a.follows && <span className="block text-mist">{a.follows}</span>}
            </li>
          ))}
        </ol>
      )}
      {mark.lifted_at && (
        <p className="mt-2 text-xs text-mist">
          Lifted {dates.dateTime(mark.lifted_at)}
          {mark.lifted_note && `: ${mark.lifted_note}`}
        </p>
      )}
      {appealing && <AppealForm troupeId={troupeId} mark={mark} onDone={() => setAppealing(false)} />}
    </li>
  );
}

function AppealForm({ troupeId, mark, onDone }: { troupeId: string; mark: BoonbreakerOut; onDone: () => void }) {
  const [to, setTo] = useState<"harpy" | "court">("harpy");
  const [outcome, setOutcome] = useState<"granted" | "refused">("refused");
  const [against, setAgainst] = useState("");
  const [note, setNote] = useState("");
  const voided = mark.voided.filter((b) => b.state === "void");
  const [restore, setRestore] = useState<string[]>([]);
  const votes = against.trim() === "" ? null : Number(against);
  const save = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/boonbreakers/{mark_id}/appeals", {
        params: { path: { troupe_id: troupeId, mark_id: mark.id } },
        body: { to, outcome, note, against: to === "court" ? votes : null, restore: outcome === "granted" ? restore : [] },
      }),
    );
    onDone();
  });
  const votesOk = to !== "court" || votes === null || (Number.isInteger(votes) && votes >= 0 && votes <= 13);
  return (
    <form
      aria-label={`Appeal of ${mark.character.name}`}
      className="mt-3 flex flex-col gap-3 rounded-md border border-ash p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="To">
          <Select value={to} onChange={(e) => setTo(e.target.value as "harpy" | "court")}>
            <option value="harpy">The Harpy</option>
            <option value="court">A court of Harpies (7 to 13)</option>
          </Select>
        </Field>
        <Field label="Outcome">
          <Select value={outcome} onChange={(e) => setOutcome(e.target.value as "granted" | "refused")}>
            <option value="refused">Mercy refused</option>
            <option value="granted">Mercy granted: lift the mark</option>
          </Select>
        </Field>
      </div>
      {to === "court" && (
        <Field label="Votes against them (optional)" hint="Upheld, each vote against adds six months (p. 398).">
          <Input inputMode="numeric" value={against} onChange={(e) => setAgainst(e.target.value)} />
        </Field>
      )}
      <Field label="Note (optional)">
        <Input maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      {outcome === "granted" && voided.length > 0 && (
        <fieldset className="flex flex-col gap-1 text-sm">
          <legend className="mb-1 text-mist">The book doesn&apos;t say the voided boons come back. Restore any?</legend>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={restore.length === voided.length}
              onChange={(e) => setRestore(e.target.checked ? voided.map((b) => b.id) : [])}
            />
            <span>All of them</span>
          </label>
          {voided.map((b) => (
            <label key={b.id} className="ml-4 flex items-center gap-2">
              <input
                type="checkbox"
                checked={restore.includes(b.id)}
                onChange={(e) => setRestore(e.target.checked ? [...restore, b.id] : restore.filter((r) => r !== b.id))}
              />
              <span>
                {owes(b)}, {kindName(b.kind).toLowerCase()}
              </span>
            </label>
          ))}
        </fieldset>
      )}
      <ErrorText error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending || !votesOk}>
          Record the appeal
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
