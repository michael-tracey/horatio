import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useMatch, useParams, useSearchParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { NotOpenHere } from "../../components/NotOpenHere";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { LinkButton } from "../../components/LinkButton";
import { BackLink } from "../../components/BackLink";
import { useMe } from "../../hooks";
import { BackstoryTab, useBackstoryStanding } from "./BackstoryTab";
import { characterTabGroups, type TabGroup } from "./characterTabs";
import { CreationWizard } from "./creation/Wizard";
import { choiceName } from "./creation/logic";
import { abilities, roleLabel } from "../troupe/roles";
import { SectionPicker } from "../../components/SectionPicker";
import { DowntimeTab } from "./DowntimeTab";
import { EquipmentTab } from "./EquipmentTab";
import { GiveEquipment } from "./GiveEquipment";
import { InCharacterTab } from "./InCharacter";
import { InfluenceTab } from "./InfluenceTab";
import { CharacterLogTab } from "./LogTab";
import { NpcBuilder } from "./NpcBuilder";
import { KindBadge } from "./NpcKindBadge";
import { CharacterMenu } from "./Actions";
import { givable } from "../troupe/GiveNpc";
import { LeavingCard } from "./Leaving";
import { RenameCharacter } from "./Rename";
import { CharacterPronouns } from "./Pronouns";
import { CharacterSire } from "./Sire";
import { Pronouns } from "../../components/PronounsInput";
import { AtHandle } from "../../components/PersonPicker";
import { CharacterPicture } from "./Picture";
import { QuestsTab } from "./QuestsTab";
import { ResultsTab } from "./ResultsTab";
import { ProjectsCard } from "./Projects";
import { newResults, useSeenUpTo } from "./resultsSeen";
import { CharacterShared } from "../troupe/SharedBackground";
import { ChoiceInfo } from "./Info";
import { useClanName } from "../../components/ClanNames";
import { SheetTab } from "./SheetTab";
import { rulesTroupe } from "./rules";
import { NextForCharacter } from "./NextSteps";
import { NominationsAbout } from "../nominations/NominationsAbout";
import { RemembrancesCard } from "../nominations/Remembrances";
import { StatusTitlesTab } from "./StatusTitlesTab";
import { TroupesTab } from "./TroupesTab";
import { XpTab } from "./XpTab";
import { useSevenTaps } from "../jyhad/taps";
import { useCatalogue } from "../../catalogue";

