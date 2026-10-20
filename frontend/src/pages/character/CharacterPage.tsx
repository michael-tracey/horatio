import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { CreationWizard } from "./creation/Wizard";
import { DowntimeTab } from "./DowntimeTab";
import { CharacterLogTab } from "./LogTab";
import { NpcBuilder } from "./NpcBuilder";
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

  if (character.isPending) return <Loading />;
  if (character.error) return <ErrorText error={character.error} />;
  const c = character.data;
  const base = `/characters/${c.id}`;

  if (c.kind === "npc") {
    // Only the troupe's running staff can see an NPC at all, and they can all edit it.
    return (
      <>
        <Header character={c}>
          <PageTitle subtitle={<Identity character={c} lead="NPC" />} actions={<Badge tone="gold">NPC</Badge>}>
            {c.name}
          </PageTitle>
        </Header>
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
          <Route path="sheet" element={<SheetTab character={c} mine={false} />} />
          <Route path="log" element={<CharacterLogTab characterId={c.id} />} />
          {!c.creation_complete && <Route path="create/:step?" element={<CreationWizard character={c} />} />}
        </Routes>
      </>
    );
  }

  const mine = c.player_id === me.data?.id;

  return (
    <>
      <Header character={c}>
        <PageTitle subtitle={<Identity character={c} lead={c.splat} />} actions={c.status === "retired" ? <Badge>retired</Badge> : undefined}>
          {c.name}
        </PageTitle>
      </Header>
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
        <Route index element={<SheetTab character={c} mine={mine} />} />
        <Route path="xp" element={<XpTab characterId={c.id} />} />
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
