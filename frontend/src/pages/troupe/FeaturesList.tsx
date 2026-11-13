import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { useToast } from "../../components/Toast";
import { Badge, Card, ErrorText } from "../../components/ui";
import { useRulesAction } from "../../hooks";
import { features, type Feature, type FeatureKey } from "./features";

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
 * Every optional feature of the troupe, at the top of Troupe settings (#783): on or off,
 * what it adds, a switch for its storytellers, and links to its tab and its settings.
 * The switches are the ones its settings cards have, so a feature switched off, with no
 * tab, can still be found.
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
    <Card title="Features">
      <p className="mb-3 text-sm text-mist">
        {canEdit
          ? "What the troupe uses beyond the sheets and downtimes. Switched off, a feature's tabs are hidden, and what was recorded is kept for when it's on again."
          : "What the troupe uses beyond the sheets and downtimes. Its storytellers switch them on and off."}
      </p>
      <ul aria-label="Features" className="flex flex-col divide-y divide-ash">
        {features(troupe).map((f) => (
          <li key={f.key} aria-label={f.name} className="flex items-start gap-3 py-3">
            {canEdit && f.switchable ? (
              <button
                type="button"
                role="switch"
                aria-checked={f.on}
                aria-label={f.name}
                disabled={save.isPending}
                onClick={() => save.mutate({ feature: f, on: !f.on })}
                className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors disabled:opacity-60 ${
                  f.on ? "border-gold bg-gold/30" : "border-ash bg-night"
                }`}
              >
                <span className={`inline-block h-4 w-4 rounded-full transition-transform ${f.on ? "translate-x-6 bg-gold" : "translate-x-1 bg-mist"}`} />
              </button>
            ) : (
              <span aria-hidden className="w-11 shrink-0" />
            )}
            <div className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
              <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                <span className="text-parchment">{f.name}</span>
                <Badge tone={f.on ? "gold" : "mist"}>{f.state}</Badge>
              </p>
              <p className="text-xs text-mist">{f.adds}</p>
              {(f.tab || f.settings) && (
                <p className="flex flex-wrap gap-x-4 text-xs">
                  {f.tab && (
                    <Link to={`${base}/${f.tab.to}`} className="text-mist underline hover:text-parchment">
                      Open {f.tab.label}
                    </Link>
                  )}
                  {f.settings &&
                    (f.settings.startsWith("#") ? (
                      <a href={f.settings} className="text-mist underline hover:text-parchment" aria-label={`Settings for ${f.name}`}>
                        Settings
                      </a>
                    ) : (
                      <Link to={`${base}/${f.settings}`} className="text-mist underline hover:text-parchment" aria-label={`Settings for ${f.name}`}>
                        Settings
                      </Link>
                    ))}
                </p>
              )}
            </div>
          </li>
        ))}
      </ul>
      <ErrorText error={save.error} />
    </Card>
  );
}
