import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Dialog } from "../../components/Dialog";
import { HERO_RATIO, heroCentred, heroFrame, heroResized, SMALLEST, toCrop, type Box, type Crop } from "../../components/crop";
import { Button, ErrorText, Notice } from "../../components/ui";
import { ACCEPT, MAX_BYTES } from "../news/PostForm";

/**
 * An article's hero picture on the writing page (#1157): the picture as it is, and
 * a way to choose another, place its 2:1 frame, or remove it. The frame is cut on
 * the server, so a picture is uploaded only once it is placed.
 */
export function HeroPicture({
  picture,
  disabled,
  saving,
  error,
  onUpload,
  onRemove,
}: {
  picture: string | null;
  disabled: boolean;
  saving: boolean;
  error: unknown;
  onUpload: (file: File, crop: Crop | null, done: () => void) => void;
  onRemove: () => void;
}) {
  const [chosen, setChosen] = useState<{ file: File; url: string } | null>(null);
  const [tooBig, setTooBig] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => (chosen ? URL.revokeObjectURL(chosen.url) : undefined), [chosen]);

  return (
    <div className="flex flex-col gap-2">
      {picture ? <img src={`${picture}/600.webp`} alt="The article's picture" className="aspect-[2/1] w-full max-w-sm rounded-md object-cover" /> : <p className="text-sm text-mist">No picture yet.</p>}
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        aria-label="Choose a picture"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          setTooBig(file.size > MAX_BYTES);
          if (file.size <= MAX_BYTES) setChosen({ file, url: URL.createObjectURL(file) });
        }}
      />
      {tooBig && <ErrorText error="That picture is over 10 MB. Try a smaller one." />}
      {!chosen && <ErrorText error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={disabled || saving} onClick={() => input.current?.click()}>
          {picture ? "Change the picture" : "Add a picture"}
        </Button>
        {picture && (
          <Button type="button" variant="ghost" disabled={disabled || saving} onClick={onRemove}>
            Remove the picture
          </Button>
        )}
      </div>
      <Dialog title="Place the picture" open={chosen !== null} onClose={() => setChosen(null)}>
        {chosen && <HeroCropper src={chosen.url} saving={saving} error={error} onCancel={() => setChosen(null)} onSave={(crop) => onUpload(chosen.file, crop, () => setChosen(null))} />}
      </Dialog>
    </div>
  );
}

/**
 * Place the hero picture's 2:1 frame on the picture: drag it, or use the arrow keys,
 * and size it with the slider. What is outside the frame is cut off.
 */
export function HeroCropper({ src, saving, error, onCancel, onSave }: { src: string; saving: boolean; error: unknown; onCancel: () => void; onSave: (crop: Crop | null) => void }) {
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [box, setBox] = useState<Box | null>(null);
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; start: Box; scale: number } | null>(null);

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
    setBox(heroFrame(natural.w, natural.h, d.start.left + (e.clientX - d.x) * d.scale, d.start.top + (e.clientY - d.y) * d.scale, d.start.width));
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!box || !natural) return;
    const step = Math.min(natural.w, natural.h) * 0.02;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    const m = moves[e.key];
    if (!m) return;
    e.preventDefault();
    setBox(heroFrame(natural.w, natural.h, box.left + m[0], box.top + m[1], box.width));
  };
  const widest = natural ? Math.min(natural.w, natural.h * HERO_RATIO) : 1;

  return (
    <div className="flex flex-col gap-3">
      {failed ? (
        <Notice>This browser can't show this kind of picture (HEIC, perhaps) before it is uploaded. Save it and the widest frame in the middle is kept.</Notice>
      ) : (
        <>
          <div ref={frame} className="relative mx-auto w-full max-w-md touch-none overflow-hidden rounded-md bg-night select-none">
            <img
              src={src}
              alt="The picture to place"
              draggable={false}
              onLoad={(e) => {
                const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
                setNatural({ w, h });
                setBox(heroCentred(w, h));
              }}
              onError={() => setFailed(true)}
              className="block w-full"
            />
            {box && natural && (
              <div
                role="slider"
                tabIndex={0}
                aria-label="Where the frame is: drag, or use the arrow keys"
                aria-valuetext={`${Math.round((box.left / natural.w) * 100)}% from the left, ${Math.round((box.top / natural.h) * 100)}% from the top`}
                aria-valuenow={Math.round((box.left / natural.w) * 100)}
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={() => (drag.current = null)}
                onKeyDown={onKeyDown}
                className="absolute cursor-move rounded-sm border-2 border-gold shadow-[0_0_0_9999px_rgba(20,16,22,0.6)]"
                style={pct(box, natural)}
              />
            )}
          </div>
          {box && natural && (
            <label className="flex items-center gap-3 text-sm text-mist">
              Size
              <input
                type="range"
                min={Math.round(SMALLEST * 100)}
                max={100}
                value={Math.round((box.width / widest) * 100)}
                onChange={(e) => setBox(heroResized(natural.w, natural.h, box, (Number(e.target.value) / 100) * widest))}
                className="flex-1 accent-gold"
              />
            </label>
          )}
          <p className="text-xs text-mist">The frame is the picture at the top of the article, twice as wide as it is high. What is outside it is cut off.</p>
        </>
      )}
      <ErrorText error={error} />
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Back
        </Button>
        <Button type="button" disabled={saving || (!box && !failed)} onClick={() => onSave(box && natural ? toCrop(natural.w, natural.h, box) : null)}>
          {saving ? "Saving…" : "Save the picture"}
        </Button>
      </div>
    </div>
  );
}
