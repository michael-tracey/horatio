import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, Route, Routes, useMatch, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Badge, ErrorText, GroupedTabs, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { BackstoryTab, useBackstoryStanding } from "./BackstoryTab";
import { CreationWizard } from "./creation/Wizard";
import { choiceName } from "./creation/logic";
import { abilities, roleLabel } from "../troupe/roles";
import { DowntimeTab } from "./DowntimeTab";
import { EquipmentTab } from "./EquipmentTab";
import { GiveEquipment } from "./GiveEquipment";
import { InfluenceTab } from "./InfluenceTab";
import { CharacterLogTab } from "./LogTab";
import { NpcBuilder } from "./NpcBuilder";
import { KindBadge } from "./NpcKindBadge";
import { CharacterMenu } from "./Actions";
import { LeavingCard } from "./Leaving";
import { RenameCharacter } from "./Rename";
import { CharacterPronouns } from "./Pronouns";
import { Pronouns } from "../../components/PronounsInput";
import { AtHandle } from "../../components/PersonPicker";
import { CharacterPicture } from "./Picture";
import { QuestsTab } from "./QuestsTab";
import { ResultsTab } from "./ResultsTab";
import { newResults, useSeenUpTo } from "./resultsSeen";
import { CharacterShared } from "../troupe/SharedBackground";
import { ChoiceInfo } from "./Info";
import { useClanName } from "../../components/ClanNames";
import { SheetTab, useCatalogue } from "./SheetTab";
import { StatusTitlesTab } from "./StatusTitlesTab";
import { TroupesTab } from "./TroupesTab";
import { XpTab } from "./XpTab";

