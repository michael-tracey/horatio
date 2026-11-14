import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../../api/client";
import type { AgencyOut } from "../../api/types";
import { Avatar } from "../../components/Avatar";
import { Button, ErrorText } from "../../components/ui";
import type { Crop } from "../../components/crop";
import { useAction } from "../../hooks";
import { Cropper } from "../character/Picture";
import { ACCEPT, MAX_BYTES } from "./PostForm";

type Step = { kind: "choose" } | { kind: "new"; file: File; url: string } | { kind: "move" };

/**
 * An agency's portrait (#883): a square picture, cut like a character's, that its stories show on
 * Discord as their sender's, beside its name. Without one, they go out under its name with Discord's
 * default picture.
 */
export function AgencyPortrait({ agency }: { agency: AgencyOut }) {
  const path = { params: { path: { agency_id: agency.id } } };
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
    await unwrap(api.POST("/api/agencies/{agency_id}/portrait", { ...path, body: form as never, bodySerializer: (body: unknown) => body as FormData }));
    setStep({ kind: "choose" });
  });
  const move = useAction(async (crop: Crop) => {
    await unwrap(api.PUT("/api/agencies/{agency_id}/portrait/crop", { ...path, body: crop }));
    setStep({ kind: "choose" });
  });
  const remove = useAction(() => unwrap(api.DELETE("/api/agencies/{agency_id}/portrait", path)));

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
  if (step.kind === "move" && agency.portrait) {
    return (
      <Cropper
        src={`${agency.portrait}/full.webp`}
        initial={agency.portrait_crop ?? null}
        badge={false}
        saving={move.isPending}
        error={move.error}
        onCancel={() => setStep({ kind: "choose" })}
        onSave={(crop) => crop && move.mutate(crop)}
      />
    );
  }
  return (
    <div className="flex flex-col items-center gap-4 text-sm">
      <Avatar name={agency.name} picture={agency.portrait} size="xl" />
      <p className="text-center text-mist">
        Optional: a square picture, such as a logo, that its stories show on Discord beside its name, as the one who posted them. Without one, they go out under its name with
        Discord's own picture. A JPEG, PNG, WebP or HEIC picture up to 10 MB.
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
          {agency.portrait ? "Upload a new portrait" : "Choose a picture"}
        </Button>
        {agency.portrait && (
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
