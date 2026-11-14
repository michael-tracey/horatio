import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { api, unwrap } from "../../../api/client";
import type { components } from "../../../api/schema";
import { Button, Card, ErrorText, Loading } from "../../../components/ui";
import { useDates } from "../../../dates";
import { useAction } from "../../../hooks";
import { manualLink } from "../../../manualLink";
import { LicenceBox, NotSetUp, RemoveDialog } from "./fetchParts";

type CryptTemplatesTool = components["schemas"]["CryptTemplatesTool"];
type CryptTemplatesUpload = components["schemas"]["CryptTemplatesUpload"];

/**
 * The clan crypt card templates (#850): the 2020 Dark Pack "Community Created Card"
 * frames, which characters' Jyhad cards are drawn on when their clan has one. They
 * are Paradox's, so the custodian uploads them here, as the PNGs or a zip of them,
 * and Horatio keeps them on the server, never in its code.
 */
export function CryptTemplates() {
  const client = useQueryClient();
  const state = useQuery({ queryKey: ["tools", "crypt-templates"], queryFn: () => unwrap(api.GET("/api/tools/crypt-templates")) });
  const input = useRef<HTMLInputElement>(null);
  const [accepted, setAccepted] = useState(false);
  const [last, setLast] = useState<CryptTemplatesUpload | null>(null);
  const [removing, setRemoving] = useState(false);
  const upload = useAction(async (files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    form.append("accept_licence", "true");
    const done = await unwrap(api.POST("/api/tools/crypt-templates", { body: form as never, bodySerializer: (body: unknown) => body as FormData }));
    setLast(done);
    client.setQueryData(["tools", "crypt-templates"], done.tool);
    return done;
  });
  const remove = useAction(async () => {
    const done = await unwrap(api.DELETE("/api/tools/crypt-templates"));
    setLast(null);
    client.setQueryData(["tools", "crypt-templates"], done);
    return done;
  });
  const s = state.data;

  return (
    <Card
      title="Jyhad card templates"
      actions={
        s && s.templates.length > 0 && (
          <Button type="button" variant="danger" disabled={!s.writable} onClick={() => setRemoving(true)}>
            Remove
          </Button>
        )
      }
    >
      <p className="mb-3 text-sm text-mist">
        The clans' 2020 crypt card templates, the Dark Pack's "Community Created Card" frames, named <code>2020_Crypt_&lt;Clan&gt;.png</code>. A character's
        Jyhad card is drawn on its clan's (a Sabbat character's on the antitribu's, where there is one); a clan without one keeps Horatio's own frame. Upload
        the PNGs, or a zip of them: they're added to those here, and one of a clan already here replaces it.{" "}
        <Link to={manualLink("custodian", "jyhad-card-templates")} className="text-gold hover:underline">
          How it works
        </Link>
      </p>
      {state.isPending ? (
        <Loading />
      ) : state.error ? (
        <ErrorText error={state.error} />
      ) : (
        <>
          <NotSetUp configured={s!.configured} writable={s!.writable} />
          <Status state={s!} />
          {s!.configured && s!.writable && (
            <div className="mt-4 flex flex-col gap-3 text-sm">
              <LicenceBox agreement={s!.agreement} accepted={accepted} onChange={setAccepted} />
              <input
                ref={input}
                type="file"
                multiple
                accept=".png,.zip,image/png,application/zip"
                aria-label="Templates to upload"
                className="sr-only"
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  e.target.value = "";
                  if (files.length) upload.mutate(files);
                }}
              />
              <div>
                <Button type="button" disabled={!accepted || upload.isPending} onClick={() => input.current?.click()}>
                  {upload.isPending ? "Uploading…" : "Upload templates"}
                </Button>
              </div>
              <ErrorText error={upload.error} />
              {last && <UploadResult result={last} />}
            </div>
          )}
          <ErrorText error={remove.error} />
        </>
      )}
      <RemoveDialog
        title="Remove the Jyhad card templates?"
        open={removing}
        pending={remove.isPending}
        onClose={() => setRemoving(false)}
        onRemove={() => remove.mutate(undefined, { onSuccess: () => setRemoving(false) })}
      >
        The templates come off the server now. Jyhad cards go back to Horatio's own frame.
      </RemoveDialog>
    </Card>
  );
}

/** What the last upload added, and what it left out and why. */
function UploadResult({ result }: { result: CryptTemplatesUpload }) {
  return (
    <div role="status" className="flex flex-col gap-1">
      <p>Added: {result.added.join(", ")}.</p>
      {result.skipped.length > 0 && (
        <div className="text-mist">
          <p>Left out:</p>
          <ul className="list-disc pl-5">
            {result.skipped.map((s) => (
              <li key={s.name}>
                {s.name}: {s.why}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** The templates here, and which of Horatio's clans use one. */
function Status({ state }: { state: CryptTemplatesTool }) {
  const dates = useDates();
  if (!state.configured) return null;
  if (!state.templates.length) return <p className="text-sm">None on this server yet.</p>;
  const without = state.clans.filter((c) => !c.symbol);
  return (
    <section aria-label="On the server" className="flex flex-col gap-2 text-sm">
      <p>
        {state.templates.length} template{state.templates.length === 1 ? "" : "s"}{state.uploaded_at ? `, last uploaded ${dates.dateTime(state.uploaded_at)}` : ""}:{" "}
        {state.templates.map((t) => t.name).join(", ")}.
      </p>
      <p>
        Horatio's clans and bloodlines with a template: {state.clans.length - without.length} of {state.clans.length}.
        {without.length > 0 && <span className="text-mist"> Horatio's frame for: {without.map((c) => c.name).join(", ")}.</span>}
      </p>
      {state.missing.length > 0 && <p className="text-mist">Not uploaded: {state.missing.join(", ")}.</p>}
    </section>
  );
}
