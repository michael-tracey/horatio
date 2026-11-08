import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { RosterEntry } from "../../api/types";
import { ActionMenu, MenuGroup, MenuItem } from "../../components/ActionMenu";
import { Dialog } from "../../components/Dialog";
import { useToast } from "../../components/Toast";
import { Button, ErrorText, Input, Loading } from "../../components/ui";
import { useAction, useMe } from "../../hooks";
import { StatusCard } from "../character/StatusCard";
import { EquipmentEditor } from "./EquipmentEditor";
import { GiveToPlayer } from "./GiveNpc";
import { abilities } from "./roles";
import { staffActions, type StaffAction, type Staffing } from "./staffActions";
import { titleGives, titleGroups, titleStatusWords } from "./titleGroups";

function useTroupe(troupeId: string) {
  return useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
}

/** Who is looking, in the troupe, for `StaffActions`: asked once for a whole list. */
export function useStaffing(troupeId: string): Staffing {
  const me = useMe();
  const troupe = useTroupe(troupeId);
  const can = abilities(troupe.data?.my_role, me.data?.is_custodian ?? false);
  return { running: can.running, storyteller: can.storyteller, archived: troupe.data?.archived ?? false };
}

/** What each item is called in the menu. */
const LABELS: Record<StaffAction, string> = {
  xp: "Award XP…",
  equipment: "Give equipment…",
  status: "Status…",
  titles: "Titles…",
  give: "Give to a player…",
  sheet: "Print sheet",
  badge: "Print badge",
  jyhad: "Show Jyhad card",
};

/**
 * A character's ⋯ for the troupe's staff (#539): what they do most for one
 * character, each in a dialog with the character filled in, the same form as where
 * it lives, then its sheet and badge to print in a new tab. Only what the reader
 * may do here shows (staffActions); nothing that can't be undone is in it.
 */
export function StaffActions({ troupeId, entry, staffing }: { troupeId: string; entry: RosterEntry; staffing: Staffing }) {
  const [open, setOpen] = useState<StaffAction | null>(null);
  const close = () => setOpen(null);
  const name = entry.character_name;
  const { doing, printing } = staffActions(entry, staffing);
  // Opened in a new tab, headed for this troupe, so the list stays as it was.
  const print = (path: string) => window.open(`/print/characters/${entry.character_id}${path}?troupe=${troupeId}`, "_blank", "noopener");
  const printed: Partial<Record<StaffAction, string>> = { sheet: "", badge: "/badge", jyhad: "/jyhad" };
  const choose = (action: StaffAction) => (printed[action] !== undefined ? print(printed[action]) : setOpen(action));
  const items = (list: StaffAction[]) =>
    list.map((action) => (
      <MenuItem key={action} onSelect={() => choose(action)}>
        {LABELS[action]}
      </MenuItem>
    ));
  return (
    <>
      <ActionMenu label={`Actions for ${name}`} variant="ghost" menuClassName="w-48">
        <MenuGroup label="For this character">{items(doing)}</MenuGroup>
        <MenuGroup label="Print">{items(printing)}</MenuGroup>
      </ActionMenu>
      {/* Each fills a phone's screen. */}
      <Dialog title={`Award XP to ${name}`} open={open === "xp"} onClose={close} phoneFull>
        <AwardXp troupeId={troupeId} entry={entry} onDone={close} />
      </Dialog>
      <Dialog title={`Give ${name} equipment`} open={open === "equipment"} onClose={close} wide phoneFull>
        <GiveEquipment troupeId={troupeId} entry={entry} onDone={close} />
      </Dialog>
      <Dialog title={`${name}'s status`} open={open === "status"} onClose={close} wide phoneFull>
        <StatusCard character={{ id: entry.character_id, name, kind: entry.kind, creation_complete: entry.creation_complete }} />
      </Dialog>
      <Dialog title={`${name}'s titles`} open={open === "titles"} onClose={close} phoneFull>
        <Titles troupeId={troupeId} entry={entry} />
      </Dialog>
      <Dialog title={`Give ${name} to a player`} open={open === "give"} onClose={close} phoneFull>
        <GiveToPlayer npcId={entry.character_id} npcName={name} troupeId={troupeId} onDone={close} />
      </Dialog>
    </>
  );
}

/** The troupe Equipment tab's editor, given to this character, as from its page. */
function GiveEquipment({ troupeId, entry, onDone }: { troupeId: string; entry: RosterEntry; onDone: () => void }) {
  const toast = useToast();
  const troupe = useTroupe(troupeId);
  if (!troupe.data) return troupe.error ? <ErrorText error={troupe.error} /> : <Loading />;
  const holder = { id: entry.character_id, name: entry.character_name, kind: entry.kind, player_name: entry.player_id ? entry.player_name : null, splat: entry.splat };
  return (
    <EquipmentEditor
      troupeId={troupeId}
      troupeName={troupe.data.name}
      holders={[holder]}
      holder={holder}
      onDone={(item) => {
        toast({ message: `Gave ${entry.character_name} ${item}.` });
        onDone();
      }}
    />
  );
}

/** A title a roster entry holds here, as a pill: the active one starred, one out
 * of its sect in red; `children` at its end, such as × to take it. */
export function TitlePill({ entry, title, children }: { entry: RosterEntry; title: string; children?: ReactNode }) {
  const outOfSect = entry.out_of_sect_titles.includes(title);
  const active = title === entry.active_title;
  return (
    <span
      className={`inline-flex h-6 items-center gap-1 rounded-full border text-xs ${children ? "pr-1 pl-2.5" : "px-2.5"} ${
        outOfSect ? "border-blood bg-blood/15 text-blood-bright" : "border-gold/50 bg-gold/10 text-gold"
      }`}
      title={
        outOfSect
          ? `Out of sect: ${entry.character_name} is ${entry.sect ?? "of no sect"}. Kept until taken.`
          : active
            ? "Active: the title that gives status"
            : undefined
      }
    >
      {active && <span aria-hidden="true">★</span>}
      {title}
      {active && <span className="sr-only"> (active)</span>}
      {outOfSect && <span className="sr-only"> (out of sect)</span>}
      {children}
    </span>
  );
}

