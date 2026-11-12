import { useId, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { BOON_PAGE } from "../../boons";
import { useToast } from "../../components/Toast";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * Whether the troupe keeps a boon ledger (#685): off by default. On, its running staff
 * keep it on the Boons screen. Switched off, it's hidden everywhere; what was
 * registered is kept, and comes back when it is switched on again.
 */
export function BoonLedgerSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const toast = useToast();
  const on = troupe.boons ?? false;
  const save = useAction(async (next: boolean) => {
    await unwrap(
      api.PUT("/api/troupes/{troupe_id}/boon-ledger", {
        params: { path: { troupe_id: troupe.id } },
        body: { on: next },
      }),
    );
    toast({
      message: next
        ? "The boon ledger is on. Staff keep it on the Boons screen, under Characters."
        : "The boon ledger is off. What was registered is kept, for if you switch it back on.",
    });
  });
  return (
    <Card title="Boons">
      <p className="mb-3 text-sm text-mist">
        Whether Horatio keeps the troupe&apos;s boon ledger: the debts characters owe each other, registered with the Harpy ({BOON_PAGE}). A boon made off the
        record isn&apos;t tracked here, and isn&apos;t enforced.
      </p>
      {!canEdit ? (
        <p className="text-sm">{on ? "The troupe keeps a boon ledger." : "The troupe doesn't keep a boon ledger."}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={on} disabled={save.isPending} onChange={(e) => save.mutate(e.target.checked)} />
            <span>
              Keep a boon ledger
              <span className="block text-xs text-mist">
                Storytellers and assistant storytellers register boons, and edit, trade, pass on, settle and void them, each with its own log. Switched off,
                it&apos;s hidden everywhere; what was registered is kept, and comes back if it is switched on again.
              </span>
            </span>
          </label>
          <ErrorText error={save.error} />
          {on && <PlayersSetting troupe={troupe} />}
          {on && <ReviewSetting troupe={troupe} />}
          {on && <HarpySetting troupe={troupe} />}
        </div>
      )}
      {!canEdit && on && <p className="mt-2 text-sm">{PLAYERS_SEE.find((p) => p.value === troupe.boon_players_see)?.summary}</p>}
      {!canEdit && on && troupe.boon_review && <p className="mt-1 text-sm">Boons players report wait for review before they stand.</p>}
      {!canEdit && on && <p className="mt-1 text-sm">{HARPY.find((h) => h.value === (troupe.boon_harpy ?? "none"))?.summary}</p>}
      {!canEdit && on && troupe.boon_harpy === "full" && troupe.boon_harpy_standings && (
        <p className="mt-1 text-sm">The Harpy also reads the boon standings and statistics, with who has left as the court knows it.</p>
      )}
    </Card>
  );
}

type PlayersSee = TroupeOut["boon_players_see"];

/** What players see of the ledger in the Play View's Boons tab (#686), least first. */
const PLAYERS_SEE: { value: NonNullable<PlayersSee>; label: string; hint: string; summary: string }[] = [
  {
    value: "intake",
    label: "The form to report a boon only",
    hint: "Players report boons; they see nothing of the ledger.",
    summary: "Players report boons in the Play View, and see nothing of the ledger.",
  },
  {
    value: "owes",
    label: "Also what they owe",
    hint: "Each player sees the boons their character owes.",
    summary: "Players report boons in the Play View, and see what their characters owe.",
  },
  {
    value: "owed",
    label: "Also what they're owed",
    hint: "Each player sees the boons their character owes and is owed.",
    summary: "Players report boons in the Play View, and see what their characters owe and are owed.",
  },
];

/**
 * The Play View's Boons tab (#686): what players see there, and whether a boon's
 * creditor's player may mark it settled, called in or forgiven. Only the creditor's:
 * a debtor saying "I paid that" is for the Harpy to judge. They settle only boons
 * they see, so it needs "Also what they're owed".
 */
function PlayersSetting({ troupe }: { troupe: TroupeOut }) {
  const toast = useToast();
  const group = useId();
  // Shown as chosen at once, while it saves.
  const [see, setSee] = useState<NonNullable<PlayersSee>>(troupe.boon_players_see ?? "intake");
  const [settle, setSettle] = useState(troupe.boon_players_settle ?? false);
  const save = useAction(async (body: { see: NonNullable<PlayersSee>; settle: boolean }) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-players", { params: { path: { troupe_id: troupe.id } }, body }));
    toast({ message: "Saved what players see of the boon ledger." });
  });
  const choose = (body: { see: NonNullable<PlayersSee>; settle: boolean }) => {
    setSee(body.see);
    setSettle(body.settle);
    save.mutate(body, {
      onError: () => {
        setSee(troupe.boon_players_see ?? "intake");
        setSettle(troupe.boon_players_settle ?? false);
      },
    });
  };
  return (
    <fieldset className="mt-2 flex flex-col gap-2 border-t border-ash/60 pt-3">
      <legend className="text-mist">In the Play View&apos;s Boons tab, players see</legend>
      {PLAYERS_SEE.map((p) => (
        <label key={p.value} className="flex items-start gap-2">
          <input type="radio" className="mt-1" name={group} checked={see === p.value} disabled={save.isPending} onChange={() => choose({ see: p.value, settle })} />
          <span>
            {p.label}
            <span className="block text-xs text-mist">{p.hint}</span>
          </span>
        </label>
      ))}
      <label className="mt-1 flex items-start gap-2">
        <input type="checkbox" className="mt-1" checked={settle} disabled={save.isPending} onChange={(e) => choose({ see, settle: e.target.checked })} />
        <span>
          Players mark boons owed to them settled
          <span className="block text-xs text-mist">
            Only a boon&apos;s creditor&apos;s player, as called in or forgiven, and only where they see what they&apos;re owed
            {see === "owed" ? "." : ": choose “Also what they're owed” for it to take effect."}
          </span>
        </span>
      </label>
      <p className="text-xs text-mist">The Boons tab can also be switched off under Play View tabs.</p>
      <ErrorText error={save.error} />
    </fieldset>
  );
}

