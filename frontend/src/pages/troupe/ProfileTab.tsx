import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import type { TroupeOut, TroupeProfileOut } from "../../api/types";
import { Button, Card, ErrorText, Field, Input, Loading, Notice, Textarea } from "../../components/ui";
import { useAction } from "../../hooks";
import { ArchiveTroupe } from "./ArchiveTroupe";
import { hasProfile, publicPath } from "./profile";
import { ProfileEditor } from "./ProfileEditor";
import type { abilities } from "./roles";
import { TroupeProfileView } from "./TroupeProfile";

/**
 * The troupe's profile, for anyone who can see the troupe. Its storytellers
 * switch it public and edit it here; its lead also renames, describes and
 * archives the troupe.
 */
export function ProfileTab({ troupe, can }: { troupe: TroupeOut; can: ReturnType<typeof abilities> }) {
  const [editing, setEditing] = useState(false);
  const profile = useQuery({
    queryKey: ["troupe-profile", troupe.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/profile", { params: { path: { troupe_id: troupe.id } } })),
  });
  if (profile.isPending) return <Loading />;
  if (profile.error) return <ErrorText error={profile.error} />;
  const p = profile.data;
  const leading = can.lead && !troupe.archived;

  return (
    <div className="flex flex-col gap-6">
      {p.can_edit && <PublicSwitch profile={p} />}
      {leading && <NameAndDescription troupe={troupe} />}
      {editing ? (
        <ProfileEditor profile={p} onDone={() => setEditing(false)} />
      ) : (
        <section aria-label="Profile" className="flex flex-col gap-3">
          {p.can_edit && (
            <div className="flex justify-end">
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit profile
              </Button>
            </div>
          )}
          {p.can_edit && !hasProfile(p) && <Notice>Nothing on the profile yet: add a portrait, links, when and where the troupe plays, and more.</Notice>}
          <TroupeProfileView profile={p} signedIn />
        </section>
      )}
      {leading && <ArchiveTroupe troupe={troupe} />}
    </div>
  );
}

/** Who sees the profile: anyone, or only people signed in. Saves as soon as it is changed. */
function PublicSwitch({ profile }: { profile: TroupeProfileOut }) {
  const [copied, setCopied] = useState(false);
  const change = useAction((on: boolean) =>
    unwrap(api.PUT("/api/troupes/{troupe_id}/profile/public", { params: { path: { troupe_id: profile.id } }, body: { public: on } })),
  );
  const on = change.isPending && change.variables !== undefined ? change.variables : profile.public;
  const address = `${window.location.origin}${publicPath(profile.id)}`;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(address);
      setCopied(true);
    } catch {
      // No clipboard here (an insecure page, or refused): the link is there to copy by hand.
    }
  };

  return (
    <Card>
      <div className="flex items-start gap-3">
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label="Public"
          disabled={change.isPending}
          onClick={() => change.mutate(!on)}
          className={`relative mt-0.5 inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors disabled:opacity-60 ${
            on ? "border-gold bg-gold/30" : "border-ash bg-night"
          }`}
        >
          <span className={`inline-block h-4 w-4 rounded-full transition-transform ${on ? "translate-x-6 bg-gold" : "translate-x-1 bg-mist"}`} />
        </button>
        <div className="flex min-w-0 flex-col gap-1 text-sm">
          <p className="text-parchment">{on ? "Public: anyone can see this profile, even people not signed in" : "Signed-in only"}</p>
          <p className="text-xs text-mist">
            {on
              ? "Share the link when recruiting. The venue's street address still shows only to people signed in."
              : "Only people signed in can see this profile. Switch it on to share it when recruiting."}
          </p>
          {on && (
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs break-all">{address}</span>
              <Button type="button" variant="ghost" className="min-h-8 px-2" onClick={() => void copy()}>
                {copied ? "Copied" : "Copy the link"}
              </Button>
            </div>
          )}
        </div>
      </div>
      <ErrorText error={change.error} />
    </Card>
  );
}

/** The troupe's name and description, which only its lead changes. */
function NameAndDescription({ troupe }: { troupe: TroupeOut }) {
  const [name, setName] = useState(troupe.name);
  const [description, setDescription] = useState(troupe.description);
  const save = useAction(() =>
    unwrap(api.PATCH("/api/troupes/{troupe_id}", { params: { path: { troupe_id: troupe.id } }, body: { name, description } })),
  );
  return (
    <Card title="Name and description">
      <form
        className="flex flex-col gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <Field label="Name">
          <Input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Description" hint="Its first lines show on the troupe list, to help players choose.">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <ErrorText error={save.error} />
        <div>
          <Button type="submit" disabled={save.isPending}>
            Save
          </Button>
        </div>
      </form>
    </Card>
  );
}
