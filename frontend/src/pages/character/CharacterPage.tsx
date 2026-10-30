import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { CreationWizard } from "./creation/Wizard";
import { choiceName } from "./creation/logic";
import { abilities } from "../troupe/roles";
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
import { CharacterPicture } from "./Picture";
import { ResultsTab } from "./ResultsTab";
import { CharacterShared } from "../troupe/SharedBackground";
import { ChoiceInfo } from "./Info";
import { SheetTab, useCatalogue } from "./SheetTab";
import { StatusTitlesTab } from "./StatusTitlesTab";
import { TroupesTab } from "./TroupesTab";
import { XpTab } from "./XpTab";

export function CharacterPage() {
  const { characterId = "" } = useParams();
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
  // A PC's influence is for its player and its home troupe's storytellers and assistants.
  const homeId = character.data?.kind === "pc" && character.data.player_id !== me.data?.id ? character.data.home_troupe_id : null;
  const home = useQuery({
    queryKey: ["troupe", homeId],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}", { params: { path: { troupe_id: homeId! } } })),
    enabled: !!homeId,
  });

  if (character.isPending) return <Loading />;
  if (character.error) return <ErrorText error={character.error} />;
  const c = character.data;
  const base = `/characters/${c.id}`;
  const custodian = !!me.data?.is_custodian;
  const play = (
    <Link
      to={`/play/characters/${c.id}`}
      className="inline-flex min-h-10 items-center justify-center rounded-md bg-blood px-5 text-sm font-medium text-parchment hover:bg-blood-bright"
    >
      Play
    </Link>
  );
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
            { to: `${base}/log`, label: "Log" },
          ]}
        />
        <Routes>
          <Route index element={<NpcBuilder character={c} />} />
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
  const influence = mine || custodian || (!!home.data && abilities(home.data.my_role, custodian).running);
  // The custodian renames at any time; the player once every 3 months in a troupe.
  const canRename = custodian || (mine && c.status === "active");
  const renameOn = !custodian && mine && c.status === "active" ? c.next_rename_on : null;

  return (
    <>
      <Header character={c}>
        <PageTitle
          subtitle={<Identity character={c} lead={c.splat} />}
          actions={
            <div className="flex flex-wrap items-center gap-3">
              {c.status === "retired" && <Badge>retired</Badge>}
              {play}
              {c.status === "active" && <GiveEquipment character={c} />}
              <CharacterMenu
                character={c}
                canRename={canRename && !renaming && !renameOn}
                renameOn={renameOn}
                onRename={() => setRenaming(true)}
                canRetire={mine && c.status === "active"}
                onPronouns={mine && c.status === "active" && !saying ? () => setSaying(true) : undefined}
                canDelete={mine || custodian}
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
      <Tabs
        tabs={[
          ...(mine && !c.creation_complete ? [{ to: `${base}/create`, label: "Create" }] : []),
          { to: base, label: "Sheet", end: true },
          { to: `${base}/status`, label: "Status & Titles" },
          { to: `${base}/equipment`, label: "Equipment" },
          { to: `${base}/xp`, label: "Experience" },
          ...(mine
            ? [
                { to: `${base}/troupes`, label: "Troupes" },
                { to: `${base}/downtime`, label: "Downtime" },
                { to: `${base}/results`, label: "Results" },
              ]
            : []),
          ...(influence ? [{ to: `${base}/influence`, label: "Influence" }] : []),
          ...(shared.data?.length ? [{ to: `${base}/shared`, label: "Shared backgrounds" }] : []),
          { to: `${base}/log`, label: "Log" },
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
        {mine && !c.creation_complete && <Route path="create/:step?" element={<CreationWizard character={c} />} />}
        {mine && (
          <>
            <Route path="troupes" element={<TroupesTab character={c} />} />
            <Route path="downtime" element={<DowntimeTab characterId={c.id} />} />
            <Route path="results" element={<ResultsTab characterId={c.id} />} />
          </>
        )}
      </Routes>
    </>
  );
}

/** The character's picture beside its name (the title's own space below moves out here). */
function Header({ character, children }: { character: CharacterOut; children: ReactNode }) {
  return (
    <div className="mb-6 flex items-center gap-4">
      <CharacterPicture character={character} />
      <div className="min-w-0 flex-1 [&>div]:mb-0">{children}</div>
    </div>
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
  const choices = (sheet.data?.traits ?? []).filter((t) => t.rating === null);
  return (
    <span className="flex flex-wrap items-center gap-x-2">
      <span className="capitalize">{lead}</span>
      {choices.map((t) => (
        <span key={t.id}>
          · <span className="text-parchment/90">{choiceName(t)}</span>
          <ChoiceInfo
            choice={t}
            shown={choiceName(t)}
            about={catalogue.data?.traits.find((c) => c.category === t.category && c.name === t.name)}
          />
        </span>
      ))}
    </span>
  );
}
