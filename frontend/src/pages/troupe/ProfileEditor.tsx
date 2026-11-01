import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, unwrap } from "../../api/client";
import type { TroupeProfileIn, TroupeProfileOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { DateInput } from "../../components/DateInput";
import { Dialog } from "../../components/Dialog";
import { Button, Card, ErrorText, Field, Input, Notice, Select, Textarea } from "../../components/ui";
import type { Crop } from "../../components/crop";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";
import { Cropper } from "../character/Picture";
import { editable, LINKS } from "./profile";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

/** Everything on the profile, for the troupe's storytellers to change. Whether it
 * is public is the Profile tab's switch, which saves on its own. */
export function ProfileEditor({ profile, onDone }: { profile: TroupeProfileOut; onDone: () => void }) {
  const path = { params: { path: { troupe_id: profile.id } } };
  const [form, setForm] = useState<TroupeProfileIn>(() => editable(profile));
  const staff = useQuery({
    queryKey: ["staff", profile.id],
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/staff", path)),
  });
  const save = useAction(async () => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/profile", { ...path, body: form }));
    onDone();
  });
  const set = (changes: Partial<TroupeProfileIn>) => setForm((f) => ({ ...f, ...changes }));
  const venue = form.venue!;
  const setting = form.setting!;

  return (
    <Card title="Edit the profile">
      <div className="flex flex-col gap-6">
        <Pictures profile={profile} />
        <form
          className="flex flex-col gap-6"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(undefined);
          }}
        >
          <Part title="Links">
            <div className="grid gap-3 sm:grid-cols-2">
              {LINKS.map(({ kind, label, placeholder }) => (
                <Field key={kind} label={label}>
                  <Input
                    type="url"
                    placeholder={placeholder}
                    value={form.links[kind] ?? ""}
                    onChange={(e) => set({ links: { ...form.links, [kind]: e.target.value } })}
                  />
                </Field>
              ))}
            </div>
          </Part>

          <Part title="When it plays">
            <Field label="How often games run" hint={`Such as "Second Saturday of the month, 7 pm to midnight".`}>
              <Input maxLength={200} value={form.schedule} onChange={(e) => set({ schedule: e.target.value })} />
            </Field>
            <Games profile={profile} />
          </Part>

          <Part title="Where it plays">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="City or region">
                <Input maxLength={200} value={venue.region} onChange={(e) => set({ venue: { ...venue, region: e.target.value } })} />
              </Field>
              <Field label="Venue name">
                <Input maxLength={200} value={venue.name} onChange={(e) => set({ venue: { ...venue, name: e.target.value } })} />
              </Field>
            </div>
            <Field label="Address" hint="Shown only to people signed in, even on a public profile.">
              <Input maxLength={200} value={venue.address} onChange={(e) => set({ venue: { ...venue, address: e.target.value } })} />
            </Field>
            <Field label="Accessibility" hint="Step-free access, parking, a quiet room.">
              <Textarea rows={2} maxLength={2000} value={venue.access} onChange={(e) => set({ venue: { ...venue, access: e.target.value } })} />
            </Field>
          </Part>

          <Part title="The setting">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Chronicle">
                <Input maxLength={200} value={setting.chronicle} onChange={(e) => set({ setting: { ...setting, chronicle: e.target.value } })} />
              </Field>
              <Field label="City it is set in">
                <Input maxLength={200} value={setting.city} onChange={(e) => set({ setting: { ...setting, city: e.target.value } })} />
              </Field>
              <Field label="Era">
                <Input maxLength={200} value={setting.era} onChange={(e) => set({ setting: { ...setting, era: e.target.value } })} />
              </Field>
              <Field label="Tone" hint="A short line.">
                <Input maxLength={200} value={setting.tone} onChange={(e) => set({ setting: { ...setting, tone: e.target.value } })} />
              </Field>
            </div>
          </Part>

          <Part title="New players">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Taking new players?" hint="Shows on the troupe list and the profile.">
                <Select
                  value={form.new_players ?? ""}
                  onChange={(e) => set({ new_players: e.target.value === "" ? null : (e.target.value as "welcoming" | "closed") })}
                >
                  <option value="">Not saying</option>
                  <option value="welcoming">Welcoming new players</option>
                  <option value="closed">Not taking new players right now</option>
                </Select>
              </Field>
              <Field label="Contact for new players" hint="One of the troupe's staff.">
                <Select value={form.contact_id ?? ""} onChange={(e) => set({ contact_id: e.target.value || null })}>
                  <option value="">No one</option>
                  {(staff.data ?? []).map((s) => (
                    <option key={s.user_id} value={s.user_id}>
                      {s.display_name} (@{s.handle})
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </Part>

          <Part title="Age and content">
            <Field label="Minimum age" hint="Leave empty for none.">
              <Input
                type="number"
                min={0}
                max={99}
                className="w-28"
                value={form.min_age ?? ""}
                onChange={(e) => set({ min_age: e.target.value === "" ? null : Number(e.target.value) })}
              />
            </Field>
            <Field label="Content notes">
              <Textarea rows={3} maxLength={2000} value={form.content_notes} onChange={(e) => set({ content_notes: e.target.value })} />
            </Field>
          </Part>

          <ErrorText error={save.error ?? staff.error} />
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save profile"}
            </Button>
          </div>
        </form>
      </div>
    </Card>
  );
}

function Part({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 font-display text-parchment">{title}</legend>
      {children}
    </fieldset>
  );
}

/** Upcoming games: each added or taken away at once, in the editor's own time zone. */
function Games({ profile }: { profile: TroupeProfileOut }) {
  const dates = useDates();
  const path = { params: { path: { troupe_id: profile.id } } };
  const [starts, setStarts] = useState("");
  const [ends, setEnds] = useState("");
  const add = useAction(async () => {
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/games", {
        ...path,
        body: { starts_at: dates.fromInput(starts).toISOString(), ends_at: dates.fromInput(ends).toISOString() },
      }),
    );
    setStarts("");
    setEnds("");
  });
  const remove = useAction((game_id: string) => unwrap(api.DELETE("/api/troupes/{troupe_id}/games/{game_id}", { params: { path: { troupe_id: profile.id, game_id } } })));

  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-sm text-mist">Upcoming games</h4>
      {profile.games.length > 0 ? (
        <ul className="divide-y divide-ash text-sm" aria-label="Upcoming games to edit">
          {profile.games.map((g) => (
            <li key={g.id} className="flex items-center justify-between gap-2 py-2">
              <span>{dates.game(g.starts_at, g.ends_at)}</span>
              <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(g.id)} aria-label={`Remove the game on ${dates.gameStart(g.starts_at)}`}>
                Remove
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-mist">None yet.</p>
      )}
      {/* Top-aligned, the button beside the inputs rather than the dates written under them. */}
      <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-start">
        <Field label="Game starts">
          <DateInput
            type="datetime-local"
            value={starts}
            onChange={(e) => {
              const value = e.target.value;
              setStarts(value);
              // Five hours on, to start with: most games are an evening.
              if (value && !ends) setEnds(dates.toInput(new Date(dates.fromInput(value).getTime() + 5 * 3_600_000)));
            }}
          />
        </Field>
        <Field label="Game ends">
          <DateInput type="datetime-local" value={ends} onChange={(e) => setEnds(e.target.value)} />
        </Field>
        <Button type="button" variant="secondary" className="sm:mt-6" disabled={!starts || !ends || add.isPending} onClick={() => add.mutate(undefined)}>
          Add game
        </Button>
      </div>
      <p className="text-xs text-mist">Times are in {dates.zone.replace(/_/g, " ")}; everyone sees them in their own time zone.</p>
      <ErrorText error={add.error ?? remove.error} />
    </div>
  );
}