/**
 * Whether boons players report wait for review (#687): off, they stand at once.
 * Either way the report is logged, and Horatio flags names that link to no character
 * and likely duplicates for review.
 */
function ReviewSetting({ troupe }: { troupe: TroupeOut }) {
  const toast = useToast();
  // Shown as chosen at once, while it saves.
  const [hold, setHold] = useState(troupe.boon_review ?? false);
  const save = useAction(async (next: boolean) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-review", { params: { path: { troupe_id: troupe.id } }, body: { hold: next } }));
    toast({ message: next ? "Boons players report now wait for review." : "Boons players report now stand at once." });
  });
  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-ash/60 pt-3">
      <label className="flex items-start gap-2">
        <input
          type="checkbox"
          className="mt-1"
          checked={hold}
          disabled={save.isPending}
          onChange={(e) => {
            const next = e.target.checked;
            setHold(next);
            save.mutate(next, { onError: () => setHold(troupe.boon_review ?? false) });
          }}
        />
        <span>
          Boons players report wait for review
          <span className="block text-xs text-mist">
            Staff accept each one, after an edit if it needs one, or don&apos;t accept it, with a reason its player sees. Off, they stand at once. Either way,
            Horatio flags names that link to no character, and likely duplicates, under “To review” on the Boons screen.
          </span>
        </span>
      </label>
      <ErrorText error={save.error} />
    </div>
  );
}

type HarpyAccess = NonNullable<TroupeOut["boon_harpy"]>;

/** How far the Harpy reaches into the ledger (#688), least first. */
const HARPY: { value: HarpyAccess; label: string; hint: string; summary: string }[] = [
  { value: "none", label: "None", hint: "The ledger is staff's alone.", summary: "The ledger is staff's alone; the Harpy has no access to it." },
  {
    value: "submissions",
    label: "Receives submissions",
    hint: "The Harpy reviews what players report, and is told of each one.",
    summary: "The Harpy reviews the boons players report, and is told of each one.",
  },
  {
    value: "full",
    label: "The full ledger",
    hint: "The Harpy registers, edits, trades, passes on and settles boons, and reviews what players report.",
    summary: "The Harpy keeps the full ledger, and reviews the boons players report.",
  },
];

/** What the Harpy is told of who has left (#749), on the setting that lets them read the standings. */
const AS_THE_COURT_KNOWS =
  "They see who has left only as the court knows it: a character the Who's Who lists under No longer with us, and why only when that is Final Death or Off-field. A player stopping (Inactive) is never shown, and a departure the Who's Who doesn't list stays at court. Weights stay yours to set.";

/**
 * The Harpy's access to the ledger (#688): whoever holds the Harpy title in the troupe
 * works it from their Play View, as their character. They never see what an edit
 * changed, nor a boon's staff note; access ends with the title. With the full ledger,
 * the troupe can let them read its boon standings and statistics too (#749).
 */
function HarpySetting({ troupe }: { troupe: TroupeOut }) {
  const toast = useToast();
  const group = useId();
  // Shown as chosen at once, while it saves.
  const [access, setAccess] = useState<HarpyAccess>(troupe.boon_harpy ?? "none");
  const [standings, setStandings] = useState(troupe.boon_harpy_standings ?? false);
  const save = useAction(async (next: HarpyAccess) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-harpy", { params: { path: { troupe_id: troupe.id } }, body: { access: next } }));
    toast({ message: `Saved: ${HARPY.find((h) => h.value === next)?.summary}` });
  });
  const saveStandings = useAction(async (next: boolean) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-harpy", { params: { path: { troupe_id: troupe.id } }, body: { access, standings: next } }));
    toast({ message: next ? "Saved: the Harpy reads the boon standings and statistics." : "Saved: the boon standings and statistics are staff's alone." });
  });
  return (
    <fieldset className="mt-2 flex flex-col gap-2 border-t border-ash/60 pt-3">
      <legend className="text-mist">The Harpy&apos;s access to the ledger</legend>
      {HARPY.map((h) => (
        <label key={h.value} className="flex items-start gap-2">
          <input
            type="radio"
            className="mt-1"
            name={group}
            checked={access === h.value}
            disabled={save.isPending}
            onChange={() => {
              setAccess(h.value);
              save.mutate(h.value, { onError: () => setAccess(troupe.boon_harpy ?? "none") });
            }}
          />
          <span>
            {h.label}
            <span className="block text-xs text-mist">{h.hint}</span>
          </span>
        </label>
      ))}
      {access === "full" && (
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={standings}
            disabled={saveStandings.isPending || save.isPending}
            onChange={(e) => {
              const next = e.target.checked;
              setStandings(next);
              saveStandings.mutate(next, { onError: () => setStandings(!next) });
            }}
          />
          <span>
            The Harpy also reads the boon standings and statistics
            <span className="block text-xs text-mist">{AS_THE_COURT_KNOWS}</span>
          </span>
        </label>
      )}
      <p className="text-xs text-mist">
        The Harpy is whoever holds the Harpy title in the troupe; with several, each has it, and it ends when the title does. They work from their Play
        View&apos;s Boons tab, as their character, and never see what an edit changed or a boon&apos;s staff note; who has left, they see only as the court
        knows it.
      </p>
      <ErrorText error={save.error} />
      <ErrorText error={saveStandings.error} />
    </fieldset>
  );
}
