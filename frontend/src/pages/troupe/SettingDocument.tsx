import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { SettingEntryOut, SettingOut } from "../../api/types";
import { useClanName } from "../../components/ClanNames";
import { Markdown } from "../../components/Markdown";
import { ErrorText, Loading } from "../../components/ui";
import { initialXpText, rarityTiers, settingText } from "./settingDocument";

/** The troupe's Setting Style Document, asked for once by every reader. */
export function useSetting(troupeId: string) {
  return useQuery({
    queryKey: ["setting", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/setting", { params: { path: { troupe_id: troupeId } } })),
  });
}

/** The document's colours: on the app's dark page, or black on white for print. */
const TONES = {
  page: { title: "text-parchment", soft: "text-mist", head: "text-gold", plain: "text-parchment" },
  print: { title: "text-black", soft: "text-neutral-700", head: "text-black font-semibold", plain: "text-black" },
};
type Tone = (typeof TONES)["page"];

/**
 * The troupe's Setting Style Document as its players read it (MET: VTM pp. 331–336):
 * what its staff write (#770) and what its own settings give (#771), in the order of
 * the book's examples. The Setting tab, the profile and the printed page all show it.
 * `editBase`, the troupe page's address, adds "Edit" links to the parts built from
 * the troupe's settings, for its running staff.
 */
export function SettingDocument({ setting: s, editBase, print = false }: { setting: SettingOut; editBase?: string; print?: boolean }) {
  const named = useClanName();
  const tone = print ? TONES.print : TONES.page;
  const g = s.generated;
  const title = s.chronicle || s.troupe;
  return (
    <article className="flex flex-col gap-6" aria-label="Setting Style Document">
      <header>
        <h2 className={`font-display text-2xl ${tone.title}`}>{title}</h2>
        {s.subtitle && <p className={tone.soft}>{s.subtitle}</p>}
      </header>

      <dl className="grid gap-4 text-sm sm:grid-cols-2">
        <Motifs label="Theme" entries={s.themes} tone={tone} />
        <Motifs label="Mood" entries={s.moods} tone={tone} />
        <Item label="Scope" tone={tone}>
          <p>{s.locale || "No locale set"}</p>
          {s.power && <p className={`whitespace-pre-line ${tone.soft}`}>Power: {s.power}</p>}
          {s.agency && <p className={`whitespace-pre-line ${tone.soft}`}>Agency: {s.agency}</p>}
        </Item>
        <Item label="Graduated XP cap" tone={tone}>
          <p>{g.graduated ? "Yes" : "No"}</p>
        </Item>
      </dl>

      <Part tone={tone} title="Setting" edit={editBase && { to: `${editBase}/settings`, label: "Edit in Settings" }}>
        <p className="text-sm">{settingText(g)}</p>
      </Part>

      {s.teaser && (
        <Part tone={tone} title="Chronicle teaser">
          <Markdown text={s.teaser} />
        </Part>
      )}

      <Part tone={tone} title="Clan rarity adjustments" edit={editBase && { to: `${editBase}/house-rules/starting`, label: "Edit under House rules" }}>
        <dl className="flex flex-col gap-2 text-sm">
          {rarityTiers(g.clan_rarity).map((tier) => (
            <div key={tier.rarity} className="grid gap-1 sm:grid-cols-[10rem_1fr]">
              <dt className={tone.soft}>{tier.label}</dt>
              <dd>
                {tier.changes.length === 0 ? (
                  "Settings default"
                ) : (
                  <ul className="flex flex-col gap-1">
                    {tier.changes.map((c) => (
                      <li key={c.clan}>
                        {named(c.clan)}
                        {c.book && c.book !== c.rarity && <span className={tone.soft}>, from {c.book}</span>}
                        {c.note && <span className={tone.soft}>, {c.note}</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
            </div>
          ))}
        </dl>
      </Part>

      <Part tone={tone} title="Cost modifications" edit={editBase && { to: `${editBase}/house-rules/costs`, label: "Edit under House rules" }}>
        <Lines lines={g.costs} />
      </Part>

      <Part tone={tone} title="Setting-specific mechanics" edit={editBase && { to: `${editBase}/house-rules/checks`, label: "Edit under House rules" }}>
        <Lines lines={[initialXpText(g), ...g.mechanics]} />
      </Part>

      {s.notes.length > 0 && (
        <Part tone={tone} title="Storyteller notes">
          <ul className="flex flex-col gap-3">
            {s.notes.map((n) => (
              <li key={n.id}>
                <Markdown text={n.description} />
              </li>
            ))}
          </ul>
        </Part>
      )}
    </article>
  );
}

/** The document, fetched: for the Setting tab and the profile. */
export function SettingDocumentFor({ troupeId, editBase }: { troupeId: string; editBase?: string }) {
  const setting = useSetting(troupeId);
  if (setting.isPending) return <Loading />;
  if (setting.error) return <ErrorText error={setting.error} />;
  return <SettingDocument setting={setting.data} editBase={editBase} />;
}

function Item({ label, tone, children }: { label: string; tone: Tone; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className={`text-xs tracking-wide uppercase ${tone.head}`}>{label}</dt>
      <dd className="flex flex-col gap-1">{children}</dd>
    </div>
  );
}

/** Themes or moods: their names, as the book writes them ("Desperate/Bitter"), each with its description. */
function Motifs({ label, entries, tone }: { label: string; entries: SettingEntryOut[]; tone: Tone }) {
  return (
    <Item label={entries.length > 1 ? `${label}s` : label} tone={tone}>
      {entries.length === 0 ? (
        <p className={tone.soft}>None chosen yet</p>
      ) : (
        <>
          <p>{entries.map((e) => e.name).join(" / ")}</p>
          {entries
            .filter((e) => e.description)
            .map((e) => (
              <div key={e.id} className={tone.soft}>
                <span className={tone.plain}>{e.name}:</span> <Markdown text={e.description} />
              </div>
            ))}
        </>
      )}
    </Item>
  );
}

function Part({ title, tone, edit, children }: { title: string; tone: Tone; edit?: { to: string; label: string } | ""; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 break-inside-avoid" aria-label={title}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className={`text-base ${tone.head}`}>{title}</h3>
        {edit && (
          <Link to={edit.to} className="text-xs text-mist underline hover:text-parchment print:hidden">
            {edit.label}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function Lines({ lines }: { lines: string[] }) {
  if (lines.length === 0) return <p className="text-sm">Settings default</p>;
  return (
    <ul className="flex list-disc flex-col gap-1 pl-5 text-sm">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

/**
 * The setting in brief, for the creation wizard's Concept step (#771): the themes,
 * moods and teaser of the troupe a character is built to the rules of, so the player
 * builds to it (MET: VTM p. 331, step 1), with a link to the whole document. Nothing
 * when the troupe hasn't written any of them.
 */
export function SettingSummary({ troupeId }: { troupeId: string }) {
  const setting = useSetting(troupeId);
  const s = setting.data;
  if (!s || (!s.themes.length && !s.moods.length && !s.teaser)) return null;
  const names = (entries: SettingEntryOut[]) => entries.map((e) => e.name).join(" / ");
  return (
    <section aria-label="The setting you're building for" className="flex flex-col gap-2 rounded-md border border-ash p-3 text-sm">
      <h3 className="text-base text-gold">
        {s.chronicle || s.troupe}
        {s.subtitle && <span className="text-mist">: {s.subtitle}</span>}
      </h3>
      {s.themes.length > 0 && (
        <p>
          <span className="text-mist">{s.themes.length > 1 ? "Themes" : "Theme"}: </span>
          {names(s.themes)}
        </p>
      )}
      {s.moods.length > 0 && (
        <p>
          <span className="text-mist">{s.moods.length > 1 ? "Moods" : "Mood"}: </span>
          {names(s.moods)}
        </p>
      )}
      {s.teaser && (
        <div className="line-clamp-4 text-mist">
          <Markdown text={s.teaser} />
        </div>
      )}
      <Link to={`/troupes/${troupeId}/setting`} className="text-mist underline hover:text-parchment">
        Read the whole setting
      </Link>
    </section>
  );
}
