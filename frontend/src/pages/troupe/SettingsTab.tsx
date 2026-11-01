import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { TroupeOut } from "../../api/types";
import { Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { BadgeSetting } from "./BadgeSetting";
import { DiablerieFlaws } from "./DiablerieFlaws";
import { FeedingSetting } from "./FeedingSetting";
import { FeedingTerritories } from "./FeedingTerritories";
import { GolcondaSetting } from "./GolcondaSetting";
import { ExperienceDefaults, StartingBlood } from "./StartingSection";
import { StatusSetting, TitlesSetting } from "./StatusSetting";
import { WhosWhoSetting } from "./WhosWhoSetting";
import { XpRangeCard } from "./XpRange";

/**
 * The settings for the whole troupe, set once a season or so, by what they are
 * for: who may join, XP, status and titles, what happens at game, and feeding. Its
 * storytellers change them; the troupe's other running staff read them. The
 * troupe's rules for traits are on the Rules tab beside it.
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
      </Group>
      <Group title="Status and titles">
        <StatusSetting troupe={troupe} canEdit={canEdit} />
        <TitlesSetting troupe={troupe} canEdit={canEdit} />
        {troupe.whos_who && <WhosWhoSetting troupe={troupe} canEdit={canEdit} />}
        <GolcondaSetting troupeId={troupe.id} canEdit={canEdit} />
      </Group>
      <Group title="At game">
        <BadgeSetting troupe={troupe} canEdit={canEdit} />
        <StartingBlood troupeId={troupe.id} canEdit={canEdit} />
        <DiablerieFlaws troupeId={troupe.id} canEdit={canEdit} />
      </Group>
      <Group title="Feeding">
        <FeedingSetting troupeId={troupe.id} canEdit={canEdit} />
        {troupe.feeding !== "off" && troupe.feeding_territories && (
          <FeedingTerritories troupeId={troupe.id} canManage={!troupe.archived && (canEdit || troupe.my_role === "assistant_storyteller")} />
        )}
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
  const catalogue = useQuery({
    queryKey: ["catalogue", "vampire", null],
    queryFn: () => unwrap(api.GET("/api/rules/{splat}", { params: { path: { splat: "vampire" }, query: {} } })),
    staleTime: 5 * 60_000,
    enabled: canEdit,
  });
  const save = useAction((allowed_sects: string[]) =>
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
