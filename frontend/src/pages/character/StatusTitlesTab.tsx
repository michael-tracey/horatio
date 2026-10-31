import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { BanOut, CharacterOut, CharacterTitlesOut, HeldTitleOut, StatusOut, TitleChoiceOut } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { InfoButton } from "../../components/InfoButton";
import { pageLabel } from "../../components/TraitInfo";
import { Badge, Button, Card, ErrorText } from "../../components/ui";
import { useAction } from "../../hooks";
import { aliasText, titleGives, titleGroups } from "../troupe/titleGroups";
import { StatusCard, useStatus, WithReason } from "./StatusCard";

/**
 * The character page's Status & Titles tab: the status the character holds now, a
 * line each, with the status bans below it, and its titles in a sidebar, where the
 * active one is picked (below the status on a phone).
 */
export function StatusTitlesTab({ character }: { character: CharacterOut }) {
  return (
    // minmax(0, …): a ban's one line is cut short rather than widening the page.
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="flex min-w-0 flex-col gap-4">
        <StatusCard character={character} />
        <Bans character={character} />
      </div>
      <aside aria-label="Titles" className="flex min-w-0 flex-col gap-4">
        <TitlesCard character={character} />
      </aside>
    </div>
  );
}

function useTitles(characterId: string) {
  return useQuery({
    queryKey: ["character-titles", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/titles", { params: { path: { character_id: characterId } } })),
  });
}

/**
 * The titles the character holds in its home troupe, the one active, and those it
 * can choose: the troupe's titles of its sect and of any sect. Its player chooses
 * them, unless the troupe keeps titles to staff; staff always can. Only the active
 * title gives status.
 */
function TitlesCard({ character }: { character: CharacterOut }) {
  const titles = useTitles(character.id);
  if (!titles.data) return titles.error ? <ErrorText error={titles.error} /> : null;
  const t = titles.data;
  const active = t.held.find((h) => h.active) ?? null;
  return (
    <Card
      dense
      title="Titles"
      info={
        <InfoButton label="About titles">
          <span className="block">
            A title is a position in {t.troupe_name ?? "a troupe"}, and means nothing outside it. Of the titles a character holds, only the active one gives
            status: a character carries the abiding status of one title, or of its social age, into a game (MET: VTM pp. 311, 313). A title that is not active
            gives none until it is made active again.
          </span>
          <span className="mt-1 block">
            {t.setting === "staff"
              ? `In ${t.troupe_name ?? "the home troupe"}, only staff give titles; players choose which of theirs is active.`
              : "Players choose their character's titles from their sect's, and the storytellers are told."}
          </span>
        </InfoButton>
      }
    >
      <div className="flex flex-col gap-3 text-sm">
        {t.why && <p className="text-mist">{t.why}</p>}
        <section aria-label="Titles held">
          {t.held.length ? (
            <ul className="flex flex-col gap-2">
              {t.held.map((h) => (
                <HeldRow key={h.name} character={character} titles={t} held={h} />
              ))}
            </ul>
          ) : (
            t.troupe_id && <p className="text-mist">{character.name} holds no title here.</p>
          )}
          {t.held.length > 0 && !active && (
            <p className="mt-1 text-xs text-blood-bright">No title is active, so none gives status. Make one active to gain its status.</p>
          )}
        </section>
        {t.choices.length > 0 && (t.acting || t.setting === "staff") && <Choices character={character} titles={t} active={active} />}
      </div>
    </Card>
  );
}

function HeldRow({ character, titles, held }: { character: CharacterOut; titles: CharacterTitlesOut; held: HeldTitleOut }) {
  const path = { character_id: character.id };
  const activate = useAction(() => unwrap(api.PUT("/api/characters/{character_id}/titles/active", { params: { path }, body: { name: held.name } })));
  const giveUp = useAction(() => unwrap(api.DELETE("/api/characters/{character_id}/titles/{name}", { params: { path: { ...path, name: held.name } } })));
  const [asking, setAsking] = useState(false);
  const page = pageLabel(held.page);
  return (
    <li aria-label={held.name} className="flex flex-col gap-0.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className={held.active ? "font-medium text-gold" : "text-parchment"}>{held.name}</span>
          {(held.sect ?? held.clan) && <span className="text-xs text-mist">{held.sect ?? held.clan}</span>}
          {held.alias_of && <span className="text-xs text-mist">{aliasText(held)}</span>}
          {held.active ? <Badge tone="gold">active</Badge> : <Badge>not active</Badge>}
          {held.out_of_sect && <Badge tone="blood">out of sect</Badge>}
        </span>
        {!asking && (
          <span className="flex flex-wrap gap-1">
            {titles.can_switch && !held.active && (
              <Button variant="ghost" className="min-h-8 px-2 text-xs" aria-label={`Make ${held.name} active`} disabled={activate.isPending} onClick={() => activate.mutate(undefined)}>
                Make active
              </Button>
            )}
            {titles.acting && (
              <Button variant="ghost" className="min-h-8 px-2 text-xs" aria-label={`Give up ${held.name}`} onClick={() => setAsking(true)}>
                Give up
              </Button>
            )}
          </span>
        )}
      </div>
      <span className={held.active ? "text-xs text-parchment/80" : "text-xs text-mist"}>
        {titleGives(held.status, held)}
        {!held.active && held.status.length > 0 && " while active"}
        {page && ` · ${page}`}
      </span>
      {held.note && <span className="text-xs text-mist">{held.note}</span>}
      {asking && (
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <span>
            Give up {held.name}
            {held.active && held.status.length > 0 ? ", and the status it gives" : ""}?
          </span>
          <Button className="min-h-8 px-2 text-xs" disabled={giveUp.isPending} onClick={() => giveUp.mutate(undefined)}>
            Yes, give it up
          </Button>
          <Button variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => setAsking(false)}>
            Cancel
          </Button>
        </span>
      )}
      <ErrorText error={activate.error ?? giveUp.error} />
    </li>
  );
}

