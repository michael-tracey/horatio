import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Badge, Button, Card, Empty, ErrorText, Loading, Notice } from "../../components/ui";
import { useAction } from "../../hooks";

/** "2.4 MB": a backup's size, to the nearest sensible unit. */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The database's backups: the nightly ones and any made here, to make and download. */
export function BackupsTab() {
  const backups = useQuery({ queryKey: ["backups"], queryFn: () => unwrap(api.GET("/api/backups")) });
  const make = useAction(() => unwrap(api.POST("/api/backups")));

  if (backups.isPending) return <Loading />;
  if (backups.data && !backups.data.available) {
    return (
      <Card>
        <Notice>Backups are not set up here. On the server they are kept in the directory HORATIO_BACKUP_DIR names.</Notice>
      </Card>
    );
  }

  return (
    <Card
      title="Database backups"
      actions={
        <Button type="button" disabled={make.isPending} onClick={() => make.mutate(undefined)}>
          {make.isPending ? "Backing up…" : "Back up now"}
        </Button>
      }
    >
      <p className="mb-3 text-sm text-mist">
        A backup is the whole database: every account, character and troupe. One is made every night, and copied to cloud storage for 30 days. The server keeps a week of
        backups, nightly or made here; download one to keep it longer. Making or downloading a backup is recorded in the audit log.
      </p>
      <ErrorText error={make.error} />
      {make.data && (
        <p role="status" className="mb-3 text-sm text-gold">
          Backed up as {make.data.name}.
        </p>
      )}
      {backups.data?.backups.length ? (
        <ul className="divide-y divide-ash text-sm">
          {backups.data.backups.map((b) => (
            <li key={b.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="flex flex-wrap items-center gap-2">
                <time dateTime={b.made_at}>{new Date(b.made_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</time>
                <Badge tone={b.manual ? "gold" : "mist"}>{b.manual ? "Made here" : "Nightly"}</Badge>
                <span className="text-xs text-mist">{fileSize(b.size)}</span>
              </span>
              <a href={`/api/backups/${encodeURIComponent(b.name)}`} download className="text-gold hover:underline" aria-label={`Download ${b.name}`}>
                Download
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <Empty>No backups yet.</Empty>
      )}
      <ErrorText error={backups.error} />
    </Card>
  );
}