export function CharacterPage() {
  const { characterId = "" } = useParams();
  // The Downtime and Backstory tabs have their own main button (Submit, Approve), so
  // Play steps back there (#920).
  const onDowntime = !!useMatch("/characters/:characterId/downtime");
  const onBackstory = !!useMatch("/characters/:characterId/backstory");
  // In the wizard, Continue creating would only lead back to where the player is.
  const onCreate = !!useMatch("/characters/:characterId/create/*");
  const me = useMe();
  const character = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}", { params: { path: { character_id: characterId } } })),
  });
  const [renaming, setRenaming] = useState(false);
  const [saying, setSaying] = useState(false);
  const [siring, setSiring] = useState(false);
  // A vampire's sire (#707): whether the caller may give it puts Sire… in the menu.
  const sireOf = useQuery({
    queryKey: ["sire", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/sire", { params: { path: { character_id: characterId } } })),
    enabled: character.data?.splat === "vampire",
  });
  // The Shared backgrounds tab shows once the character has put dots in one.
  const shared = useQuery({
    queryKey: ["character-shared", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/shared-backgrounds", { params: { path: { character_id: characterId } } })),
    enabled: character.data?.kind === "pc",
  });
  // A PC's influence is for its player and its home troupe's storytellers and assistants.
  const homeId = character.data?.kind === "pc" && character.data.player_id !== me.data?.id ? character.data.home_troupe_id : null;
  const home = useQuery({
    queryKey: ["troupe", homeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: homeId! } } })),
    enabled: !!homeId,
  });
  // The Quests tab shows to its player while a troupe it is in runs quests, and to its
  // home troupe's storytellers and assistants while that troupe runs them (#614).
  const staffQuests = !!home.data?.quests_enabled && abilities(home.data.my_role, !!me.data?.is_custodian).running;
  const quests = useQuery({
    queryKey: ["character-quests", characterId],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/quests", { params: { path: { character_id: characterId } } })),
    enabled: character.data?.kind === "pc" && (character.data.player_id === me.data?.id || staffQuests),
  });

  // An NPC's storytellers can give it to a player (#481).
  const npcTroupeId = character.data?.kind === "npc" ? character.data.home_troupe_id : null;
  const npcTroupe = useQuery({
    queryKey: ["troupe", npcTroupeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: npcTroupeId! } } })),
    enabled: !!npcTroupeId,
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
    <LinkButton variant={secondary ? "secondary" : "primary"} to={to}>
      {label}
    </LinkButton>
  );
  // None where its troupe doesn't use the Play View (#673).
  const play = c.play_view && primaryLink(`/play/characters/${c.id}`, "Play", onDowntime || onBackstory);
  const rename = renaming && <RenameCharacter key={c.id} character={c} asCustodian={custodian} onDone={() => setRenaming(false)} />;
  const pronouns = saying && <CharacterPronouns key={c.id} character={c} onDone={() => setSaying(false)} />;
  const sire = siring && sireOf.data && <CharacterSire key={c.id} character={c} sire={sireOf.data} onDone={() => setSiring(false)} />;
  const onSire = sireOf.data?.can_change && !siring ? () => setSiring(true) : undefined;
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
                  onSire={onSire}
                  canDelete
                  canExport
                  canGive={!!npcTroupe.data && abilities(npcTroupe.data.my_role, custodian).storyteller && !npcTroupe.data.archived && givable(c)}
                  canPostInCharacter={c.status === "active" && !!npcTroupe.data && abilities(npcTroupe.data.my_role, custodian).running && !npcTroupe.data.archived}
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
        {sire}
        <Tabs
          tabs={[
            ...(!c.creation_complete ? [{ to: `${base}/create`, label: "Create" }] : []),
            { to: base, label: "Build", end: true },
            { to: `${base}/sheet`, label: "Sheet" },
            { to: `${base}/status`, label: "Status & Titles" },
            { to: `${base}/equipment`, label: "Equipment" },
            { to: `${base}/influence`, label: "Influence" },
            { to: `${base}/ic-chat`, label: "IC chat" },
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
          <Route path="ic-chat" element={<InCharacterTab character={c} />} />
          <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
          {/* Once it's made, the wizard's address leads to the NPC (as finishing it does). */}
          <Route path="create/:step?" element={c.creation_complete ? <Navigate to={base} replace /> : <CreationWizard character={c} />} />
          {/* A tab not open to them, or no such tab (#907); not before Backstory is known. */}
          <Route path="*" element={backstory.isLoading ? <Loading /> : <NotOpenHere name={c.name} to={base} />} />
        </Routes>
      </>
    );
  }

  const mine = c.player_id === me.data?.id;
  // Its home troupe's storytellers and assistants keep its projects (#507).
  const keepsProjects = !mine && !!home.data && abilities(home.data.my_role, custodian).running;
  // While its player is still creating it, the page opens on the wizard (#915), with the
  // sheet on a tab of its own, and the tabs for a character in play (experience,
  // downtimes, influence) wait until it's done.
  const creating = mine && !c.creation_complete;
  const influence = mine || custodian || (!!home.data && abilities(home.data.my_role, custodian).running);
  // The custodian renames at any time; the player once every 3 months in a troupe.
  const canRename = custodian || (mine && c.status === "active");
  const renameOn = !custodian && mine && c.status === "active" ? c.next_rename_on : null;
  // Badges are the staff's to print; whoever else sees the page is staff.
  const sheet = (
    <>
      {/* For its player, the Player Nominations about it (#470): nothing while there are none. */}
      {mine && c.kind === "pc" && <NominationsAbout character={c} />}
      <SheetTab
        character={c}
        mine={mine}
        badge={!mine || custodian}
        give={!mine && (custodian || (!!home.data && abilities(home.data.my_role, custodian).running))}
      />
    </>
  );

  return (
    <>
      {!mine && <StaffView character={c} />}
      <Header character={c}>
        <PageTitle
          subtitle={<Identity character={c} lead={c.splat} />}
          actions={
            <div className="flex flex-wrap items-center gap-3">
              {c.status === "retired" && <Badge>Retired</Badge>}
              {creating ? !onCreate && primaryLink(`${base}/create`, "Continue creating") : play}
              {c.status === "active" && <GiveEquipment character={c} />}
              <CharacterMenu
                character={c}
                canRename={canRename && !renaming && !renameOn}
                renameOn={renameOn}
                onRename={() => setRenaming(true)}
                canRetire={mine && c.status === "active"}
                onPronouns={mine && c.status === "active" && !saying ? () => setSaying(true) : undefined}
                onSire={onSire}
                canDelete={mine}
                canMove={custodian}
                canExport={mine || custodian}
                canMakeNpc={!mine && c.status === "retired" && !!home.data && abilities(home.data.my_role, custodian).running && !home.data.archived}
              />
            </div>
          }
        >
          {name}
        </PageTitle>
      </Header>
      {rename}
      {c.status === "retired" && <LeavingCard character={c} canChange={mine || custodian || (!!home.data && abilities(home.data.my_role, custodian).running)} />}
      {c.status === "retired" && c.kind === "pc" && <RemembrancesCard character={c} />}
      {pronouns}
      {sire}
      {/* What is next for it (#1051), for its player; not in the wizard, which is the one thing next. */}
      {mine && c.status === "active" && !onCreate && <NextForCharacter characterId={c.id} />}
      <CharacterTabs
        groups={characterTabGroups({
          base,
          mine,
          creating,
          staffQuests,
          questsOn: !!quests.data?.enabled,
          influence,
          keepsProjects,
          shared: !!shared.data?.length,
          backstory: !!backstory.data?.read,
          due: waiting.data?.due ? 1 : 0,
          newResults: waiting.data ? newResults(waiting.data.delivered, seen) : 0,
        })}
      />
      <Routes>
        <Route index element={creating ? <Navigate to={`${base}/create`} replace /> : sheet} />
        {/* The sheet's own address while its player creates it; once it's made, the page itself. */}
        <Route path="sheet" element={creating ? sheet : <Navigate to={base} replace />} />
        <Route path="status" element={<StatusTitlesTab character={c} />} />
        <Route path="equipment" element={<EquipmentTab character={c} />} />
        <Route path="xp" element={<XpTab character={c} mine={mine} selfEntering={mine && !c.home_troupe_id && c.status === "active"} />} />
        <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
        {influence && <Route path="influence" element={<InfluenceTab character={c} mine={mine} />} />}
        <Route path="shared" element={<CharacterShared characterId={c.id} />} />
        {keepsProjects && <Route path="projects" element={<ProjectsCard characterId={c.id} />} />}
        {/* One Quests route, as one tab (#788): its player's view, else its staff's. */}
        {quests.data?.enabled && (mine || staffQuests) && <Route path="quests/*" element={<QuestsTab characterId={c.id} staffOf={mine ? undefined : home.data?.id} />} />}
        {backstory.data?.read && <Route path="backstory" element={<BackstoryTab character={c} />} />}
        {/* Once it's made, the wizard's address leads to the sheet (as finishing it does). */}
        {mine && <Route path="create/:step?" element={creating ? <CreationWizard character={c} /> : <Navigate to={base} replace />} />}
        {mine && (
          <>
            <Route path="troupes" element={<TroupesTab character={c} />} />
            <Route path="downtime" element={<DowntimeTab characterId={c.id} />} />
            <Route path="results" element={<ResultsTab characterId={c.id} />} />
          </>
        )}
        {/* A tab not open to them, or no such tab (#907); not before the tabs that wait on an answer are known. */}
        <Route path="*" element={backstory.isLoading || quests.isLoading || home.isLoading ? <Loading /> : <NotOpenHere name={c.name} to={base} />} />
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
      <BackLink label={t.name} to={`/troupes/${t.id}/${back}`} />
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

/**
 * A PC's tabs: on a phone one picker of them all, in their groups (#904); on a
 * wider screen all in one row, as they fit.
 */
function CharacterTabs({ groups }: { groups: TabGroup[] }) {
  return (
    <>
      <SectionPicker label="Character tabs" groups={groups} className="mb-4 sm:hidden" />
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
  const catalogue = useCatalogue(character.splat, rulesTroupe(character));
  const named = useClanName();
  // Tapping the clan's name seven times opens the character's Jyhad card (#537).
  const taps = useSevenTaps(character.id);
  const choices = (sheet.data?.traits ?? []).filter((t) => t.rating === null);
  return (
    <span className="flex flex-wrap items-center gap-x-2">
      <span className="capitalize">{lead}</span>
      {choices.map((t) => (
        <span key={t.id}>
          ·{" "}
          <span className="text-parchment/90" onClick={t.category === "clan" ? taps : undefined}>
            {named(choiceName(t))}
          </span>
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
