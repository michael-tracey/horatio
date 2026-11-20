import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { RadioList } from "../../components/RadioList";
import { useToast } from "../../components/Toast";
import { Toggle } from "../../components/Toggle";
import { SettingCard } from "../../components/SettingCard";
import { ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { ApprovalKinds } from "./BoonApproval";
import { approvalSummary } from "./boonApproval";
import { ToldOfReports } from "./BoonReportsTold";
import { TalonsSetting } from "./BoonTalons";
import { SETTINGS } from "./settingsIndex";

/**
 * How the troupe keeps its boon ledger (#685): what players see, review, the Harpy, talons
 * and the ban. In the Boons tab's Settings (#784, #909); the ledger itself is switched on
 * and off in Troupe settings' Features list. Switched off, it's hidden everywhere; what was
 * registered is kept, and comes back when it is switched on again.
 */
export function BoonLedgerSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const on = troupe.boons ?? false;
  return (
    <SettingCard
      setting={SETTINGS.boonLedger}
      state={on ? "On" : "Off"}
      readOnly={!canEdit}
    >
      {!canEdit ? (
        <p className="text-sm">{on ? "The troupe keeps a boon ledger." : "The troupe doesn't keep a boon ledger."}</p>
      ) : (
        on && (
          <div className="flex flex-col gap-2 text-sm">
            <PlayersSetting troupe={troupe} />
            <ReviewSetting troupe={troupe} />
            <HarpySetting troupe={troupe} />
            <TalonsSetting troupe={troupe} />
            <JudgeBanSetting troupe={troupe} />
          </div>
        )
      )}
      {!canEdit && on && <p className="mt-2 text-sm">{PLAYERS_SEE.find((p) => p.value === troupe.boon_players_see)?.summary}</p>}
      {!canEdit && on && troupe.boon_review && (
        <p className="mt-1 text-sm">Boons players report wait for review before they stand. {approvalSummary(troupe.boon_auto_accept ?? [])}</p>
      )}
      {!canEdit && on && troupe.boons_judge_ban && (
        <p className="mt-1 text-sm">The ledger judges the Camarilla&apos;s ban on no boons registered with the Harpy.</p>
      )}
      {!canEdit && on && <p className="mt-1 text-sm">{HARPY.find((h) => h.value === (troupe.boon_harpy ?? "none"))?.summary}</p>}
      {!canEdit && on && troupe.boon_harpy === "full" && troupe.boon_harpy_standings && (
        <p className="mt-1 text-sm">The Harpy also reads the boon standings and statistics, with who has left as the court knows it.</p>
      )}
      {!canEdit && on && troupe.boon_harpy === "full" && troupe.boon_harpy_export && (
        <p className="mt-1 text-sm">The Harpy may export the ledger, as they see it.</p>
      )}
      {!canEdit && on && troupe.boon_talons && troupe.boon_harpy === "full" && (
        <p className="mt-1 text-sm">The Harpy may give others access to the ledger, as {troupe.boon_talon_word ?? "Lesser Harpies"}.</p>
      )}
      {!canEdit && on && troupe.boon_talons && troupe.boon_harpy === "full" && (
        <p className="mt-1 text-sm">
          {troupe.boon_harpy_sees_talons === false ? "What talons change is kept from the Harpy." : "The Harpy sees what their talons change."}
        </p>
      )}
      {on && <ToldOfReports troupeId={troupe.id} as="staff" />}
    </SettingCard>
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
    <div className="mt-2 flex flex-col gap-2 border-t border-ash/60 pt-3">
      <RadioList
        label="In the Play View's Boons tab, players see"
        value={see}
        options={PLAYERS_SEE.map((p) => ({ value: p.value, label: p.label, hint: p.hint }))}
        disabled={save.isPending}
        onChange={(next) => choose({ see: next, settle })}
      />
      <Toggle
        label="Players mark boons owed to them settled"
        hint={
          <>
            Only a boon&apos;s creditor&apos;s player, as called in or forgiven, and only where they see what they&apos;re owed
            {see === "owed" ? "." : ": choose “Also what they're owed” for it to take effect."}
          </>
        }
        checked={settle}
        disabled={save.isPending}
        onChange={(on) => choose({ see, settle: on })}
      />
      <p className="text-xs text-mist">The Boons tab can also be switched off under Play View tabs.</p>
      <ErrorText error={save.error} />
    </div>
  );
}

/**
 * Whether boons players report wait for review (#687): off, they stand at once.
 * Either way the report is logged, and Horatio flags names that link to no character
 * and likely duplicates for review. While they wait, which kinds go straight in all
 * the same (#993), as the To review tab's Approval settings say too.
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
      <Toggle
        label="Boons players report wait for review"
        hint={
          <>
            Staff, or the Harpy given the review queue, accept each one, after an edit if it needs one, or don&apos;t accept it, with a reason its player sees.
            Off, they stand at once. Either way, Horatio flags names that link to no character, and likely duplicates, under “To review” on the Boons screen.
          </>
        }
        checked={hold}
        disabled={save.isPending}
        onChange={(next) => {
          setHold(next);
          save.mutate(next, { onError: () => setHold(troupe.boon_review ?? false) });
        }}
      />
      <ErrorText error={save.error} />
      {hold && (troupe.boon_review ?? false) && (
        <fieldset className="ml-1 flex flex-col gap-1 border-l border-ash/60 pl-3">
          <legend className="text-mist">Boons that go straight in</legend>
          <ApprovalKinds troupeId={troupe.id} kinds={troupe.boon_auto_accept ?? []} />
        </fieldset>
      )}
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
    hint: "This is how the Harpy edits boons: they register, correct, trade, pass on and settle them, and review what players report, from their Play View. Lesser Harpies are set below.",
    summary: "The Harpy keeps the full ledger, and reviews the boons players report.",
  },
];

/** What the Harpy is told of who has left (#749), on the setting that lets them read the standings. */
const AS_THE_COURT_KNOWS =
  "They see who has left only as the court knows it: a character the Who's Who lists under No longer with us, and why only when that is Final Death or Off-field. A player stopping (Inactive) is never shown, and a departure the Who's Who doesn't list stays at court. Lesser Harpies who see the ledger follow it. Weights stay yours to set.";

