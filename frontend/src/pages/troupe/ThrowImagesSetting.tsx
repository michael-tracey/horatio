import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { ThrowImagesOut, TroupeOut } from "../../api/types";
import { Button, Card, ErrorText, Loading } from "../../components/ui";
import { useAction } from "../../hooks";
import { THROW_PANEL, THEMES, type Theme } from "../../theme";
import { ThrowFace, troupeImages } from "../play/throwImages";
import { THROW_NAMES, THROWS, type Throw } from "../play/throws";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";
const THEME_NAMES: Record<Theme, string> = { dark: "Dark", ultragoth: "Ultra goth" };

export function throwImagesKey(troupeId: string) {
  return ["throw-images", troupeId];
}

export function useThrowImages(troupeId: string) {
  return useQuery({
    queryKey: throwImagesKey(troupeId),
    queryFn: () => unwrap(api.GET("/api/troupes/{troupe_id}/throw-images", { params: { path: { troupe_id: troupeId } } })),
  });
}

/** The set as the Throws tab takes it, once all three are there. */
export function fullSet(images: ThrowImagesOut): Record<Throw, string> | null {
  const { rock, paper, scissors } = images;
  return rock && paper && scissors ? { rock, paper, scissors } : null;
}

/**
 * Throw pictures (#670): a troupe's own rock, paper and scissors for the Play View's
 * Throws tab. Its storytellers upload one picture for each and may name the set; it
 * is offered to players only with all three. Removing it puts the troupe back on
 * Horatio's own. Each change goes in the troupe log.
 */
export function ThrowImagesSetting({ troupe, canEdit }: { troupe: TroupeOut; canEdit: boolean }) {
  const images = useThrowImages(troupe.id);
  return (
    <Card title="Throw pictures">
      <p className="mb-3 text-sm text-mist">
        Your troupe's own rock, paper and scissors for the Play View's Throws tab, instead of Horatio's. Once all three are here, the set can be offered to your players.
      </p>
      {images.isPending ? (
        <Loading />
      ) : images.error ? (
        <ErrorText error={images.error} />
      ) : canEdit ? (
        <Editor troupeId={troupe.id} images={images.data} />
      ) : (
        <p className="text-sm">{fullSet(images.data) ? `The troupe has its own set${images.data.name ? `: ${images.data.name}` : ""}.` : "The troupe throws with Horatio's own pictures."}</p>
      )}
      {!images.isPending && !images.error && <Preview images={images.data} />}
    </Card>
  );
}

function Editor({ troupeId, images }: { troupeId: string; images: ThrowImagesOut }) {
  const path = { params: { path: { troupe_id: troupeId } } };
  const [name, setName] = useState(images.name);
  const [removing, setRemoving] = useState(false);
  const saveName = useAction(() => unwrap(api.PUT("/api/troupes/{troupe_id}/throw-images/name", { ...path, body: { name } })), [throwImagesKey(troupeId)]);
  const remove = useAction(() => unwrap(api.DELETE("/api/troupes/{troupe_id}/throw-images", path)), [throwImagesKey(troupeId)]);
  const any = THROWS.some((which) => images[which]);
  return (
    <div className="flex flex-col gap-4 text-sm">
      <ul className="grid gap-3 sm:grid-cols-3" aria-label="Throw pictures">
        {THROWS.map((which) => (
          <Slot key={which} troupeId={troupeId} which={which} url={images[which]} />
        ))}
      </ul>
      {!fullSet(images) && <p className="text-mist">{any ? "Add the rest: the set is offered only with all three." : "JPEG, PNG, WebP or HEIC, up to 10 MB each. A PNG keeps its transparency."}</p>}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          saveName.mutate(undefined);
        }}
      >
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span>
            Title for the set <span className="text-mist">(optional)</span>
          </span>
          <input value={name} maxLength={60} placeholder="Land of the Sky bones" onChange={(e) => setName(e.target.value)} className="rounded-md border border-line bg-night px-3 py-2" />
        </label>
        <Button type="submit" variant="secondary" disabled={saveName.isPending || name.trim() === images.name}>
          Use this title
        </Button>
      </form>
      {any &&
        (removing ? (
          <div role="alertdialog" aria-label="Remove the throw pictures" className="flex flex-col gap-2 rounded-md border border-blood/60 bg-blood/10 p-3">
            <p>Remove all three pictures? The troupe throws with Horatio's own again, and players who chose this set go back to Horatio's.</p>
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={() => {
                  remove.mutate(undefined);
                  setRemoving(false);
                }}
              >
                Remove them
              </Button>
              <Button variant="secondary" onClick={() => setRemoving(false)}>
                Keep them
              </Button>
            </div>
          </div>
        ) : (
          <div>
            <Button variant="ghost" disabled={remove.isPending} onClick={() => setRemoving(true)}>
              Remove the set
            </Button>
          </div>
        ))}
      <ErrorText error={saveName.error ?? remove.error} />
    </div>
  );
}

