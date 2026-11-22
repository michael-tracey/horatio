import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../api/client";
import type { MyAuthor } from "../../api/types";
import { AuthorCard, AuthorPicture, authorPath } from "../../components/AuthorCard";
import type { Crop } from "../../components/crop";
import { SectionLabel } from "../../components/Headings";
import { LinksEditor } from "../../components/LinksEditor";
import { useToast } from "../../components/Toast";
import { Button, Card, ErrorText, Field, Input, Loaded, Textarea } from "../../components/ui";
import { useAction, useLeaveWarning } from "../../hooks";
import { Cropper } from "../character/Picture";
import { ACCEPT, MAX_BYTES } from "../news/PostForm";

/** As the server keeps it (api/blog_authors.py: MAX_BIO). */
export const MAX_AUTHOR_BIO = 1000;
const KEY = ["blog-author"];

type Form = Pick<MyAuthor, "display_name" | "handle" | "bio" | "links">;

export function formOf(author: MyAuthor): Form {
  return { display_name: author.display_name, handle: author.handle, bio: author.bio, links: author.links };
}

/**
 * Account › Blog author (#1159): how the person shows on the game developer blog, under
 * each article they write and on their author page. Apart from their profile: it starts
 * from their name and handle, and nothing else of their profile is shown unless they
 * put it here. Saved with one button, with a live preview of the card beside it.
 */
export function BlogAuthorPage() {
  const author = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/blog/author")) });
  return <Loaded query={author}>{(data) => <AuthorForm author={data} />}</Loaded>;
}

function AuthorForm({ author }: { author: MyAuthor }) {
  const toast = useToast();
  const client = useQueryClient();
  const [kept, setKept] = useState(() => formOf(author));
  const [form, setForm] = useState(kept);
  const set = (change: Partial<Form>) => setForm((f) => ({ ...f, ...change }));
  const save = useAction(async () => {
    const saved = await unwrap(api.PUT("/api/blog/author", { body: form }));
    client.setQueryData(KEY, saved);
    // As the server tidied it: a link gets a label, the @ goes from the handle.
    setKept(formOf(saved));
    setForm(formOf(saved));
    toast({ message: "Author profile saved." });
  });
  const unsaved = !author.saved || JSON.stringify(form) !== JSON.stringify(kept);
  useLeaveWarning(author.saved && unsaved, { inApp: true });

  return (
    <div className="flex flex-col gap-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(undefined);
        }}
      >
        <Card title="Blog author">
          <p className="mb-4 text-sm text-mist">
            How you show on Horatio's blog, under each article you write and on your author page, for anyone to read, signed in or not. It's apart from your profile: nothing
            from your profile shows here unless you put it here.
          </p>
          <Visibility author={author} />
          <div className="grid gap-6 md:grid-cols-2">
            <div className="flex flex-col gap-4">
              <Field label="Display name" hint="Your name as readers see it.">
                <Input required maxLength={100} value={form.display_name} onChange={(e) => set({ display_name: e.target.value })} />
              </Field>
              <Field label="Author handle" hint={`Your page's address: ${authorPath(form.handle.replace(/^@/, "") || "…")}. 3 to 30 letters, numbers, underscores and hyphens.`}>
                <Input required maxLength={31} autoComplete="off" value={form.handle} onChange={(e) => set({ handle: e.target.value })} />
              </Field>
              <Field label="Bio" hint={`A few lines about you and the games you run, in Markdown (**bold**, *italic*, links). Up to ${MAX_AUTHOR_BIO} characters.`}>
                <Textarea rows={5} maxLength={MAX_AUTHOR_BIO} value={form.bio} onChange={(e) => set({ bio: e.target.value })} />
              </Field>
              <div className="flex flex-col gap-3">
                <SectionLabel>Links</SectionLabel>
                <LinksEditor links={form.links} onChange={(links) => set({ links })} full="That's the most links an author shows." />
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <SectionLabel>How it shows</SectionLabel>
              <AuthorCard author={{ ...form, handle: form.handle.replace(/^@/, ""), picture: author.picture }} />
            </div>
          </div>
          <div className="mt-6 flex flex-col gap-3 border-t border-ash/60 pt-4">
            <ErrorText error={save.error} />
            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" disabled={save.isPending}>
                Save
              </Button>
              {unsaved && <span className="text-sm text-mist">{author.saved ? "Not saved yet" : "Not saved yet: you have no author profile until you save"}</span>}
            </div>
          </div>
        </Card>
      </form>
      <Card title="Picture">
        {!author.pictures_available ? (
          <p className="text-sm text-mist">Pictures aren't set up on this server.</p>
        ) : !author.saved ? (
          <p className="text-sm text-mist">Save your author profile first, then add a picture.</p>
        ) : (
          <PictureEditor key={author.picture ?? "none"} author={author} />
        )}
      </Card>
    </div>
  );
}