/** What the Harpy's export holds (#987), on the setting that lets them export. */
const EXPORT_HINT =
  "From the ledger's ⋯ menu, as a CSV file or a spreadsheet, as their character. It holds only what they see on the ledger: no staff notes, no one who entered a boon, no edit history, and who has left only as the court knows it. Each export is logged. They may let a Lesser Harpy export it too.";

/**
 * The Harpy's access to the ledger (#688): whoever holds the Harpy title in the troupe
 * works it from their Play View, as their character. They never see what an edit
 * changed, nor a boon's staff note; access ends with the title. With the full ledger,
 * the troupe can let them read its boon standings and statistics too (#749), and
 * export the ledger as they see it (#987).
 */
function HarpySetting({ troupe }: { troupe: TroupeOut }) {
  const toast = useToast();
  // Shown as chosen at once, while it saves.
  const [access, setAccess] = useState<HarpyAccess>(troupe.boon_harpy ?? "none");
  const [standings, setStandings] = useState(troupe.boon_harpy_standings ?? false);
  const [exports, setExports] = useState(troupe.boon_harpy_export ?? false);
  const save = useAction(async (next: HarpyAccess) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-harpy", { params: { path: { troupe_id: troupe.id } }, body: { access: next } }));
    toast({ message: `Saved: ${HARPY.find((h) => h.value === next)?.summary}` });
  });
  const saveStandings = useAction(async (next: boolean) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-harpy", { params: { path: { troupe_id: troupe.id } }, body: { access, standings: next } }));
    toast({ message: next ? "Saved: the Harpy reads the boon standings and statistics." : "Saved: the boon standings and statistics are staff's alone." });
  });
  const saveExports = useAction(async (next: boolean) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-harpy", { params: { path: { troupe_id: troupe.id } }, body: { access, export: next } }));
    toast({ message: next ? "Saved: the Harpy may export the ledger." : "Saved: only staff export the ledger." });
  });
  return (
    <div className="mt-2 flex flex-col gap-2 border-t border-ash/60 pt-3">
      <RadioList
        label="The Harpy's access to the ledger"
        value={access}
        options={HARPY.map((h) => ({ value: h.value, label: h.label, hint: h.hint }))}
        disabled={save.isPending}
        onChange={(next) => {
          setAccess(next);
          save.mutate(next, { onError: () => setAccess(troupe.boon_harpy ?? "none") });
        }}
      />
      {access === "full" && (
        <Toggle
          label="The Harpy also reads the boon standings and statistics"
          hint={AS_THE_COURT_KNOWS}
          checked={standings}
          disabled={saveStandings.isPending || save.isPending}
          onChange={(next) => {
            setStandings(next);
            saveStandings.mutate(next, { onError: () => setStandings(!next) });
          }}
        />
      )}
      {access === "full" && (
        <Toggle
          label="The Harpy may export the ledger"
          hint={EXPORT_HINT}
          checked={exports}
          disabled={saveExports.isPending || save.isPending}
          onChange={(next) => {
            setExports(next);
            saveExports.mutate(next, { onError: () => setExports(!next) });
          }}
        />
      )}
      <p className="text-xs text-mist">
        The Harpy is whoever holds the Harpy title in the troupe; with several, each has it, and it ends when the title does. They work from their Play
        View&apos;s Boons tab, as their character, and never see what an edit changed or a boon&apos;s staff note; who has left, they see only as the court
        knows it.
      </p>
      <ErrorText error={save.error} />
      <ErrorText error={saveStandings.error} />
      <ErrorText error={saveExports.error} />
    </div>
  );
}

/**
 * Whether the ledger judges the Camarilla's lesser status ban on no boons registered
 * with the Harpy (MET: VTM p. 403, #692). Off by default: a ledger that doesn't yet
 * hold every boon would put the whole court under the ban. Off, staff mark that ban.
 */
function JudgeBanSetting({ troupe }: { troupe: TroupeOut }) {
  const toast = useToast();
  // Shown as chosen at once, while it saves.
  const [on, setOn] = useState(troupe.boons_judge_ban ?? false);
  const save = useAction(async (next: boolean) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/boon-ban", { params: { path: { troupe_id: troupe.id } }, body: { on: next } }));
    toast({
      message: next
        ? "The boon ledger now judges the ban on no boons registered with the Harpy."
        : "Staff mark the ban on no boons registered with the Harpy again.",
    });
  });
  return (
    <div className="mt-2 border-t border-ash/60 pt-3">
      <Toggle
        label={<>Judge &ldquo;No boons registered&rdquo; from the boon ledger</>}
        hint={
          <>
            The Camarilla&apos;s lesser status ban on no boons registered with the Harpy (MET: VTM p. 403) then applies to any member with no boon in the
            ledger, owed or owed to them. Switch it on once the ledger holds every boon, or the whole court comes under the ban. Off, staff mark that ban by
            hand, and a mark always decides it.
          </>
        }
        checked={on}
        disabled={save.isPending}
        onChange={(next) => {
          setOn(next);
          save.mutate(next, { onError: () => setOn(troupe.boons_judge_ban ?? false) });
        }}
      />
      <ErrorText error={save.error} />
    </div>
  );
}
