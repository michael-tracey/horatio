import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useMatch } from "react-router";
import { api, unwrap } from "../api/client";
import type { PlayerOut } from "../api/types";
import { SectionLabel } from "../components/Headings";
import { PronounsInput } from "../components/PronounsInput";
import { useToast } from "../components/Toast";
import { LinksEditor } from "../components/LinksEditor";
import { Button, Card, ErrorText, Field, Input, Loading, PageTitle, Tabs, Textarea } from "../components/ui";
import { useAction, useLeaveWarning, useMe } from "../hooks";
import { DevicePanel } from "../offline/DevicePanel";
import { LinesVeilsForm } from "./LinesVeilsForm";
import { BlogAuthorPage } from "./settings/BlogAuthorPage";
import { NotificationsPage } from "./settings/NotificationsPage";
import { PreferencesPage } from "./settings/PreferencesPage";
import { SignInPage } from "./settings/SignInPage";

/** Where the Discord username's hint sends the player to link or unlink their Discord. */
const SIGN_IN = (
  <Link to="/account/sign-in" className="underline hover:text-parchment">
    the Sign-in and email tab
  </Link>
);

const TABS = [
  { to: "/account", label: "Profile", end: true },
  { to: "/account/lines-veils", label: "Lines and veils" },
  { to: "/account/blog", label: "Blog author" },
  { to: "/account/preferences", label: "Preferences" },
  { to: "/account/notifications", label: "Notifications" },
  { to: "/account/sign-in", label: "Sign-in and email" },
  { to: "/account/device", label: "This device" },
];

/** The signed-in player's own profile, as others see it on their player page;
 * their lines and veils, which are never public; how they show on the blog, if they
 * write for it (#1159); their preferences; which
 * notifications come and how (#1053); how they sign in; and what this device keeps
 * for games with no signal. */
export function AccountPage() {
  const me = useMe();
  const id = me.data?.id ?? "";
  const player = useQuery({
    queryKey: ["player", id],
    queryFn: () => unwrap(api.GET("/api/players/{user_id}", { params: { path: { user_id: id } } })),
    enabled: !!id,
  });
  const onDevice = !!useMatch("/account/device");
  const title = (
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
      <Tabs tabs={TABS} />
    </>
  );
  // This device works offline too: Remove is for a phone with no signal as much as any.
  if (onDevice)
    return (
      <>
        {title}
        <DevicePanel />
      </>
    );
  if (player.isPending) return <Loading />;
  if (player.error) return <ErrorText error={player.error} />;

  return (
    <>
      {title}
      <Routes>
        <Route index element={<ProfileForm key={player.data.id} player={player.data} />} />
        <Route path="lines-veils" element={player.data.lines_veils && <LinesVeilsForm key={`${player.data.id}-lines-veils`} value={player.data.lines_veils} />} />
        <Route path="blog" element={<BlogAuthorPage />} />
        <Route path="preferences" element={<PreferencesPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="sign-in" element={<SignInPage player={player.data} />} />
        <Route path="settings" element={<SettingsMoved />} />
      </Routes>
    </>
  );
}

/**
 * Account › Settings became Preferences and Sign-in and email (#910). Its old address,
 * in emails already sent, lands on Preferences, or on the notifications it named (#1053).
 */
function SettingsMoved() {
  const { hash } = useLocation();
  return <Navigate replace to={hash === "#notifications" ? "/account/notifications" : "/account/preferences"} />;
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
  useLeaveWarning(unsaved, { inApp: true });

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
            <Field
              label="Discord username"
              hint={
                player.discord_linked ? (
                  <>From your linked Discord account. Unlink it on {SIGN_IN} to type one instead.</>
                ) : (
                  <>Your username, such as mrcarbuncle, so staff and the troupe's Discord can find you. Or link your Discord account on {SIGN_IN}.</>
                )
              }
            >
              <Input
                autoComplete="off"
                placeholder="mrcarbuncle"
                readOnly={player.discord_linked}
                value={form.discord_handle}
                onChange={(e) => set({ discord_handle: e.target.value })}
              />
            </Field>
          </div>
          <div className="flex flex-col gap-3">
            <SectionLabel>Social media</SectionLabel>
            <LinksEditor links={form.links} onChange={(links) => set({ links })} />
          </div>
        </div>
        <div className="mt-6 flex flex-col gap-3 border-t border-ash/60 pt-4">
          <ErrorText error={save.error} />
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
            {unsaved && <span className="text-sm text-mist">Not saved yet</span>}
          </div>
        </div>
      </Card>
    </form>
  );
}