export function CharacterPage() {
  const { characterId = "" } = useParams();
  // The Downtime tab has its own main button, Submit, so Play steps back there.
  const onDowntime = !!useMatch("/characters/:characterId/downtime");
  const me = useMe();
  const character = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}", { params: { path: { character_id: characterId } } })),
  });
  const [renaming, setRenaming] = useState(false);
  const [saying, setSaying] = useState(false);
  // The Shared backgrounds tab shows once the character has put dots in one.
  const shared = useQuery({
    queryKey: ["character-shared", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/shared-backgrounds", { params: { path: { character_id: characterId } } })),
    enabled: character.data?.kind === "pc",
  });
  // The Quests tab shows to its player while a troupe it is in runs quests.
  const quests = useQuery({
    queryKey: ["character-quests", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/quests", { params: { path: { character_id: characterId } } })),
    enabled: character.data?.kind === "pc" && character.data.player_id === me.data?.id,
  });
  // A PC's influence is for its player and its home troupe's storytellers and assistants.
  const homeId = character.data?.kind === "pc" && character.data.player_id !== me.data?.id ? character.data.home_troupe_id : null;
  const home = useQuery({
    queryKey: ["troupe", homeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: homeId! } } })),
    enabled: !!homeId,
  });

  // The Backstory tab shows to its player and the storytellers deciding on or keeping it.
  const backstory = useBackstoryStanding(characterId, !!character.data);
  // The counts on Downtime and Results, for its player once the character is in play.
  const waiting = useQuery({
    queryKey: ["downtime-waiting", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/downtime/waiting", { params: { path: { character_id: characterId } } })),
    enabled: character.data?.kind === "pc" && character.data.player_id === me.data?.id && character.data.creation_complete,
  });
  const seen = useSeenUpTo(characterId);

  if (character.isPending) return <Loading />;
  if (character.error) return <ErrorText error={character.error} />;
  const c = character.data;
  const base = `/characters/${c.id}`;
  const custodian = !!me.data?.is_custodian;
  const primaryLink = (to: string, label: string, secondary = false) => (
    <Link
      to={to}
      className={`inline-flex min-h-10 items-center justify-center rounded-md px-5 text-sm font-medium text-parchment ${secondary ? "border border-ash bg-dusk hover:border-mist" : "bg-blood hover:bg-blood-bright"}`}
    >
      {label}
    </Link>
  );
  const play = primaryLink(`/play/characters/${c.id}`, "Play", onDowntime);
  const rename = renaming && <RenameCharacter key={c.id} character={c} asCustodian={custodian} onDone={() => setRenaming(false)} />;
  const pronouns = saying && <CharacterPronouns key={c.id} character={c} onDone={() => setSaying(false)} />;
  const name = (
    <>
      {c.name}
      <Pronouns pronouns={c.pronouns} className="text-base text-mist" />
    </>
  );

  if (c.kind === "npc") {
    // Only the troupe's running staff can see an NPC at all, and they can all edit it.
    return (
      <>
        <Header character={c}>
          <PageTitle
            subtitle={<Identity character={c} lead="NPC" />}
            actions={
              <div className="flex flex-wrap items-center gap-3">
                <Badge tone="gold">NPC</Badge>
                <KindBadge kind={c.npc_kind} name={c.npc_kind_name} />
                {play}
                <GiveEquipment character={c} />
                <CharacterMenu
                  character={c}
                  canRename={!renaming}
                  renameOn={null}
                  onRename={() => setRenaming(true)}
                  canRetire={c.status === "active"}
                  onPronouns={saying ? undefined : () => setSaying(true)}
                  canDelete
                />
              </div>
            }
          >
            {name}
          </PageTitle>
        </Header>
        {rename}
        {c.status === "retired" && <LeavingCard character={c} canChange />}
        {pronouns}
        <Tabs
          tabs={[
            ...(!c.creation_complete ? [{ to: `${base}/create`, label: "Create" }] : []),
            { to: base, label: "Build", end: true },
            { to: `${base}/sheet`, label: "Sheet" },
            { to: `${base}/status`, label: "Status & Titles" },
            { to: `${base}/equipment`, label: "Equipment" },
            { to: `${base}/influence`, label: "Influence" },
            ...(backstory.data?.read ? [{ to: `${base}/backstory`, label: "Backstory" }] : []),
            { to: `${base}/log`, label: "Log" },
          ]}
        />
        <Routes>
          <Route index element={<NpcBuilder character={c} />} />
          {backstory.data?.read && <Route path="backstory" element={<BackstoryTab character={c} />} />}
          <Route path="sheet" element={<SheetTab character={c} mine={false} badge />} />
          <Route path="status" element={<StatusTitlesTab character={c} />} />
          <Route path="equipment" element={<EquipmentTab character={c} />} />
          <Route path="influence" element={<InfluenceTab character={c} mine={false} />} />
          <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
          {!c.creation_complete && <Route path="create/:step?" element={<CreationWizard character={c} />} />}
        </Routes>
      </>
    );
  }

  const mine = c.player_id === me.data?.id;
  // While its player is still creating it, the page leads back to the wizard, and the
  // tabs for a character in play (experience, downtimes, influence) wait until it's done.
  const creating = mine && !c.creation_complete;
  const influence = mine || custodian || (!!home.data && abilities(home.data.my_role, custodian).running);
  // The custodian renames at any time; the player once every 3 months in a troupe.
  const canRename = custodian || (mine && c.status === "active");
  const renameOn = !custodian && mine && c.status === "active" ? c.next_rename_on : null;

  return (
    <>
      {!mine && <StaffView character={c} />}
      <Header character={c}>
        <PageTitle
          subtitle={<Identity character={c} lead={c.splat} />}
          actions={
            <div className="flex flex-wrap items-center gap-3">
              {c.status === "retired" && <Badge>Retired</Badge>}
              {creating ? primaryLink(`${base}/create`, "Continue creating") : play}
              {c.status === "active" && <GiveEquipment character={c} />}
              <CharacterMenu
                character={c}
                canRename={canRename && !renaming && !renameOn}
                renameOn={renameOn}
                onRename={() => setRenaming(true)}
                canRetire={mine && c.status === "active"}
                onPronouns={mine && c.status === "active" && !saying ? () => setSaying(true) : undefined}
                canDelete={mine}
                canMove={custodian}
              />
            </div>
          }
        >
          {name}
        </PageTitle>
      </Header>
      {rename}
      {c.status === "retired" && <LeavingCard character={c} canChange={mine || custodian || (!!home.data && abilities(home.data.my_role, custodian).running)} />}
      {pronouns}
      <CharacterTabs
        groups={[
          { label: "Create", tabs: creating ? [{ to: `${base}/create`, label: "Create" }] : [] },
          {
            label: "Sheet",
            tabs: [
              { to: base, label: "Sheet", end: true },
              { to: `${base}/status`, label: "Status & Titles" },
              { to: `${base}/equipment`, label: "Equipment" },
              ...(creating ? [] : [{ to: `${base}/xp`, label: "Experience" }]),
              ...(shared.data?.length ? [{ to: `${base}/shared`, label: "Shared backgrounds" }] : []),
            ],
          },
          {
            label: "Between games",
            tabs: [
              ...(mine && !creating
                ? [
                    { to: `${base}/downtime`, label: "Downtime", count: waiting.data?.due ? 1 : 0, countLabel: "due" },
                    { to: `${base}/results`, label: "Results", count: waiting.data ? newResults(waiting.data.delivered, seen) : 0, countLabel: "new" },
                    ...(quests.data?.enabled ? [{ to: `${base}/quests`, label: "Quests" }] : []),
                  ]
                : []),
              ...(influence && !creating ? [{ to: `${base}/influence`, label: "Influence" }] : []),
            ],
          },
          {
            label: "About",
            tabs: [
              ...(mine ? [{ to: `${base}/troupes`, label: "Troupes" }] : []),
              ...(backstory.data?.read ? [{ to: `${base}/backstory`, label: "Backstory" }] : []),
              { to: `${base}/log`, label: "Log" },
            ],
          },
        ]}
      />
      <Routes>
        {/* Badges are the staff's to print; whoever else sees the page is staff. */}
        <Route
          index
          element={
            <SheetTab
              character={c}
              mine={mine}
              badge={!mine || custodian}
              give={!mine && (custodian || (!!home.data && abilities(home.data.my_role, custodian).running))}
            />
          }
        />
        <Route path="status" element={<StatusTitlesTab character={c} />} />
        <Route path="equipment" element={<EquipmentTab character={c} />} />
        <Route path="xp" element={<XpTab characterId={c.id} selfEntering={mine && !c.home_troupe_id && c.status === "active"} />} />
        <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
        {influence && <Route path="influence" element={<InfluenceTab character={c} mine={mine} />} />}
        <Route path="shared" element={<CharacterShared characterId={c.id} />} />
        {backstory.data?.read && <Route path="backstory" element={<BackstoryTab character={c} />} />}
        {creating && <Route path="create/:step?" element={<CreationWizard character={c} />} />}
        {mine && (
          <>
            <Route path="troupes" element={<TroupesTab character={c} />} />
            <Route path="downtime" element={<DowntimeTab characterId={c.id} />} />
            <Route path="results" element={<ResultsTab characterId={c.id} />} />
            {quests.data?.enabled && <Route path="quests/*" element={<QuestsTab characterId={c.id} />} />}
          </>
        )}
      </Routes>
    </>
  );
}

