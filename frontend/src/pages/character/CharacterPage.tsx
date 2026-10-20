import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { CreationWizard } from "./creation/Wizard";
import { DowntimeTab } from "./DowntimeTab";
import { CharacterLogTab } from "./LogTab";
import { NpcBuilder } from "./NpcBuilder";
import { CharacterMenu } from "./Actions";
import { RenameCharacter } from "./Rename";
import { CharacterPicture } from "./Picture";
import { ResultsTab } from "./ResultsTab";
import { SheetTab } from "./SheetTab";
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
                {play}
                <CharacterMenu character={c} canRename={!renaming} renameOn={null} onRename={() => setRenaming(true)} canDelete />
              </div>
            }
          >
            {c.name}
          </PageTitle>
        </Header>
        {rename}
        <Tabs
          tabs={[
            ...(!c.creation_complete ? [{ to: `${base}/create`, label: "Create" }] : []),
            { to: base, label: "Build", end: true },
            { to: `${base}/sheet`, label: "Sheet" },
            { to: `${base}/log`, label: "Log" },
          ]}
        />
        <Routes>
          <Route index element={<NpcBuilder character={c} />} />
          <Route path="sheet" element={<SheetTab character={c} mine={false} badge />} />
          <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
          {!c.creation_complete && <Route path="create/:step?" element={<CreationWizard character={c} />} />}
        </Routes>
      </>
    );
  }

  const mine = c.player_id === me.data?.id;
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
              <CharacterMenu
                character={c}
                canRename={canRename && !renaming && !renameOn}
                renameOn={renameOn}
                onRename={() => setRenaming(true)}
                canDelete={mine || custodian}
              />
            </div>
          }
        >
          {c.name}
        </PageTitle>
      </Header>
      {rename}
      <Tabs
        tabs={[
          ...(mine && !c.creation_complete ? [{ to: `${base}/create`, label: "Create" }] : []),
          { to: base, label: "Sheet", end: true },
          { to: `${base}/xp`, label: "Experience" },
          ...(mine
            ? [
                { to: `${base}/troupes`, label: "Troupes" },
                { to: `${base}/downtime`, label: "Downtime" },
                { to: `${base}/results`, label: "Results" },
              ]
            : []),
          { to: `${base}/log`, label: "Log" },
        ]}
      />
      <Routes>
        {/* Badges are the staff's to print; whoever else sees the page is staff. */}
        <Route index element={<SheetTab character={c} mine={mine} badge={!mine || custodian} />} />
        <Route path="xp" element={<XpTab characterId={c.id} selfEntering={mine && !c.home_troupe_id && c.status === "active"} />} />
        <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
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
  const choices = (sheet.data?.traits ?? []).filter((t) => t.rating === null);
  return (
    <span className="flex flex-wrap items-center gap-x-2">
      <span className="capitalize">{lead}</span>
      {choices.map((t) => (
        <span key={t.id} title={t.category_name}>
          · <span className="text-parchment/90">{t.name}</span>
        </span>
      ))}
    </span>
  );
}