/** The portrait (cropped square, like a character's picture) and the banner. */
function Pictures({ profile }: { profile: TroupeProfileOut }) {
  const [open, setOpen] = useState(false);
  if (!profile.pictures_available) {
    return <Notice>Pictures are not set up here. On the server they are kept in the directory HORATIO_UPLOAD_DIR names.</Notice>;
  }
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 font-display text-parchment">Portrait and banner</legend>
      <div className="flex flex-wrap items-center gap-4">
        <Avatar name={profile.name} picture={profile.portrait} size="md" />
        <Button type="button" variant="secondary" onClick={() => setOpen(true)}>
          {profile.portrait ? "Change the portrait" : "Add a portrait"}
        </Button>
      </div>
      <Dialog title={`${profile.name}'s portrait`} open={open} onClose={() => setOpen(false)}>
        <PortraitEditor profile={profile} onDone={() => setOpen(false)} />
      </Dialog>
      <Banner profile={profile} />
    </fieldset>
  );
}

type Step = { kind: "choose" } | { kind: "new"; file: File; url: string } | { kind: "move" };

function PortraitEditor({ profile, onDone }: { profile: TroupeProfileOut; onDone: () => void }) {
  const path = { params: { path: { troupe_id: profile.id } } };
  const [step, setStep] = useState<Step>({ kind: "choose" });
  const [tooBig, setTooBig] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => () => (step.kind === "new" ? URL.revokeObjectURL(step.url) : undefined), [step]);

  const upload = useAction(async ({ file, crop }: { file: File; crop: Crop | null }) => {
    const form = new FormData();
    form.append("file", file);
    if (crop) {
      form.append("crop_x", String(crop.x));
      form.append("crop_y", String(crop.y));
      form.append("crop_size", String(crop.size));
    }
    // The form goes as it is: multipart, with the browser's own boundary.
    await unwrap(api.POST("/api/troupes/{troupe_id}/portrait", { ...path, body: form as never, bodySerializer: (body: unknown) => body as FormData }));
    onDone();
  });
  const move = useAction(async (crop: Crop) => {
    await unwrap(api.PUT("/api/troupes/{troupe_id}/portrait/crop", { ...path, body: crop }));
    onDone();
  });
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/troupes/{troupe_id}/portrait", path));
    onDone();
  });

  if (step.kind === "new") {
    return (
      <Cropper
        src={step.url}
        initial={null}
        badge={false}
        saving={upload.isPending}
        error={upload.error}
        unreadable="This browser cannot show this kind of picture (HEIC, perhaps) before it is uploaded. Save it and it will be centred; you can move the crop afterwards."
        onCancel={() => setStep({ kind: "choose" })}
        onSave={(crop) => upload.mutate({ file: step.file, crop })}
      />
    );
  }
  if (step.kind === "move" && profile.portrait) {
    return (
      <Cropper
        src={`${profile.portrait}/full.webp`}
        initial={profile.portrait_crop}
        badge={false}
        saving={move.isPending}
        error={move.error}
        onCancel={() => setStep({ kind: "choose" })}
        onSave={(crop) => crop && move.mutate(crop)}
      />
    );
  }
  return (
    <div className="flex flex-col items-center gap-4">
      <Avatar name={profile.name} picture={profile.portrait} size="xl" />
      <p className="text-center text-sm text-mist">
        A JPEG, PNG, WebP or HEIC picture up to 10 MB, shown on the troupe's page, in troupe lists and on its printed sheets. Where it was taken and other details phones add
        are removed.
      </p>
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPT}
        aria-label="Choose a portrait"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setTooBig(file.size > MAX_BYTES);
          if (file.size <= MAX_BYTES) setStep({ kind: "new", file, url: URL.createObjectURL(file) });
        }}
      />
      {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
      <ErrorText error={remove.error} />
      <div className="flex flex-wrap justify-center gap-2">
        <Button type="button" onClick={() => fileInput.current?.click()}>
          {profile.portrait ? "Upload a new portrait" : "Choose a picture"}
        </Button>
        {profile.portrait && (
          <>
            <Button type="button" variant="secondary" onClick={() => setStep({ kind: "move" })}>
              Move the crop
            </Button>
            <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
              Remove
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

/** A wide picture across the top of the troupe's page, cut 3:1 from its middle. */
function Banner({ profile }: { profile: TroupeProfileOut }) {
  const path = { params: { path: { troupe_id: profile.id } } };
  const fileInput = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState(false);
  const upload = useAction(async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    await unwrap(api.POST("/api/troupes/{troupe_id}/banner", { ...path, body: form as never, bodySerializer: (body: unknown) => body as FormData }));
  });
  const remove = useAction(() => unwrap(api.DELETE("/api/troupes/{troupe_id}/banner", path)));
  return (
    <div className="flex flex-col gap-2">
      {profile.banner && <img src={`${profile.banner}/750.webp`} alt="The troupe's banner" className="aspect-[3/1] w-full max-w-md rounded-md border border-ash object-cover" />}
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPT}
        aria-label="Choose a banner"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setTooBig(file.size > MAX_BYTES);
          if (file.size <= MAX_BYTES) upload.mutate(file);
        }}
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="secondary" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
          {upload.isPending ? "Uploading…" : profile.banner ? "Upload a new banner" : "Add a banner"}
        </Button>
        {profile.banner && (
          <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
            Remove the banner
          </Button>
        )}
      </div>
      <p className="text-xs text-mist">Optional: a wide picture across the top of the troupe's page, three times as wide as it is high, cut from the middle of what you upload.</p>
      {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
      <ErrorText error={upload.error ?? remove.error} />
    </div>
  );
}
