import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import type { TroupeOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { showFound } from "../../components/SettingCard";
import { Button } from "../../components/ui";
import { BackstorySettings } from "./BackstorySettings";
import { BadgeSetting } from "./BadgeSetting";
import { BloodBondsSetting } from "./BloodBondsSetting";
import { BoonLedgerSetting } from "./BoonLedgerSetting";
import { SETTINGS_HASH, settingsPart, type SettingsPart } from "./features";
import { FreeChangesSettings } from "./FreeChangesSettings";
import { LocationRulesSection } from "./LocationRulesSection";
import { PlayTabsSetting } from "./PlayTabsSetting";
import { QuestSettings } from "./QuestSettings";
import { RetainerRules } from "./RetainerRules";
import { SETTINGS_DIALOGS, type SettingsDialog } from "./settingsIndex";
import { StatusAtCheckinSetting } from "./StatusSetting";
import { TeacherRules } from "./TeacherRules";
import { ThrowImagesSetting } from "./ThrowImagesSetting";
import { WhosWhoSetting } from "./WhosWhoSetting";

/**
 * Scrolls the dialog's own scroller to `card`, and nothing beyond the dialog: scrollIntoView
 * would also move the page under it, and on a phone the dialog itself, off the screen.
 */
function scrollWithin(card: HTMLElement) {
  for (let el = card.parentElement; el; el = el.parentElement) {
    const { overflowY } = getComputedStyle(el);
    if ((overflowY === "auto" || overflowY === "scroll") && el.scrollHeight > el.clientHeight) {
      el.scrollTop += card.getBoundingClientRect().top - el.getBoundingClientRect().top - 16;
      return;
    }
    if (el instanceof HTMLDialogElement) return;
  }
}

/**
 * A feature's own settings, behind one Settings button right-aligned above its tab's content
 * (#909), in a dialog named after the tab: full screen on a phone. Switching the feature on and
 * off is the Features list's, on Troupe settings; its Settings link lands here, with the dialog
 * open. An address ending `#settings-<part>` (#785) opens it at that part's card. Those who may
 * read but not change them see the same cards, read-only.
 */
export function FeatureSettings({ tab, children, single = false }: { tab: string; children: ReactNode; single?: boolean }) {
  const { hash, pathname, search, key } = useLocation();
  const navigate = useNavigate();
  const asked = hash === `#${SETTINGS_HASH}` || hash.startsWith(`#${SETTINGS_HASH}-`);
  const [open, setOpen] = useState(asked);
  useEffect(() => {
    if (asked) setOpen(true);
  }, [asked, hash]);
  // Landing on a part or a card, it is scrolled to once the cards above it have loaded and
  // taken their height: again each time a load ends, until none is left. A card glows a
  // moment as it is found (#1047).
  const client = useQueryClient();
  const fetching = useIsFetching();
  const landed = useRef<string | null>(null);
  const shown = useRef<string | null>(null);
  useEffect(() => {
    if (!open || !asked || landed.current === key) return;
    const card = document.getElementById(hash.slice(1));
    if (card) scrollWithin(card);
    if (card && hash !== `#${SETTINGS_HASH}` && shown.current !== key) {
      shown.current = key;
      showFound(card);
    }
    if (client.isFetching() === 0) landed.current = key;
  }, [open, asked, hash, key, fetching, client]);
  const close = () => {
    setOpen(false);
    landed.current = null;
    // The address no longer opens it, so going back to the tab doesn't either.
    if (asked) void navigate({ pathname, search }, { replace: true });
  };
  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button variant="secondary" onClick={() => setOpen(true)}>
          Settings
        </Button>
      </div>
      <Dialog title={`${tab} settings`} open={open} onClose={close} wide phoneFull>
        {/* On a wider screen the cards scroll under the dialog's title, which stays in sight; a phone's dialog does that itself. */}
        <div id={SETTINGS_HASH} className={`grid items-start gap-6 sm:max-h-[calc(100dvh-9rem)] sm:overflow-y-auto ${single ? "" : "md:grid-cols-2"}`}>
          {children}
        </div>
      </Dialog>
    </>
  );
}

/** The features whose settings are behind the Settings button of their own tab. */
type OnTab = Extract<SettingsDialog, "whos_who" | "play_view" | "boons" | "blood_bonds">;

/** A feature's tab's Settings, with the cards that were on Troupe settings (#784). */
export function TabSettings({ troupe, feature, canEdit }: { troupe: TroupeOut; feature: OnTab; canEdit: boolean }) {
  return (
    <FeatureSettings tab={SETTINGS_DIALOGS[feature].tab} single={feature !== "play_view"}>
      {feature === "whos_who" && <WhosWhoSetting troupe={troupe} canEdit={canEdit} />}
      {feature === "play_view" && (
        <>
          <PlayTabsSetting troupe={troupe} canEdit={canEdit} />
          <StatusAtCheckinSetting troupe={troupe} canEdit={canEdit} />
          <BadgeSetting troupe={troupe} canEdit={canEdit} />
          <ThrowImagesSetting troupe={troupe} canEdit={canEdit} />
        </>
      )}
      {feature === "boons" && <BoonLedgerSetting troupe={troupe} canEdit={canEdit} />}
      {feature === "blood_bonds" && <BloodBondsSetting troupe={troupe} canEdit={canEdit} />}
    </FeatureSettings>
  );
}

type Place = Extract<SettingsDialog, "locations" | "quests" | "characters" | "approvals">;

/**
 * The house rules that set up a feature rather than a rule, behind the Settings button of the
 * tab where staff meet that feature (#785): Locations on World › Locations, Quests on Downtimes › Quests,
 * Retainers on Characters, and Backstories, Teachers and Free changes on Approvals, where what
 * they ask for is reviewed. Running staff read them; storytellers change them, as under House rules.
 */
export function PartSettings({ troupeId, place, canEdit }: { troupeId: string; place: Place; canEdit: boolean }) {
  const part = (key: SettingsPart, card: ReactNode) => (
    <div id={settingsPart(key)}>
      {card}
    </div>
  );
  return (
    <FeatureSettings tab={SETTINGS_DIALOGS[place].tab} single>
      {place === "locations" && part("locations", <LocationRulesSection troupeId={troupeId} canEdit={canEdit} />)}
      {place === "quests" && part("quests", <QuestSettings troupeId={troupeId} canEdit={canEdit} />)}
      {place === "characters" && part("retainers", <RetainerRules troupeId={troupeId} canEdit={canEdit} />)}
      {place === "approvals" && (
        <>
          {part("backstories", <BackstorySettings troupeId={troupeId} />)}
          {part("teachers", <TeacherRules troupeId={troupeId} canEdit={canEdit} />)}
          {part("free-changes", <FreeChangesSettings troupeId={troupeId} canEdit={canEdit} />)}
        </>
      )}
    </FeatureSettings>
  );
}