/** Experience for a character whose home troupe this is, in its dialog: amount and
 * reason, as the XP history shows them. */
function AwardXp({ troupeId, entry, onDone }: { troupeId: string; entry: RosterEntry; onDone: () => void }) {
  // Starts at the troupe's usual XP for a session (Starting points).
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId } } })),
  });
  const sessionXp = troupe.data?.session_xp ?? 8;
  const [amount, setAmount] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const award = useAction(async () => {
    await unwrap(
      api.POST("/api/characters/{character_id}/xp", {
        params: { path: { character_id: entry.character_id } },
        body: { amount: amount ?? sessionXp, reason },
      }),
    );
    onDone();
  });
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        award.mutate(undefined);
      }}
    >
      <div className="flex gap-2">
        <Input
          aria-label={`XP for ${entry.character_name}`}
          type="number"
          min={1}
          required
          value={amount ?? sessionXp}
          onChange={(e) => setAmount(Number(e.target.value))}
          className="w-20"
        />
        <Input
          aria-label={`Reason for ${entry.character_name}'s XP`}
          placeholder="Reason, such as a game"
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="min-w-0 flex-1"
        />
      </div>
      <ErrorText error={award.error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={award.isPending}>
          Award
        </Button>
      </div>
    </form>
  );
}

/** The character's titles here, in its dialog: each with × to take it away, and
 * the troupe's and the book's titles to give it another. */
function Titles({ troupeId, entry }: { troupeId: string; entry: RosterEntry }) {
  const save = useAction((names: string[]) =>
    unwrap(
      api.PUT("/api/troupes/{troupe_id}/characters/{character_id}/titles", {
        params: { path: { troupe_id: troupeId, character_id: entry.character_id } },
        body: { titles: names },
      }),
    ),
  );
  return (
    <div className="flex flex-col gap-4">
      <section>
        <h3 className="mb-1 text-xs text-mist">Holds</h3>
        {entry.titles.length ? (
          <ul className="flex flex-wrap gap-1.5">
            {entry.titles.map((t) => (
              <li key={t}>
                <TitlePill entry={entry} title={t}>
                  <button
                    type="button"
                    aria-label={`Take the title ${t} from ${entry.character_name}`}
                    className="grid h-4 w-4 place-items-center rounded-full leading-none opacity-70 hover:bg-blood hover:text-parchment hover:opacity-100 pointer-coarse:h-6 pointer-coarse:w-6"
                    disabled={save.isPending}
                    onClick={() => save.mutate(entry.titles.filter((x) => x !== t))}
                  >
                    ×
                  </button>
                </TitlePill>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-mist">No titles here yet.</p>
        )}
        <ErrorText error={save.error} />
      </section>
      <section>
        <h3 className="mb-1 text-xs text-mist">Give a title</h3>
        <GiveTitle troupeId={troupeId} entry={entry} onGive={(title) => save.mutate([...entry.titles, title])} />
      </section>
    </div>
  );
}

/** Pick one of the troupe's or the book's titles that the character can hold (of
 * its sect, or of any sect), grouped by sect, or type a new one. */
function GiveTitle({ troupeId, entry, onGive }: { troupeId: string; entry: RosterEntry; onGive: (title: string) => void }) {
  const [typed, setTyped] = useState("");
  const titles = useQuery({
    queryKey: ["titles", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/titles", { params: { path: { troupe_id: troupeId } } })),
    staleTime: 60_000,
  });
  const q = typed.trim().toLowerCase();
  const open = (titles.data?.titles ?? []).filter((t) => t.offered && !entry.titles.includes(t.name) && (t.sect === null || t.sect === entry.sect));
  const matching = open.filter((t) => t.name.toLowerCase().includes(q));
  const choices = matching.map((t) => t.name);
  const exact = choices.some((t) => t.toLowerCase() === q);
  const give = (title: string) => {
    onGive(title);
    setTyped("");
  };
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (typed.trim()) give(choices.find((t) => t.toLowerCase() === q) ?? typed.trim());
      }}
    >
      <Input autoFocus aria-label="Title" placeholder="Search or type a new title…" value={typed} onChange={(e) => setTyped(e.target.value)} />
      <p className="text-xs text-mist">
        {entry.sect
          ? `${entry.character_name} is ${entry.sect}: ${entry.sect} titles and those of any sect.`
          : `${entry.character_name} has no sect: only titles of any sect.`}
      </p>
      <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
        {titleGroups(entry.sect ? [entry.sect] : [], matching).map(([sect, list]) => (
          <section key={sect ?? ""}>
            <h3 className="mb-1 text-xs text-mist">{sect ?? "Any sect"}</h3>
            <ul className="flex flex-wrap gap-1.5">
              {list.map((t) => (
                <li key={t.name}>
                  <button
                    type="button"
                    className="rounded-full border border-ash px-2.5 py-1 text-xs hover:border-gold hover:text-gold"
                    title={titleGives(titleStatusWords(t), t)}
                    onClick={() => give(t.name)}
                  >
                    {t.name}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
        {titles.isPending && <p className="text-sm text-mist">Loading…</p>}
      </div>
      {q && !exact && (
        <Button type="submit" variant="secondary">
          Give the new title “{typed.trim()}”
        </Button>
      )}
    </form>
  );
}