/** Whether anyone else can see the page yet: only while the person writes for the blog. */
function Visibility({ author }: { author: MyAuthor }) {
  if (!author.saved) return null;
  if (author.public)
    return (
      <p className="mb-4 text-sm">
        <Link to={authorPath(author.handle)} className="text-gold underline hover:text-parchment">
          See your author page
        </Link>
      </p>
    );
  return (
    <p className="mb-4 text-sm text-mist">
      Only you can see your author page for now. The blog is written by the staff of Horatio's troupes, so it shows to everyone once you're on a troupe's staff.
    </p>
  );
}

type Step = { kind: "choose" } | { kind: "new"; file: File; url: string } | { kind: "move" };

/** Upload a picture, cut square as a character's is, move its crop, or remove it. */
function PictureEditor({ author }: { author: MyAuthor }) {
  const client = useQueryClient();
  const [step, setStep] = useState<Step>({ kind: "choose" });
  const [tooBig, setTooBig] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  useEffect(() => () => (step.kind === "new" ? URL.revokeObjectURL(step.url) : undefined), [step]);
  const done = (saved: MyAuthor) => {
    client.setQueryData(KEY, saved);
    setStep({ kind: "choose" });
  };

  const upload = useAction(async ({ file, crop }: { file: File; crop: Crop | null }) => {
    const form = new FormData();
    form.append("file", file);
    if (crop) {
      form.append("crop_x", String(crop.x));
      form.append("crop_y", String(crop.y));
      form.append("crop_size", String(crop.size));
    }
    // The form goes as it is: multipart, with the browser's own boundary.
    done(await unwrap(api.POST("/api/blog/author/picture", { body: form as never, bodySerializer: (body: unknown) => body as FormData })));
  });
  const move = useAction(async (crop: Crop) => done(await unwrap(api.PUT("/api/blog/author/picture/crop", { body: crop }))));
  const remove = useAction(async () => done(await unwrap(api.DELETE("/api/blog/author/picture"))));

  if (step.kind === "new")
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
  if (step.kind === "move" && author.picture)
    return (
      <Cropper
        src={`${author.picture}/full.webp`}
        initial={author.picture_crop ?? null}
        badge={false}
        saving={move.isPending}
        error={move.error}
        onCancel={() => setStep({ kind: "choose" })}
        onSave={(crop) => crop && move.mutate(crop)}
      />
    );
  return (
    <div className="flex flex-col items-start gap-4 text-sm sm:flex-row sm:items-center">
      <AuthorPicture name={author.display_name} picture={author.picture} size="lg" />
      <div className="flex flex-col gap-3">
        <p className="text-mist">Optional: a square picture of you, or one that stands for you, shown round. A JPEG, PNG, WebP or HEIC picture up to 10 MB.</p>
        <Input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          aria-label="Choose a picture"
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
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => fileInput.current?.click()}>
            {author.picture ? "Upload a new picture" : "Choose a picture"}
          </Button>
          {author.picture && (
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
    </div>
  );
}
