import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { components } from "../../api/schema";
import { AtHandle, PersonPicker } from "../../components/PersonPicker";
import { useToast } from "../../components/Toast";
import { Button, ErrorText, Field, Input } from "../../components/ui";
import { useAction } from "../../hooks";

type GivePreview = components["schemas"]["GivePreview"];

/** The NPC kinds a player can be given: those players build. */
export const GIVABLE_KINDS = ["vampire", "ghoul"];

/** Whether staff can give this NPC to a player: a finished, sheeted vampire or ghoul. */
export function givable(npc: { kind: string; npc_kind?: string | null; npc_form?: string | null; creation_complete: boolean; status: string }): boolean {
  return npc.kind === "npc" && npc.npc_form === "sheeted" && GIVABLE_KINDS.includes(npc.npc_kind ?? "") && npc.creation_complete && npc.status === "active";
}

/** "Unspent XP to carry over" and its reason. */
function CarriedFields({ xp, reason, onXp, onReason }: { xp: number; reason: string; onXp: (n: number) => void; onReason: (s: string) => void }) {
  return (
    <>
      <Field label="Unspent XP to carry over" hint="What the player had banked elsewhere, given as its own entry. Leave at 0 for none.">
        <Input type="number" min={0} max={10000} value={xp} onChange={(e) => onXp(Math.max(0, Number(e.target.value) || 0))} />
      </Field>
      {xp > 0 && (
        <Field label="Why" hint="Kept with the XP entry.">
          <Input maxLength={500} value={reason} placeholder="Banked in our old records" onChange={(e) => onReason(e.target.value)} />
        </Field>
      )}
    </>
  );
}

/** What giving the NPC does, as a list, from the server's preview. */
function WhatHappens({ preview: p, carried }: { preview: GivePreview; carried: number }) {
  const to = p.to_player ? `@${p.to_player.handle}` : "Whoever claims it";
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      <li>
        It becomes {p.to_player ? `${to}'s` : "their"} character, at home in {p.troupe_name} and already accepted. Its sheet as it stands is its accepted sheet, so later changes go
        through approvals as any new character's do.
      </li>
      <li>
        Its sheet costs {p.xp} XP at {p.troupe_name}'s prices: it gets an “Imported” award of that, spent on the sheet, so nothing is left unspent.
        {carried > 0 && <> Then {carried} XP carried over, as its own entry.</>}
      </li>
      {p.free.length > 0 && <li>Kept as free dots, as the troupe's costs don't price them: {p.free.join(", ")}.</li>}
      {p.retainers.map((r) => (
        <li key={`${r.character_name}/${r.name}`}>
          {r.character_name}'s Retainer {r.name} is no longer linked to it.
        </li>
      ))}
      <li>It leaves the NPCs list, and the Who's Who shows it as a player's character.</li>
    </ul>
  );
}

/**
 * Give a sheeted NPC to someone who has signed up (#481): pick them, add any XP
 * they had banked elsewhere, then confirm what will happen.
 */
export function GiveToPlayer({ npcId, npcName, troupeId, onDone }: { npcId: string; npcName: string; troupeId: string; onDone: () => void }) {
  const [handle, setHandle] = useState("");
  const [xp, setXp] = useState(0);
  const [reason, setReason] = useState("");
  const toast = useToast();
  const path = { params: { path: { character_id: npcId } } };
  const review = useMutation({
    mutationFn: () => unwrap(api.GET("/api/characters/{character_id}/give-to-player", { params: { path: { character_id: npcId }, query: { handle } } })),
  });
  const give = useAction(async () => {
    await unwrap(api.POST("/api/characters/{character_id}/give-to-player", { ...path, body: { handle, carried_xp: xp, carried_reason: reason } }));
    toast({ message: `${npcName} is @${review.data?.to_player?.handle ?? handle}'s now.` });
    onDone();
  });

  if (review.data) {
    const p = review.data;
    return (
      <div className="flex flex-col gap-3 text-sm">
        <p>
          Give <strong>{p.character_name}</strong> to {p.to_player?.display_name} {p.to_player && <AtHandle handle={p.to_player.handle} />}?
        </p>
        <WhatHappens preview={p} carried={xp} />
        <p className="text-mist">They're told, and it's in the troupe's log.</p>
        <ErrorText error={p.refusal} />
        <ErrorText error={give.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => review.reset()}>
            Back
          </Button>
          <Button type="button" disabled={!!p.refusal || give.isPending} onClick={() => give.mutate(undefined)}>
            Give {p.character_name} to @{p.to_player?.handle}
          </Button>
        </div>
      </div>
    );
  }
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        review.mutate();
      }}
    >
      <p className="text-sm">It becomes their character, at home here and accepted. They must have signed up.</p>
      <Field label="Player">
        <PersonPicker required value={handle} onChange={setHandle} troupeId={troupeId} staffToo />
      </Field>
      <CarriedFields xp={xp} reason={reason} onXp={setXp} onReason={setReason} />
      <ErrorText error={review.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={review.isPending || !handle.trim()}>
          Continue
        </Button>
      </div>
    </form>
  );
}
