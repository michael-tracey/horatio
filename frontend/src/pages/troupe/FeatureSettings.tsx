import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router";
import type { TroupeOut } from "../../api/types";
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
import { StatusAtCheckinSetting } from "./StatusSetting";
import { TeacherRules } from "./TeacherRules";
import { ThrowImagesSetting } from "./ThrowImagesSetting";
import { WhosWhoSetting } from "./WhosWhoSetting";

/**
 * A feature's own settings, folded at the top of its tab (#784), for those who may change
 * them. Switching the feature on and off is the Features list's, on Troupe settings; its
 * Settings link lands here, open. An address ending `#settings-<part>` (#785) opens it too,
 * at that part's card.
 */
export function FeatureSettings({ children, single = false }: { children: ReactNode; single?: boolean }) {
  const { hash } = useLocation();
  const asked = hash === `#${SETTINGS_HASH}` || hash.startsWith(`#${SETTINGS_HASH}-`);
  const [open, setOpen] = useState(asked);
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!asked) return;
    setOpen(true);
    (document.getElementById(hash.slice(1)) ?? ref.current)?.scrollIntoView({ block: "start" });
  }, [asked, hash]);
  return (
    <details
      ref={ref}
      id={SETTINGS_HASH}
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
      className="mb-6 scroll-mt-4 rounded-lg border border-ash"
    >
      <summary className="cursor-pointer px-4 py-3 text-sm text-parchment">Settings</summary>
      <div className={`grid items-start gap-6 border-t border-ash p-4 ${single ? "" : "md:grid-cols-2"}`}>{children}</div>
    </details>
  );
}

/** The features whose settings are folded at the top of their own tab. */
type OnTab = "whos_who" | "play_view" | "boons" | "blood_bonds";

/** A feature's tab's folded Settings, with the cards that were on Troupe settings (#784). */
export function TabSettings({ troupe, feature }: { troupe: TroupeOut; feature: OnTab }) {
  return (
    <FeatureSettings single={feature !== "play_view"}>
      {feature === "whos_who" && <WhosWhoSetting troupe={troupe} canEdit />}
      {feature === "play_view" && (
        <>
          <PlayTabsSetting troupe={troupe} canEdit />
          <StatusAtCheckinSetting troupe={troupe} canEdit />
          <BadgeSetting troupe={troupe} canEdit />
          <ThrowImagesSetting troupe={troupe} canEdit />
        </>
      )}
      {feature === "boons" && <BoonLedgerSetting troupe={troupe} canEdit />}
      {feature === "blood_bonds" && <BloodBondsSetting troupe={troupe} canEdit />}
    </FeatureSettings>
  );
}

/**
 * The house rules that set up a feature rather than a rule, folded at the top of the tab where
 * staff meet that feature (#785): Locations on World › Locations, Quests on Downtimes › Quests,
 * Retainers on Characters, and Backstories, Teachers and Free changes on Approvals, where what
 * they ask for is reviewed. Running staff read them; storytellers change them, as under House rules.
 */
export function PartSettings({ troupeId, place, canEdit }: { troupeId: string; place: "locations" | "quests" | "characters" | "approvals"; canEdit: boolean }) {
  const part = (key: SettingsPart, card: ReactNode) => (
    <div id={settingsPart(key)} className="scroll-mt-4">
      {card}
    </div>
  );
  return (
    <FeatureSettings single>
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
