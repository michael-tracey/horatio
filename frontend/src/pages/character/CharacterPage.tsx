import { useQuery } from "@tanstack/react-query";
import { Route, Routes, useParams } from "react-router";
import { api, unwrap } from "../../api/client";
import { Badge, ErrorText, Loading, PageTitle, Tabs } from "../../components/ui";
import { useMe } from "../../hooks";
import { CreationWizard } from "./creation/Wizard";
import { DowntimeTab } from "./DowntimeTab";
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
  const mine = c.player_id === me.data?.id;
  const base = `/characters/${c.id}`;

  return (
    <>
      <PageTitle subtitle={<span className="capitalize">{c.splat}</span>} actions={<Badge tone={c.status === "active" ? "gold" : "mist"}>{c.status}</Badge>}>
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
