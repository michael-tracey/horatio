import { useQuery } from "@tanstack/react-query";
import { Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { CreationWizard } from "./creation/Wizard";
import { DowntimeTab } from "./DowntimeTab";
import { NpcBuilder } from "./NpcBuilder";
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
        <PageTitle subtitle="NPC" actions={<Badge tone="gold">NPC</Badge>}>
          {c.name}
        </PageTitle>
        <Tabs
          tabs={[
            ...(!c.creation_complete ? [{ to: `${base}/create`, label: "Create" }] : []),
            { to: base, label: "Build", end: true },
            { to: `${base}/sheet`, label: "Sheet" },
          ]}
        />
        <Routes>
          <Route index element={<NpcBuilder character={c} />} />
          <Route path="sheet" element={<SheetTab character={c} mine={false} />} />
          {!c.creation_complete && <Route path="create/:step?" element={<CreationWizard character={c} />} />}
        </Routes>
      </>
    );
  }

  const mine = c.player_id === me.data?.id;

  return (
    <>
      <PageTitle subtitle={<span className="capitalize">{c.splat}</span>} actions={c.status === "retired" ? <Badge>retired</Badge> : undefined}>
        {c.name}
      </PageTitle>
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
        ]}
      />
      <Routes>
        <Route index element={<SheetTab character={c} mine={mine} />} />
        <Route path="xp" element={<XpTab characterId={c.id} />} />
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
