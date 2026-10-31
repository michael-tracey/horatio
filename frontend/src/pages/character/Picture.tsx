import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { api, unwrap } from "../../api/client";
import type { CharacterOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Dialog } from "../../components/Dialog";
import { Button, ErrorText, Notice } from "../../components/ui";
import { fromCrop, portraitFrame, resized, SMALLEST, square, toCrop, type Box, type Crop } from "../../components/crop";
import { useDates } from "../../dates";
import { useAction } from "../../hooks";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif";

/**
 * The character's picture at the top of its page. Whoever can see the character
 * (its player, its troupes' staff, the custodian) can change it: a click opens
 * a dialog to upload one, move its crop or remove it.
 */
export function CharacterPicture({ character }: { character: CharacterOut }) {
  const [open, setOpen] = useState(false);
  const changeable = character.status !== "retired";
  // Smaller on a phone. The sizes are marked important to win over the avatar's own, set inline.
  const avatar = <Avatar name={character.name} picture={character.picture} clan={character.clan} size="lg" className="size-14! max-sm:text-xl! sm:size-28!" />;
  if (!changeable) return avatar;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={character.picture ? `Change ${character.name}'s picture` : `Add a picture of ${character.name}`}
        title={character.picture ? "Change the picture" : "Add a picture"}
        className="group relative shrink-0 rounded-full"
      >
        {avatar}
        <span className="absolute right-0 bottom-0 grid h-5 w-5 place-items-center rounded-full border border-ash bg-dusk text-[10px] text-mist group-hover:border-gold group-hover:text-gold sm:h-7 sm:w-7 sm:text-xs">
          ✎
        </span>
      </button>
      <Dialog title={`${character.name}'s picture`} open={open} onClose={() => setOpen(false)}>
        <PictureEditor character={character} onDone={() => setOpen(false)} />
      </Dialog>
    </>
  );
}

type Step = { kind: "choose" } | { kind: "new"; file: File; url: string } | { kind: "move" };

function PictureEditor({ character, onDone }: { character: CharacterOut; onDone: () => void }) {
  const path = { params: { path: { character_id: character.id } } };
  const picture = useQuery({
    queryKey: ["picture", character.id],
    queryFn: () => unwrap(api.GET("/api/characters/{character_id}/picture", path)),
  });
  const [step, setStep] = useState<Step>({ kind: "choose" });
  const [tooBig, setTooBig] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const dates = useDates();
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
    await unwrap(
      api.POST("/api/characters/{character_id}/picture", {
        ...path,
        // The form goes as it is: multipart, with the browser's own boundary.
        body: form as never,
        bodySerializer: (body: unknown) => body as FormData,
      }),
    );
    onDone();
  });
  const move = useAction(async (crop: Crop) => {
    await unwrap(api.PUT("/api/characters/{character_id}/picture/crop", { ...path, body: crop }));
    onDone();
  });
  const remove = useAction(async () => {
    await unwrap(api.DELETE("/api/characters/{character_id}/picture", path));
    onDone();
  });

  if (picture.data && !picture.data.available) {
    return <Notice>Pictures are not set up here. On the server they are kept in the directory HORATIO_UPLOAD_DIR names.</Notice>;
  }
  const current = picture.data?.picture;

  if (step.kind === "new") {
    return (
      <Cropper
        src={step.url}
        initial={null}
        saving={upload.isPending}
        error={upload.error}
        unreadable="This browser cannot show this kind of picture (HEIC, perhaps) before it is uploaded. Save it and it will be centred; you can move the crop afterwards."
        onCancel={() => setStep({ kind: "choose" })}
        onSave={(crop) => upload.mutate({ file: step.file, crop })}
      />
    );
  }
  if (step.kind === "move" && current) {
    return (
      <Cropper
        src={`${current}/full.webp`}
        initial={picture.data?.crop ?? null}
        saving={move.isPending}
        error={move.error}
        onCancel={() => setStep({ kind: "choose" })}
        onSave={(crop) => crop && move.mutate(crop)}
      />
    );
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <Avatar name={character.name} picture={current} clan={character.clan} size="xl" />
      {picture.data?.uploaded_by && (
        <p className="text-xs text-mist">
          Uploaded by {picture.data.uploaded_by}
          {picture.data.uploaded_at && ` on ${dates.date(picture.data.uploaded_at)}`}
        </p>
      )}
      <p className="text-center text-sm text-mist">
        A JPEG, PNG, WebP or HEIC picture up to 10 MB. It shows straight away to everyone who can see {character.name}, and on game badges. Where it was taken and other
        details phones add are removed.
      </p>
      <input
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
      <ErrorText error={remove.error ?? picture.error} />
      <div className="flex flex-wrap justify-center gap-2">
        <Button type="button" onClick={() => fileInput.current?.click()}>
          {current ? "Upload a new picture" : "Choose a picture"}
        </Button>
        {current && (
          <Button type="button" variant="secondary" onClick={() => setStep({ kind: "move" })}>
            Move the crop
          </Button>
        )}
        {current &&
          (confirming ? (
            <Button type="button" variant="danger" disabled={remove.isPending} onClick={() => remove.mutate(undefined)}>
              Yes, remove it
            </Button>
          ) : (
            <Button type="button" variant="ghost" onClick={() => setConfirming(true)}>
              Remove
            </Button>
          ))}
      </div>
    </div>
  );
}

