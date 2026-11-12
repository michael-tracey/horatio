import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Button, Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { TABS, tabNames, tabsOn, type Tab } from "../play/tabs";

// What a few of the tabs bring with them, under their switches.
const NOTES: Partial<Record<Tab, string>> = {
  tracker: "Blood, Willpower, health, limited uses and the game's log. Off, the strip of Blood, Willpower and health on the other tabs goes with it.",
  status: "Only for characters with sect status.",
};

/**
 * Play View tabs (#673): a switch for each of the Play View's tabs, all on until the
 * troupe switches one off. With every tab off, the troupe doesn't use the Play View for
 * its players, which the card says before that is saved. Staff always see every tab on
 * NPCs, and run them and scenes whatever is set.
 */
export function PlayTabsSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const save = useAction((play_tabs_off: Tab[]) => unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { play_tabs_off } })));
  // The last tab switched off waits here until the storyteller says yes.
  const [last, setLast] = useState<Tab | null>(null);
  const off = troupe.play_tabs_off;
  const on = tabsOn(off);
  const change = (tab: Tab, checked: boolean) => {
    if (!checked && on.length === 1) setLast(tab);
    else save.mutate(checked ? off.filter((t) => t !== tab) : [...off, tab]);
  };
  return (
    <Card title="Play View tabs">
      <p className="mb-3 text-sm text-mist">
        The tabs players see on the Play View at games. Staff always see every tab on NPCs. Turn them all off if your players keep their sheets here but don't play from Horatio.
      </p>
      {!canEdit ? (
        <p className="text-sm">{on.length === 0 ? "The troupe doesn't use the Play View for players." : on.length === TABS.length ? "Players see every tab." : `Players see ${tabNames(on)}.`}</p>
      ) : (
        <div className="flex flex-col gap-2 text-sm">
          {on.length === 0 && <p className="text-gold">The Play View is off for players. Staff still run NPCs and scenes. Switch a tab on to give it back to players.</p>}
          {TABS.map(({ key, label }) => (
            <label key={key} className="flex items-start gap-2">
              <input type="checkbox" className="mt-1" checked={on.includes(key) && last !== key} disabled={save.isPending || last !== null} onChange={(e) => change(key, e.target.checked)} />
              <span>
                {label}
                {NOTES[key] && <span className="block text-xs text-mist">{NOTES[key]}</span>}
              </span>
            </label>
          ))}
          {last && (
            <div role="alertdialog" aria-label="Turn the Play View off for players" className="mt-1 flex flex-col gap-2 rounded-md border border-blood/60 bg-blood/10 p-3">
              <p>
                {TABS.find((t) => t.key === last)?.label} is the last tab on. With it off, the troupe doesn't use the Play View for players: their characters have no Play,
                check-in doesn't open it, and phones don't keep it for games with no signal. Staff still run NPCs and scenes, with every tab. Sheets stay as they are, and
                switching a tab on brings it all back.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  onClick={() => {
                    save.mutate([...off, last]);
                    setLast(null);
                  }}
                >
                  Turn the Play View off for players
                </Button>
                <Button variant="secondary" onClick={() => setLast(null)}>
                  Keep {TABS.find((t) => t.key === last)?.label}
                </Button>
              </div>
            </div>
          )}
          <ErrorText error={save.error} />
        </div>
      )}
    </Card>
  );
}