/**
 * The titles the character can choose, by sect: each with the status it gives and
 * who holds it. Open at first only while the character holds no title, so the
 * sidebar stays short once it does.
 */
function Choices({ character, titles, active }: { character: CharacterOut; titles: CharacterTitlesOut; active: HeldTitleOut | null }) {
  const [open, setOpen] = useState(titles.held.length === 0);
  const groups = titleGroups(titles.sect ? [titles.sect] : [], titles.choices);
  return (
    <section aria-label="Titles to choose" className="flex flex-col gap-2 border-t border-ash pt-3">
      <h3 className="font-sans text-sm tracking-normal">
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="flex items-center gap-1.5 text-left text-gold hover:text-parchment">
          <span aria-hidden>{open ? "▾" : "▸"}</span>
          {titles.held.length ? "Choose another title" : "Choose a title"}
          {titles.troupe_name ? ` in ${titles.troupe_name}` : ""}
        </button>
      </h3>
      {open && groups.map(([sect, list]) => {
        const rows = (
          <ul className="flex flex-col divide-y divide-ash/60">
            {list.map((c) => (
              <ChoiceRow key={c.name} character={character} titles={titles} choice={c} active={active} />
            ))}
          </ul>
        );
        // Titles of any sect give no status in the rules: out of the way until wanted.
        return sect ? (
          <div key={sect}>
            <h4 className="mb-1 text-sm text-gold">{sect} titles</h4>
            {rows}
          </div>
        ) : (
          <details key="any">
            <summary className="cursor-pointer text-sm text-gold">Titles of any sect ({list.length})</summary>
            {rows}
          </details>
        );
      })}
    </section>
  );
}

