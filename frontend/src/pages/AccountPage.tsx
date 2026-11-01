import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Route, Routes } from "react-router";
import { api, unwrap } from "../api/client";
import type { PlayerOut, ProfileLink } from "../api/types";
import { PronounsInput } from "../components/PronounsInput";
import { useToast } from "../components/Toast";
import { Button, Card, ErrorText, Field, Input, Loading, PageTitle, Tabs, Textarea } from "../components/ui";
import { useAction, useLeaveWarning, useMe } from "../hooks";
import { LinesVeilsForm } from "./LinesVeilsForm";
import { HandleCard } from "./settings/HandleCard";
import { SettingsPage } from "./settings/SettingsPage";

const MAX_LINKS = 6;

/** The signed-in player's own profile, as others see it on their player page;
 * their lines and veils, which are never public; and their settings, with their
 * email and password. */
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
          { to: "/account/lines-veils", label: "Lines and veils" },
          { to: "/account/settings", label: "Settings" },
        ]}
      />
      <Routes>
        <Route
          index
          element={
            <div className="flex flex-col gap-6">
              <ProfileForm key={player.data.id} player={player.data} />
              <HandleCard />
            </div>
          }
        />
        <Route
          path="lines-veils"
          element={player.data.lines_veils && <LinesVeilsForm key={`${player.data.id}-lines-veils`} value={player.data.lines_veils} />}
        />
        <Route path="settings" element={<SettingsPage player={player.data} />} />
      </Routes>
    </>
  );
}

type Profile = Pick<PlayerOut, "display_name" | "links"> & { pronouns: string; bio: string; discord_handle: string };

/** The profile as the form edits it. */
function profileOf(player: Pick<PlayerOut, "display_name" | "pronouns" | "bio" | "discord_handle" | "links">): Profile {
  return {
    display_name: player.display_name,
    pronouns: player.pronouns ?? "",
    bio: player.bio ?? "",
    discord_handle: player.discord_handle ?? "",
    links: player.links,
  };
}

/** What others see of you, saved with one button: your name, pronouns, bio,
 * Discord and links. Asks before the page is left with changes not saved. */
function ProfileForm({ player }: { player: PlayerOut }) {
  const toast = useToast();
  const [kept, setKept] = useState(() => profileOf(player));
  const [form, setForm] = useState(kept);
  const set = (change: Partial<Profile>) => setForm((f) => ({ ...f, ...change }));
  const save = useAction(async () => {
    // Show what was kept, as the server tidied it: "@Name" becomes "name", a link gets a label.
    const saved = profileOf(await unwrap(api.PUT("/api/profile", { body: form })));
    setKept(saved);
    setForm(saved);
    toast({ message: "Profile saved." });
  });
  const unsaved = JSON.stringify(form) !== JSON.stringify(kept);
  useLeaveWarning(unsaved);
  const { links } = form;
  const setLink = (i: number, change: Partial<ProfileLink>) => set({ links: links.map((l, j) => (j === i ? { ...l, ...change } : l)) });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(undefined);
      }}
    >
      <Card title="Profile">
        <p className="mb-4 text-sm text-mist">Anyone signed in can see this, on your player page.</p>
        <div className="grid gap-6 md:grid-cols-2">
          <div className="flex flex-col gap-4">
            <Field label="Display name">
              <Input required maxLength={100} autoComplete="name" value={form.display_name} onChange={(e) => set({ display_name: e.target.value })} />
            </Field>
            <Field label="Pronouns" hint="Optional. Shown beside your name to other players; never printed on a badge.">
              <PronounsInput value={form.pronouns} onChange={(e) => set({ pronouns: e.target.value })} />
            </Field>
            <Field label="Bio" hint="A little about you: how long you've played, what you like to play. Up to 2000 characters.">
              <Textarea rows={6} maxLength={2000} value={form.bio} onChange={(e) => set({ bio: e.target.value })} />
            </Field>
            <Field label="Discord username" hint="Your username, such as mrcarbuncle, so staff and the troupe's Discord can find you.">
              <Input autoComplete="off" placeholder="mrcarbuncle" value={form.discord_handle} onChange={(e) => set({ discord_handle: e.target.value })} />
            </Field>
          </div>
          <div className="flex flex-col gap-3">
            <h3 className="text-sm text-mist">Social media</h3>
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
                <Button type="button" variant="ghost" aria-label={`Remove link ${i + 1}`} onClick={() => set({ links: links.filter((_, j) => j !== i) })}>
                  Remove
                </Button>
              </fieldset>
            ))}
            {links.length < MAX_LINKS ? (
              <Button type="button" variant="secondary" className="self-start" onClick={() => set({ links: [...links, { label: "", url: "" }] })}>
                Add a link
              </Button>
            ) : (
              <p className="text-sm text-mist">That's the most links a profile shows.</p>
            )}
          </div>
        </div>
        <div className="mt-6 flex flex-col gap-3 border-t border-ash/60 pt-4">
          <ErrorText error={save.error} />
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={save.isPending}>
              Save profile
            </Button>
            {unsaved && <span className="text-sm text-mist">Not saved yet</span>}
          </div>
        </div>
      </Card>
    </form>
  );
}
