import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText, Loading } from "../../components/ui";
import { useAction, useRulesAction } from "../../hooks";
import { BadgeSetting } from "./BadgeSetting";
import { BloodBondsSetting } from "./BloodBondsSetting";
import { BoonLedgerSetting } from "./BoonLedgerSetting";
import { ClanNamesSetting } from "./ClanNamesSetting";
import { CourtHistorySetting } from "./CourtHistorySetting";
import { DiablerieFlaws } from "./DiablerieFlaws";
import { FeedingSetting } from "./FeedingSetting";
import { FeedingTerritories } from "./FeedingTerritories";
import { GameXpCard } from "./GameXpSettings";
import { GolcondaSetting } from "./GolcondaSetting";
import { ItemExpirySetting } from "./ItemExpirySetting";
import { PlayTabsSetting } from "./PlayTabsSetting";
import { ThrowImagesSetting } from "./ThrowImagesSetting";
import { NominationsSetting } from "../nominations/NominationsSetting";
import { RemembrancesSetting } from "../nominations/RemembrancesSetting";
import { ExperienceDefaults, StartingBlood } from "./StartingSection";
import { StatusBanClans } from "./StatusBanClans";
import { StatusAtCheckinSetting, StatusSetting, TitlesSetting } from "./StatusSetting";
import { WhosWhoSetting } from "./WhosWhoSetting";
import { XpRangeCard } from "./XpRange";
import { useCatalogue } from "../../catalogue";

/**
 * The settings for the whole troupe, set once a season or so, by what they are
 * for: who may join, XP, status and titles, what happens at game, downtimes,
 * feeding, and what a clan is called. Its storytellers change them; the troupe's other running
 * staff read them. The troupe's rules for traits are on the Rules tab beside it.
 */
export function SettingsTab({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const base = `/troupes/${troupe.id}`;
  return (
    <div className="flex flex-col gap-8">
      <p className="text-sm text-mist">
        {canEdit ? "Settings for the whole troupe. Each change takes effect straight away." : "Settings for the whole troupe. Its storytellers change them."}{" "}
        What traits cost and what new characters start with are under Rules, beside this.
      </p>
      <Group title="Who may join">
        <SplatsCard troupe={troupe} canEdit={canEdit} />
        <SectsCard troupe={troupe} canEdit={canEdit} />
      </Group>
      <Group title="XP">
        <ExperienceDefaults troupeId={troupe.id} canEdit={canEdit} />
        <XpRangeCard
          troupeId={troupe.id}
          canEdit={canEdit}
          link={
            <Link to={`${base}/xp`} className="text-sm text-mist underline hover:text-parchment">
              Award XP
            </Link>
          }
        />
        <GameXpCard troupeId={troupe.id} canEdit={canEdit} sessionXp={troupe.session_xp} />
      </Group>
      <Group title="Status and titles">
        <StatusSetting troupe={troupe} canEdit={canEdit} />
        <TitlesSetting troupe={troupe} canEdit={canEdit} />
        <StatusAtCheckinSetting troupe={troupe} canEdit={canEdit} />
        {troupe.whos_who && <WhosWhoSetting troupe={troupe} canEdit={canEdit} />}
        <CourtHistorySetting troupe={troupe} canEdit={canEdit} />
        <GolcondaSetting troupeId={troupe.id} canEdit={canEdit} />
        <StatusBanClans troupeId={troupe.id} canEdit={canEdit} />
      </Group>
      <Group title="At game">
        <PlayTabsSetting troupe={troupe} canEdit={canEdit} />
        <ThrowImagesSetting troupe={troupe} canEdit={canEdit} />
        <BadgeSetting troupe={troupe} canEdit={canEdit} />
        <StartingBlood troupeId={troupe.id} canEdit={canEdit} />
        <DiablerieFlaws troupeId={troupe.id} canEdit={canEdit} />
        <ItemExpirySetting troupe={troupe} canEdit={canEdit} />
        <BloodBondsSetting troupe={troupe} canEdit={canEdit} />
        <BoonLedgerSetting troupe={troupe} canEdit={canEdit} />
      </Group>
      <Group title="Downtimes">
        <NominationsSetting troupe={troupe} canEdit={canEdit} />
        <RemembrancesSetting troupe={troupe} canEdit={canEdit} />
      </Group>
      <Group title="Feeding">
        <FeedingSetting troupeId={troupe.id} canEdit={canEdit} />
        {/* Unlike the settings around it, assistant storytellers keep the territories too, as the
            API lets them: who holds which changes in play, as the Authority proclaims it. */}
        {troupe.feeding !== "off" && troupe.feeding_territories && (
          <FeedingTerritories troupeId={troupe.id} canManage={!troupe.archived && (canEdit || troupe.my_role === "assistant_storyteller")} />
        )}
      </Group>
      <Group title="Names">
        <ClanNamesSetting troupeId={troupe.id} canEdit={canEdit} />
      </Group>
    </div>
  );
}

/** A few settings for one purpose, under its name. A div, not a section, so a card's own section is the one around its heading. */
function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={title}>
      <h2 className="mb-3 font-sans text-xs tracking-wide text-mist uppercase">{title}</h2>
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
  const save = useRulesAction((allowed_sects: string[]) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { allowed_sects } })),
  );
  const allowed = troupe.allowed_sects;
  const sects = (catalogue.data?.traits ?? []).filter((t) => t.category === "sect").map((t) => t.name);

  return (
    <Card title="Sects">
      {!canEdit ? (
        <p className="text-sm">{sectsText(allowed)}</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm text-mist">Which sects may player characters join from? Leave all unticked to take any sect. NPCs are not limited.</legend>
          {sects.map((sect) => (
            <label key={sect} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={allowed.includes(sect)}
                disabled={save.isPending}
                onChange={(e) => save.mutate(e.target.checked ? [...allowed, sect] : allowed.filter((s) => s !== sect))}
              />
              {sect}
            </label>
          ))}
          <ErrorText error={save.error ?? catalogue.error} />
        </fieldset>
      )}
    </Card>
  );
}

/** Which splats' player characters may join, and be built for the troupe: Vampire, Ghoul. At least one. */
function SplatsCard({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const { splats, text } = useSplatsText(troupe);
  const save = useAction((allowed_splats: string[]) =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { allowed_splats } })),
  );
  const allowed = troupe.allowed_splats;

  return (
    <Card title="Splats">
      {!canEdit ? (
        <p className="text-sm">{text} player characters may join.</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm text-mist">
            Which splats may player characters be? Tick at least one: new characters built for the troupe, and those joining it, must be one of these. NPCs are not limited.
          </legend>
          {splats.isPending && <Loading compact />}
          {(splats.data ?? []).map(({ splat, label }) => (
            <label key={splat} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={allowed.includes(splat)}
                disabled={save.isPending || (allowed.length === 1 && allowed.includes(splat))}
                onChange={(e) => save.mutate(e.target.checked ? [...allowed, splat] : allowed.filter((s) => s !== splat))}
              />
              {label}
            </label>
          ))}
          <ErrorText error={save.error ?? splats.error} />
        </fieldset>
      )}
    </Card>
  );
}