/** One throw's picture: what is there, and a way to upload or replace it. */
function Slot({ troupeId, which, url }: { troupeId: string; which: Throw; url: string | null }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [tooBig, setTooBig] = useState(false);
  const upload = useAction(async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    await unwrap(
      api.POST("/api/troupes/{troupe_id}/throw-images/{which}", {
        params: { path: { troupe_id: troupeId, which } },
        body: form as never,
        bodySerializer: (body: unknown) => body as FormData,
      }),
    );
  }, [throwImagesKey(troupeId)]);
  const label = THROW_NAMES[which];
  return (
    <li className="flex flex-col items-center gap-2 rounded-md border border-ash p-3">
      <span className="font-display text-gold">{label}</span>
      {url ? (
        <img src={`${url}/128.webp`} alt={`The troupe's ${label.toLowerCase()}`} className="size-24 object-contain" />
      ) : (
        <span className="flex size-24 items-center justify-center rounded-md border border-dashed border-line text-xs text-mist">None yet</span>
      )}
      <input
        ref={fileInput}
        type="file"
        accept={ACCEPT}
        aria-label={`Choose a picture for ${label}`}
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setTooBig(file.size > MAX_BYTES);
          if (file.size <= MAX_BYTES) upload.mutate(file);
        }}
      />
      <Button type="button" variant="secondary" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
        {upload.isPending ? "Uploading…" : url ? `Replace ${label.toLowerCase()}` : `Upload ${label.toLowerCase()}`}
      </Button>
      {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
      <ErrorText error={upload.error} />
    </li>
  );
}

/**
 * The pictures uploaded so far at the size the Throws tab shows them, on its panel
 * in Dark or Ultra goth, so staff can see they read at arm's length in either.
 */
function Preview({ images }: { images: ThrowImagesOut }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const shown = THROWS.filter((which) => images[which]);
  if (shown.length === 0) return null;
  const set = troupeImages(images.name, { rock: images.rock ?? "", paper: images.paper ?? "", scissors: images.scissors ?? "" });
  const panel = THROW_PANEL[theme];
  return (
    <section aria-label="Preview" className="mt-4 flex flex-col gap-2 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-mist">Preview, as the Throws tab shows them, in</span>
        {THEMES.map((t) => (
          <label key={t} className="flex items-center gap-1">
            <input type="radio" name="throw-preview-theme" checked={theme === t} onChange={() => setTheme(t)} />
            {THEME_NAMES[t]}
          </label>
        ))}
      </div>
      <div
        className="flex flex-wrap justify-center gap-6 rounded-lg border border-ash p-4"
        style={{ backgroundColor: panel.dusk, ["--color-gold" as string]: panel.gold }}
        data-testid="throw-preview"
      >
        {shown.map((which) => (
          <ThrowFace key={which} images={set} which={which} />
        ))}
      </div>
    </section>
  );
}
