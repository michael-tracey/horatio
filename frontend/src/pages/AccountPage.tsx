import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes } from "react-router";
import { api, unwrap } from "../api/client";
import type { PlayerOut, ProfileLink } from "../api/types";
import { PronounsInput } from "../components/PronounsInput";
import { Button, Card, ErrorText, Field, Input, Loading, Notice, PageTitle, Tabs, Textarea } from "../components/ui";
import { useAction, useMe } from "../hooks";
import { SettingsPage } from "./settings/SettingsPage";

const MAX_LINKS = 6;

/** The signed-in player's own profile, as others see it on their player page,
 * and their settings. */
export function AccountPage() {
  const me = useMe();
  const id = me.data?.id ?? "";
  const player = useQuery({
    queryKey: ["player", id],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: id } } })),
    enabled: !!id,
  });
  if (player.isPending) return <Loading />;
  if (player.error) return <ErrorText error={player.error} />;

  return (
    <>
      <PageTitle
        subtitle="Anyone signed in can see your profile. Your email stays private."
        actions={
          <Link to={`/players/${id}`} className="text-sm text-gold underline">
            See your profile
          </Link>
        }
      >
        Your account
      </PageTitle>
      <Tabs
        tabs={[
          { to: "/account", label: "Profile", end: true },
          { to: "/account/settings", label: "Settings" },
        ]}
      />
      <Routes>
        <Route index element={<ProfileForm key={player.data.id} player={player.data} />} />
        <Route path="settings" element={<SettingsPage />} />
      </Routes>
    </>
  );
}

function ProfileForm({ player }: { player: PlayerOut }) {
  const [name, setName] = useState(player.display_name);
  const [pronouns, setPronouns] = useState(player.pronouns ?? "");
  const [bio, setBio] = useState(player.bio ?? "");
  const [discord, setDiscord] = useState(player.discord_handle ?? "");
  const [links, setLinks] = useState<ProfileLink[]>(player.links);
  const [saved, setSaved] = useState(false);
  const save = useAction(async () => {
    // Show what was kept, as the server tidied it: "@Name" becomes "name", a link gets a label.
    const kept = await unwrap(api.PUT("/api/profile", { body: { display_name: name, pronouns, bio, discord_handle: discord, links } }));
    setName(kept.display_name);
    setPronouns(kept.pronouns ?? "");
    setBio(kept.bio ?? "");
    setDiscord(kept.discord_handle ?? "");
    setLinks(kept.links);
    setSaved(true);
  });
  const setLink = (i: number, change: Partial<ProfileLink>) => {
    setLinks(links.map((l, j) => (j === i ? { ...l, ...change } : l)));
    setSaved(false);
  };

  return (
    <form
      className="grid gap-6 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
      onChange={() => setSaved(false)}
    >
      <Card title="Profile">
        <div className="flex flex-col gap-4">
          <Field label="Display name">
            <Input required maxLength={100} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Pronouns" hint="Optional. Shown beside your name to other players; never printed on a badge.">
            <PronounsInput value={pronouns} onChange={(e) => setPronouns(e.target.value)} />
          </Field>
          <Field label="Bio" hint="A little about you: how long you've played, what you like to play. Up to 2000 characters.">
            <Textarea rows={6} maxLength={2000} value={bio} onChange={(e) => setBio(e.target.value)} />
          </Field>
          <Field label="Discord username" hint="Your username, such as mrcarbuncle, so staff and the troupe's Discord can find you.">
            <Input autoComplete="off" placeholder="mrcarbuncle" value={discord} onChange={(e) => setDiscord(e.target.value)} />
          </Field>
        </div>
      </Card>
      <Card title="Social media">
        <div className="flex flex-col gap-3">
          {links.map((link, i) => (
            <fieldset key={i} className="flex flex-col gap-2 rounded-md border border-ash p-3 sm:flex-row sm:items-end">
              <legend className="sr-only">Link {i + 1}</legend>
              <div className="sm:w-32">
                <Field label="Label">
                  <Input placeholder="Bluesky" maxLength={40} value={link.label} onChange={(e) => setLink(i, { label: e.target.value })} />
                </Field>
              </div>
              <div className="min-w-0 flex-1">
                <Field label="Address">
                  <Input type="url" required placeholder="https://" value={link.url} onChange={(e) => setLink(i, { url: e.target.value })} />
                </Field>
              </div>
              <Button type="button" variant="ghost" aria-label={`Remove link ${i + 1}`} onClick={() => setLinks(links.filter((_, j) => j !== i))}>
                Remove
              </Button>
            </fieldset>
          ))}
          {links.length < MAX_LINKS ? (
            <Button type="button" variant="secondary" onClick={() => setLinks([...links, { label: "", url: "" }])}>
              Add a link
            </Button>
          ) : (
            <p className="text-sm text-mist">That's the most links a profile shows.</p>
          )}
        </div>
      </Card>
      <div className="flex flex-col gap-3 md:col-span-2">
        <ErrorText error={save.error} />
        {saved && <Notice>Saved.</Notice>}
        <Button type="submit" disabled={save.isPending} className="self-start">
          Save profile
        </Button>
      </div>
    </form>
  );
}