/**
 * Place the square portrait on the picture: drag it, or use the arrow keys, and
 * size it with the slider. The dashed frame around it is the badge's portrait
 * (characters only: troupes have no badges).
 */
export function Cropper({
  src,
  initial,
  saving,
  error,
  unreadable,
  badge = true,
  onCancel,
  onSave,
}: {
  src: string;
  initial: Crop | null;
  saving: boolean;
  error: unknown;
  /** What to say if the browser cannot show the picture; without it, that is an error. */
  unreadable?: string;
  /** Show the badge's portrait frame. */
  badge?: boolean;
  onCancel: () => void;
  onSave: (crop: Crop | null) => void;
}) {
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [box, setBox] = useState<Box | null>(null);
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; start: Box; scale: number } | null>(null);

  const loaded = (img: HTMLImageElement) => {
    const w = img.naturalWidth;
    const h = img.naturalHeight;
    setNatural({ w, h });
    setBox(fromCrop(w, h, initial));
  };
  const pct = (b: Box, n: { w: number; h: number }) => ({
    left: `${(b.left / n.w) * 100}%`,
    top: `${(b.top / n.h) * 100}%`,
    width: `${(b.width / n.w) * 100}%`,
    height: `${(b.height / n.h) * 100}%`,
  });

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (!box || !natural || !frame.current) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, start: box, scale: natural.w / frame.current.getBoundingClientRect().width };
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || !natural) return;
    const left = d.start.left + (e.clientX - d.x) * d.scale;
    const top = d.start.top + (e.clientY - d.y) * d.scale;
    setBox(square(natural.w, natural.h, left, top, d.start.width));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!box || !natural) return;
    const step = Math.min(natural.w, natural.h) * 0.02;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const m = moves[e.key];
    if (!m) return;
    e.preventDefault();
    setBox(square(natural.w, natural.h, box.left + m[0], box.top + m[1], box.width));
  };

  const shorter = natural ? Math.min(natural.w, natural.h) : 1;
  return (
    <div className="flex flex-col gap-3">
      {failed && unreadable ? (
        <Notice>{unreadable}</Notice>
      ) : failed ? (
        <ErrorText error="The picture could not be shown." />
      ) : (
        <>
          <div ref={frame} className="relative mx-auto w-full max-w-sm touch-none overflow-hidden rounded-md bg-night select-none">
            <img src={src} alt="The picture to crop" draggable={false} onLoad={(e) => loaded(e.currentTarget)} onError={() => setFailed(true)} className="block w-full" />
            {box && natural && (
              <>
                {badge && (
                  <div aria-hidden="true" className="pointer-events-none absolute border border-dashed border-parchment/80" style={pct(portraitFrame(natural.w, natural.h, box), natural)} />
                )}
                <div
                  role="slider"
                  tabIndex={0}
                  aria-label="Where the portrait is: drag, or use the arrow keys"
                  aria-valuetext={`${Math.round((box.left / natural.w) * 100)}% from the left, ${Math.round((box.top / natural.h) * 100)}% from the top`}
                  aria-valuenow={Math.round((box.left / natural.w) * 100)}
                  onPointerDown={onPointerDown}
                  onPointerMove={onPointerMove}
                  onPointerUp={() => (drag.current = null)}
                  onKeyDown={onKeyDown}
                  className="absolute cursor-move rounded-full border-2 border-gold shadow-[0_0_0_9999px_rgba(20,16,22,0.6)]"
                  style={pct(box, natural)}
                />
              </>
            )}
          </div>
          {box && natural && (
            <label className="flex items-center gap-3 text-sm text-mist">
              Size
              <input
                type="range"
                min={Math.round(SMALLEST * 100)}
                max={100}
                value={Math.round((box.width / shorter) * 100)}
                onChange={(e) => setBox(resized(natural.w, natural.h, box, (Number(e.target.value) / 100) * shorter))}
                className="flex-1 accent-gold"
              />
            </label>
          )}
          <p className="text-xs text-mist">
            The circle is the picture everywhere in Horatio{badge ? "; the dashed frame is what a printed badge shows." : "."}
          </p>
        </>
      )}
      <ErrorText error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Back
        </Button>
        <Button type="button" disabled={saving || (!box && !(failed && unreadable))} onClick={() => onSave(box && natural ? toCrop(natural.w, natural.h, box) : null)}>
          {saving ? "Saving…" : "Save picture"}
        </Button>
      </div>
    </div>
  );
}
