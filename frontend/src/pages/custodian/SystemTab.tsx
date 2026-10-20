import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import { Badge, Card, ErrorText, Loading } from "../../components/ui";

function when(at: string | null | undefined) {
  return at ? new Date(at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : null;
}

/** What is running here: the build deployed, since when, and whether the database
 * is on its latest migration. Enough to tell whether a fix has gone live. */
export function SystemTab() {
  const system = useQuery({ queryKey: ["system"], queryFn: () => unwrap(api.GET("/api/system")) });
  if (system.isPending) return <Loading />;
  if (system.error) return <ErrorText error={system.error} />;
  const s = system.data;
  const current = s.database_revision != null && s.database_revision === s.code_revision;

  return (
    <Card title="What is running">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <Row label="Version">
          {s.commit && s.commit_url ? (
            <a href={s.commit_url} target="_blank" rel="noreferrer" className="font-mono text-gold hover:underline">
              {s.commit.slice(0, 7)}
              {s.commit.endsWith("-dirty") && " with uncommitted changes"}
            </a>
          ) : (
            <span className="text-mist">A local build, not deployed by deploy/deploy.sh</span>
          )}
        </Row>
        <Row label="Built">{when(s.built_at) ?? <span className="text-mist">Unknown</span>}</Row>
        <Row label="Running since">{when(s.started_at)}</Row>
        <Row label="Database">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono">{s.database_revision ?? "not migrated"}</span>
            <Badge tone={current ? "gold" : "blood"}>{current ? "Up to date" : `Behind: this build expects ${s.code_revision ?? "unknown"}`}</Badge>
          </span>
        </Row>
        <Row label="PostgreSQL">{s.database_version}</Row>
      </dl>
    </Card>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-mist">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}
