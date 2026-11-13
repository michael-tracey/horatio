import { useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation } from "react-router";
import type { TroupeOut } from "../../api/types";
import { BadgeSetting } from "./BadgeSetting";
import { BloodBondsSetting } from "./BloodBondsSetting";
import { BoonLedgerSetting } from "./BoonLedgerSetting";
import { SETTINGS_HASH } from "./features";
import { PlayTabsSetting } from "./PlayTabsSetting";
import { StatusAtCheckinSetting } from "./StatusSetting";
import { ThrowImagesSetting } from "./ThrowImagesSetting";
import { WhosWhoSetting } from "./WhosWhoSetting";

/**
 * A feature's own settings, folded at the top of its tab (#784), for those who may change
 * them. Switching the feature on and off is the Features list's, on Troupe settings; its
 * Settings link lands here, open.
 */
export function FeatureSettings({ children, single = false }: { children: ReactNode; single?: boolean }) {
  const { hash } = useLocation();
  const asked = hash === `#${SETTINGS_HASH}`;
  const [open, setOpen] = useState(asked);
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!asked) return;
    setOpen(true);
    ref.current?.scrollIntoView({ block: "start" });
  }, [asked]);
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
