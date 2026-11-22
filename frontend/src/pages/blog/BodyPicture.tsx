import { useMutation } from "@tanstack/react-query";
import type { Editor } from "@tiptap/react";
import { useEffect, useId, useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, ErrorText, Field, Input } from "../../components/ui";
import type { Tool } from "../character/RichEditor";
import { ACCEPT, MAX_BYTES } from "../news/PostForm";

/** The editor the Picture button was pressed in, and the picture chosen in it, if one was. */
export type Placing = { editor: Editor; chosen: { alt: string; caption: string } | null };

/** The editor's Picture button (#1163): adds a picture where the cursor is, or changes what the chosen one says. */
export function pictureTool(editor: Editor, open: boolean, onOpen: (placing: Placing | null) => void): Tool {
  return {
    label: "Insert a picture",
    face: "Picture",
    active: open,
    run: () => {
      if (open) return onOpen(null);
      const chosen = editor.isActive("blogPicture") ? editor.getAttributes("blogPicture") : null;
      onOpen({ editor, chosen: chosen && { alt: String(chosen.alt ?? ""), caption: String(chosen.caption ?? "") } });
    },
  };
}

/**
 * Under the editor's toolbar: choose a picture, say what it shows (asked every time,
 * for readers who can't see it) and give it a caption if wanted, and it goes in
 * where the cursor was. With a picture chosen in the words, it changes what that
 * one says instead. A new article is saved first, as the picture is kept with it.
 */
export function BodyPictureForm({ articleId, placing, onDone }: { articleId: string | undefined; placing: Placing; onDone: () => void }) {
  const changing = placing.chosen !== null;
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [alt, setAlt] = useState(placing.chosen?.alt ?? "");
  const [caption, setCaption] = useState(placing.chosen?.caption ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const heading = useId();
  useEffect(() => () => (preview ? URL.revokeObjectURL(preview) : undefined), [preview]);
  const upload = useMutation({
    mutationFn: (chosen: File) => {
      const sent = new FormData();
      sent.append("file", chosen);
      // The form goes as it is: multipart, with the browser's own boundary.
      return unwrap(
        api.POST("/api/blog/articles/{article_id}/body-pictures", {
          params: { path: { article_id: articleId ?? "" } },
          body: sent as never,
          bodySerializer: (b: unknown) => b as FormData,
        }),
      );
    },
  });

  if (!articleId) {
    return (
      <div className="flex flex-wrap items-center gap-2 border-b border-line p-3 text-sm text-mist">
        <p className="min-w-0 flex-1">Save it as a draft first, then add pictures to its words.</p>
        <Button type="button" variant="ghost" className="min-h-9 px-3" onClick={onDone}>
          Close
        </Button>
      </div>
    );
  }

  const said = { alt: alt.trim(), caption: caption.trim() };
  const save = () => {
    if (!changing && !file) return setProblem("Choose a picture first.");
    if (!said.alt) return setProblem("Say what the picture shows: readers who can't see it are told this instead.");
    setProblem(null);
    if (changing) {
      placing.editor.chain().focus().updateAttributes("blogPicture", said).run();
      return onDone();
    }
    upload.mutate(file!, {
      onSuccess: (picture) => {
        placing.editor
          .chain()
          .focus()
          .insertContent({ type: "blogPicture", attrs: { id: picture.id, ...said } })
          .run();
        onDone();
      },
    });
  };

  return (
    <form
      aria-labelledby={heading}
      className="flex flex-col gap-3 border-b border-line p-3"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <h3 id={heading} className="text-sm text-parchment">
        {changing ? "Change what the picture says" : "Add a picture to the words"}
      </h3>
      {!changing && (
        <div className="flex flex-col gap-1 text-sm">
          <label className="text-mist">
            Picture to add
            <input
              type="file"
              accept={ACCEPT}
              className="mt-1 block w-full text-parchment file:mr-3 file:min-h-9 file:rounded-md file:border file:border-ash file:bg-dusk file:px-3 file:text-parchment"
              onChange={(e) => {
                const chosen = e.target.files?.[0] ?? null;
                if (chosen && chosen.size > MAX_BYTES) {
                  e.target.value = "";
                  setFile(null);
                  setPreview(null);
                  return setProblem("That picture is over 10 MB. Try a smaller one.");
                }
                setProblem(null);
                setFile(chosen);
                setPreview(chosen ? URL.createObjectURL(chosen) : null);
              }}
            />
          </label>
          <span className="text-xs text-mist">A JPEG, PNG, WebP or HEIC picture up to 10 MB, kept whole. Only a picture you made or may share: never one from the books.</span>
          {preview && <img src={preview} alt="" className="mt-1 max-h-40 w-fit max-w-full rounded-md" />}
        </div>
      )}
      <Field label="What it shows" hint="In a sentence, for readers who can't see it: their screen reader says this instead.">
        <Input value={alt} maxLength={300} onChange={(e) => setAlt(e.target.value)} />
      </Field>
      <Field label="Caption (optional)" hint="Shown under the picture.">
        <Input value={caption} maxLength={300} onChange={(e) => setCaption(e.target.value)} />
      </Field>
      <ErrorText error={problem ?? upload.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="secondary" className="min-h-9 px-3" disabled={upload.isPending}>
          {changing ? "Save" : upload.isPending ? "Adding…" : "Add the picture"}
        </Button>
        <Button type="button" variant="ghost" className="min-h-9 px-3" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