/**
 * For staff on another player's character: whose it is, as whom they are looking,
 * and the way back to the troupe they came from (named by `?troupe=`, as the log
 * links), or else to its home troupe, or the troupe it is asking to join.
 */
function StaffView({ character: c }: { character: CharacterOut }) {
  const [params] = useSearchParams();
  const me = useMe();
  const troupeId = params.get("troupe") ?? c.home_troupe_id ?? c.asking_troupe_id;
  const troupe = useQuery({
    queryKey: ["troupe", troupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupeId! } } })),
    enabled: !!troupeId,
  });
  const player = useQuery({
    queryKey: ["player", c.player_id],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: c.player_id } } })),
  });
  const t = troupe.data;
  const custodian = !!me.data?.is_custodian;
  if (!t || (!t.my_role && !custodian)) return null;
  // A character asking to make the troupe its home is waiting on Approvals; otherwise it is on the roster.
  const back = c.home_troupe_id !== t.id && c.asking_troupe_id === t.id ? "approvals" : "characters";
  return (
    <div
      role="note"
      aria-label="Viewing as staff"
      className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md border border-gold/40 bg-gold/5 px-3 py-2 text-sm text-mist"
    >
      <span>
        <span className="text-parchment">Viewing as {t.my_role ? roleLabel(t.my_role).toLowerCase() : "custodian"}</span>
        {player.data && (
          <>
            {" "}
            · played by{" "}
            <Link to={`/players/${c.player_id}`} className="text-parchment hover:text-gold">
              {player.data.display_name}
            </Link>{" "}
            <AtHandle handle={player.data.handle} />
          </>
        )}
      </span>
      <Link to={`/troupes/${t.id}/${back}`} className="text-gold underline hover:text-parchment">
        ← back to {t.name}
      </Link>
    </div>
  );
}

/** The character's picture beside its name (the title's own space below moves out here).
 * On a phone the name keeps to one line, cut short if it must, to leave room for the page. */
function Header({ character, children }: { character: CharacterOut; children: ReactNode }) {
  return (
    <div className="mb-4 flex items-center gap-3 sm:mb-6 sm:gap-4">
      <CharacterPicture character={character} />
      <div className="min-w-0 flex-1 [&>div]:mb-0 max-sm:[&>div>div:first-child]:max-w-full max-sm:[&_h1]:truncate max-sm:[&>div]:gap-2">{children}</div>
    </div>
  );
}

type Group = Parameters<typeof GroupedTabs>[0]["groups"][number];

/**
 * A PC's tabs: on a phone in groups, with the open group's tabs under them; on
 * a wider screen all in one row, as they fit. A group of one shows as its tab.
 */
function CharacterTabs({ groups }: { groups: Group[] }) {
  const named = groups.map((g) => (g.tabs.length === 1 ? { ...g, label: g.tabs[0]!.label } : g));
  return (
    <>
      <div className="sm:hidden">
        <GroupedTabs label="Tab groups" groups={named} />
      </div>
      <div className="hidden sm:block">
        <Tabs tabs={groups.flatMap((g) => g.tabs)} />
      </div>
    </>
  );
}

/** Who the character is, beside the name: splat, then the choices that define
 * them (clan, sect, archetype...) in sheet order. */
function Identity({ character, lead }: { character: CharacterOut; lead: string }) {
  const sheet = useQuery({
    queryKey: ["sheet", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sheet", { params: { path: { character_id: character.id } } })),
  });
  const catalogue = useCatalogue(character);
  const named = useClanName();
  const choices = (sheet.data?.traits ?? []).filter((t) => t.rating === null);
  return (
    <span className="flex flex-wrap items-center gap-x-2">
      <span className="capitalize">{lead}</span>
      {choices.map((t) => (
        <span key={t.id}>
          · <span className="text-parchment/90">{named(choiceName(t))}</span>
          <ChoiceInfo
            choice={t}
            shown={named(choiceName(t))}
            about={catalogue.data?.traits.find((c) => c.category === t.category && c.name === t.name)}
          />
        </span>
      ))}
    </span>
  );
}
