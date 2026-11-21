import { useIsFetching, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Checkbox } from "../../components/Checkbox";
import { SectionLabel } from "../../components/Headings";
import { PartPicker } from "../../components/PartPicker";
import { SettingCard, showFound, useSaveOnChange } from "../../components/SettingCard";
import { ErrorText, Loading } from "../../components/ui";
import { AbbreviationSetting } from "./AbbreviationSetting";
import { ClanNamesSetting } from "./ClanNamesSetting";
import { ClanWeaknesses } from "./ClanWeaknesses";
import { DiablerieFlaws } from "./DiablerieFlaws";
import { FeedingSetting } from "./FeedingSetting";
import { FeedingTerritories } from "./FeedingTerritories";
import { GameXpCard } from "./GameXpSettings";
import { NewCharacterIncentive } from "./NewCharacterIncentive";
import { SettingStyle } from "./SettingStyle";
import { ExperienceDefaults, StartingBlood } from "./StartingSection";
import { FeaturesList } from "./FeaturesList";
import { GettingReadySetup } from "./GettingReady";
import { features, settingsAnchor, troupeSettings, type FeatureKey } from "./features";
import { SETTINGS, TROUPE_SETTINGS_PARTS } from "./settingsIndex";
import { StatusBanClans } from "./StatusBanClans";
import { StatusSetting, TitlesSetting } from "./StatusSetting";
import { XpRangeCard } from "./XpRange";
import { useCatalogue } from "../../catalogue";

/**
 * The settings for the whole troupe, set once a season or so, a part for each purpose (#908):
 * the Features list first, every optional feature on or off (#783), then the steps of getting
 * a new troupe ready (#1049, #1048), the setting players read (#770), who may join, XP, status
 * and titles, Blood, diablerie and feeding, and names (the troupe's abbreviation, what a clan is called), each at `settings/<part>`. A feature with a tab of its own keeps the rest of its
 * settings behind that tab's Settings button (#784, #909). Its storytellers change them; the
 * troupe's other running staff read them (assistant storytellers write the setting too). The
 * troupe's rules for traits are on the House rules tab beside it (#782).
 */
export function SettingsTab({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const base = `/troupes/${troupe.id}`;
  const settings = `${base}/${troupeSettings()}`;
  useLandOnCard();
  return (
    <PartPicker
      label="Settings"
      parts={[{ to: settings, label: "Features", end: true }, ...TROUPE_SETTINGS_PARTS.map((p) => ({ to: `${base}/${troupeSettings(p.part)}`, label: p.label }))]}
    >
      <Routes>
        <Route index element={<FeaturesPart troupe={troupe} canEdit={canEdit} />} />
        <Route
          path="getting-ready"
          element={
            <div role="group" aria-label="Getting ready">
              <SectionLabel as="h2" className="mb-3">
                Getting ready
              </SectionLabel>
              <div className="max-w-3xl">
                <GettingReadySetup troupeId={troupe.id} canEdit={canEdit} />
              </div>
            </div>
          }
        />
        <Route
          path="setting"
          element={
            <Part title="The setting">
              <SettingStyle troupeId={troupe.id} />
            </Part>
          }
        />
        <Route
          path="joining"
          element={
            <Part title="Who may join">
              <SplatsCard troupe={troupe} canEdit={canEdit} />
              <SectsCard troupe={troupe} canEdit={canEdit} />
            </Part>
          }
        />
        <Route
          path="xp"
          element={
            <Part title="XP">
              <ExperienceDefaults troupeId={troupe.id} canEdit={canEdit} />
              <XpRangeCard
                troupeId={troupe.id}
                canEdit={canEdit}
                link={
                  <Link to={`${base}/award-xp`} className="text-sm text-mist underline hover:text-parchment">
                    Award XP
                  </Link>
                }
              />
              <GameXpCard troupeId={troupe.id} canEdit={canEdit} sessionXp={troupe.session_xp} />
              <NewCharacterIncentive troupeId={troupe.id} canEdit={canEdit} />
            </Part>
          }
        />
        <Route
          path="status"
          element={
            <Part title="Status and titles">
              <StatusSetting troupe={troupe} canEdit={canEdit} />
              <TitlesSetting troupe={troupe} canEdit={canEdit} />
              <StatusBanClans troupeId={troupe.id} canEdit={canEdit} />
            </Part>
          }
        />
        <Route
          path="blood"
          element={
            <Part title="Blood, diablerie and feeding">
              <StartingBlood troupeId={troupe.id} canEdit={canEdit} />
              <DiablerieFlaws troupeId={troupe.id} canEdit={canEdit} />
              <ClanWeaknesses troupeId={troupe.id} canEdit={canEdit} />
              <Anchored feature="feeding">
                <FeedingSetting troupeId={troupe.id} canEdit={canEdit} />
              </Anchored>
              {/* Unlike the settings around it, assistant storytellers keep the territories too, as the
                  API lets them: who holds which changes in play, as the Authority proclaims it. */}
              {troupe.feeding !== "off" && troupe.feeding_territories && (
                <FeedingTerritories troupeId={troupe.id} canManage={!troupe.archived && (canEdit || troupe.my_role === "assistant_storyteller")} />
              )}
            </Part>
          }
        />
        <Route
          path="names"
          element={
            <Part title="Names">
              <AbbreviationSetting troupe={troupe} />
              <ClanNamesSetting troupeId={troupe.id} canEdit={canEdit} />
            </Part>
          }
        />
        {/* A part that isn't one: back to the Features list. */}
        <Route path="*" element={<Navigate to={settings} replace />} />
      </Routes>
    </PartPicker>
  );
}

/**
 * The Features list, the part Settings opens on, under a word on the whole page. An
 * old address of a feature's card, `settings#feature-feeding` from when every part was on one
 * page, goes to wherever that card is now: its part of Settings, or its tab's Settings (#908).
 */
function FeaturesPart({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const { hash } = useLocation();
  const moved = hash.startsWith("#feature-") ? features(troupe).find((f) => hash === `#${settingsAnchor(f.key)}`)?.settings : undefined;
  if (moved) return <Navigate to={`/troupes/${troupe.id}/${moved}`} replace />;
  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-mist">
        {canEdit
          ? "Settings for the whole troupe. Switches and choices save as you make them; a card with fields to type in has its own Save button."
          : `Settings for the whole troupe. Its storytellers change them${troupe.my_role === "assistant_storyteller" && !troupe.archived ? "; you write the setting with them." : "."}`}{" "}
        A feature with a tab of its own has the rest of its settings behind that tab's Settings button. What traits cost and what new characters start with are
        under House rules, beside this.
      </p>
      <FeaturesList troupe={troupe} canEdit={canEdit} />
    </div>
  );
}

/**
 * Landing on a card's anchor (`settings/blood#feature-feeding`), scrolls to it once the cards
 * above it have loaded and taken their height: again each time a load ends, until none is left.
 * The card glows a moment as it is found (#1047), each time it is landed on.
 */
function useLandOnCard() {
  const { hash, key } = useLocation();
  const client = useQueryClient();
  const fetching = useIsFetching();
  const landed = useRef<string | null>(null);
  const shown = useRef<string | null>(null);
  useEffect(() => {
    if (!hash || landed.current === key) return;
    // Not there yet, as on the Features list an old anchor is sent on from: tried again once it is.
    const card = document.getElementById(hash.slice(1));
    if (!card) return;
    card.scrollIntoView({ block: "start" });
    if (shown.current !== key) {
      shown.current = key;
      showFound(card);
    }
    if (client.isFetching() === 0) landed.current = key;
  }, [key, hash, fetching, client]);
}

/** A feature's settings card, where the Features list's Settings link lands. */
function Anchored({ feature, children }: { feature: FeatureKey; children: ReactNode }) {
  return (
    <div id={settingsAnchor(feature)} className="scroll-mt-4">
      {children}
    </div>
  );
}

/**
 * One part of Settings: a few settings for one purpose, under its name. A div, not a
 * section, so a card's own section is the one around its heading.
 */
function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={title}>
      <SectionLabel as="h2" className="mb-3">
        {title}
      </SectionLabel>
      <div className="grid items-start gap-6 md:grid-cols-2">{children}</div>
    </div>
  );
}

