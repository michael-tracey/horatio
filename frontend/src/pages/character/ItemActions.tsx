import { useState } from "react";
import type { EquipmentItemOut, EquipmentReceiverOut } from "../../api/types";
import { CharacterPicker } from "../../components/CharacterPicker";
import { Button, ErrorText, Field, Input } from "../../components/ui";

/**
 * Give and Discard at an item's foot (#282), for the holder's player and its home
 * troupe's staff: give it to another character of the home troupe, picked as a
 * status's patron is (PCs, and NPCs holding a title there), or discard it with a
 * note. Each happens at once; the caller says how (a request, or a Play View tap).
 */
export function ItemActions({
  item,
  receivers,
  give,
  discard,
}: {
  item: EquipmentItemOut;
  receivers: EquipmentReceiverOut[];
  give: (to: EquipmentReceiverOut, note: string) => Promise<unknown> | void;
  discard: (note: string) => Promise<unknown> | void;
}) {
  const [doing, setDoing] = useState<"" | "give" | "discard">("");
  const done = () => setDoing("");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onClick={() => setDoing(doing === "give" ? "" : "give")}>
          Give
        </Button>
        <Button variant="ghost" onClick={() => setDoing(doing === "discard" ? "" : "discard")}>
          Discard
        </Button>
      </div>
      {/* Keyed, so each opening starts afresh. */}
      {doing === "give" && <GiveForm key="give" item={item} receivers={receivers} give={give} onDone={done} />}
      {doing === "discard" && <DiscardForm key="discard" item={item} discard={discard} onDone={done} />}
    </div>
  );
}

/** Runs an action, keeping whether it is under way and why it failed; `onDone` once it has worked. */
function useRun(onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const run = async (act: () => Promise<unknown> | void) => {
    setBusy(true);
    setError(null);
    try {
      await act();
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

/** Give an item to another character, with an optional note; `onDone` once given, or on Cancel. */
export function GiveForm({
  item,
  receivers,
  give,
  onDone,
}: {
  item: EquipmentItemOut;
  receivers: EquipmentReceiverOut[];
  give: (to: EquipmentReceiverOut, note: string) => Promise<unknown> | void;
  onDone: () => void;
}) {
  const [to, setTo] = useState<EquipmentReceiverOut | null>(null);
  const [note, setNote] = useState("");
  const { busy, error, run } = useRun(onDone);
  return (
    <form
      aria-label={`Give ${item.name}`}
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (to) void run(() => give(to, note));
      }}
    >
      <CharacterPicker
        label="Give it to"
        listLabel="Characters"
        choices={receivers}
        picked={to?.id ?? null}
        onPick={setTo}
        extra={(c) => c.player_name && <span className="shrink-0 text-xs text-mist">{c.player_name}</span>}
      />
      <Field label="Note (optional)">
        <Input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <p className="text-xs text-mist">It goes at once, with its history. {to?.kind === "pc" && to.player_name ? `${to.player_name} is told.` : ""}</p>
      <ErrorText error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={!to || busy}>
          {to ? `Give to ${to.name}` : "Give"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Discard an item, with a note of where it went; `onDone` once discarded, or on Cancel. */
export function DiscardForm({ item, discard, onDone }: { item: EquipmentItemOut; discard: (note: string) => Promise<unknown> | void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const { busy, error, run } = useRun(onDone);
  return (
    <form
      aria-label={`Discard ${item.name}`}
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        void run(() => discard(note));
      }}
    >
      <Field label="Where it went (optional)" hint="Your storytellers keep it, and can give it back if this was a mistake.">
        <Input value={note} maxLength={300} placeholder="Lost in the river" onChange={(e) => setNote(e.target.value)} />
      </Field>
      <ErrorText error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="danger" disabled={busy}>
          Discard {item.name}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