function ChoiceRow({ character, titles, choice, active }: { character: CharacterOut; titles: CharacterTitlesOut; choice: TitleChoiceOut; active: HeldTitleOut | null }) {
  const [asking, setAsking] = useState(false);
  const take = useAction((makeActive: boolean) =>
    unwrap(api.POST("/api/characters/{character_id}/titles", { params: { path: { character_id: character.id } }, body: { name: choice.name, active: makeActive } })),
  );
  const page = pageLabel(choice.page);
  const alias = aliasText(choice);
  return (
    <li aria-label={choice.name} className="flex flex-col gap-1 py-1.5">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 flex-1">
          <span className="text-parchment">{choice.name}</span>
          {alias && <span className="text-xs text-mist"> — {alias}</span>}
          <span className="block text-xs text-mist">
            {titleGives(choice.status, choice)}
            {page && ` · ${page}`}
          </span>
          {choice.note && <span className="block text-xs text-mist">{choice.note}</span>}
          {choice.holders.length > 0 && (
            <span className="block text-xs text-mist">
              Held by {choice.holders.join(", ")}
              {choice.unique && !choice.open && ": only one holds it at a time, so ask your storytellers"}
            </span>
          )}
        </span>
        {choice.open && !asking && (
          <Button
            variant="ghost"
            className="min-h-8 shrink-0 px-2 text-xs"
            aria-label={`Take ${choice.name}`}
            disabled={take.isPending}
            // The first title held is active at once; another asks.
            onClick={() => (titles.held.length ? setAsking(true) : take.mutate(false))}
          >
            Take
          </Button>
        )}
      </div>
      {asking && (
        <div role="group" aria-label={`Take ${choice.name}`} className="flex flex-col gap-2 rounded-md border border-ash p-2 text-xs">
          <p>
            {active
              ? `Make ${choice.name} the active title, in place of ${active.name}? Only the active title gives status.`
              : `Make ${choice.name} the active title? No title is active now, and only the active one gives status.`}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button className="min-h-8 px-2 text-xs" disabled={take.isPending} onClick={() => take.mutate(true)}>
              Make it active
            </Button>
            <Button variant="secondary" className="min-h-8 px-2 text-xs" disabled={take.isPending} onClick={() => take.mutate(false)}>
              {active ? `Keep it beside ${active.name}` : "Keep it, not active"}
            </Button>
            <Button variant="ghost" className="min-h-8 px-2 text-xs" onClick={() => setAsking(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
      <ErrorText error={take.error} />
    </li>
  );
}

/** Whether a ban holds, in a word or two. */
function holds(ban: BanOut): string {
  if (ban.marked === false) return "exempt";
  return ban.applies ? "applies" : "does not apply";
}

/**
 * The status bans: those that apply, and for staff every ban of the sect, a line
 * each. Each opens in a panel over the page (the whole screen on a phone) saying
 * what it does and why it holds; there staff apply or lift it with a reason.
 */
function Bans({ character }: { character: CharacterOut }) {
  const status = useStatus(character.id);
  const [open, setOpen] = useState<string | null>(null);
  const s = status.data;
  if (!s?.accepted) return null;
  const bans = s.bans.filter((b) => b.applies || s.staff);
  const shown = bans.find((b) => b.applies_to === open) ?? null;
  return (
    <Card dense title="Status bans">
      {bans.length ? (
        <ul className="flex flex-col gap-1">
          {bans.map((b) => (
            <li key={b.applies_to}>
              <button
                type="button"
                aria-label={`${b.level} ban: ${b.applies_to}`}
                onClick={() => setOpen(b.applies_to)}
                className="flex min-h-9 w-full items-center gap-2 rounded-md px-1.5 text-left hover:bg-night"
              >
                <Badge tone={b.applies ? "blood" : "mist"}>{b.level}</Badge>
                <span className={`min-w-0 flex-1 truncate text-sm ${b.applies ? "text-parchment" : "text-mist"}`}>{b.applies_to}</span>
                <span className="shrink-0 text-xs text-mist">{holds(b)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-mist">No status ban applies to {character.name}.</p>
      )}
      <Dialog title={shown?.level === "greater" ? "Greater status ban" : "Lesser status ban"} open={!!shown} onClose={() => setOpen(null)} phoneFull>
        {shown && <BanPanel character={character} status={s} ban={shown} />}
      </Dialog>
    </Card>
  );
}

/** One ban: what it does, why it holds, and for staff, applying or lifting it with a reason. */
function BanPanel({ character, status, ban }: { character: CharacterOut; status: StatusOut; ban: BanOut }) {
  const mark = useAction((body: { mark: "applies" | "exempt" | null; reason: string }) =>
    unwrap(api.PUT("/api/characters/{character_id}/status/bans", { params: { path: { character_id: character.id } }, body: { ban: ban.applies_to, ...body } })),
  );
  const why =
    ban.marked === false
      ? `Staff made ${character.name} exempt: ${ban.reason}`
      : ban.marked
        ? `Staff say it applies: ${ban.reason}`
        : ban.by_sheet
          ? `It applies: ${character.name}'s sheet shows it.`
          : ban.by_sheet === false
            ? `It does not apply: ${character.name}'s sheet does not show it.`
            : "The sheet cannot show it: staff say whether it applies.";
  const page = pageLabel(ban.page);
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="text-parchment">
        <Badge tone={ban.applies ? "blood" : "mist"}>{ban.level}</Badge> {ban.applies_to}
      </p>
      <p className="text-mist">
        A lesser ban cuts fleeting status to 3, a greater to 1 (MET: VTM p. 312).{page && ` ${page}.`}
      </p>
      <p>{why}</p>
      {status.staff && (
        <div className="flex flex-wrap gap-1">
          {ban.applies && ban.marked !== false && (
            <WithReason label="Exempt" name={`Exempt ${character.name}`} needed pending={mark.isPending} onConfirm={(reason) => mark.mutate({ mark: "exempt", reason })} />
          )}
          {!ban.applies && <WithReason label="It applies" needed pending={mark.isPending} onConfirm={(reason) => mark.mutate({ mark: "applies", reason })} />}
          {ban.marked !== null && (
            <Button variant="ghost" className="min-h-8 px-2 text-xs" disabled={mark.isPending} onClick={() => mark.mutate({ mark: null, reason: "" })}>
              As the sheet shows
            </Button>
          )}
        </div>
      )}
      <ErrorText error={mark.error} />
    </div>
  );
}