/** "Vampire and Ghoul": the splats whose player characters may join, in words. */
export function useSplatsText(troupe: TroupeOut) {
  const splats = useQuery({
    queryKey: ["splats"],
    queryFn: () => unwrap(api.GET("/api/rules")),
    staleTime: 5 * 60_000,
  });
  const label = (splat: string) => splats.data?.find((s) => s.splat === splat)?.label ?? splat;
  const named = troupe.allowed_splats.map(label);
  return { splats, text: named.length > 1 ? `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}` : named[0] };
}

/** Which sects' player characters may join, in a sentence. */
export function sectsText(allowed: string[]) {
  return allowed.length ? `Player characters from ${allowed.join(", ")} may join.` : "Player characters from any sect may join.";
}

/** Which sects' player characters may join. None ticked means any may. */
function SectsCard({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  // The book's sects alone: nothing else on this page needs the catalogue.
  const catalogue = useCatalogue("vampire", null, { category: "sect", enabled: canEdit });
  const save = useSaveOnChange(
    (allowed_sects: string[]) => unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { allowed_sects } })),
    { rules: true },
  );
  const allowed = troupe.allowed_sects;
  const sects = (catalogue.data?.traits ?? []).filter((t) => t.category === "sect").map((t) => t.name);

  return (
    <SettingCard setting={SETTINGS.sects} about={canEdit ? undefined : null} readOnly={!canEdit}>
      {!canEdit ? (
        <p className="text-sm">{sectsText(allowed)}</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">Which sects may player characters join from?</legend>
          {sects.map((sect) => (
            <Checkbox
              key={sect}
              label={sect}
              checked={allowed.includes(sect)}
              disabled={save.isPending}
              onChange={(on) => save.mutate(on ? [...allowed, sect] : allowed.filter((s) => s !== sect))}
            />
          ))}
          <ErrorText error={save.error ?? catalogue.error} />
        </fieldset>
      )}
    </SettingCard>
  );
}

/** Which splats' player characters may join, and be built for the troupe: Vampire, Ghoul. At least one. */
function SplatsCard({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const { splats, text } = useSplatsText(troupe);
  const save = useSaveOnChange((allowed_splats: string[]) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { allowed_splats } })),
  );
  const allowed = troupe.allowed_splats;

  return (
    <SettingCard setting={SETTINGS.splats} about={canEdit ? undefined : null} readOnly={!canEdit}>
      {!canEdit ? (
        <p className="text-sm">{text} player characters may join.</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">Which splats may player characters be?</legend>
          {splats.isPending && <Loading compact />}
          {(splats.data ?? []).map(({ splat, label }) => (
            <Checkbox
              key={splat}
              label={label}
              checked={allowed.includes(splat)}
              disabled={save.isPending || (allowed.length === 1 && allowed.includes(splat))}
              onChange={(on) => save.mutate(on ? [...allowed, splat] : allowed.filter((s) => s !== splat))}
            />
          ))}
          <ErrorText error={save.error ?? splats.error} />
        </fieldset>
      )}
    </SettingCard>
  );
}
