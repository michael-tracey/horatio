import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { ClanLogoOut } from "../../api/types";
import { Button, Card, ErrorText, Input, Loading, Notice } from "../../components/ui";
import { useAction } from "../../hooks";

/**
 * A logo for each clan and bloodline, for game badges. The official symbols
 * belong to the game's publisher, so Horatio ships none: the custodian adds
 * images the troupe has the right to use.
 */
export function ClanLogosTab() {
  const logos = useQuery({ queryKey: ["clan-logos"], queryFn: () => unwrap(api.GET("/api/clan-logos")) });
  const [query, setQuery] = useState("");
  if (logos.isPending) return <Loading />;
  if (logos.error) return <ErrorText error={logos.error} />;
  if (!logos.data.available) {
    return (
      <Card>
        <Notice>Uploads are not set up here. On the server they are kept in the directory HORATIO_UPLOAD_DIR names.</Notice>
      </Card>
    );
  }
  const q = query.trim().toLowerCase();
  const shown = logos.data.clans.filter((c) => !q || c.clan.toLowerCase().includes(q));
  const count = logos.data.clans.filter((c) => c.logo).length;

  return (
    <Card title="Clan logos">
      <p className="mb-3 text-sm text-mist">
        Badges show the clan's logo beside the character's picture, or in its place when there is none. The official clan symbols belong to the game's publisher and
        cannot come with Horatio, so upload images your troupes have the right to use. A bloodline without its own logo uses its clan's; a clan without one shows its
        name only. A PNG with a transparent background prints best.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Input type="search" aria-label="Search clans" placeholder="Clan or bloodline…" value={query} onChange={(e) => setQuery(e.target.value)} className="min-w-40 flex-1" />
        <span className="text-sm text-mist">
          {count} of {logos.data.clans.length} have a logo
        </span>
      </div>
      <ul className="grid gap-2 sm:grid-cols-2">
        {shown.map((c) => (
          <ClanRow key={`${c.splat}/${c.clan}`} clan={c} />
        ))}
      </ul>
    </Card>
  );
}

function ClanRow({ clan }: { clan: ClanLogoOut }) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useAction((file: File) => {
    const form = new FormData();
    form.append("clan", clan.clan);
    form.append("splat", clan.splat);
    form.append("file", file);
    return unwrap(api.POST("/api/clan-logos", { body: form as never, bodySerializer: (body: unknown) => body as FormData }));
  });
  const remove = useAction(() => unwrap(api.DELETE("/api/clan-logos/{logo_id}", { params: { path: { logo_id: clan.logo_id! } } })));
  const bloodline = clan.clan.includes(":");
  return (
    <li className="flex items-center gap-3 rounded-md border border-ash p-2">
      <span className="grid h-14 w-14 shrink-0 place-items-center rounded bg-night">
        {clan.logo ? <img src={`${clan.logo}/128.webp`} alt={`${clan.clan} logo`} className="h-12 w-12 object-contain" /> : <span className="text-xs text-mist">none</span>}
      </span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-sm ${bloodline ? "text-parchment/80" : ""}`}>{clan.clan}</span>
        <ErrorText error={upload.error ?? remove.error} />
      </span>
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp,image/heic,.heic"
        aria-label={`Logo for ${clan.clan}`}
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) upload.mutate(file);
        }}
      />
      <span className="flex shrink-0 gap-1">
        <Button type="button" variant="secondary" disabled={upload.isPending} onClick={() => input.current?.click()}>
          {upload.isPending ? "…" : clan.logo ? "Replace" : "Upload"}
        </Button>
        {clan.logo && (
          <Button type="button" variant="ghost" aria-label={`Remove the logo for ${clan.clan}`} disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
            ×
          </Button>
        )}
      </span>
    </li>
  );
}
