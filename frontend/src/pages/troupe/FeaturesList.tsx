import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Toggle } from "../../components/Toggle";
import { SettingCard } from "../../components/SettingCard";
import { Badge, ErrorText } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { features, type Feature, type FeatureKey } from "./features";
import { SETTINGS, switchAnchor } from "./settingsIndex";

/** Switches a feature on or off, through the same endpoint as its settings card. */
async function setFeature(troupe: TroupeOut, key: FeatureKey, on: boolean): Promise<unknown> {
  const path = { params: { path: { troupe_id: troupe.id } } };
  switch (key) {
    case "boons":
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/boon-ledger", {
          ...path,
          body: { on },
        }),
      );
    case "blood_bonds":
      // Switched on from here, staff keep the bonds; the other ways are in its settings.
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/blood-bonds", {
          ...path,
          body: { setting: on ? "staff" : "off" },
        }),
      );
    case "nominations":
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/player-nominations", {
          ...path,
          body: { on },
        }),
      );
    case "remembrances":
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/remembrances", {
          ...path,
          body: { on },
        }),
      );
    case "court_history":
      return unwrap(
        api.PATCH("/api/troupes/{troupe_id}", {
          ...path,
          body: { court_history_players: on },
        }),
      );
    case "chronicle":
      return unwrap(
        api.PATCH("/api/troupes/{troupe_id}", {
          ...path,
          body: { chronicle_players: on },
        }),
      );
    case "quests":
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/quest-settings", {
          ...path,
          body: {
            enabled: on,
            requests_per_cycle: troupe.quest_requests_per_cycle,
          },
        }),
      );
    case "feeding":
      // Its options are kept, and come back with it.
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/feeding", {
          ...path,
          body: {
            feeding: on ? "book" : "off",
            resonance: troupe.feeding_resonance,
            territories: troupe.feeding_territories,
            rack: troupe.feeding_rack,
          },
        }),
      );
    case "golconda":
      return unwrap(api.PUT("/api/troupes/{troupe_id}/golconda", { ...path, body: { on } }));
    case "item_expiry":
      return unwrap(
        api.PUT("/api/troupes/{troupe_id}/item-expiry", {
          ...path,
          body: { on },
        }),
      );
    case "whos_who":
    case "news":
    case "play_view":
      throw new Error(`${key} has no switch`);
  }
}

/**
 * Every optional feature of the troupe, the first part of Troupe settings (#783, #908): on or
 * off, what it adds, a switch for its storytellers, and links to its tab and its settings.
 * Each feature is switched on and off here only; the rest of its settings are behind the Settings
 * button of its own tab (#784, #909), so a feature switched off, with no tab, can still be found.
 */
export function FeaturesList({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const toast = useToast();
  // Feeding and Golconda change what the rules allow, so the rules are asked again too.
  const save = useRulesAction(async ({ feature, on }: { feature: Feature; on: boolean }) => {
    await setFeature(troupe, feature.key, on);
    toast({
      message: `${feature.name}: ${on ? "switched on" : "switched off"}.`,
    });
  });
  const base = `/troupes/${troupe.id}`;
  return (
    <SettingCard
      setting={SETTINGS.features}
      readOnly={!canEdit && "Its storytellers switch them on and off."}
      about={canEdit ? undefined : "What the troupe uses beyond the sheets and downtimes."}
    >
      <ul aria-label="Features" className="flex flex-col divide-y divide-ash">
        {features(troupe).map((f) => {
          return (
            <li key={f.key} id={switchAnchor(f.key)} aria-label={f.name} className="scroll-mt-4 py-1">
              {canEdit ? (
                // A feature that is always on (Who's Who, News) or goes tab by tab (the Play View)
                // has its switch too, held as it is, so every row lines up (#908).
                <Toggle
                  label={
                    <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className="text-parchment">{f.name}</span>
                      <Badge tone={f.on ? "gold" : "mist"}>{f.state}</Badge>
                    </span>
                  }
                  aria-label={f.name}
                  hint={f.adds}
                  checked={f.on}
                  disabled={!f.switchable || save.isPending}
                  onChange={(on) => save.mutate({ feature: f, on })}
                >
                  <FeatureLinks feature={f} base={base} settings={f.settings} />
                </Toggle>
              ) : (
                <div className="flex items-start gap-3 py-2">
                  <span aria-hidden className="w-11 shrink-0" />
                  <div className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
                    <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className="text-parchment">{f.name}</span>
                      <Badge tone={f.on ? "gold" : "mist"}>{f.state}</Badge>
                    </p>
                    <p className="text-xs text-mist">{f.adds}</p>
                    <FeatureLinks feature={f} base={base} settings={f.settings} />
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <ErrorText error={save.error} />
    </SettingCard>
  );
}

/** A feature's links: to its tab, and to its settings. */
function FeatureLinks({ feature: f, base, settings }: { feature: Feature; base: string; settings: string | undefined }) {
  if (!f.tab && !settings) return null;
  return (
    <p className="flex flex-wrap gap-x-4 text-xs">
      {f.tab && (
        <Link to={`${base}/${f.tab.to}`} className="inline-flex items-center text-mist underline hover:text-parchment pointer-coarse:min-h-10">
          Open {f.tab.label}
        </Link>
      )}
      {settings && (
        <Link to={`${base}/${settings}`} className="inline-flex items-center text-mist underline hover:text-parchment pointer-coarse:min-h-10" aria-label={`Settings for ${f.name}`}>
          Settings
        </Link>
      )}
    </p>
  );
}
